"""Bounded, once-only public read-view integration on two fresh known worlds.

The six programs are handwritten contract checks, never saved model code. Their
account data, API values, stdout and wire records remain private. No model,
evaluator, hidden database or reserved task is consulted. This tests integration,
not task quality, workload savings, or novelty.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import time

from container_api_python import ApiChannel
from field_read_contract import verify_public_implementation
from inspect_appworld_api_schemas import load_public_tools
from persistent_read_view_python import PersistentReadViewPython
from preflight_public_api_live import RecordedBridge, confirm_initial_world
from public_api_result_transport import PublicResultTransport, TypedBridgeProcess
from public_contract_read_views import PublicContractReadProgram
from public_name_catalog import PublicNameCatalog
from shared_api_reservations import RequestBudget

PLAN_PATH = 'configs/public_read_views_live_v01.json'
PROGRAMS = [
    '''import json
passwords = call_api('supervisor', 'show_account_passwords')
profile = call_api('supervisor', 'show_profile')
matches = [p for p in passwords if p['account_name'] == 'spotify']
assert len(matches) == 1
login = call_api('spotify', 'login', username=profile['email'], password=matches[0]['password'])
token = login['access_token']
del passwords, profile, matches, login
library = call_api('spotify', 'show_song_library', access_token=token, page_index=0, page_limit=3)
assert type(library) is list and len(library) == 3
ids = [item['song_id'] for item in library]
assert len(set(ids)) == 3
private_flags = call_api('spotify', 'show_song_privates', song_id=ids[1], access_token=token)
assert type(private_flags['liked']) is bool
was_liked = private_flags['liked']
del private_flags
refreshed = call_api('spotify', 'show_song_library', access_token=token, page_index=0, page_limit=3)
assert refreshed == library
print(json.dumps(library, sort_keys=True))
del refreshed''',
    '''original = read_view('spotify', 'show_song', song_id=ids[0])
assert original['title'] == library[0]['title']
aliases = {'saved': original}
del original
print(json.dumps({'title': aliases['saved']['title'], 'artists': aliases['saved']['artists']}, sort_keys=True))''',
    '''later = aliases.pop('saved')
genre = later['genre']
complete = dict(later)
assert genre == complete['genre']
same = read_view('spotify', 'show_song', song_id=ids[0])
assert dict(same) == complete
print(json.dumps(complete, sort_keys=True))
del later, same, complete, genre, aliases''',
    '''unused = read_view('spotify', 'show_song', song_id=ids[2])
assert unused['title'] == library[2]['title']
print(json.dumps({'title': unused['title'], 'artists': unused['artists']}, sort_keys=True))
del unused''',
    '''held = read_view('spotify', 'show_song', song_id=ids[1])
assert held['title'] == library[1]['title']
print(json.dumps({'title': held['title'], 'artists': held['artists']}, sort_keys=True))''',
    '''operation = 'unlike_song' if was_liked else 'like_song'
delta = -1 if was_liked else 1
call_api('spotify', operation, song_id=ids[1], access_token=token)
before_change = dict(held)
after_change = call_api('spotify', 'show_song', song_id=ids[1])
assert after_change['like_count'] == before_change['like_count'] + delta
assert before_change['title'] == after_change['title'] == library[1]['title']
print(json.dumps({'before': before_change, 'after': after_change}, sort_keys=True))
del held, before_change, after_change, library, ids, token''',
]
EXPECTED_API = {'eager': [6, 1, 0, 1, 1, 2], 'deferred': [6, 0, 1, 0, 0, 3]}
EXPECTED_PENDING = {'eager': [0, 0, 0, 0, 0, 0], 'deferred': [0, 1, 0, 0, 1, 0]}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    path = Path(path)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
    temporary.replace(path)


def execute_programs(*, program, session, transport, catalog, budget, folder,
                     storage, condition, recorded, deadline, stop, plan, on_record):
    """One fixed sequence. Record its failing attempt before stopping; never retry."""
    policy = condition['policy']
    for index, source in enumerate(PROGRAMS):
        remaining = deadline - time.monotonic()
        if stop() or remaining <= 0:
            raise InterruptedError('live_read_view_stop_before_program')
        timeout = min(plan['program_timeout_seconds'], remaining)
        recorded.deadline = min(deadline, time.monotonic() + timeout)
        result = program(source, {}, ApiChannel(catalog, transport, budget.limit - budget.spent),
            storage_root=storage, record_dir=folder / f'program_{index + 1:02d}',
            timeout=timeout, on_record=on_record)
        evidence = json.loads((folder / f'program_{index + 1:02d}' / 'view_program_private.json').read_text())
        row = {key: result.get(key) for key in
               ('status', 'api_requests', 'unknown_effects', 'declared_complete', 'wall_seconds')}
        row.update(number=index + 1, budget=budget.snapshot(),
            stdout_sha256=hashlib.sha256(result.get('stdout', '').encode()).hexdigest(),
            stdout_truncated=result.get('stdout_truncated'),
            control_requests=evidence['control_requests'],
            control_request_bytes=evidence['control_request_bytes'],
            control_reply_bytes=evidence['control_reply_bytes'],
            client_setup_included=evidence['setup'] is not None)
        condition['programs'].append(row)
        save(folder / 'progress.json', condition)
        if (result['status'] != 'ok' or result.get('unknown_effects')
                or result.get('declared_complete') or result.get('stdout_truncated')
                or not session.usable or session.closed):
            raise ValueError('fixed_handwritten_program_failed')
        if (result['api_requests'] != EXPECTED_API[policy][index]
                or budget.pending != EXPECTED_PENDING[policy][index]):
            raise ValueError('fixed_program_accounting_mismatch')
    if (budget.spent != sum(EXPECTED_API[policy]) or budget.pending or budget.stopped
            or program.host.records or program.host.exact_reuses != 1):
        raise ValueError('final_read_view_contract_mismatch')


def probe(storage, repo):
    plan = json.loads((repo / PLAN_PATH).read_text())
    output = storage / plan['private_output']
    world_root = storage / '.runtime/appworld/r18_probe_01'
    for policy in plan['policies']:
        world = world_root / 'experiments/outputs' / (plan['experiment_prefix'] + '_' + policy)
        if world.exists():
            raise FileExistsError('preserve_every_prior_read_view_world')
    output.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    deadline = started + plan['active_deadline_seconds']
    stopped = lambda: (storage / plan['stop_marker']).exists()
    report = dict(phase='public_read_view_live_contract_check', status='running',
        started_at=datetime.now(timezone.utc).isoformat(), plan_sha256=sha(repo / PLAN_PATH),
        source_commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=repo, text=True).strip(),
        conditions=[dict(policy=p, status='not_attempted', programs=[]) for p in plan['policies']],
        model_calls=0, evaluator_calls=0, reserved_scenarios_read=False,
        database_contents_inspected=False, saved_model_programs_executed=False,
        task_success_or_cost_improvement_measured=False, automatic_retries=0)
    try:
        if subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=no'], cwd=repo):
            raise ValueError('live_read_view_requires_clean_tracked_source')
        for filename, expected_sha in plan['source_sha256'].items():
            if sha(repo / filename) != expected_sha:
                raise ValueError('prepared_source_changed: ' + filename)
        known = storage / plan['known_public_task']
        if sha(known) != plan['known_public_task_sha256']:
            raise ValueError('known_initial_public_task_changed')
        expected = json.loads(known.read_text())
        package = storage / '.runtime/appworld/venv/lib/python3.12/site-packages/appworld'
        for filename, expected_sha in plan['runtime_source_sha256'].items():
            if sha(package / filename) != expected_sha:
                raise ValueError('installed_runtime_source_changed: ' + filename)
        contract = verify_public_implementation(package / 'apps/spotify')
        tools, sources, _ = load_public_tools(world_root / 'data')
        if sources != plan['public_schema_sha256']:
            raise ValueError('public_schema_sources_changed')
        report.update(public_contract_verified=contract, public_schema_sha256=sources,
                      runtime_source_sha256=plan['runtime_source_sha256'])
        for condition in report['conditions']:
            if stopped() or time.monotonic() >= deadline:
                raise InterruptedError('live_read_view_stop_before_world')
            folder = output / condition['policy']
            folder.mkdir()
            raw = recorded = transport = session = program = None
            budget = RequestBudget(plan['max_api_requests_per_policy'])
            rows = []
            condition.update(status='running', initialization_attempts=0)
            cell_started = time.monotonic()
            try:
                raw = TypedBridgeProcess(storage / '.runtime/appworld/venv/bin/python', world_root,
                                         folder, timeout_seconds=plan['bridge_timeout_seconds'])
                condition['owned_bridge_pid'] = raw.process.pid
                recorded = RecordedBridge(raw, folder, deadline, stop=stopped)
                transport = PublicResultTransport(recorded)
                condition['initialization_attempts'] += 1
                init_started = time.monotonic()
                response = transport.request(dict(op='init', task_id=plan['task_id'],
                    experiment=plan['experiment_prefix'] + '_' + condition['policy'], seed=plan['seed']))
                confirm_initial_world(response, expected)
                condition.update(initial_world_confirmed=True,
                                 world_initialization_wall_seconds=time.monotonic() - init_started)
                session = PersistentReadViewPython(storage, folder / 'python_session')
                catalog = PublicNameCatalog(tools)
                program = PublicContractReadProgram(session, budget,
                    execution_scope=plan['experiment_prefix'] + '_' + condition['policy'],
                    verified_contract=contract, defer=condition['policy'] == 'deferred')
                def record(row):
                    rows.append(row)
                    save(folder / f'record_{len(rows):02d}_private.json', row)
                execute_programs(program=program, session=session, transport=transport,
                    catalog=catalog, budget=budget, folder=folder, storage=storage,
                    condition=condition, recorded=recorded, deadline=deadline, stop=stopped,
                    plan=plan, on_record=record)
                if (len(transport.receipts) != budget.spent
                        or any(r['status'] != 'returned' for r in transport.receipts)
                        or len(session.controls) != 14 or not all(session.controls.values())):
                    raise ValueError('receipt_or_container_contract_mismatch')
                condition['status'] = 'complete'
            except BaseException as error:
                condition.update(status='stopped', error_type=type(error).__name__)
                save(folder / 'error_private.json', dict(type=type(error).__name__, message=str(error)))
                raise
            finally:
                condition['active_wall_seconds'] = time.monotonic() - cell_started
                cleanup_started = time.monotonic()
                cleanup_errors = []
                if session is not None:
                    try:
                        condition['python_cleanup'] = session.close()
                        condition['container_controls'] = session.controls
                    except BaseException as error:
                        cleanup_errors.append('python:' + type(error).__name__)
                if raw is not None:
                    try:
                        condition['bridge_cleanup'] = raw.close()
                    except BaseException as error:
                        cleanup_errors.append('bridge:' + type(error).__name__)
                condition.update(cleanup_wall_seconds=time.monotonic() - cleanup_started,
                    full_wall_seconds=time.monotonic() - cell_started, budget=budget.snapshot(),
                    cleanup_errors=cleanup_errors,
                    api_rows_recorded=sum(bool(r['api_request_sent']) for r in rows),
                    api_names=dict(Counter(r['action']['name'] for r in rows if r['api_request_sent'])),
                    exact_reuses=program.host.exact_reuses if program and program.host else None,
                    surviving_host_views=len(program.host.records) if program and program.host else None,
                    bridge_attempts=len(recorded.attempts) if recorded else 0,
                    typed_requests_started=sum(a['raw_request_started'] and a['command']['op']=='call_typed'
                                               for a in recorded.attempts) if recorded else 0)
                save(folder / 'progress.json', condition)
                save(output / 'status.json', report)
            if (condition['cleanup_errors']
                    or not condition.get('python_cleanup', {}).get('container_removed')
                    or not condition.get('bridge_cleanup', {}).get('process_stopped')
                    or not condition.get('bridge_cleanup', {}).get('graceful')
                    or condition['api_rows_recorded'] != budget.spent
                    or condition['typed_requests_started'] != budget.spent):
                condition['status'] = 'cleanup_or_accounting_failed'
                raise ValueError('cleanup_or_dispatch_accounting_failed')
        first, second = report['conditions']
        equal = ([r['stdout_sha256'] for r in first['programs']]
                 == [r['stdout_sha256'] for r in second['programs']])
        report['all_six_observations_equal'] = equal
        if not equal:
            raise ValueError('paired_handwritten_observations_differ')
        report['status'] = 'complete'
    except BaseException as error:
        report.update(status='stopped', error_type=type(error).__name__)
        save(output / 'error_private.json', dict(type=type(error).__name__, message=str(error)))
        raise
    finally:
        report['wall_seconds'] = time.monotonic() - started
        save(output / 'status.json', report)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--storage-root', type=Path, required=True)
    args = parser.parse_args()
    result = probe(args.storage_root.resolve(), Path(__file__).resolve().parents[1])
    print(json.dumps({k: result[k] for k in ('status', 'all_six_observations_equal', 'wall_seconds')}))
