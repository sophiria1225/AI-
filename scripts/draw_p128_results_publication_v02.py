"""Standalone P128 closed-results scientific figures, or handwritten synthetic preview.

No project modules are imported. Actual loading starts with the completed collector,
then frozen closure/start/independent-review gates. Raw task records and saved
programs are never read or executed. Existing output directories are preserved.
"""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import re
import sys
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
from matplotlib.lines import Line2D
from matplotlib.ticker import FuncFormatter, MaxNLocator

HEAD = '0c29b754b23c8ca97ead6e9319661395b6c603a9'
PLAN_SHA = '8b061a77f3e778716e0a846ea3be46e05ec6012aecd826c44b8c9b84bf006d00'
COLLECTOR_SHA = '96d9b6e9a06475777e2e14e8f1f3b4a5fa5aaf8d9a835262709da8fe90f9b7c2'
LAUNCHER_SHA = '66bc5b5ab0fcbd7292a016713295ec954b0f2ca0691fe45f1dec6f79d0b3b1b6'
REVIEW_SHA = 'a9346a064ccabc1ea618e47a163e165c13539cece53f839291e9ef8d8690a6b8'
MODES = ('full', 'disclose')
LABELS = ('Full receipts', 'Receipt disclosure')
SEEDS = (57, 157)
TASKS = ('Photo', 'Expenses', 'Refund', 'CSV')
COLORS = ('#4477AA', '#228877')
MATERIALS = 'materials/20261026_p128_results'
REPORT = 'reports/P128_comparison.json'
SESSION = 'reports/P128_server_session.json'
PLAN = 'configs/P128_whole_task_receipt_disclosure_v01.json'
ACTIVATION = 'reports/P128_activation_v01.json'
PREFLIGHT = 'reports/P128_initial_checks.json'
AUDITOR = 'scripts/audit_whole_task_receipt_disclosure.py'
INSPECTOR = 'scripts/inspect_whole_task_receipt_disclosure_session.py'
STATUSES = ('evaluated', 'unevaluated', 'not_run', 'incomplete_worker', 'audit_error')
CORE = ('replication', 'model_seed', 'receipt_mode', 'run_id', 'task_id', 'projection_policy',
        'checkpoint_policy', 'record_status', 'success')
TIME_FIELDS = ('setup_wall_seconds', 'wall_seconds', 'cleanup_wall_seconds', 'full_wall_seconds')
RUNTIME_COUNTS = ('program_attempts', 'program_evidence_records', 'static_eligible_programs',
    'transformed_programs', 'ordinary_complete_cache_hits', 'projection_lookup_requests',
    'projection_partial_hits', 'projection_complete_lookup_hits', 'projection_lookup_misses',
    'projection_failure_events', 'explicit_field_requests', 'explicit_field_partial_hits',
    'automatic_region_partial_hits', 'known_control_requests', 'known_control_request_bytes',
    'known_control_reply_bytes', 'schema_deliveries', 'known_schema_reply_wire_bytes')
RUNTIME_TIMES = ('program_wall_seconds', 'control_wall_seconds_including_backend', 'projection_lookup_wall_seconds')
RUNTIME_FLAGS = ('control_accounting_complete', 'schema_accounting_complete', 'execution_trace_accounting_complete')
RECEIPT_COUNTS = ('receipt_disclosures', 'receipt_disclosed_turns', 'receipt_eligible_turns',
    'receipt_read_span_actions', 'receipt_read_span_returned_characters', 'removed_receipt_UTF8_bytes')
RECEIPT_FLAGS = ('receipt_disclosure_contract_failed', 'receipt_disclosure_contract_intact', 'receipt_disclosure_audit_complete')
MEASURES = ('api_requests', 'model_calls', 'input_tokens', 'output_tokens', 'cached_input_tokens',
            *TIME_FIELDS, *RUNTIME_COUNTS, *RUNTIME_TIMES, *RECEIPT_COUNTS)
COUNT_FIELDS = ('model_calls', 'known_total_tokens', 'unknown_usage_calls', 'api_requests',
                'input_tokens', 'output_tokens', 'cached_input_tokens', 'projection_hits',
                'exact_total_tokens', 'checkpoint_opportunity', 'checkpoint_installations',
                *RUNTIME_COUNTS, *RECEIPT_COUNTS)
PUBLIC_FIELDS = (*CORE, 'stop_reason', 'model_calls', 'known_total_tokens', 'unknown_usage_calls',
    'api_requests', 'input_tokens', 'output_tokens', 'cached_input_tokens', 'projection_hits',
    'exact_total_tokens', *TIME_FIELDS, 'checkpoint_installed', 'checkpoint_opportunity',
    'checkpoint_installations', 'projection_contract_failed', *RUNTIME_COUNTS, *RUNTIME_TIMES,
    *RUNTIME_FLAGS, *RECEIPT_COUNTS, *RECEIPT_FLAGS, 'receipt_snapshot_sha256', 'summary_sha256',
    'usage_sha256', 'evaluation_sha256')


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def count(value):
    return type(value) is int and value >= 0


