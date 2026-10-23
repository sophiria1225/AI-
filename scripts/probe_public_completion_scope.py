"""Fourteen fixed terminal interventions after replay of all unfinished P71 worlds.

No model calls, generated-code execution, hidden-test inspection, or mutation
of an original world. All new evaluations remain separate from agent results.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

from public_name_catalog import PublicNameCatalog
from public_completion_scope import fixed_cases, verify_complete_selection, verify_source_usage
from probe_completion_scope import sent_events, terminal_changes, worker_record
from probe_notice_calibration import confirmed_ci
from inspect_input_exposure import check_resume
from later_handoff_sources import prepare_later_sources
from probe_prefix_replay import db_hashes
from recorded_python_replay import canonical
from run_context_comparison import Bridge, write_json
from run_handoff_factors import ROOT, read, sha

PLAN = 'configs/P72_public_completion_scope_v01.json'
CODE = tuple(sorted({str(p.relative_to(ROOT)) for p in (
    list((ROOT / 'scripts').glob('*.py')) + list((ROOT / 'tests').glob('test_*.py'))
    + list((ROOT / 'configs').glob('*.json'))
)} | {PLAN, 'docs/experiments/P72_public_completion_scope.md',
      'reports/P71_comparison.json', 'reports/P71_outcome_scope.json'}))


def now():
    return datetime.now(timezone.utc).isoformat()


def verify_sources(storage, plan):
    fixed_cases(plan)
    for path, expected in [('reports/P71_comparison.json', plan['source_audit_sha256']),
                           ('reports/P71_outcome_scope.json', plan['source_outcome_scope_sha256'])]:
        if sha(ROOT / path) != expected:
            raise ValueError('closed P71 evidence changed')
    audit = read(ROOT / 'reports/P71_comparison.json')
    verify_complete_selection(audit, plan)
    _, original, tools, _, prepared = prepare_later_sources(storage, ROOT)
    if original['seed'] != plan['environment_seed']:
        raise ValueError('original environment seed differs')
    result = {}
    for rid in plan['source_runs'] + [plan['completion_reference']]:
        row = next(r for r in audit['rows'] if r['run_id'] == rid)
        task = next(x for x in prepared if x['task_id'] == row['task_id'])
        folder = storage / 'records/context_pilot' / rid
        for name, digest in row['source_sha256'].items():
            if sha(folder / name) != digest:
                raise ValueError('audited source changed: ' + rid + '/' + name)
        summary = read(folder / 'summary.json')
        verify_source_usage(summary, read(folder / 'usage.json'), read(folder / 'events.json'))
        if summary['task_id'] != row['task_id'] or summary['run_id'] != rid:
            raise ValueError('source task identity differs')
        public = read(folder / 'public_task.json')
        if public != task['prefix']['public_task'] or public['ground_truth_loaded']:
            raise ValueError('public task differs or ground truth was loaded')
        evaluation = read(folder / 'evaluation.json')
        world = storage / '.runtime/appworld/r18_probe_01/experiments/outputs' / rid / 'tasks' / row['task_id'] / 'dbs'
        expected = {'dbs/' + k: v for k, v in evaluation['frozen_database_hashes'].items()}
        if db_hashes(world) != expected:
            raise ValueError('original evaluated world changed')
        evaluator = storage / '.runtime/appworld/venv/lib/python3.12/site-packages/appworld/evaluator.py'
        if (evaluation['evaluation_script_sha256'] != sha(ROOT / 'scripts/evaluate_context_trial.py')
                or evaluation['official_evaluator_sha256'] != sha(evaluator)):
            raise ValueError('evaluation implementation differs from P71')
        spans = read(folder / 'spans.json')
        events = sent_events(read(folder / 'prefix_events.json'), read(folder / 'events.json'), spans)
        completions = [e for e in events if spans[e['span_id']]['action']['name'] == 'supervisor__complete_task']
        if rid == plan['completion_reference']:
            if (len(completions) != 1 or completions[0] != events[-1]
                    or spans[completions[0]['span_id']]['action'] != plan['completion_action']
                    or not row['success']):
                raise ValueError('fixed observed completion reference differs')
        elif completions or summary['declared_complete']:
            raise ValueError('fixed unfinished source changed')
        if len(events) != summary['total_task_api_requests']:
            raise ValueError('source sent-request accounting differs')
        result[rid] = {'folder': folder, 'row': row, 'public_task': public,
                       'events': events, 'spans': spans, 'database_hashes': expected}
    expected = 2 * sum(len(result[rid]['events']) for rid in plan['source_runs'])
    if expected != plan['expected_replay_api_requests']:
        raise ValueError('fixed replay request count differs')
    if any(len(result[rid]['events']) + 1 > plan['max_api_requests_per_case'] for rid in plan['source_runs']):
        raise ValueError('source plus intervention exceeds case budget')
    return tools, result


class ProbeDeadline(BaseException):
    pass


def interrupted(*_):
    raise ProbeDeadline('fixed deadline or explicit interruption')


def run_case(storage, case):
    plan = read(ROOT / PLAN)
    parent = read(storage / 'records/context_pilot' / plan['batch_id'] / 'status.json')
    if (parent['status'] != 'running' or parent.get('active') != case['run_id']
            or case not in parent['planned_cases']
            or subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip() != parent['git_commit']
            or any(sha(ROOT / name) != digest for name, digest in parent['code_sha256'].items())):
        raise ValueError('worker requires its frozen, CI-checked parent batch')
    tools, sources = verify_sources(storage, plan)
    source = sources[case['source_run']]
    output = storage / 'records/context_pilot' / plan['batch_id'] / case['run_id']
    world_root = storage / '.runtime/appworld/r18_probe_01'
    world = world_root / 'experiments/outputs' / case['run_id']
    if output.exists() or world.exists():
        raise FileExistsError('preserve every case and world, including failures')
    output.mkdir(parents=True)
    row = {**case, 'task_id': case['task_id'], 'status': 'started',
           'replay_api_requests': 0, 'intervention_api_requests': 0,
           'unknown_effect_requests': 0, 'observation_matches': 0,
           'model_generations': 0, 'evaluator_calls': 0}
    bridge = None
    private = []
    started = time.monotonic()
    old = signal.signal(signal.SIGALRM, interrupted)
    signal.signal(signal.SIGTERM, interrupted)
    try:
        signal.setitimer(signal.ITIMER_REAL, plan['max_execution_seconds_per_case'])
        check_resume(storage)
        if (storage / '.runtime/P72.stop').exists():
            raise ProbeDeadline('explicit P72 stop')
        bridge = Bridge(storage / '.runtime/appworld/venv/bin/python', world_root, output)
        initial = bridge.request({'op': 'init', 'task_id': case['task_id'],
                                  'experiment': case['run_id'], 'seed': plan['environment_seed']})
        if not initial['ok'] or initial['result'] != source['public_task']:
            raise ValueError('public initialization differs')
        row['ground_truth_loaded'] = initial['result']['ground_truth_loaded']
        catalog = PublicNameCatalog(tools)

        def call(action, stage):
            if (storage / '.runtime/P72.stop').exists():
                raise ProbeDeadline('explicit P72 stop')
            if row['replay_api_requests'] + row['intervention_api_requests'] >= plan['max_api_requests_per_case']:
                raise ValueError('fixed API budget reached')
            decoded = catalog.decode(action)
            record = {'stage': stage, 'action': action, 'response': None}
            private.append(record)
            row[stage + '_api_requests'] += 1
            write_json(output / 'calls_private.json', private)
            write_json(output / 'result.json', row)
            try:
                response = bridge.request({'op': 'call', 'call': decoded})
            except (Exception, ProbeDeadline):
                row['unknown_effect_requests'] += 1
                raise
            record['response'] = response
            write_json(output / 'calls_private.json', private)
            observation = response['result'] if response['ok'] else {'api_error': response['error']}
            exposed = catalog.expose_requested_document(decoded) if response['ok'] else []
            return response, observation, exposed

        for event in source['events']:
            span = source['spans'][event['span_id']]
            _, observation, exposed = call(span['action'], 'replay')
            if canonical(observation) != canonical(span['observation']) or exposed != event['new_tools']:
                raise ValueError('public replay observation or schema exposure differs')
            row['observation_matches'] += 1
        dbs = world / 'tasks' / case['task_id'] / 'dbs'
        before = db_hashes(dbs)
        row['restored_database_matches'] = before == source['database_hashes']
        if not row['restored_database_matches']:
            raise ValueError('restored source world differs')
        row['before_database_hashes'] = before
        if case['arm'] == 'append_completion':
            response, _, _ = call(plan['completion_action'], 'intervention')
            if not response['ok'] or not response['result']['declared_complete']:
                raise ValueError('fixed completion request did not declare completion')
        after = db_hashes(dbs)
        changed = terminal_changes(before, after, case['arm'])
        row.update(status='execution_frozen', after_database_hashes=after,
                   changed_saved_files=changed, non_supervisor_files_unchanged=True)
    except (Exception, ProbeDeadline) as error:
        row.update(status='execution_failed', error_type=type(error).__name__)
        (output / 'error_private.txt').write_text(str(error))
    finally:
        signal.setitimer(signal.ITIMER_REAL, plan['max_cleanup_seconds_per_case'])
        try:
            if bridge is not None:
                bridge.close()
                row['bridge_exit_code'] = bridge.process.returncode
                if bridge.process.returncode != 0:
                    raise ValueError('bridge did not exit cleanly')
                if row['status'] == 'execution_frozen' and db_hashes(dbs) != row['after_database_hashes']:
                    raise ValueError('closing the world changed the frozen database')
        except (Exception, ProbeDeadline) as error:
            row.update(status='cleanup_failed', cleanup_error_type=type(error).__name__)
            if bridge is not None and bridge.process.poll() is None:
                bridge.process.kill(); bridge.process.wait(timeout=5)
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, old)
            row['execution_wall_seconds_including_cleanup'] = time.monotonic() - started
            row['request_accounting_finalized'] = True
            write_json(output / 'result.json', row)
    if row['status'] == 'execution_frozen':
        write_json(output / 'summary.json', {'run_id': case['run_id'], 'task_id': case['task_id'],
                   'finished_at': now(), 'evaluation': 'not_run', 'scope': 'terminal intervention, not an agent run'})
    return row


def run(storage, head, ci_ids):
    current = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    if current != head or subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True).strip():
        raise ValueError('exact clean frozen commit required')
    origin = subprocess.check_output(['git', 'remote', 'get-url', 'origin'], cwd=ROOT, text=True).strip()
    if origin not in ('https://github.com/sophiria1225/AI-', 'https://github.com/sophiria1225/AI-.git'):
        raise ValueError('wrong repository')
    ci = confirmed_ci(head, ci_ids)
    plan = read(ROOT / PLAN); cases = fixed_cases(plan)
    _, sources = verify_sources(storage, plan)
    resume = check_resume(storage)
    output = storage / 'records/context_pilot' / plan['batch_id']
    target = ROOT / 'reports/P72_public_completion_scope.json'
    if output.exists() or target.exists():
        raise FileExistsError('preserve prior batch, including failure')
    output.mkdir(parents=True)
    hashes = {name: sha(ROOT / name) for name in CODE}
    report = {'phase': 'P72', 'status': 'running', 'started_at': now(), 'git_commit': head,
        'ci': ci, 'research_resume': resume, 'code_sha256': hashes, 'plan': plan,
        'rows': [], 'planned_cases': cases, 'attempted_cases': [], 'model_generations': 0, 'tokenizer_requests': 0,
        'reserved_scenarios_read': 0, 'source_rows_sha256': {
            rid: value['row']['source_sha256'] for rid, value in sources.items()}}
    started = time.monotonic(); child = None
    def save():
        report['wall_seconds'] = time.monotonic() - started
        write_json(output / 'status.json', report); write_json(target, report)
    try:
        save()
        for index, case in enumerate(cases):
            if time.monotonic() - started >= plan['max_batch_seconds']:
                raise ProbeDeadline('batch deadline')
            check_resume(storage)
            if (storage / '.runtime/P72.stop').exists(): raise ProbeDeadline('explicit P72 stop')
            if any(sha(ROOT / name) != digest for name, digest in hashes.items()):
                raise ValueError('frozen code changed')
            report['active'] = case['run_id']; report['attempted_cases'].append(case['run_id']); save()
            with (output / (case['run_id'] + '_worker.log')).open('w') as log:
                child = subprocess.Popen([sys.executable, str(ROOT / 'scripts/probe_public_completion_scope.py'),
                    '--storage-root', str(storage), '--case', str(index)], stdout=log, stderr=log, start_new_session=True)
                timeout = min(plan['max_execution_seconds_per_case'] + plan['max_cleanup_seconds_per_case'] + 30,
                              plan['max_batch_seconds'] - (time.monotonic() - started))
                code = child.wait(timeout=max(1, timeout))
            folder = output / case['run_id']
            row = worker_record(folder, case)
            report['rows'].append(row); save()
            if code or not row.get('request_accounting_finalized'):
                raise ValueError('case worker failed or final accounting unavailable; no retry')
            if row['status'] != 'execution_frozen' or row['unknown_effect_requests']:
                raise ValueError('invalid execution or cleanup')
            row['evaluator_calls'] = 1; save()
            evaluated_at = time.monotonic()
            try:
                with (folder / 'evaluation.log').open('w') as log:
                    result = subprocess.run([str(storage / '.runtime/appworld/venv/bin/python'),
                        str(ROOT / 'scripts/evaluate_context_trial.py'), '--appworld-root',
                        str(storage / '.runtime/appworld/r18_probe_01'), '--trial', str(folder)],
                        stdout=log, stderr=log,
                        timeout=min(plan['max_evaluation_seconds_per_case'],
                                    max(1, plan['max_batch_seconds'] - (time.monotonic() - started))))
                if result.returncode: raise ValueError('independent evaluation failed')
                evaluation = read(folder / 'evaluation.json')
                row.update(status='evaluated', official_success=evaluation['official_success'],
                    pass_count=evaluation['pass_count'], fail_count=evaluation['fail_count'],
                    evaluation_sha256=sha(folder / 'evaluation.json'))
                if case['arm'] == 'no_completion' and row['official_success'] != sources[case['source_run']]['row']['success']:
                    raise ValueError('no-intervention control did not reproduce original outcome')
            finally:
                row['evaluation_wall_seconds'] = time.monotonic() - evaluated_at
                write_json(folder / 'result.json', row); save()
            print({k: row[k] for k in ('run_id', 'official_success', 'replay_api_requests', 'intervention_api_requests')}, flush=True)
        verify_sources(storage, plan)
        report.update(status='complete', original_sources_unchanged=True, active=None)
    except (Exception, ProbeDeadline) as error:
        report.update(status='stopped', error_type=type(error).__name__)
        (output / 'error_private.txt').write_text(str(error))
    finally:
        if child is not None and child.poll() is None:
            child.terminate()
            try: child.wait(timeout=plan['max_cleanup_seconds_per_case'] + 10)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid, signal.SIGKILL); child.wait(timeout=5)
        recorded = {r['run_id'] for r in report['rows']}
        for case in cases:
            if case['run_id'] in report['attempted_cases'] and case['run_id'] not in recorded:
                report['rows'].append(worker_record(output / case['run_id'], case))
        try:
            verify_sources(storage, plan)
            report['original_sources_unchanged'] = True
        except Exception as error:
            report.update(status='stopped', original_sources_unchanged=False,
                          final_source_check_error_type=type(error).__name__)
        completed = {r['run_id'] for r in report['rows']}
        report['not_recorded_cases'] = [c['run_id'] for c in cases if c['run_id'] not in completed]
        report['known_api_requests'] = sum(r['replay_api_requests'] + r['intervention_api_requests'] for r in report['rows'])
        report['unknown_request_count_cases'] = [r['run_id'] for r in report['rows'] if not r.get('request_accounting_finalized')]
        report['total_api_requests'] = None if report['unknown_request_count_cases'] else report['known_api_requests']
        report['evaluator_calls'] = sum(r['evaluator_calls'] for r in report['rows'])
        report['finished_at'] = now(); save()
    print({k: report[k] for k in ('status', 'total_api_requests', 'evaluator_calls', 'wall_seconds')})
    return 0 if report['status'] == 'complete' else 1


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--storage-root', type=Path, required=True)
    p.add_argument('--expected-commit'); p.add_argument('--push-ci', type=int); p.add_argument('--pr-ci', type=int)
    p.add_argument('--case', type=int, choices=range(14)); args = p.parse_args()
    signal.signal(signal.SIGTERM, interrupted); signal.signal(signal.SIGINT, interrupted)
    if args.case is not None:
        row = run_case(args.storage_root, fixed_cases(read(ROOT / PLAN))[args.case])
        raise SystemExit(0 if row['status'] == 'execution_frozen' else 1)
    if not args.expected_commit or not args.push_ci or not args.pr_ci:
        p.error('fixed commit and both exact-head CI run identifiers required')
    raise SystemExit(run(args.storage_root, args.expected_commit, [args.push_ci, args.pr_ci]))
