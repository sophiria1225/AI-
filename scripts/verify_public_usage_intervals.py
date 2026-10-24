"""Recompute P100 from public records using only the Python standard library.

Checks published bytes, accounting identities and conditional interval arithmetic.
Does not inspect private receipts, prove missing server usage, rerun evaluations,
or replace the original P97 decision. No model, network or environment calls.
"""
import argparse
import csv
from itertools import combinations, product
import json
from pathlib import Path

from verify_public_letter_evidence import public_path, digest, read, count

ROOT = Path(__file__).resolve().parents[1]
PLAN = 'configs/P100_recorded_usage_intervals_v01.json'
REPORT = 'reports/P100_recorded_usage_intervals.json'
PROVENANCE = 'reports/P100_results_provenance_20261024.json'
MATERIALS = 'materials/20261024_p100_results/'
INTERVALS = ('conditional_request_interval', 'conditional_context_interval')
IDENTITY = ('run_id', 'task_id', 'notice_policy', 'success', 'record_status',
            'stop_reason', 'model_calls', 'api_requests', 'known_total_tokens',
            'unknown_usage_calls', 'usage_sha256')
ZERO = ('model_generations', 'environment_API_requests', 'evaluations',
        'saved_code_executions', 'task_databases_read', 'reserved_scenarios_read',
        'P99_intermediate_outcomes_read')
ASSUMPTIONS = [
    'The server honors the recorded request output cap.',
    'The recorded tokenizer input count applies to that exact request.',
    'No unrecorded retry or extra generation is included in the defined logical cost.',
    'The context-only bound additionally assumes the recorded context cap is enforced.']


def require(condition, message):
    if not condition:
        raise ValueError(message)


def check_interval(stored, expected):
    require(isinstance(stored, list) and len(stored) == 2
            and all(type(x) is int for x in stored) and stored == expected,
            'conditional_interval_disagrees')


def totals(rows):
    return dict(cells=len(rows), successes=sum(r['success'] for r in rows),
        model_attempts=sum(r['model_calls'] for r in rows),
        API_requests=sum(r['api_requests'] for r in rows),
        known_logical_tokens=sum(r['known_total_tokens'] for r in rows),
        unknown_usage_attempts=sum(r['unknown_usage_calls'] for r in rows),
        **{key: [sum(r[key][i] for r in rows) for i in (0, 1)] for key in INTERVALS})


def differences(rows, policies):
    by = {r['notice_policy']: r for r in rows}
    result = []
    for left, right in combinations(policies, 2):
        entry = dict(minuend=right, subtrahend=left)
        for key in INTERVALS:
            lower = by[right][key][0] - by[left][key][1]
            upper = by[right][key][1] - by[left][key][0]
            sign = ('positive' if lower > 0 else 'negative' if upper < 0
                    else 'zero' if lower == upper == 0 else 'not_identified')
            entry[key] = dict(bounds=[lower, upper], sign_under_assumptions=sign)
        result.append(entry)
    return result