def number(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def same(a, b):
    return json.dumps(a, sort_keys=True, allow_nan=False) == json.dumps(b, sort_keys=True, allow_nan=False)


def sha(path):
    path = Path(path)
    require(path.is_file() and not path.is_symlink() and path.stat().st_size <= 64 * 1024 * 1024,
            'bounded_regular_input_required')
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    sha(path)
    return json.loads(Path(path).read_text(), parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite_json')))


def public_path(root, name):
    require(type(name) is str and not Path(name).is_absolute() and '..' not in Path(name).parts
            and name.split('/')[0] in ('scripts', 'tests', 'configs', 'docs', 'reports', 'materials'),
            'public_relative_source_required')
    path = root / name
    require(path.resolve().is_relative_to(root), 'public_source_escape')
    return path


def identity(row):
    match = re.fullmatch(r'BOC_P128_R0([12])_0([1-4])_(FULL|DISCLOSE)', row['run_id'])
    require(match is not None, 'fixed_slot_id_required')
    rep, slot = int(match[1]), int(match[2])
    require(type(row['replication']) is int and row['replication'] == rep
            and type(row['model_seed']) is int and row['model_seed'] == SEEDS[rep - 1]
            and row['receipt_mode'] == match[3].lower(), 'fixed_slot_seed_mode_required')
    return rep, slot, row['receipt_mode']


def aggregate(rows):
    known = [r['known_total_tokens'] for r in rows if count(r.get('known_total_tokens'))]
    unknown = [r['unknown_usage_calls'] for r in rows if count(r.get('unknown_usage_calls'))]
    exact = bool(rows) and len(known) == len(unknown) == len(rows) and sum(unknown) == 0
    measures = {}
    for key in MEASURES:
        values = [r[key] for r in rows if number(r.get(key))]
        complete = bool(rows) and len(values) == len(rows)
        if key in ('input_tokens', 'output_tokens', 'cached_input_tokens'):
            complete &= exact
        if key in RECEIPT_COUNTS:
            complete &= all(r.get('receipt_disclosure_audit_complete') is True for r in rows)
        if key.startswith('known_control_') or key == 'control_wall_seconds_including_backend':
            complete &= all(r.get('control_accounting_complete') is True for r in rows)
        if key in ('known_schema_reply_wire_bytes', 'schema_deliveries'):
            complete &= all(r.get('schema_accounting_complete') is True for r in rows)
        measures[key] = dict(known_subtotal=sum(values), reported_conditions=len(values),
                             exact_all_condition_total=sum(values) if complete else None)
    return dict(planned_conditions=len(rows), accounted_conditions=len(known),
        evaluated_conditions=sum(r['record_status'] == 'evaluated' for r in rows),
        successful_conditions=sum(r['success'] is True for r in rows), known_token_subtotal=sum(known),
        recorded_unknown_usage_calls=sum(unknown), unknown_usage_count_missing_conditions=len(rows) - len(unknown),
        exact_total_tokens=sum(known) if exact else None, all_condition_usage_known=exact, measures=measures)


def criteria(rows, error_count):
    index = {identity(r): r for r in rows}
    common = {(rep, slot) for rep in (1, 2) for slot in range(1, 5)
              if all(index[rep, slot, mode]['success'] is True for mode in MODES)}
    seeds = []
    for rep, seed in enumerate(SEEDS, 1):
        subset = [r for r in rows if r['replication'] == rep]
        complete = all(r['record_status'] == 'evaluated' and r['unknown_usage_calls'] == 0 for r in subset)
        evaluated = all(r['record_status'] == 'evaluated' for r in subset)
        losses = sum(index[rep, n, 'full']['success'] is True and index[rep, n, 'disclose']['success'] is False for n in range(1, 5)) if evaluated else None
        gains = sum(index[rep, n, 'disclose']['success'] is True and index[rep, n, 'full']['success'] is False for n in range(1, 5)) if evaluated else None
        delta = sum(index[rep, n, 'disclose']['known_total_tokens'] - index[rep, n, 'full']['known_total_tokens'] for n in range(1, 5)) if complete else None
        common_delta = sum(index[rep, n, 'disclose']['known_total_tokens'] - index[rep, n, 'full']['known_total_tokens'] for n in range(1, 5) if (rep, n) in common) if complete else None
        seeds.append(dict(replication=rep, model_seed=seed, all_eight_complete_with_known_usage=complete,
            paired_success_losses=losses, paired_success_gains=gains,
            paired_successful_tasks=sum((rep, n) in common for n in range(1, 5)) if evaluated else None,
            disclose_minus_full_whole_task_tokens=delta, paired_successful_token_difference=common_delta,
            development_gate_met=bool(complete and not error_count and losses == 0 and delta < 0
                                      and any(k[0] == rep for k in common) and common_delta < 0)))
    complete = all(s['all_eight_complete_with_known_usage'] for s in seeds)
    evaluated = all(r['record_status'] == 'evaluated' for r in rows)
    values = [index[rep, n, 'disclose']['receipt_disclosures'] for rep, n in sorted(common)]
    disclosures = sum(values) if values and all(count(v) for v in values) else None
    failures = [r['receipt_disclosure_contract_failed'] for r in rows]
    runtime = [r['projection_contract_failed'] for r in rows]
    failure_count = sum(failures) if all(type(v) is bool for v in failures) else None
    runtime_count = sum(runtime) if all(type(v) is bool for v in runtime) else None
    intact = failure_count == 0 and runtime_count == 0
    result = dict(all_sixteen_complete_with_known_usage=complete, per_seed=seeds,
        paired_success_losses=sum(s['paired_success_losses'] for s in seeds) if evaluated else None,
        paired_success_gains=sum(s['paired_success_gains'] for s in seeds) if evaluated else None,
        paired_successful_tasks=len(common) if evaluated else None,
        disclose_minus_full_whole_task_tokens=sum(s['disclose_minus_full_whole_task_tokens'] for s in seeds) if complete else None,
        paired_successful_token_difference=sum(s['paired_successful_token_difference'] for s in seeds) if complete else None,
        receipt_disclosures_on_common_success=disclosures,
        receipt_disclosure_contract_failure_cells=failure_count, shared_runtime_contract_failure_cells=runtime_count,
        mechanism_contracts_intact=intact,
        development_gate_met=bool(not error_count and all(s['development_gate_met'] for s in seeds)
                                 and disclosures is not None and disclosures >= 1 and intact),
        planned_rows=16, independent_tasks=4, repetitions=2, model_seeds=list(SEEDS),
        general_quality_preservation_claim=False, novel_method_claim=False)
    return result, common


def check_subset(expected, given, reason):
    require(type(given) is dict, reason)
    for key, value in expected.items():
        if key == 'per_seed':
            require(type(given.get(key)) is list and len(given[key]) == 2, reason)
            for wanted, actual in zip(value, given[key], strict=True):
                check_subset(wanted, actual, reason)
        else:
            require(key in given and same(value, given[key]), reason + ':' + key)


def summary_for(rows, errors):
    computed, common = criteria(rows, errors)
    def groups(subset):
        return dict(all_conditions=aggregate(subset),
            by_policy={m: aggregate([r for r in subset if r['receipt_mode'] == m]) for m in MODES},
            common_success_costs_by_policy={m: aggregate([r for r in subset if r['receipt_mode'] == m
                and identity(r)[:2] in common]) for m in MODES})
    summary = dict(phase='P128', **groups(rows), conditions=rows, audit_error_count=errors,
        common_successful_task_seed_pairs=len(common), independent_tasks=4, repetitions=2,
        model_seeds=list(SEEDS), audited_criteria=computed, by_replication={},
        general_quality_preservation_claim=False, novel_method_claim=False, unknown_usage_is_not_zero=True)
    for rep, seed in enumerate(SEEDS, 1):
        summary['by_replication'][str(rep)] = dict(model_seed=seed,
            common_success_task_pairs=sum(k[0] == rep for k in common),
            **groups([r for r in rows if r['replication'] == rep]))
    return summary


def validate_rows(rows, summary, error_count):
    require(count(error_count), 'audit_error_count_required')
    expected = {(rep, n, mode) for rep in (1, 2) for n in range(1, 5) for mode in MODES}
    require(type(rows) is list and len(rows) == 16 and {identity(r) for r in rows} == expected,
            'all_sixteen_unique_conditions_required')
    index = {identity(r): r for r in rows}
    tasks = []
    for n in range(1, 5):
        task = index[1, n, 'full']['task_id']
        require(type(task) is str and all(index[rep, n, mode]['task_id'] == task for rep in (1, 2) for mode in MODES),
                'same_four_tasks_across_modes_and_seeds_required')
        tasks.append(task)
    require(len(set(tasks)) == 4, 'four_distinct_tasks_required')
    for row in rows:
        require(set(row) == set(PUBLIC_FIELDS), 'fixed_public_field_allowlist_required')
        status = row['record_status']
        require(status in STATUSES, 'known_status_required')
        require(type(row['success']) is bool if status == 'evaluated' else row['success'] is None,
                'official_success_status_disagrees')
        require(row['projection_policy'] == 'explicit_joined_fields' and row['checkpoint_policy'] == 'rolling_separate',
                'shared_runtime_and_checkpoint_required')
        if status not in ('evaluated', 'unevaluated'):
            require(all(v is None for k, v in row.items() if k not in CORE), 'missing_condition_cannot_gain_measurements')
            continue
        require(all(count(row[k]) for k in ('known_total_tokens', 'unknown_usage_calls', 'input_tokens', 'output_tokens', 'model_calls', 'api_requests')),
                'known_subtotals_and_attempt_counts_required')
        for field in COUNT_FIELDS:
            require(row[field] is None or count(row[field]), 'nonnegative_count_or_null:' + field)
        for field in (*TIME_FIELDS, *RUNTIME_TIMES):
            require(row[field] is None or number(row[field]), 'finite_duration_or_null:' + field)
        for flag in ('projection_contract_failed', 'checkpoint_installed', *RUNTIME_FLAGS, *RECEIPT_FLAGS):
            require(row[flag] is None or type(row[flag]) is bool, 'boolean_or_null:' + flag)
        require(row['input_tokens'] + row['output_tokens'] == row['known_total_tokens']
                and row['unknown_usage_calls'] <= row['model_calls'], 'token_subtotal_or_attempt_count_differs')
        require(same(row['exact_total_tokens'], row['known_total_tokens'] if row['unknown_usage_calls'] == 0 else None),
                'unknown_usage_is_not_exact')
        if row['cached_input_tokens'] is not None:
            require(row['cached_input_tokens'] <= row['input_tokens'], 'cached_input_exceeds_input')
        require(all(count(row[k]) for k in RECEIPT_COUNTS)
                and row['receipt_disclosures'] <= row['receipt_disclosed_turns'] <= row['receipt_eligible_turns'],
                'paid_exposure_final_turn_eligibility_order')
        if row['receipt_mode'] == 'full':
            require(row['receipt_disclosed_turns'] == row['receipt_disclosures'] == 0, 'full_mode_cannot_disclose')
        require(row['projection_hits'] in (None, 0) and row['automatic_region_partial_hits'] in (None, 0),
                'automatic_region_disabled_in_both_modes')
    computed = summary_for(rows, error_count)
    for key in ('phase', 'all_conditions', 'by_policy', 'common_success_costs_by_policy', 'by_replication',
                'common_successful_task_seed_pairs', 'independent_tasks', 'repetitions', 'model_seeds', 'audit_error_count'):
        require(same(summary.get(key), computed[key]), 'row_derived_summary_differs:' + key)
    check_subset(computed['audited_criteria'], summary['audited_criteria'], 'fixed_criteria_differs')
    for flag in ('general_quality_preservation_claim', 'novel_method_claim'):
        require(summary.get(flag) is False, 'unsupported_general_claim')
    require(summary.get('unknown_usage_is_not_zero') is True, 'unknown_is_not_zero_required')
    return dict(computed, synthetic=False, unknown_is_not_zero=True,
                development_gate_met=computed['audited_criteria']['development_gate_met'])


def load_closed(root, closure_path, collector_path, collector_start_path, pipeline_start_path, review_path):
    # Do not move any cohort/material read before these gates.
    collector = read(collector_path)
    require(collector.get('status') == 'complete', 'completed_collector_required_before_results_read')
    start, closure, launch, review = map(read, (collector_start_path, closure_path, pipeline_start_path, review_path))
    external = {key: sha(path) for key, path in (
        ('collector', collector_path), ('collector_start', collector_start_path), ('closure', closure_path),
        ('pipeline_start', pipeline_start_path), ('independent_review', review_path))}
    require(start.get('source_head') == HEAD and start.get('wrapper_sha256') == COLLECTOR_SHA
            and start.get('closure_sha256') == external['closure'], 'frozen_collector_closure_binding')
    require(launch.get('source_head') == HEAD and launch.get('plan_sha256') == PLAN_SHA
            and launch.get('wrapper_sha256') == LAUNCHER_SHA, 'frozen_launch_head_plan_binding')
    stages = closure.get('stages')
    require(type(stages) is list and [s.get('stage') for s in stages] == ['audit', 'session', 'report']
            and all(count(s.get('exit_code')) for s in stages)
            and all(s['exit_code'] == 0 for s in stages[1:]), 'closed_audit_session_material_stages_required')
    require(review.get('status') == 'pass' and review.get('phase') == 'P128_closed_independent_review'
            and review.get('fixed_head') == HEAD and review.get('plan_sha256') == PLAN_SHA
            and review.get('review_script_sha256') == REVIEW_SHA
            and review.get('collector_complete_seen_before_trial_read') is True
            and review.get('collector_end_sha256') == external['collector'], 'fixed_independent_review_pass_required')
    require(same(review.get('planned_rows'), 16) and same(review.get('independent_tasks'), 4)
            and same(review.get('repetitions'), 2) and same(review.get('model_seeds'), list(SEEDS)),
            'independent_review_fixed_scope_required')
    require(type(review.get('checks')) is list and review['checks']
            and all(c.get('passed') is True for c in review['checks']), 'independent_review_all_checks_pass_required')
    for key in ('additional_model_calls', 'additional_API_requests', 'additional_evaluations', 'additional_tokenizer_calls'):
        require(type(review.get(key)) is int and review[key] == 0, 'review_cannot_add_experiment_calls')
    root = Path(root).resolve()
    hashes = {}
    def bind(name):
        path = public_path(root, name)
        hashes[name] = sha(path)
        return path
    copied = collector.get('copied_source_sha256')
    required = {REPORT, SESSION, PREFLIGHT, ACTIVATION,
                *[MATERIALS + '/' + n for n in ('summary.json', 'conditions.csv', 'build_manifest.json')]}
    require(type(copied) is dict and required.issubset(copied), 'all_copied_public_artifacts_required')
    for name, value in copied.items():
        require(sha(bind(name)) == value, 'collector_copy_changed')
    report, session, summary, manifest, plan, activation = [read(bind(n)) for n in (
        REPORT, SESSION, MATERIALS + '/summary.json', MATERIALS + '/build_manifest.json', PLAN, ACTIVATION)]
    require(hashes[PLAN] == PLAN_SHA, 'fixed_plan_bytes_required')
    require(report.get('phase') == session.get('phase') == summary.get('phase') == manifest.get('phase') == 'P128'
            and plan.get('experiment') == 'P128' and same(plan.get('model_seeds'), list(SEEDS))
            and plan.get('receipt_modes') == list(MODES), 'fixed_phase_seeds_modes_required')
    require(report.get('batch_status') in ('complete', 'stopped') and report.get('owned_processes_absent') is True
            and session.get('status') == 'stopped' and session.get('owned_processes_absent') is True,
            'closed_owned_cohort_required')
    require(closure.get('audit_sha256') == hashes[REPORT] == session.get('audit_source_sha256')
            and closure.get('session_sha256') == hashes[SESSION]
            and closure.get('report_manifest_sha256') == hashes[MATERIALS + '/build_manifest.json'],
            'closure_hash_binding_differs')
    for name, value in manifest['source_sha256'].items():
        require(sha(bind(name)) == value, 'materials_source_changed')
    for name, value in manifest['artifact_sha256'].items():
        require('/' not in name and sha(bind(MATERIALS + '/' + name)) == value, 'materials_artifact_changed')
    for mapping in (activation['source_hashes'], plan['source_sha256']):
        require(type(mapping) is dict and mapping, 'frozen_source_map_required')
        for name, value in mapping.items():
            require(sha(bind(name)) == value, 'frozen_source_changed')
    require(report.get('auditor_sha256') == hashes.get(AUDITOR)
            and session.get('inspector_sha256') == hashes.get(INSPECTOR), 'auditor_inspector_source_binding')
    require(manifest.get('activation_bound_source_count') == len(activation['source_hashes'])
            and manifest.get('activation_source_mapping_sha256') == hashlib.sha256(
                json.dumps(activation['source_hashes'], sort_keys=True).encode()).hexdigest(), 'activation_source_mapping_binding')
    require(report.get('plan_sha256') == hashes[PLAN] and report.get('activation_sha256') == hashes[ACTIVATION]
            and activation.get('preflight_sha256') == hashes[PREFLIGHT], 'plan_activation_preflight_binding')
    require(session.get('pipeline_source_sha256') == report.get('pipeline_status_sha256')
            and session.get('source_sha256') == report.get('server_final_sha256'), 'pipeline_server_binding')
    # The fixed review binds original public bytes; its private paths never enter output.
    reviewed = review.get('source_hashes')
    require(type(reviewed) is dict, 'independent_review_source_bindings_required')
    for name in (REPORT, SESSION, MATERIALS + '/summary.json', MATERIALS + '/build_manifest.json'):
        matching = [v for k, v in reviewed.items() if k.endswith('/' + name)]
        require(matching and all(v == hashes[name] for v in matching), 'independent_review_public_bytes_differ')
    errors = report.get('audit_errors')
    require(type(errors) is list and same(summary.get('audit_error_count'), len(errors))
            and same(closure.get('audit_errors'), len(errors)) and same(collector.get('audit_errors'), len(errors))
            and same(review.get('audit_errors'), errors), 'audit_error_counts_disagree')
    rows, raw = summary['conditions'], report.get('rows')
    require(type(raw) is list and len(raw) == 16 and len({identity(r) for r in raw}) == 16,
            'all_sixteen_audit_rows_required')
    tasks = plan.get('known_tasks')
    require(type(tasks) is list and len(tasks) == 4, 'fixed_four_task_plan_required')
    order = [(rep, n, m) for rep in (1, 2) for n in range(1, 5)
             for m in (MODES if (rep + n) % 2 == 0 else MODES[::-1])]
    require([identity(r) for r in raw] == order, 'fixed_ordered_audit_rows_required')
    for r in raw:
        require(r['task_id'] == tasks[identity(r)[1] - 1]['task_id'], 'fixed_plan_task_identity')
    raw_index = {identity(r): r for r in raw}
    with bind(MATERIALS + '/conditions.csv').open(newline='') as handle:
        csv_rows = list(csv.DictReader(handle))
    require(len(csv_rows) == 16 and len({r.get('run_id') for r in csv_rows}) == 16, 'sixteen_csv_rows_required')
    csv_index = {r['run_id']: r for r in csv_rows}
    for row in rows:
        original, csv_row = raw_index[identity(row)], csv_index[row['run_id']]
        require(set(row) == set(csv_row) and all(csv_row[k] == ('' if v is None else str(v)) for k, v in row.items()),
                'csv_material_fields_disagree')
        for field, value in row.items():
            if field == 'exact_total_tokens' or (row['record_status'] not in ('evaluated', 'unevaluated') and field not in CORE):
                continue
            if field in (*RUNTIME_COUNTS, *RUNTIME_TIMES, *RUNTIME_FLAGS):
                wanted = (original.get('projection_runtime') or {}).get(field)
            elif field == 'receipt_snapshot_sha256':
                wanted = (original.get('receipt_disclosure') or {}).get('snapshot_sha256')
            elif field in ('receipt_disclosed_turns', 'receipt_eligible_turns'):
                wanted = (original.get('receipt_disclosure') or {}).get(field.removeprefix('receipt_'))
            elif field in RECEIPT_COUNTS and field != 'receipt_disclosures':
                wanted = (original.get('receipt_disclosure') or {}).get(field)
            else:
                wanted = original.get(field)
            require(same(value, wanted), 'audit_public_field_differs:' + field)
    data = validate_rows(rows, summary, len(errors))
    check_subset(data['audited_criteria'], report, 'audit_fixed_criteria_differs')
    check_subset(data['audited_criteria'], review['independent_criteria'], 'independent_fixed_criteria_differs')
    for key in ('all_conditions', 'by_policy', 'by_replication', 'common_success_costs_by_policy'):
        require(same(review.get(key), data[key]), 'independent_aggregate_differs:' + key)
    for key in ('planned_conditions', 'evaluated_conditions', 'known_token_subtotal', 'recorded_unknown_usage_calls',
                'unknown_usage_count_missing_conditions', 'exact_total_tokens'):
        require(same(collector.get(key), data['all_conditions'][key]), 'collector_aggregate_differs')
    require(collector.get('development_gate_met') is review.get('development_gate_met') is data['development_gate_met']
            and collector.get('audit_passed') is (not errors), 'collector_gate_differs')
    for key in ('additional_model_calls', 'additional_API_requests', 'additional_evaluations'):
        require(type(collector.get(key)) is int and collector[key] == 0, 'collector_cannot_add_experiment_calls')
    require(all(sha(public_path(root, n)) == v for n, v in hashes.items()), 'source_changed_during_load')
    return data, hashes, external


def outcome(row):
    value = 'Success' if row['success'] is True else 'Failure' if row['success'] is False else 'Not evaluated'
    if row.get('projection_contract_failed') is True or row.get('receipt_disclosure_contract_failed') is True:
        value += '\nContract stop'
    return value


def token_axis(ax):
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f'{v / 1000:,.0f}k'))
    ax.yaxis.set_major_locator(MaxNLocator(nbins=5, integer=True))
    ax.grid(axis='y', alpha=.22)
    ax.set_axisbelow(True)


