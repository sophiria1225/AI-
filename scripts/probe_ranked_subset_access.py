"""Fixed three-control access probe in isolated known AppWorld states; no model."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import signal
import subprocess
import time

from appworld_native_tools import NativeCatalog, dispatch_native_calls
from inspect_appworld_api_schemas import load_public_tools
from native_boundary_record import verify_boundary
from probe_prefix_replay import db_hashes
from ranked_subset_read import AccessContract, ReadReceipt, subset_maximum
from run_context_comparison import Bridge, write_json

ROOT = Path(__file__).resolve().parents[1]
PLAN = 'configs/P54_ranked_subset_access_v01.json'
SOURCES = ('scripts/probe_ranked_subset_access.py', 'scripts/ranked_subset_read.py',
           'scripts/run_context_comparison.py', 'scripts/appworld_bridge.py',
           'scripts/appworld_native_tools.py', 'scripts/context_preservation.py',
           'scripts/inspect_appworld_api_schemas.py', 'scripts/native_boundary_record.py',
           'scripts/probe_prefix_replay.py', 'tests/test_ranked_subset_read.py',
           'tests/test_probe_ranked_subset_access.py', PLAN)


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def value_sha(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     allow_nan=False).encode()).hexdigest()


def fixed_access_contract(spec, snapshot):
    expected = {'app': 'spotify', 'point_api': 'show_song', 'ranked_api': 'search_songs',
                'id_field': 'song_id', 'score_field': 'like_count', 'value_fields': ['title'],
                'query': '', 'sort_by': '-like_count'}
    if spec != expected:
        raise ValueError('API identity, filters or rank semantics differ from inspected contract')
    return AccessContract('spotify.Song.public', snapshot, 'song_id', 'like_count',
                          ('title',), 'global_desc', True, True)


def extract_targets(spans, maximum):
    span = spans['s5']
    if span['action']['name'] != 'spotify__show_playlist_library':
        raise ValueError('target source is not the fixed public collection')
    args = json.loads(span['action']['arguments'])
    rows = json.loads(span['observation']['observation'])
    if (args.get('page_index') != 0 or args.get('page_limit') != 20
            or not isinstance(rows, list) or not 0 < len(rows) < 20):
        raise ValueError('target source does not have its fixed finite collection shape')
    ids = []
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get('song_ids'), list):
            raise ValueError('invalid target collection')
        for key in row['song_ids']:
            if type(key) is not int or key <= 0:
                raise ValueError('invalid public target identifier')
            if key not in ids:
                ids.append(key)
    if not 0 < len(ids) <= maximum:
        raise ValueError('target count outside fixed limit')
    return ids


def validate_sources(storage, plan):
    fixed_access_contract(plan['contract'], 'preflight')
    source = storage / 'records/context_pilot' / plan['source_run']
    for path, digest in plan['source_sha256'].items():
        if sha(source / path) != digest:
            raise ValueError('known source changed: ' + path)
    installed = storage / '.runtime/appworld/venv/lib/python3.12/site-packages/appworld/apps'
    for path, digest in plan['installed_source_sha256'].items():
        if sha(installed / path) != digest:
            raise ValueError('installed public API source changed: ' + path)
    verify_boundary(source / 'boundaries', plan['boundary'])
    provenance = read(source / 'provenance.json')
    for name in ('appworld_bridge.py', 'appworld_native_tools.py', 'context_preservation.py',
                 'inspect_appworld_api_schemas.py'):
        if sha(ROOT / 'scripts' / name) != provenance['sources'][name]:
            raise ValueError('bridge differs from source run')
    world_root = storage / '.runtime/appworld/r18_probe_01'
    tools, schemas, _ = load_public_tools(world_root / 'data')
    if schemas != provenance['public_schema_hashes']:
        raise ValueError('public schemas changed')
    if sha(world_root / 'data/tasks' / provenance['task_id'] / 'specs.json') != provenance['spec_sha256']:
        raise ValueError('known task specification changed')
    return source, provenance, world_root, tools


class ProbeDeadline(BaseException):
    pass


def deadline_handler(*_):
    raise ProbeDeadline('fixed wall deadline')


def run_case(storage, plan, mode, output, batch_deadline):
    source, provenance, world_root, tools = validate_sources(storage, plan)
    targets = extract_targets(read(source / 'spans.json'), plan['maximum_target_ids'])
    run_id = plan['batch_id'] + '_' + mode
    world_output = world_root / 'experiments/outputs' / run_id
    if output.exists() or world_output.exists():
        raise FileExistsError('refusing to replace prior case or world')
    output.mkdir()
    write_json(output / 'target_ids_private.json', targets)
    row = {'mode': mode, 'run_id': run_id, 'status': 'started',
           'setup_api_requests_attempted': 0, 'lookup_api_requests_attempted': 0,
           'api_requests_attempted': 0, 'lookup_response_utf8_bytes': 0,
           'target_count': len(targets), 'target_ids_sha256': value_sha(targets),
           'prefix_observations_matched': 0, 'prefix_db_files_match': None,
           'read_db_files_unchanged': None, 'ground_truth_loaded': None,
           'model_generations': 0, 'evaluator_calls': 0, 'tokenizer_requests': 0}
    started = time.monotonic()
    bridge = None
    original_handler = signal.signal(signal.SIGALRM, deadline_handler)
    private_calls = []
    stage = 'setup'
    try:
        remaining = min(plan['max_seconds_per_arm'], batch_deadline - started)
        if remaining <= 0:
            raise ProbeDeadline('batch budget exhausted before case')
        signal.setitimer(signal.ITIMER_REAL, remaining)
        bridge = Bridge(storage / '.runtime/appworld/venv/bin/python', world_root, output)

        class RecordedBridge:
            def request(self, command):
                if command['op'] != 'call':
                    return bridge.request(command)
                key = stage + '_api_requests_attempted'
                cap = plan['max_setup_api_per_arm'] if stage == 'setup' else plan['max_requests_per_arm']
                if row[key] >= cap:
                    raise RuntimeError('fixed API allocation exceeded')
                row[key] += 1
                row['api_requests_attempted'] += 1
                entry = {'stage': stage, 'request': command, 'response': None}
                private_calls.append(entry)
                write_json(output / 'calls_private.json', private_calls)
                write_json(output / 'result.json', row)
                result = bridge.request(command)
                entry['response'] = result
                if stage == 'lookup':
                    row['lookup_response_utf8_bytes'] += len(json.dumps(result, ensure_ascii=False).encode())
                write_json(output / 'calls_private.json', private_calls)
                return result

        recorded = RecordedBridge()
        initialized = recorded.request({'op': 'init', 'task_id': provenance['task_id'],
                                        'experiment': run_id, 'seed': read(source / 'plan.json')['seed']})
        if not initialized['ok'] or initialized['result'] != read(source / 'public_task.json'):
            raise ValueError('public task initialization mismatch')
        row['ground_truth_loaded'] = initialized['result']['ground_truth_loaded']
        if row['ground_truth_loaded']:
            raise ValueError('ground truth must not load')
        catalog = NativeCatalog(tools)
        spans, events = read(source / 'spans.json'), read(source / 'events.json')
        for call_id in plan['prefix_calls']:
            request, response = read(source / call_id / 'request.json'), read(source / call_id / 'response.json')
            if request['tools'] != catalog.tools() or response['status'] != 'ok':
                raise ValueError('prefix public interface differs')
            actual = dispatch_native_calls(response['message'], catalog, recorded, None,
                remaining_api_calls=plan['max_setup_api_per_arm'] - row['setup_api_requests_attempted'])
            expected = [event for event in events if event['call'] == call_id]
            if len(actual) != len(expected):
                raise ValueError('prefix event count differs')
            for returned, event in zip(actual, expected, strict=True):
                original = spans[event['span_id']]
                if (returned['action'] != original['action'] or returned['observation'] != original['observation']
                        or any(returned.get(k, False) != event.get(k, False)
                               for k in ('api_request_sent', 'effects_unknown', 'new_tools'))):
                    raise ValueError('prefix observation differs')
                row['prefix_observations_matched'] += 1
        if row['prefix_observations_matched'] != plan['prefix_events']:
            raise ValueError('prefix length differs')
        dbs = world_output / 'tasks' / provenance['task_id'] / 'dbs'
        before = db_hashes(dbs)
        boundary = read(source / 'boundaries/manifests' / (plan['boundary'] + '.json'))
        expected_dbs = {name: item['sha256'] for name, item in boundary['files'].items() if name.startswith('dbs/')}
        row['prefix_db_files_match'] = before == expected_dbs
        if not row['prefix_db_files_match']:
            raise ValueError('prefix saved DB files differ')
        write_json(output / 'prefix_db_hashes.json', before)
        spec = plan['contract']
        contract = fixed_access_contract(spec, value_sha(before))
        stage = 'lookup'

        def read_api(api, arguments, is_page):
            decoded = catalog.decode({'name': spec['app'] + '__' + api,
                                      'arguments': json.dumps(arguments)})
            result = recorded.request({'op': 'call', 'call': decoded})
            if not result['ok'] or result['result']['declared_complete']:
                raise ValueError('read failed or unexpectedly completed task')
            payload = json.loads(result['result']['observation'])
            after = db_hashes(dbs)
            row['read_db_files_unchanged'] = after == before
            if not row['read_db_files_unchanged']:
                raise ValueError('read changed saved DB files')
            if is_page and not isinstance(payload, list):
                raise ValueError('ranked API did not return a collection')
            return ReadReceipt(contract.source_id, value_sha(after), payload if is_page else [payload])

        result = subset_maximum(targets, contract=contract,
            point_read=lambda key: read_api(spec['point_api'], {'song_id': key}, False),
            page_read=lambda index, size: read_api(spec['ranked_api'],
                {'query': spec['query'], 'sort_by': spec['sort_by'], 'page_index': index, 'page_limit': size}, True),
            mode=mode, max_requests=plan['max_requests_per_arm'], page_limit=plan['page_limit'],
            exploratory_pages=plan['exploratory_pages'])
        write_json(output / 'access_result_private.json', result)
        row['access'] = {k: v for k, v in result.items() if k != 'winners'}
        row['winner_count'] = len(result['winners'])
        row['winners_sha256'] = value_sha(result['winners']) if result['status'] == 'complete' else None
        row['projected_output_utf8_bytes'] = len(json.dumps(result['winners'], ensure_ascii=False).encode())
        if result['requests_attempted'] != row['lookup_api_requests_attempted']:
            raise ValueError('access and bridge request counters differ')
        row['status'] = ('complete' if result['status'] == 'complete' else
                         'incomplete' if result['stop_reason'] == 'request_budget_exhausted' else 'failed')
    except (Exception, ProbeDeadline) as error:
        row.update(status='failed', failure_type=type(error).__name__)
        write_json(output / 'error_private.json', {'type': type(error).__name__, 'message': str(error)})
    finally:
        signal.setitimer(signal.ITIMER_REAL, plan['max_cleanup_seconds_per_arm'])
        try:
            if bridge is not None:
                bridge.close()
                row['bridge_exit_code'] = bridge.process.returncode
        except (Exception, ProbeDeadline) as error:
            row.update(status='failed', cleanup_failure_type=type(error).__name__)
            if bridge is not None and bridge.process.poll() is None:
                bridge.process.kill()
                bridge.process.wait(timeout=5)
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, original_handler)
            row['wall_seconds_including_cleanup'] = time.monotonic() - started
            write_json(output / 'result.json', row)
    return row


def run(storage, expected_commit):
    current = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    if current != expected_commit or subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True):
        raise ValueError('run only the exact clean frozen commit')
    plan = read(ROOT / PLAN)
    validate_sources(storage, plan)
    output = storage / 'records/context_pilot' / plan['batch_id']
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / 'plan.json', plan)
    source_dir = output / 'source'; source_dir.mkdir()
    for name in SOURCES:
        (source_dir / Path(name).name).write_bytes((ROOT / name).read_bytes())
    started = time.monotonic()
    state = {'phase': 'P54', 'status': 'running', 'git_commit': current,
             'started_at': datetime.now(timezone.utc).isoformat(), 'planned': plan['arms'],
             'source_sha256': {p: sha(ROOT / p) for p in SOURCES}, 'rows': [],
             'model_generations': 0, 'tokenizer_requests': 0, 'evaluator_calls': 0,
             'reserved_scenarios_read': 0, 'is_autonomous_task_comparison': False,
             'is_novel_algorithm': False, 'claims_model_token_savings': False}
    write_json(output / 'status.json', state)
    try:
        for mode in plan['arms']:
            row = run_case(storage, plan, mode, output / mode, started + plan['max_batch_seconds'])
            state['rows'].append(row)
            write_json(output / 'status.json', state)
            print(json.dumps({k: row.get(k) for k in ('mode', 'status', 'setup_api_requests_attempted',
                'lookup_api_requests_attempted', 'wall_seconds_including_cleanup')}), flush=True)
            if row['status'] == 'failed' or (mode == 'point' and row['status'] != 'complete'):
                state['status'] = 'stopped'; break
        else:
            state['status'] = 'complete'
    except (Exception, ProbeDeadline) as error:
        state.update(status='failed', failure_type=type(error).__name__)
        write_json(output / 'error_private.json', {'type': type(error).__name__, 'message': str(error)})
    finally:
        state['not_attempted'] = [mode for mode in plan['arms'] if mode not in [r['mode'] for r in state['rows']]]
        state['wall_seconds'] = time.monotonic() - started
        state['api_requests_attempted'] = sum(r['api_requests_attempted'] for r in state['rows'])
        state['all_completed_outputs_equal'] = (len(state['rows']) == 3
            and all(r['status'] == 'complete' for r in state['rows'])
            and len({r['winners_sha256'] for r in state['rows']}) == 1)
        write_json(output / 'status.json', state)
    return state


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--storage-root', type=Path, required=True)
    parser.add_argument('--expected-commit', required=True)
    args = parser.parse_args()
    result = run(args.storage_root.resolve(), args.expected_commit)
    print(json.dumps({k: result[k] for k in ('status', 'api_requests_attempted', 'all_completed_outputs_equal', 'not_attempted')}))
