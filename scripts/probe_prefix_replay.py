"""Re-execute fixed public API prefixes; no LLM, answers or task evaluator.

This checks observable prefix and saved DB-file equality, not arbitrary process
restoration. Any mismatch stops that case. All new worlds are isolated simulations.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import time

from appworld_native_tools import NativeCatalog, dispatch_native_calls
from inspect_appworld_api_schemas import load_public_tools
from native_boundary_record import verify_boundary
from prepare_event_view_probe import reject_response
from run_context_comparison import Bridge, write_json

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def db_hashes(directory):
    entries = list(directory.iterdir())
    if not entries or any(not p.is_file() or p.is_symlink() for p in entries):
        raise ValueError('unexpected saved DB directory')
    return {'dbs/' + p.name: sha(p) for p in entries}


def run_case(storage, inputs, case_meta, number, batch, output):
    source = storage/'records/context_pilot'/case_meta['source_run']
    case_path = inputs/(case_meta['case_id']+'.json')
    if sha(case_path) != case_meta['case_sha256']:
        raise ValueError('prepared input changed')
    case = read(case_path)
    for name, digest in case['source_hashes'].items():
        if sha(source/name) != digest:
            raise ValueError('original prefix source changed')
    provenance, plan = read(source/'provenance.json'), read(source/'plan.json')
    for name in ('appworld_bridge.py', 'appworld_native_tools.py',
                 'context_preservation.py', 'inspect_appworld_api_schemas.py'):
        if sha(ROOT/'scripts'/name) != provenance['sources'][name]:
            raise ValueError('API bridge differs from original')
    appworld_root = storage/'.runtime/appworld/r18_probe_01'
    tools, schema_hashes, _ = load_public_tools(appworld_root/'data')
    if schema_hashes != provenance['public_schema_hashes']:
        raise ValueError('public API schema changed')
    task_id = provenance['task_id']
    if sha(appworld_root/'data/tasks'/task_id/'specs.json') != provenance['spec_sha256']:
        raise ValueError('task specification changed')
    events, spans = read(source/'events.json'), read(source/'spans.json')
    selected_call = case['source_call_id']
    start = next(i for i, e in enumerate(events) if e['call'] == selected_call)
    prefix = events[:start]
    order = list(dict.fromkeys(e['call'] for e in prefix))
    boundary_id = order[-1] if order else 'initial'
    verify_boundary(source/'boundaries', boundary_id)
    boundary = read(source/'boundaries/manifests'/(boundary_id+'.json'))
    expected_dbs = {name: row['sha256'] for name, row in boundary['files'].items() if name.startswith('dbs/')}
    run_id = f'{batch}_{number:02d}'
    world_output = appworld_root/'experiments/outputs'/run_id
    if world_output.exists():
        raise FileExistsError('existing simulation must not be replaced')
    output.mkdir()
    write_json(output/'source_identity.json', {'source_run': case_meta['source_run'],
               'case_sha256': sha(case_path), 'boundary_id': boundary_id,
               'boundary_manifest_sha256': sha(source/'boundaries/manifests'/(boundary_id+'.json'))})
    catalog = NativeCatalog(tools)
    bridge = Bridge(storage/'.runtime/appworld/venv/bin/python', appworld_root, output)
    result = {'case_id': case_meta['case_id'], 'source_run': case_meta['source_run'],
              'run_id': run_id, 'status': 'started', 'api_requests': 0,
              'replayed_responses': 0, 'observation_matches': 0, 'db_files_match': None,
              'model_calls': 0, 'ground_truth_loaded': None, 'boundary_id': boundary_id}
    started = time.monotonic()
    private_rows = []
    try:
        initialized = bridge.request({'op': 'init', 'task_id': task_id, 'experiment': run_id, 'seed': plan['seed']})
        if not initialized['ok']:
            raise RuntimeError('simulation initialization failed')
        result['ground_truth_loaded'] = initialized['result']['ground_truth_loaded']
        if result['ground_truth_loaded'] or initialized['result'] != case['task']:
            raise ValueError('initial public task differs')
        for call_id in order:
            if time.monotonic() - started > 600 or result['api_requests'] >= 80:
                raise TimeoutError('fixed replay limit')
            request, response = read(source/call_id/'request.json'), read(source/call_id/'response.json')
            if response['status'] != 'ok' or request['tools'] != catalog.tools():
                raise ValueError('original response or public tool set differs')
            def no_archive(*_):
                raise ValueError('archive replay is outside this fixed prefix check')
            rows = dispatch_native_calls(response['message'], catalog, bridge, no_archive,
                                         remaining_api_calls=80-result['api_requests'])
            private_rows.append({'call_id': call_id, 'rows': rows})
            write_json(output/'replay_private.json', private_rows)
            result['api_requests'] += sum(r['api_request_sent'] for r in rows)
            result['replayed_responses'] += 1
            expected = [e for e in prefix if e['call'] == call_id]
            if len(rows) != len(expected):
                raise ValueError('prefix event count differs')
            for row, event in zip(rows, expected, strict=True):
                original = spans[event['span_id']]
                if (row['action'] != original['action'] or row['observation'] != original['observation']
                        or row['api_request_sent'] != event['api_request_sent']
                        or row.get('effects_unknown', False) != event.get('effects_unknown', False)
                        or row['new_tools'] != event['new_tools']):
                    result['first_mismatch'] = {'call_id': call_id, 'span_id': event['span_id']}
                    raise ValueError('prefix observation or dispatch differs')
                result['observation_matches'] += 1
        dbs = world_output/'tasks'/task_id/'dbs'
        before = db_hashes(dbs)
        result['db_files_match'] = before == expected_dbs
        result['db_files'] = len(before)
        result['db_mismatch_names'] = sorted(k for k in set(before)|set(expected_dbs) if before.get(k) != expected_dbs.get(k))
        if not result['db_files_match']:
            raise ValueError('saved pre-action DB files differ')
        selected = read(source/selected_call/'response.json')['message']
        if read(source/selected_call/'request.json')['tools'] != catalog.tools():
            raise ValueError('selected call tool discovery differs')
        faulty, expected_rejection = reject_response(selected, case['tools'], '__p16_unknown_parameter__')
        rejected = dispatch_native_calls(faulty, catalog, bridge, None, remaining_api_calls=80-result['api_requests'])
        result['rejection_requests_sent'] = sum(r['api_request_sent'] for r in rejected)
        result['api_requests'] += result['rejection_requests_sent']
        result['rejection_matches'] = rejected == expected_rejection
        result['db_unchanged_after_rejection'] = db_hashes(dbs) == before
        if result['rejection_requests_sent'] or not result['rejection_matches'] or not result['db_unchanged_after_rejection']:
            raise ValueError('rejection or post-rejection saved DB differs')
        result['status'] = 'passed_observable_prefix_check'
    except Exception as error:
        result.update(status='failed', error_type=type(error).__name__, error=str(error))
    finally:
        try:
            bridge.close()
        except Exception as error:
            result.update(status='failed', close_error_type=type(error).__name__)
        result['wall_seconds'] = time.monotonic() - started
        write_json(output/'result.json', result)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--storage-root', type=Path, required=True)
    parser.add_argument('--inputs', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--public-report', type=Path, required=True)
    args = parser.parse_args()
    manifest = read(args.inputs/'manifest.json')
    cases = [c for c in manifest['cases'] if c['condition'] == 'recorded']
    if [c['source_run'] for c in cases] != [f'P11_{i:02d}_ROLES' for i in range(1,5)]:
        raise ValueError('only the four fixed P16 source cases are allowed')
    if args.output.exists() or args.public_report.exists():
        raise FileExistsError('keep previous replay records')
    args.output.mkdir(parents=True)
    report = {'started_at': datetime.now(timezone.utc).isoformat(),
              'git_commit': subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
              'script_sha256': sha(Path(__file__)), 'input_manifest_sha256': sha(args.inputs/'manifest.json'),
              'model_calls': 0, 'evaluator_invocations': 0, 'results': [],
              'scope': 'Strict public-observation and saved-DB byte comparison before the selected action. '
                       'Re-execution from task initialization, not full process checkpoint restoration. '
                       'Runs concurrently with P16 memory generation; no wall-time performance comparison.'}
    for number, case in enumerate(cases,1):
        result = run_case(args.storage_root,args.inputs,case,number,'P16_REPLAY_V01',args.output/f'case_{number:02d}')
        report['results'].append(result)
        write_json(args.output/'report.json',report)
        write_json(args.public_report,report)
        print(json.dumps(result),flush=True)
    return int(any(r['status']!='passed_observable_prefix_check' for r in report['results']))


if __name__ == '__main__':
    raise SystemExit(main())