def legend():
    return [Patch(facecolor=c, edgecolor='#33434b', label=label) for c, label in zip(COLORS, LABELS)] + [
        Patch(facecolor='white', edgecolor='#33434b', hatch='///', label='Official failure'),
        Line2D([], [], color='#33434b', marker='^', markerfacecolor='white', linestyle='None', label='Unknown total; known subtotal shown'),
        Line2D([], [], color='#555555', marker='x', linestyle='None', label='Missing measurement (NA)')]


def task_panel(ax, rows, seed):
    max_value = max([r['known_total_tokens'] for r in rows if count(r['known_total_tokens'])] + [1])
    for row in rows:
        _, slot, mode = identity(row)
        arm = MODES.index(mode)
        x = slot - 1 + (arm - .5) * .38
        exact, known = row['exact_total_tokens'], row['known_total_tokens']
        stopped = row['projection_contract_failed'] is True or row['receipt_disclosure_contract_failed'] is True
        if exact is not None:
            ax.bar(x, exact, width=.33, color=COLORS[arm], edgecolor='#a32e2e' if stopped else '#33434b',
                   linewidth=1.6 if stopped else .6, hatch='///' if row['success'] is False else None, zorder=3)
            if exact == 0:
                ax.plot(x, 0, marker='_', color=COLORS[arm], markersize=10, clip_on=False)
            label, y = f'{exact:,}', exact
        elif known is not None:
            ax.plot(x, known, marker='^', markersize=9, markerfacecolor='white', markeredgecolor=COLORS[arm],
                    markeredgewidth=1.7, zorder=4)
            label, y = f'Total unknown\n{known:,} known', known
        else:
            # This x is a missingness marker in the label strip, not a numerical zero.
            ax.plot(x, .025, transform=ax.get_xaxis_transform(), marker='x', color=COLORS[arm], markersize=8)
            label, y = 'NA\n' + row['record_status'].replace('_', ' '), max_value * .08
        label += '\n' + outcome(row)
        ax.annotate(label, (x, y), xytext=(0, 7), textcoords='offset points', ha='center', va='bottom',
                    fontsize=9, linespacing=1.18)
    ax.set_xticks(range(4), TASKS)
    ax.set_xlim(-.65, 3.65)
    ax.set_ylim(0, max_value * 1.65)
    ax.set_ylabel('Whole-job logical tokens')
    ax.set_title(f'Model seed {seed} — the same four known tasks', loc='left', fontsize=12)
    token_axis(ax)


