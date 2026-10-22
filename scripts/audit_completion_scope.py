"""Read-only audit of every fixed P56 replay and terminal intervention."""
import argparse
from pathlib import Path

from appworld_native_tools import NativeCatalog
from probe_completion_scope import CODE, PLAN, fixed_cases, terminal_changes, verify_sources
from probe_prefix_replay import db_hashes
from recorded_python_replay import canonical
from run_context_comparison import write_json
from run_handoff_factors import ROOT, read, sha


def audit(storage, frozen):
    report = read(frozen / 'reports/P56_completion_scope.json')
    plan = read(frozen / PLAN)
    if report['status'] not in ('complete', 'stopped') or report['plan'] != plan:
        raise ValueError('closed fixed P56 report required')
    batch = storage / 'records/context_pilot' / plan['batch_id']
    if read(batch / 'status.json') != report:
        raise ValueError('private and public batch reports differ')
    for name in CODE:
        if (sha(frozen / name) != report['code_sha256'][name]
                or sha(ROOT / name) != report['code_sha256'][name]):
            raise ValueError('audit dependency differs from executed source: ' + name)
    tools, sources = verify_sources(storage, plan)
    cases = fixed_cases(plan)
    if report['planned_cases'] != cases or report['attempted_cases'] != [c['run_id'] for c in cases][:len(report['attempted_cases'])]:
        raise ValueError('fixed case order differs')
    rows = []
    for case in cases:
        existing = [r for r in report['rows'] if r['run_id'] == case['run_id']]
        if len(existing) > 1: raise ValueError('duplicate case')
        if not existing:
            rows.append({**case, 'record_status': 'not_run', 'official_success': None})
            continue
        row = existing[0]; folder = batch / case['run_id']
        if row['status'] != 'evaluated':
            rows.append({**case, 'record_status': 'attempted_incomplete', 'official_success': None,
                         'reported_execution': row})
            continue
        source = sources[case['source_run']]
        if (read(folder / 'result.json') != row or row['unknown_effect_requests']
                or not row['request_accounting_finalized'] or row['bridge_exit_code'] != 0
                or row['ground_truth_loaded'] or row['model_generations']
                or row['evaluator_calls'] != 1 or not row['restored_database_matches']
                or row['before_database_hashes'] != source['database_hashes']):
            raise ValueError('execution, restoration or cleanup differs')
        receipts = read(folder / 'calls_private.json')
        expected_count = len(source['events']) + (case['arm'] == 'append_completion')
        if (len(receipts) != expected_count or row['replay_api_requests'] != len(source['events'])
                or row['intervention_api_requests'] != (case['arm'] == 'append_completion')
                or row['observation_matches'] != len(source['events'])):
            raise ValueError('request accounting or intervention count differs')
        catalog = NativeCatalog(tools)
        for entry, event in zip(receipts[:len(source['events'])], source['events'], strict=True):
            expected = source['spans'][event['span_id']]
            if entry['stage'] != 'replay' or entry['action'] != expected['action']:
                raise ValueError('replayed request differs from original')
            decoded = catalog.decode(entry['action']); response = entry['response']
            actual = response['result'] if response['ok'] else {'api_error': response['error']}
            exposed = catalog.expose_requested_document(decoded) if response['ok'] else []
            if canonical(actual) != canonical(expected['observation']) or exposed != event['new_tools']:
                raise ValueError('recorded public response or tool exposure differs')
        if case['arm'] == 'append_completion':
            last = receipts[-1]
            if (last['stage'] != 'intervention' or last['action'] != plan['completion_action']
                    or not last['response']['ok'] or not last['response']['result']['declared_complete']):
                raise ValueError('terminal intervention differs')
        changed = terminal_changes(row['before_database_hashes'], row['after_database_hashes'], case['arm'])
        if changed != row['changed_saved_files'] or not row['non_supervisor_files_unchanged']:
            raise ValueError('saved state change differs')
        dbs = storage / '.runtime/appworld/r18_probe_01/experiments/outputs' / case['run_id'] / 'tasks' / plan['task_id'] / 'dbs'
        if db_hashes(dbs) != row['after_database_hashes']:
            raise ValueError('post-intervention world changed')
        ev = read(folder / 'evaluation.json')
        if (sha(folder / 'evaluation.json') != row['evaluation_sha256']
                or ev['execution_summary_sha256'] != sha(folder / 'summary.json')
                or ev['evaluation_script_sha256'] != sha(frozen / 'scripts/evaluate_context_trial.py')
                or {'dbs/' + k: v for k, v in ev['frozen_database_hashes'].items()} != row['after_database_hashes']
                or ev['evaluation_returned_to_model'] or type(ev['official_success']) is not bool
                or any(ev[k] != row[k] for k in ('official_success', 'pass_count', 'fail_count'))):
            raise ValueError('independent evaluator linkage differs')
        evaluator = storage / '.runtime/appworld/venv/lib/python3.12/site-packages/appworld/evaluator.py'
        if sha(evaluator) != ev['official_evaluator_sha256']:
            raise ValueError('evaluator source changed')
        if case['arm'] == 'no_completion' and ev['official_success'] != source['row']['success']:
            raise ValueError('no-intervention outcome differs from original')
        rows.append({**case, 'record_status': 'evaluated', 'official_success': ev['official_success'],
            'replay_api_requests': row['replay_api_requests'], 'intervention_api_requests': row['intervention_api_requests'],
            'observation_matches': row['observation_matches'], 'database_files': len(row['before_database_hashes']),
            'non_supervisor_files_unchanged': True, 'changed_saved_files': changed,
            'final_world_equals_original_D': row['after_database_hashes'] == sources[plan['completion_reference']]['database_hashes'],
            'execution_wall_seconds_including_cleanup': row['execution_wall_seconds_including_cleanup'],
            'evaluation_wall_seconds': row['evaluation_wall_seconds'],
            'source_sha256': {n: sha(folder / n) for n in ('result.json', 'calls_private.json', 'summary.json', 'evaluation.json')}})
    complete = all(r['record_status'] == 'evaluated' for r in rows)
    if report['status'] == 'complete' and not complete:
        raise ValueError('completed batch lacks four audited evaluations')
    comparisons = []
    for source in plan['source_runs']:
        pair = [next(r for r in rows if r['source_run'] == source and r['arm'] == arm) for arm in plan['arms']]
        comparisons.append({'source_run': source, 'outcomes': [r['official_success'] for r in pair],
            'both_evaluated': all(r['record_status'] == 'evaluated' for r in pair),
            'outcome_changed_by_completion': pair[0]['official_success'] != pair[1]['official_success']
                if all(r['record_status'] == 'evaluated' for r in pair) else None})
    return {'phase': 'P56_audit', 'batch_status': report['status'], 'audit_errors': [],
        'all_four_cases_accounted': True, 'all_four_evaluated': complete, 'rows': rows, 'comparisons': comparisons,
        'known_api_requests': report['known_api_requests'], 'total_api_requests': report['total_api_requests'],
        'unknown_request_count_cases': report['unknown_request_count_cases'],
        'original_sources_unchanged': True, 'additional_model_calls': 0, 'additional_api_requests': 0,
        'additional_evaluator_calls': 0, 'hidden_test_details_read': False,
        'autonomous_finalizer_validated': False, 'original_outcomes_relabelled': False,
        'source_report_sha256': sha(frozen / 'reports/P56_completion_scope.json'),
        'source_plan_sha256': sha(frozen / PLAN), 'auditor_sha256': sha(Path(__file__)),
        'limits': ['Post-hoc known-task diagnostic, not an independent agent-quality trial.',
            'Only the prespecified terminal API intervention is isolated; no safe automatic completion rule is established.',
            'Extra replay, intervention and evaluation costs are separate from original P55 costs.',
            'Original P55 outcomes and unknown model usage remain unchanged.']}


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--storage-root', type=Path, required=True)
    p.add_argument('--frozen-root', type=Path, required=True); args = p.parse_args()
    target = ROOT / 'reports/P56_completion_audit.json'
    if target.exists(): raise FileExistsError('preserve prior audit')
    result = audit(args.storage_root, args.frozen_root); write_json(target, result)
    print({k: result[k] for k in ('all_four_evaluated', 'total_api_requests', 'comparisons')})
