"""P94: execute all eighteen saved outputs after a matched live public prefix.

Fresh known worlds, no model, evaluator or original process-state equivalence.
Any prefix divergence stops subsequent conditions; attempts are never replaced.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

from code_agent_interface import execute_response
from context_preservation import page_span
from fallback_output_replay import schedule
from inspect_appworld_api_schemas import load_public_tools
from matched_live_prefix import (MatchedLiveChannel, assemble_programs, canonical,
                                 digest, public_next_message, result_comparison)
from native_data_compute import selected_receipts
from persistent_api_python import PersistentApiPython
from preflight_public_api_live import RecordedBridge, confirm_initial_world
from public_api_result_transport import PublicResultTransport, TypedBridgeProcess
from public_name_catalog import PublicNameCatalog

PLAN = 'configs/P94_saved_action_execution_v01.json'
PREFIX = 'records/context_pilot/BOC_P80_04_NOT_EXPOSED'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n')


def read_private(storage, plan, name, *, lines=False):
    path = storage / name
    path.resolve().relative_to((storage / 'records/context_pilot').resolve())
    if path.is_symlink() or path.stat().st_size > plan['max_file_bytes']:
        raise ValueError('private_file_bounds')
    content = path.read_bytes()
    if hashlib.sha256(content).hexdigest() != plan['private_file_sha256'][name]:
        raise ValueError('private_file_changed: ' + name)
    return ([json.loads(line) for line in content.splitlines()] if lines else json.loads(content))


def prepare(storage, root, plan):
    fixed = dict(phase='P94', schedule=schedule(), prefix_source=PREFIX,
        task_id='6104387_1', world_seed=42, active_deadline_seconds=1200,
        per_condition_deadline_seconds=180, max_api_requests_per_condition=80,
        max_api_requests_total=1440, program_timeout_seconds=30,
        bridge_timeout_seconds=30, max_file_bytes=16777216,
        original_prefix_programs=12, original_prefix_api_requests=28,
        model_generations=0, evaluator_calls=0, reserved_scenarios_read=0)
    if any(plan.get(k) != v for k, v in fixed.items()):
        raise ValueError('fixed_P94_scope_changed')
    for name, expected in plan['source_sha256'].items():
        if sha(root / name) != expected:
            raise ValueError('bound_source_changed: ' + name)
    package = storage / '.runtime/appworld/venv/lib/python3.12/site-packages/appworld'
    for name, expected in plan['runtime_source_sha256'].items():
        if sha(package / name) != expected:
            raise ValueError('bound_runtime_source_changed: ' + name)
    world_root = storage / '.runtime/appworld/r18_probe_01'
    tools, schema_sources, _ = load_public_tools(world_root / 'data')
    if schema_sources != plan['public_schema_sha256']:
        raise ValueError('public_schema_sources_changed')
    schemas = {t['function']['name']: t['function'] for t in tools}
    events = [e for e in read_private(storage, plan, PREFIX + '/events.json')
              if e['call'] < 'call_014']
    original_spans = read_private(storage, plan, PREFIX + '/spans.json')
    spans = {e['span_id']: original_spans[e['span_id']] for e in events}
    program_files = []
    for n in range(1, 13):
        base = PREFIX + f'/programs/call_{n:03d}_01/'
        program_files.append(dict(input=read_private(storage, plan, base + 'input_private.json'),
            result=read_private(storage, plan, base + 'result_private.json'),
            wire=read_private(storage, plan, base + 'wire_private.jsonl', lines=True)))
    programs = assemble_programs(events, spans, program_files, schemas)
    prior = json.loads((root / 'reports/P93_public_action_structure.json').read_text())
    messages = []
    if prior['status'] != 'complete' or len(prior['rows']) != 18:
        raise ValueError('closed_all_eighteen_P93_required')
    for item, row in zip(schedule(), prior['rows'], strict=True):
        if any(row[k] != v for k, v in item.items()):
            raise ValueError('original_schedule_changed')
        name = 'records/context_pilot/P84_fallback_output_v01/' + item['id'] + '/response.json'
        response = read_private(storage, plan, name)
        if plan['private_file_sha256'][name] != row['private_file_sha256']['response.json']:
            raise ValueError('original_response_binding_changed')
        messages.append(public_next_message(response, row['structure']['public_output_sha256']))
    public = read_private(storage, plan, PREFIX + '/public_task.json')
    return tools, programs, spans, public, messages


def reconstruct(programs, session, catalog, bridge, recorded, folder, storage, plan,
                deadline, stopped, condition):
    rows = []
    for program in programs:
        if stopped() or time.monotonic() >= deadline:
            raise InterruptedError('prefix_deadline_or_stop')
        source = program['source']
        exposed = {n: catalog.catalog[n]['function'] for n in sorted(catalog.visible)}
        if canonical(exposed) != canonical(source['api_schemas']):
            raise ValueError('prefix_initial_schemas_differ')
        channel = MatchedLiveChannel(catalog, bridge,
            plan['max_api_requests_per_condition'] - sum(r['api_request_sent'] for r in rows),
            program['entries'], lambda: time.monotonic() < deadline and not stopped())
        timeout = min(plan['program_timeout_seconds'], deadline - time.monotonic())
        recorded.deadline = min(deadline, time.monotonic() + timeout)
        actual = session.run(source['code'], source['observations'], channel,
            storage_root=storage, record_dir=folder / 'prefix' / program['name'], timeout=timeout)
        rows.extend(channel.rows)
        check = result_comparison(channel, actual, program['expected'])
        check.update(program=program['name'], wall_seconds=actual['wall_seconds'])
        condition['prefix_programs'].append(check)
        condition['prefix_api_requests'] = sum(r['api_request_sent'] for r in rows)
        condition['prefix_api_trace_sha256'] = digest(rows)
        write(folder / 'prefix_rows_private.json', rows)
        write(folder / 'progress.json', condition)
        if not check['public_prefix_matches']:
            raise ValueError('prefix_observable_mismatch_no_suffix')
    if condition['prefix_api_requests'] != 28:
        raise ValueError('prefix_api_total_differs')
    condition['public_prefix_matched'] = True


def suffix(message, original_spans, session, catalog, transport, recorded, folder,
           storage, plan, deadline, stopped, condition):
    spans = dict(original_spans)
    rows = []
    prefix_api = condition['prefix_api_requests']
    def record(row, display=True):
        sid = 's' + str(len(spans) + 1)
        spans[sid] = dict(id=sid, action=row['action'], observation=row['observation'])
        rows.append(dict(row, model_tool=display))
        write(folder / 'suffix_rows_private.json', rows)
        return sid
    def program(source, observations, channel, **kwargs):
        kwargs['timeout'] = min(plan['program_timeout_seconds'], kwargs['timeout'])
        recorded.deadline = min(deadline, time.monotonic() + kwargs['timeout'])
        return session.run(source, observations, channel, **kwargs)
    result = execute_response(message, catalog, transport,
        selected_receipts(list(original_spans), original_spans), record,
        out=folder, storage=storage, call_id='next',
        remaining_api=lambda: plan['max_api_requests_per_condition'] - prefix_api
            - sum(r['api_request_sent'] for r in rows),
        may_continue=lambda: time.monotonic() < deadline and not stopped() and not transport.complete,
        remaining_wall=lambda: deadline - time.monotonic(), program=program,
        read_archive=lambda sid, offset: page_span(original_spans, sid, offset,
                                                   plan['observation_page_characters']))
    write(folder / 'suffix_result_private.json', result)
    sent = [r for r in rows if r['api_request_sent']]
    public_rows = [r for r in rows if r['model_tool']]
    condition.update(suffix_api_requests=len(sent),
        suffix_API_names=dict(Counter(r['action']['name'] for r in sent)),
        suffix_request_sequence_sha256=digest([r['action'] for r in sent]),
        suffix_execution_evidence_sha256=digest(rows),
        structured_submissions=len(message['tool_calls']),
        suffix_saved_programs=len(session.programs) - len(condition['prefix_programs']),
        suffix_public_results=[dict(status=r['observation'].get('status'),
            format_error_present='format_error' in r['observation'],
            format_error_sha256=digest(r['observation'].get('format_error')),
            stdout_sha256=digest(r['observation'].get('stdout')),
            stdout_characters=len(r['observation'].get('stdout', '')),
            stdout_truncated=r['observation'].get('stdout_truncated'),
            error_sha256=digest(r['observation'].get('error')),
            api_requests=r['observation'].get('api_requests'),
            declared_complete=r['observation'].get('declared_complete')) for r in public_rows])
    if transport.fatal or not session.usable or any(r.get('effects_unknown') for r in rows):
        raise RuntimeError('suffix_unknown_effect_or_interpreter_failure')


def run(storage, root):
    plan = json.loads((root / PLAN).read_text())
    if (plan.get('private_output') != 'records/context_pilot/P94_saved_action_execution_v01'
            or plan.get('experiment_prefix') != 'P94_ACTION_V01'
            or plan.get('stop_marker') != '.runtime/P94.stop'):
        raise ValueError('fixed_P94_output_scope')
    output = storage / plan['private_output']
    target = root / 'reports/P94_saved_action_execution.json'
    if output.exists() or target.exists():
        raise FileExistsError('preserve_every_P94_attempt')
    output.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    deadline = started + 1200
    stopped = lambda: (storage / plan['stop_marker']).exists()
    report = dict(phase='P94', status='running', started_at=datetime.now(timezone.utc).isoformat(),
        source_commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip(),
        plan_sha256=sha(root / PLAN), conditions=[dict(**s, status='not_attempted',
            prefix_programs=[], prefix_api_requests=0, public_prefix_matched=False) for s in schedule()],
        model_generations=0, evaluator_calls=0, reserved_scenarios_read=0,
        original_full_state_restored=False, task_quality_measured=False,
        new_method_claim=False, automatic_retries=0)
    try:
        if subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=no'], cwd=root):
            raise ValueError('clean_tracked_source_required')
        tools, programs, spans, public, messages = prepare(storage, root, plan)
        world_root = storage / '.runtime/appworld/r18_probe_01'
        for condition in report['conditions']:
            if (world_root / 'experiments/outputs' / (plan['experiment_prefix'] + '_' + condition['id'])).exists():
                raise FileExistsError('preserve_existing_reconstruction_world')
        for condition, message in zip(report['conditions'], messages, strict=True):
            if stopped() or time.monotonic() >= deadline:
                raise InterruptedError('P94_stop_before_condition')
            cell_started = time.monotonic()
            cell_deadline = min(deadline, cell_started + plan['per_condition_deadline_seconds'])
            folder = output / condition['id']; folder.mkdir()
            raw = recorded = transport = session = None
            condition['status'] = 'running'
            try:
                raw = TypedBridgeProcess(storage / '.runtime/appworld/venv/bin/python', world_root,
                    folder, timeout_seconds=plan['bridge_timeout_seconds'])
                condition['owned_bridge_pid'] = raw.process.pid
                recorded = RecordedBridge(raw, folder, cell_deadline, stop=stopped)
                transport = PublicResultTransport(recorded)
                confirm_initial_world(transport.request(dict(op='init', task_id=plan['task_id'],
                    experiment=plan['experiment_prefix'] + '_' + condition['id'], seed=plan['world_seed'])), public)
                session = PersistentApiPython(storage, folder / 'python_session')
                catalog = PublicNameCatalog(tools)
                reconstruct(programs, session, catalog, transport, recorded, folder, storage,
                            plan, cell_deadline, stopped, condition)
                suffix(message, spans, session, catalog, transport, recorded, folder, storage,
                       plan, cell_deadline, stopped, condition)
                condition['status'] = 'complete'
            except BaseException as error:
                condition.update(status='stopped', error_type=type(error).__name__)
                write(folder / 'error_private.json', dict(type=type(error).__name__, message=str(error)))
                raise
            finally:
                condition['active_wall_seconds'] = time.monotonic() - cell_started
                cleanup_started = time.monotonic(); errors = []
                if session is not None:
                    try:
                        clean = session.close()
                        condition['python_cleanup'] = {k: clean.get(k) for k in
                            ('status', 'container_removed', 'cleanup_wall_seconds', 'oom_killed')}
                        condition['container_controls'] = session.controls
                        condition['saved_program_executions'] = len(session.programs)
                    except BaseException as error:
                        errors.append('python:' + type(error).__name__)
                if raw is not None:
                    try:
                        condition['bridge_cleanup'] = raw.close()
                        try:
                            os.kill(raw.process.pid, 0); condition['owned_bridge_absent'] = False
                        except ProcessLookupError:
                            condition['owned_bridge_absent'] = True
                    except BaseException as error:
                        errors.append('bridge:' + type(error).__name__)
                receipts = transport.receipts if transport else []
                condition.update(cleanup_errors=errors, cleanup_wall_seconds=time.monotonic() - cleanup_started,
                    full_wall_seconds=time.monotonic() - cell_started,
                    transport_attempts=len(receipts),
                    typed_status_counts=dict(Counter(r['status'] for r in receipts)),
                    bridge_attempts=len(recorded.attempts) if recorded else 0,
                    typed_requests_started=sum(a['raw_request_started'] and a['command']['op'] == 'call_typed'
                                              for a in recorded.attempts) if recorded else 0)
                write(folder / 'progress.json', condition); write(output / 'status.json', report)
            total = condition['prefix_api_requests'] + condition['suffix_api_requests']
            if (condition['cleanup_errors'] or not condition['python_cleanup']['container_removed']
                    or not condition['bridge_cleanup']['graceful'] or not condition['owned_bridge_absent']
                    or not all(condition['container_controls'].values()) or len(condition['container_controls']) != 14
                    or not total == condition['transport_attempts'] == condition['typed_requests_started']
                    or total > plan['max_api_requests_per_condition']):
                condition['status'] = 'cleanup_or_accounting_failed'
                raise ValueError('P94_cleanup_or_accounting')
            print(json.dumps({k: condition[k] for k in ('id', 'case', 'status',
                'prefix_api_requests', 'suffix_api_requests', 'suffix_saved_programs')}), flush=True)
        report['status'] = 'complete'
    except BaseException as error:
        report.update(status='stopped', error_type=type(error).__name__)
        write(output / 'error_private.json', dict(type=type(error).__name__, message=str(error)))
    finally:
        report.update(wall_seconds=time.monotonic() - started,
            environment_api_requests=sum(c.get('typed_requests_started', 0) for c in report['conditions']),
            saved_program_executions=sum(c.get('saved_program_executions', 0) for c in report['conditions']),
            completed_conditions=sum(c['status'] == 'complete' for c in report['conditions']),
            finished_at=datetime.now(timezone.utc).isoformat())
        write(output / 'status.json', report); write(target, report)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--storage-root', type=Path, required=True)
    args = parser.parse_args()
    result = run(args.storage_root.resolve(), Path(__file__).resolve().parents[1])
    print(json.dumps({k: result[k] for k in ('status', 'completed_conditions', 'environment_api_requests',
                                            'saved_program_executions', 'wall_seconds')}))
    raise SystemExit(0 if result['status'] == 'complete' else 1)