def cost_panel(ax, group, common_count, title):
    groups = (group['by_policy'], group['common_success_costs_by_policy'])
    maximum = max([v['known_token_subtotal'] for g in groups for v in g.values()] + [1])
    for xgroup, values in enumerate(groups):
        for arm, mode in enumerate(MODES):
            item = values[mode]
            x = xgroup + (arm - .5) * .32
            exact = item['exact_total_tokens']
            if exact is not None:
                ax.bar(x, exact, width=.28, color=COLORS[arm], edgecolor='#33434b', linewidth=.6)
                label, y = f'{exact:,}', exact
            elif item['accounted_conditions']:
                y = item['known_token_subtotal']
                ax.plot(x, y, marker='^', markerfacecolor='white', markeredgecolor=COLORS[arm], markersize=8)
                label = f'Unknown total\n{y:,} known'
            else:
                ax.plot(x, .025, transform=ax.get_xaxis_transform(), marker='x', color=COLORS[arm], markersize=7)
                label, y = ('No common\nsuccess' if item['planned_conditions'] == 0 else 'NA'), maximum * .07
            ax.annotate(label, (x, y), xytext=(0, 32 if exact is None and item['accounted_conditions'] and arm == 0 else 5), textcoords='offset points', ha='center', fontsize=8.5)
    ax.set_xticks((0, 1), (f'All {group["by_policy"]["full"]["planned_conditions"]} pairs', f'Common success\n({common_count} pairs)'))
    ax.set_xlim(-.55, 1.55)
    ax.set_ylim(0, maximum * 1.48)
    ax.set_title(title, fontsize=11)
    ax.set_ylabel('Logical tokens')
    token_axis(ax)