def recompute(plan, report, original):
    """An independent arithmetic check; never call the original analysis code."""
    require(plan['phase'] == report['phase'] == 'P100'
        and report['status'] == 'complete' and original['batch_status'] == 'complete'
        and original['audit_errors'] == [] and original['owned_processes_absent'] is True,
        'closed_reports_required')
    require(plan['limits'] == dict(context_tokens=65536, output_tokens=4096,
        cell_tokens=450000, max_calls=80), 'original_limits_required')
    require(plan['cells'] == 12 and plan['expected_attempts'] == 223
        and plan['expected_unknown_attempts'] == 2
        and len(plan['task_ids']) == 4 and len(set(plan['task_ids'])) == 4
        and plan['policies'] == ['none', 'generic', 'factual'], 'fixed_cohort_required')
    for key, expected in {
        'lower_bound_does_not_assert_zero_actual_usage': True,
        'unknown_terminal_usage_reconstructed': False,
        'posthoc_sensitivity_analysis': True, 'pairs_independent': False,
        'original_gate_replaced': False, 'novel_method_claim': False,
        'general_quality_preservation_established': False,
        'server_cap_compliance_proven_for_unknown': False,
        'private_reasoning_inspected_semantically': False,
        'original_factual_notice_benefit_gate_met': False}.items():
        require(report[key] is expected, 'scope_or_gate_changed:' + key)
    require(original['factual_notice_benefit_gate_met'] is False
        and report['assumptions'] == ASSUMPTIONS
        and report['independent_known_tasks'] == 4,
        'original_gate_assumptions_and_task_count_required')
    require(all(type(report[k]) is int and report[k] == 0 for k in ZERO),
            'read_only_analysis_required')
    rows, originals = report['rows'], original['rows']
    require(len(rows) == len(originals) == len(plan['run_ids']) == 12
        and len(set(plan['run_ids'])) == 12
        and [r['run_id'] for r in rows] == [r['run_id'] for r in originals] == plan['run_ids']
        and {(r['task_id'], r['notice_policy']) for r in rows}
            == set(product(plan['task_ids'], plan['policies'])), 'complete_ordered_cohort_required')
    for row, source in zip(rows, originals, strict=True):
        require(all(row[k] == source[k] for k in IDENTITY), 'original_cell_changed')
        require(type(row['success']) is bool and row['record_status'] == 'evaluated',
                'original_evaluation_required')
        for k in ('model_calls', 'api_requests', 'known_total_tokens', 'unknown_usage_calls'):
            count(row[k])
        calls, checks = row['calls'], source['request_checks']
        require(0 < len(calls) == len(checks) == row['model_calls'] <= 80,
                'all_original_attempts_required')
        known = unknown = request_upper = context_upper = 0
        for index, (call, check) in enumerate(zip(calls, checks, strict=True), 1):
            require(call['call_id'] == check['call_id'] == f'call_{index:03d}'
                and all(call[k] == check[k] for k in ('status', 'request_sha256', 'response_sha256'))
                and bool(call['request_sha256'])
                and type(call['terminal_record_present']) is bool
                and call['terminal_record_present'] is check['terminal_usage_recorded'],
                'original_attempt_receipt_changed')
            predicted = count(call['predicted_input_tokens'])
            cap = count(call['requested_output_cap'])
            require(predicted > 0 and cap > 0
                and cap == min(4096, 450000 - known - predicted)
                and predicted + cap <= 65536, 'request_reservation_changed')
            observed = call['observed_logical_tokens']
            if call['status'] == 'ok':
                require(type(observed) is int and predicted <= observed <= predicted + cap
                    and call['terminal_record_present'], 'known_usage_outside_recorded_cap')
                known += observed
                request_interval = context_interval = [observed, observed]
            else:
                require(call['status'] == 'error' and observed is None and index == len(calls),
                        'unknown_must_remain_missing_and_terminal')
                unknown += 1
                request_upper += predicted + cap
                context_upper += 65536
                request_interval, context_interval = [0, predicted + cap], [0, 65536]
            check_interval(call[INTERVALS[0]], request_interval)
            check_interval(call[INTERVALS[1]], context_interval)
        require(known == row['known_total_tokens'] and unknown == row['unknown_usage_calls'],
                'original_cell_accounting_disagrees')
        check_interval(row[INTERVALS[0]], [known, known + request_upper])
        check_interval(row[INTERVALS[1]], [known, known + context_upper])
    aggregate = []
    for policy in plan['policies']:
        selected = [r for r in rows if r['notice_policy'] == policy]
        aggregate.append(dict(notice_policy=policy, **totals(selected),
            successful=totals([r for r in selected if r['success']]),
            unsuccessful=totals([r for r in selected if not r['success']])))
    pairs = []
    for task in plan['task_ids']:
        selected = [r for r in rows if r['task_id'] == task]
        flags = {r['notice_policy']: r['success'] for r in selected}
        for pair in differences(selected, plan['policies']):
            pairs.append(dict(task_id=task, **pair,
                minuend_success=flags[pair['minuend']],
                subtrahend_success=flags[pair['subtrahend']] ))
    result = dict(totals=aggregate, whole_cohort_differences=differences(aggregate, plan['policies']),
                  all_task_differences=pairs, all_conditions=totals(rows))
    require(all(report[k] == value for k, value in result.items()),
            'stored_totals_or_differences_disagree')
    require(result['all_conditions']['model_attempts'] == 223
            and result['all_conditions']['unknown_usage_attempts'] == 2,
            'all_223_attempts_and_two_unknowns_required')
    return result