def success_panel(ax, group):
    maximum = max(g['planned_conditions'] for g in group['by_policy'].values())
    for arm, mode in enumerate(MODES):
        item = group['by_policy'][mode]
        successful, evaluated, planned = (item[k] for k in ('successful_conditions', 'evaluated_conditions', 'planned_conditions'))
        if evaluated:
            ax.bar(arm, successful, width=.52, color=COLORS[arm], edgecolor='#33434b', linewidth=.6)
            if successful == 0:
                ax.plot(arm, 0, marker='_', color=COLORS[arm], markersize=12, clip_on=False)
            y = successful
            label = f'{successful} / {planned} observed successes\n{evaluated} evaluated'
            if evaluated < planned:
                label += f'; {planned - evaluated} unassessed'
        else:
            ax.plot(arm, .025, transform=ax.get_xaxis_transform(), marker='x', color=COLORS[arm], markersize=8)
            label, y = f'NA: all {planned} unassessed', maximum * .08
        ax.annotate(label, (arm, y), xytext=(0, 6), textcoords='offset points', ha='center', fontsize=8.5)
    ax.set_xticks((0, 1), LABELS, fontsize=9)
    ax.set_xlim(-.6, 1.6)
    ax.set_ylim(0, maximum * 1.38)
    ax.set_ylabel('Official successful conditions')
    ax.yaxis.set_major_locator(MaxNLocator(integer=True, nbins=5))
    ax.grid(axis='y', alpha=.22)
    ax.set_axisbelow(True)


def save(fig, path):
    for extension in ('png', 'pdf'):
        fig.savefig(path.with_suffix('.' + extension), dpi=220, metadata={'Creator': Path(__file__).name})
    plt.close(fig)


def render(data, output):
    plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 10, 'pdf.fonttype': 42, 'ps.fonttype': 42,
                         'axes.spines.top': False, 'axes.spines.right': False})
    title = 'SYNTHETIC PREVIEW — NOT P128 RESULTS' if data['synthetic'] else 'P128 — ordinary receipt disclosure calibration'
    fig, axes = plt.subplots(2, 1, figsize=(14.2, 10.8))
    for rep, ax in enumerate(axes, 1):
        task_panel(ax, [r for r in data['conditions'] if r['replication'] == rep], SEEDS[rep - 1])
    fig.suptitle(title, fontsize=17, y=.985)
    fig.legend(handles=legend(), loc='upper center', bbox_to_anchor=(.5, .951), ncol=3, frameon=False, fontsize=9)
    fig.text(.075, .024,
        'All 16 conditions retained. Logical input + output includes agent/focus, summaries, failed work, recovery and paid read_span expansion.\n'
        'Failure hatching describes the official outcome. Official success can coexist with a contract stop. Unknown totals are never drawn as zero.\n'
        'Four previously exposed tasks, repeated with seeds 57 and 157: two seeds do not create eight independent tasks. No general quality or novelty claim.',
        fontsize=9, linespacing=1.6)
    fig.subplots_adjust(left=.085, right=.98, top=.84, bottom=.14, hspace=.36)
    save(fig, output / 'p128_task_tokens_outcomes')
    fig, axes = plt.subplots(2, 3, figsize=(16.5, 9.8), gridspec_kw={'height_ratios': [1.35, 1]})
    columns = [(data['by_replication'][str(rep)], data['by_replication'][str(rep)]['common_success_task_pairs'], f'Model seed {seed}')
               for rep, seed in enumerate(SEEDS, 1)]
    columns.append((data, data['common_successful_task_seed_pairs'], 'Both fixed seeds (descriptive sum)'))
    for col, (group, common, caption) in enumerate(columns):
        cost_panel(axes[0, col], group, common, caption)
        success_panel(axes[1, col], group)
    fig.suptitle(title, fontsize=17, y=.985)
    fig.legend(handles=legend()[:2] + legend()[3:], loc='upper center', bbox_to_anchor=(.5, .947), ncol=4, frameon=False, fontsize=9)
    gate = data['audited_criteria']
    seed_gates = ', '.join(f'{s["model_seed"]}: {s["development_gate_met"]}' for s in gate['per_seed'])
    fig.text(.067, .025,
        f'Fixed development gate: {data["development_gate_met"]}. Per-seed token/quality checks: {seed_gates}. Audit errors: {data["audit_error_count"]}.\n'
        'All-task totals include failures. Common success means both modes succeeded on the same task and seed; it does not replace the all-task total.\n'
        'Success counts retain unassessed conditions. Repeated seeds are not independent tasks; sums are descriptive, not confidence intervals.\n'
        'Bytes, API/cache counts and receipt disclosures are not token savings. Overlapping time measures are not added or stacked.',
        fontsize=9, linespacing=1.5)
    fig.subplots_adjust(left=.065, right=.985, top=.85, bottom=.20, hspace=.50, wspace=.27)
    save(fig, output / 'p128_totals_success')