def csv_rows(report):
    cells, calls, pairs = [], [], []
    for row in report['rows']:
        cells.append({**{k: row[k] for k in ('run_id', 'task_id', 'notice_policy', 'success',
            'model_calls', 'api_requests', 'known_total_tokens', 'unknown_usage_calls')},
            'conditional_request_lower': row[INTERVALS[0]][0],
            'conditional_request_upper': row[INTERVALS[0]][1],
            'conditional_context_upper': row[INTERVALS[1]][1]})
        for call in row['calls']:
            calls.append({**{k: row[k] for k in ('run_id', 'task_id', 'notice_policy')},
                **{k: call[k] for k in ('call_id', 'status', 'predicted_input_tokens',
                    'requested_output_cap', 'observed_logical_tokens', 'terminal_record_present',
                    'request_sha256', 'response_sha256')},
                'conditional_request_lower': call[INTERVALS[0]][0],
                'conditional_request_upper': call[INTERVALS[0]][1],
                'conditional_context_upper': call[INTERVALS[1]][1]})
    for pair in report['all_task_differences']:
        pairs.append({**{k: pair[k] for k in ('task_id', 'minuend', 'subtrahend',
            'minuend_success', 'subtrahend_success')},
            'conditional_request_lower': pair[INTERVALS[0]]['bounds'][0],
            'conditional_request_upper': pair[INTERVALS[0]]['bounds'][1],
            'conditional_request_sign': pair[INTERVALS[0]]['sign_under_assumptions'],
            'conditional_context_lower': pair[INTERVALS[1]]['bounds'][0],
            'conditional_context_upper': pair[INTERVALS[1]]['bounds'][1]})
    return dict(all_twelve_conditions=cells, all_223_attempts=calls, all_twelve_task_pairs=pairs)


def verify(root):
    plan, report, provenance = (read(public_path(root, name)) for name in (PLAN, REPORT, PROVENANCE))
    require(report['plan_sha256'] == digest(public_path(root, PLAN))
        and report['source_sha256'] == plan['source_sha256'], 'plan_binding_changed')
    bindings = dict(plan['source_sha256'])
    for name, expected in provenance['source_sha256'].items():
        require(name not in bindings or bindings[name] == expected, 'conflicting_hash_binding')
        bindings[name] = expected
    require(len(plan['source_sha256']) == 9 and len(provenance['source_sha256']) == 7
        and REPORT in bindings and all(MATERIALS + n + '.csv' in bindings
            for n in ('all_twelve_conditions', 'all_223_attempts', 'all_twelve_task_pairs')),
        'complete_public_bindings_required')
    for name, expected in bindings.items():
        require(digest(public_path(root, name)) == expected, 'public_file_changed:' + name)
    require(report['source_commit'] == provenance['executed_head']
        == provenance['preparation_publication']['head']
        and len(report['source_commit']) == 40 and report['CI'] == provenance['CI']
        and len(report['CI']) == 2 and {c['event'] for c in report['CI']} == {'push', 'pull_request'}
        and all(c['head'] == report['source_commit'] and c['success'] is True
            and count(c['workflow']) > 0 and count(c['job']) > 0 for c in report['CI']),
        'published_execution_and_CI_records_disagree')
    original = read(public_path(root, 'reports/P97_comparison.json'))
    result = recompute(plan, report, original)
    summary = read(public_path(root, MATERIALS + 'summary.json'))
    require(summary == {**result, 'assumptions': ASSUMPTIONS, 'wall_seconds': report['wall_seconds']},
            'published_summary_disagrees')
    for name, rows in csv_rows(report).items():
        expected = [{k: '' if v is None else str(v) for k, v in row.items()} for row in rows]
        with public_path(root, MATERIALS + name + '.csv').open(newline='') as stream:
            reader = csv.DictReader(stream)
            require(reader.fieldnames == list(rows[0]) and list(reader) == expected,
                    'published_CSV_disagrees:' + name)
    return dict(status='verified_public_records_and_conditional_arithmetic',
        checked_bindings=len(bindings), plan_sha256=digest(public_path(root, PLAN)),
        report_sha256=digest(public_path(root, REPORT)), provenance_sha256=digest(public_path(root, PROVENANCE)),
        conditions=12, attempts=223, unknown_attempts_preserved=2, task_pairs=12,
        whole_cohort_pairs=3, independent_known_tasks=4, **result,
        original_gate_replaced=False, novel_method_established=False,
        scope='Public byte consistency and conditional arithmetic only. Private token receipts, '
              'server cap compliance on missing calls, evaluator truth, live CI, and scientific '
              'sufficiency are not independently verified.',
        additional_model_generations=0, additional_API_requests=0, additional_evaluations=0)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo-root', type=Path, default=ROOT)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = verify(args.repo_root.resolve())
    rendered = json.dumps(result, ensure_ascii=False, indent=2) + '\n'
    if args.output:
        with args.output.open('x') as stream:
            stream.write(rendered)
    print(json.dumps({k: result[k] for k in ('status', 'checked_bindings', 'conditions',
        'attempts', 'unknown_attempts_preserved', 'task_pairs', 'whole_cohort_pairs', 'scope')}))