def synthetic_rows():
    # Handwritten, unrelated values. Includes cheap failures, unknown usage, a missing
    # condition, quality gain/loss, and official success plus a runtime contract stop.
    specifications = [
        [(120000, 0, True), (105000, 0, True), (80000, 0, True), (99000, 0, True),
         (60000, 0, False), (15000, 0, False), (132000, 1, None), (None, None, None)],
        [(110000, 0, True), (80000, 0, False), (90000, 0, False), (120000, 0, True),
         (70000, 0, True), (65000, 0, True), (90000, 0, True), (99000, 0, True)]]
    rows = []
    for rep in (1, 2):
        for n in range(1, 5):
            for arm, mode in enumerate(MODES):
                tokens, unknown, success = specifications[rep - 1][2 * (n - 1) + arm]
                row = {k: None for k in PUBLIC_FIELDS}
                row.update(replication=rep, model_seed=SEEDS[rep - 1], receipt_mode=mode,
                    run_id=f'BOC_P128_R{rep:02d}_{n:02d}_{mode.upper()}', task_id=f'SYNTHETIC_TASK_{n}',
                    projection_policy='explicit_joined_fields', checkpoint_policy='rolling_separate',
                    record_status='not_run' if tokens is None else 'unevaluated' if success is None else 'evaluated', success=success)
                if tokens is not None:
                    row.update({k: 0 for k in COUNT_FIELDS})
                    row.update({k: 0.0 for k in (*TIME_FIELDS, *RUNTIME_TIMES)})
                    row.update({k: True for k in (*RUNTIME_FLAGS, *RECEIPT_FLAGS)})
                    row.update(known_total_tokens=tokens, unknown_usage_calls=unknown,
                        exact_total_tokens=tokens if unknown == 0 else None, input_tokens=tokens - 1000,
                        output_tokens=1000, model_calls=5, api_requests=12, checkpoint_installed=False,
                        projection_contract_failed=(rep, n, mode) == (1, 2, 'disclose'),
                        receipt_disclosure_contract_failed=False, receipt_eligible_turns=4,
                        receipt_disclosed_turns=3 if arm else 0, receipt_disclosures=2 if arm else 0,
                        receipt_read_span_actions=1 if arm else 0, receipt_read_span_returned_characters=120 if arm else 0,
                        removed_receipt_UTF8_bytes=180 if arm else 0,
                        summary_sha256='0' * 64, usage_sha256='0' * 64,
                        evaluation_sha256='0' * 64 if success is not None else None, receipt_snapshot_sha256='0' * 64)
                rows.append(row)
    return rows


def synthetic_data():
    rows = synthetic_rows()
    data = validate_rows(rows, summary_for(rows, 0), 0)
    data['synthetic'] = True
    return data


def main(args):
    paths = (args.repo_root, args.closure_record, args.collector_record, args.collector_start,
             args.pipeline_start, args.independent_review)
    if args.synthetic_preview:
        require(not any(paths), 'synthetic_mode_cannot_read_actual_artifacts')
        data, hashes, external = synthetic_data(), {}, {}
    else:
        require(all(paths), 'all_closed_artifact_and_review_paths_required')
        data, hashes, external = load_closed(*paths)
    output = Path(args.output_dir).resolve()
    require(not output.exists() and not output.is_symlink(), 'new_output_directory_required')
    output.mkdir(parents=True, exist_ok=False)
    render(data, output)
    (output / 'figure_data.json').write_text(json.dumps(data, indent=2, allow_nan=False) + '\n')
    command = (f'python {Path(__file__).name} --synthetic-preview --output-dir NEW_DIRECTORY' if data['synthetic'] else
        f'python {Path(__file__).name} --repo-root CLOSED_PUBLIC_REPO --closure-record P128_closure_once_end.json '
        '--collector-record P128_report_collector_once_end.json --collector-start P128_report_collector_once_start.json '
        '--pipeline-start P128_pipeline_once_start.json --independent-review AI_P128_closed_independent_review_20261026.json '
        '--output-dir NEW_DIRECTORY')
    note = f'''# P128 scientific figures{' — SYNTHETIC PREVIEW, NOT ACTUAL RESULTS' if data['synthetic'] else ''}

Reproduce with Python {sys.version.split()[0]} and matplotlib {matplotlib.__version__}: `{command}`.
Publication revision 2 staggers adjacent unknown-total annotations. Original v01 artifacts remain unchanged; data, gates and validation are identical.
The renderer produces two standalone figures, each as PNG and vector PDF. Output directories must be new; no result or prior figure is overwritten.

The task figure has one panel per fixed model seed and retains all sixteen task/mode/seed conditions. Color identifies full receipts versus receipt disclosure. Hatching means official failure. A contract stop is explicitly labeled and can coexist with official success. Exact totals alone are bars. An open triangle means the total is unknown and is positioned at the recorded known subtotal; it is not an estimate of missing usage. The NA cross is a missingness symbol in the label strip, not a zero-valued measurement. Failed cheap cells remain visible.

The second figure separates all-task totals from the common-success subset, for each seed and a descriptive sum over the two seeds. Common success requires both modes to succeed on the same task and seed. Success bars count observed official successes; evaluated and unassessed denominators are stated. Unknown token totals and zero common-success cohorts are never imputed as zero. Input and output components also stay unknown when any usage is unknown. Cached input is never subtracted from logical input.

The fixed gate is recomputed from every row and compared with the public audit and independent closed review. Each seed must have all-task and common-success token reductions without a full-mode success loss. At least one actual paid-input disclosure on a common success and intact receipt/shared-runtime contracts are also required. A gate pass is a development result on four already exposed tasks, not a general quality, noninferiority or novelty result. Two seeds do not create eight independent tasks. Cheap failure, fewer bytes, API/cache hits and disclosure counts do not establish token savings.

All actor/focus roles, summaries, failed work, recovery and paid read_span expansion remain in whole-job cost. No time quantities are stacked or added: program, control, cell and server durations overlap. The renderer does not inspect raw prompts, reasoning, saved generated programs, task values or evaluator text, and invokes no model, task API, tokenizer or evaluator.

Actual loading requires the completed fixed collector, hash-linked closure and launch records, a PASS from the frozen independent review, stopped/absent owned process attestations, all sixteen rows, exact CSV correspondence, every frozen source hash, and row-recomputed aggregates and criteria. The review/collector certify historical owned-process absence; the renderer does not start or inspect a live server. Synthetic mode uses handwritten data only and makes no closure or measured-result claim. Only relative repository sources and metadata digests enter this output manifest; private metadata paths are not copied into it.
'''
    (output / 'README.md').write_text(note)
    if not data['synthetic']:
        require(all(sha(public_path(Path(args.repo_root).resolve(), n)) == v for n, v in hashes.items()), 'source_changed_during_render')
    manifest = dict(phase='P128', presentation_revision=2,
        presentation_change='Stagger adjacent unknown-total labels; all data, gates and validation unchanged.',
        original_renderer_sha256='138058a0c5f55d03201c877110c676fe5ec683aa7c518fb7692b8d1ede0994d9',
        synthetic_preview=data['synthetic'], actual_results=not data['synthetic'],
        source_sha256=hashes, closure_collector_review_sha256=external, renderer_sha256=sha(__file__),
        fixed_execution_head=HEAD, fixed_plan_sha256=PLAN_SHA, fixed_independent_review_source_sha256=REVIEW_SHA,
        python_version=sys.version.split()[0], matplotlib_version=matplotlib.__version__,
        artifact_sha256={p.name: sha(p) for p in sorted(output.iterdir())}, all_sixteen_slots_retained=True,
        independent_tasks=4, repetitions=2, model_seeds=list(SEEDS), unknown_is_not_zero=True,
        closed_and_independently_reviewed_public_artifacts_verified=not data['synthetic'],
        general_quality_preservation_claim=False, novel_method_claim=False,
        additional_model_API_evaluator_tokenizer_calls=0, saved_program_execution=0, outcome_based_selection=False)
    (output / 'output_manifest.json').write_text(json.dumps(manifest, indent=2, allow_nan=False) + '\n')
    return dict(synthetic=data['synthetic'], conditions=16, output_directory=str(output))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo-root', type=Path)
    parser.add_argument('--closure-record', type=Path)
    parser.add_argument('--collector-record', type=Path)
    parser.add_argument('--collector-start', type=Path)
    parser.add_argument('--pipeline-start', type=Path)
    parser.add_argument('--independent-review', type=Path)
    parser.add_argument('--synthetic-preview', action='store_true')
    parser.add_argument('--output-dir', type=Path, required=True)
    print(json.dumps(main(parser.parse_args())))
