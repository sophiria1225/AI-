"""Standalone P129 closed-only figures, or an explicitly synthetic preview.

Only public aggregate artifacts are read, after completed collector and frozen
independent-review gates. No model, API, tokenizer, evaluator or saved program
is executed. This is ordinary output-grounding calibration, not a novelty claim.
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

HEAD = '35640e5a447f99f182293e6e26033b25c640061c'
PLAN_SHA = 'f2d546c56b568b3c8b11a2b785ec10b6c93c5f8dea9b3d9a9395c677d091168f'
COLLECTOR_SHA = 'c54da2c69f4e1dd0e274ae05d4178bdb9d188804b24b1ab756b601f61ce408a3'
LAUNCHER_SHA = '707e8cc679d515d8a1932a13cd5e4464e1ff5d958afbfe705d626b6b68f8880f'
REVIEW_SHA = 'b13f72b316ceed6a4c5f5bf6a6d2fd9f56fec8ac23b6217bd04bea8e0b67ab20'
MODES = ('off', 'feedback', 'repair')
LABELS = ('Off', 'Feedback', 'Repair')
SEEDS = (57, 157)
COLORS = ('#777777', '#4477AA', '#228877')
MATERIALS = 'materials/20261026_p129_results'
REPORT = 'reports/P129_comparison.json'
SESSION = 'reports/P129_server_session.json'
PLAN = 'configs/P129_whole_task_output_grounding_v01.json'
ACTIVATION = 'reports/P129_activation_v01.json'
PREFLIGHT = 'reports/P129_initial_checks.json'
AUDITOR = 'scripts/audit_whole_task_output_grounding.py'
INSPECTOR = 'scripts/inspect_whole_task_output_grounding_session.py'
STATUSES = ('evaluated', 'unevaluated', 'not_run', 'incomplete_worker', 'audit_error')
CORE = ('replication', 'model_seed', 'grounding_mode', 'run_id', 'task_id', 'projection_policy',
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
GROUNDING_COUNTS = ('grounding_write_checks', 'grounding_feedback_blocks', 'grounding_repair_attempts',
    'grounding_sent_repairs', 'grounding_repairs', 'grounding_incomplete_write_records', 'grounding_pending_notices')
GROUNDING_TIMES = ('grounding_wall_seconds',)
GROUNDING_FLAGS = ('grounding_contract_failed', 'grounding_accounting_complete')
COUNT_FIELDS = ('model_calls', 'known_total_tokens', 'unknown_usage_calls', 'api_requests',
                'input_tokens', 'output_tokens', 'cached_input_tokens', 'projection_hits')
PUBLIC_FIELDS = (*CORE, 'stop_reason', *COUNT_FIELDS, 'exact_total_tokens', *TIME_FIELDS,
    'checkpoint_installed', 'checkpoint_opportunity', 'checkpoint_installations', 'projection_contract_failed',
    *RUNTIME_COUNTS, *RUNTIME_TIMES, *RUNTIME_FLAGS, *GROUNDING_COUNTS, *GROUNDING_FLAGS,
    *GROUNDING_TIMES, 'grounding_ledger_sha256', 'summary_sha256', 'usage_sha256', 'evaluation_sha256')


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


def aggregate(rows):
    known = [r for r in rows if count(r.get('known_total_tokens'))]
    unknown_known = [r['unknown_usage_calls'] for r in rows if count(r.get('unknown_usage_calls'))]
    exact = bool(rows) and len(known) == len(rows) and len(unknown_known) == len(rows) and not sum(unknown_known)
    measures = {}
    for key in ('api_requests', 'model_calls', 'input_tokens', 'output_tokens',
                'cached_input_tokens', *TIME_FIELDS, *RUNTIME_COUNTS, *RUNTIME_TIMES, *GROUNDING_COUNTS, *GROUNDING_TIMES):
        values = [r[key] for r in rows if number(r.get(key))]
        complete = bool(rows) and len(values) == len(rows)
        if key in ('input_tokens', 'output_tokens', 'cached_input_tokens'):
            complete &= exact
        if key in GROUNDING_COUNTS + GROUNDING_TIMES:
            complete &= all(r.get('grounding_accounting_complete') is True for r in rows)
        if key.startswith('known_control_') or key == 'control_wall_seconds_including_backend':
            complete &= all(r.get('control_accounting_complete') is True for r in rows)
        if key in ('known_schema_reply_wire_bytes', 'schema_deliveries'):
            complete &= all(r.get('schema_accounting_complete') is True for r in rows)
        measures[key] = {'known_subtotal': sum(values), 'reported_conditions': len(values),
                         'exact_all_condition_total': sum(values) if complete else None}
    return {'planned_conditions': len(rows), 'accounted_conditions': len(known),
        'evaluated_conditions': sum(r.get('record_status') == 'evaluated' for r in rows),
        'successful_conditions': sum(r.get('success') is True for r in rows),
        'known_token_subtotal': sum(r['known_total_tokens'] for r in known),
        'recorded_unknown_usage_calls': sum(unknown_known),
        'unknown_usage_count_missing_conditions': len(rows) - len(unknown_known),
        'exact_total_tokens': sum(r['known_total_tokens'] for r in known) if exact else None,
        'all_condition_usage_known': exact, 'measures': measures}


def comparison_groups(rows, comparison, baseline, *, replication=None):
    """Keep quality transitions separate; neither gains nor cheap failures are savings."""
    pairs = [p for p in comparison['paired_results']
             if replication is None or p['replication'] == replication]
    conditions = [r for r in rows if r['grounding_mode'] in (baseline, 'repair')
                  and (replication is None or r['replication'] == replication)]
    classes = {'common_success': [], 'quality_gain': [], 'quality_loss': [],
               'both_failed': [], 'not_both_evaluated': []}
    for pair in pairs:
        key = ('not_both_evaluated' if not pair['both_evaluated'] else
               'common_success' if pair['both_successful'] else
               'quality_gain' if pair['success_gained'] else
               'quality_loss' if pair['success_lost'] else 'both_failed')
        classes[key].append((pair['replication'], pair['task_id']))
    return dict(baseline=baseline, planned_pairs=len(pairs),
        all_pairs_by_policy={mode: aggregate([r for r in conditions if r['grounding_mode'] == mode])
                             for mode in (baseline, 'repair')},
        outcome_groups={label: dict(pairs=len(keys), by_policy={mode: aggregate([
            r for r in conditions if r['grounding_mode'] == mode
            and (r['replication'], r['task_id']) in keys]) for mode in (baseline, 'repair')})
            for label, keys in classes.items()})



def identity(row):
    match = re.fullmatch(r'BOC_P129_R0([12])_01_(OFF|FEEDBACK|REPAIR)', row['run_id'])
    require(match is not None, 'fixed_six_slot_identity_required')
    rep, mode = int(match[1]), match[2].lower()
    require(type(row['replication']) is int and row['replication'] == rep
        and type(row['model_seed']) is int and row['model_seed'] == SEEDS[rep - 1]
        and row['grounding_mode'] == mode, 'fixed_seed_replication_mode_required')
    return rep, mode


def criteria(rows, error_count):
    index = {identity(r): r for r in rows}
    complete = all(r['record_status'] == 'evaluated' and type(r['success']) is bool
        and count(r['known_total_tokens']) and type(r['unknown_usage_calls']) is int
        and r['unknown_usage_calls'] == 0 for r in rows)
    comparisons = {}
    for baseline in ('feedback', 'off'):
        pairs = []
        for rep, seed in enumerate(SEEDS, 1):
            a, b = index[rep, baseline], index[rep, 'repair']
            evaluated = all(r['record_status'] == 'evaluated' and type(r['success']) is bool for r in (a, b))
            known = evaluated and all(count(r['known_total_tokens']) and type(r['unknown_usage_calls']) is int
                                      and r['unknown_usage_calls'] == 0 for r in (a, b))
            pairs.append(dict(replication=rep, model_seed=seed, task_id=a['task_id'], baseline=baseline,
                both_evaluated=evaluated, both_usage_known=known, baseline_success=a['success'], repair_success=b['success'],
                success_lost=a['success'] and not b['success'] if evaluated else None,
                success_gained=b['success'] and not a['success'] if evaluated else None,
                both_successful=a['success'] and b['success'] if evaluated else None,
                repair_minus_baseline_tokens=b['known_total_tokens'] - a['known_total_tokens'] if known else None))
        evaluated = all(p['both_evaluated'] for p in pairs)
        known = all(p['both_usage_known'] for p in pairs)
        common = [p for p in pairs if p['both_successful']]
        comparisons[baseline] = dict(paired_results=pairs,
            paired_success_losses=sum(p['success_lost'] for p in pairs) if evaluated else None,
            paired_success_gains=sum(p['success_gained'] for p in pairs) if evaluated else None,
            paired_successful_task_seed_pairs=len(common) if evaluated else None,
            repair_minus_baseline_whole_task_tokens=sum(p['repair_minus_baseline_tokens'] for p in pairs) if known else None,
            paired_successful_token_difference=sum(p['repair_minus_baseline_tokens'] for p in common) if known else None,
            both_failed_token_difference=sum(p['repair_minus_baseline_tokens'] for p in pairs if p['both_evaluated']
                and not p['baseline_success'] and not p['repair_success']) if known else None,
            every_seed_tokens_lower=all(p['repair_minus_baseline_tokens'] < 0 for p in pairs) if known else None)
    primary = comparisons['feedback']
    counts = [index[p['replication'], 'repair']['grounding_repairs'] for p in primary['paired_results'] if p['both_successful']]
    repairs = sum(counts) if counts and all(count(v) for v in counts) else None
    intact = all(r.get(k) is False for r in rows for k in ('grounding_contract_failed', 'projection_contract_failed'))
    intact &= all(r.get('grounding_accounting_complete') is True for r in rows)
    gate = bool(complete and not error_count and intact and repairs is not None and repairs > 0
        and all(c['paired_success_losses'] == 0 for c in comparisons.values())
        and primary['paired_successful_task_seed_pairs'] > 0
        and primary['repair_minus_baseline_whole_task_tokens'] < 0
        and primary['paired_successful_token_difference'] < 0)
    return dict(all_six_complete_with_known_usage=complete, comparisons=comparisons,
        paired_results=primary['paired_results'], paired_success_losses=primary['paired_success_losses'],
        paired_successful_token_difference=primary['paired_successful_token_difference'],
        repair_minus_feedback_whole_task_tokens=primary['repair_minus_baseline_whole_task_tokens'],
        successful_repairs_on_primary_common_success=repairs, mechanism_contracts_intact=bool(intact),
        development_gate_met=gate, planned_rows=6, independent_tasks=1, repetitions=2, model_seeds=list(SEEDS),
        prior_results_pooled=False, general_quality_preservation_claim=False, novel_method_claim=False)


def summary_for(rows, errors):
    computed = criteria(rows, errors)
    return dict(phase='P129', all_conditions=aggregate(rows),
        by_policy={m: aggregate([r for r in rows if r['grounding_mode'] == m]) for m in MODES},
        primary_baseline='feedback', auxiliary_baseline='off',
        comparison_costs={b: comparison_groups(rows, computed['comparisons'][b], b) for b in ('feedback', 'off')},
        by_replication={str(rep): dict(model_seed=SEEDS[rep - 1],
            all_conditions=aggregate([r for r in rows if r['replication'] == rep]),
            by_policy={m: aggregate([r for r in rows if r['replication'] == rep and r['grounding_mode'] == m]) for m in MODES},
            comparisons={b: comparison_groups(rows, computed['comparisons'][b], b, replication=rep) for b in ('feedback', 'off')})
            for rep in (1, 2)}, independent_tasks=1, repetitions=2, model_seeds=list(SEEDS),
        audited_criteria=computed, audit_error_count=errors, conditions=rows, unknown_usage_is_not_zero=True,
        general_quality_preservation_claim=False, novel_method_claim=False)


def check_subset(expected, given, reason):
    require(type(given) is dict, reason)
    for key, value in expected.items():
        require(key in given and same(value, given[key]), reason + ':' + key)


def validate_rows(rows, summary, error_count):
    require(count(error_count), 'audit_error_count_required')
    require(type(rows) is list and len(rows) == 6 and {identity(r) for r in rows} ==
            {(rep, mode) for rep in (1, 2) for mode in MODES}, 'all_six_unique_slots_required')
    require(all(type(r['task_id']) is str for r in rows) and len({r['task_id'] for r in rows}) == 1,
            'same_one_known_CSV_task_required')
    for row in rows:
        require(set(row) == set(PUBLIC_FIELDS), 'fixed_public_field_allowlist_required')
        status = row['record_status']
        require(status in STATUSES, 'known_status_required')
        require(type(row['success']) is bool if status == 'evaluated' else row['success'] is None,
                'official_success_status_disagrees')
        require(row['projection_policy'] == 'explicit_joined_fields' and row['checkpoint_policy'] == 'rolling_separate',
                'shared_runtime_and_checkpoint_required')
        if status not in ('evaluated', 'unevaluated'):
            require(all(v is None for k, v in row.items() if k not in CORE), 'missing_slot_cannot_gain_measurements')
            continue
        require(all(count(row[k]) for k in COUNT_FIELDS if k not in ('cached_input_tokens', 'projection_hits')),
                'known_subtotals_and_attempt_counts_required')
        for field in (*COUNT_FIELDS, 'exact_total_tokens', 'checkpoint_opportunity', 'checkpoint_installations', *RUNTIME_COUNTS, *GROUNDING_COUNTS):
            require(row[field] is None or count(row[field]), 'count_or_null:' + field)
        for field in (*TIME_FIELDS, *RUNTIME_TIMES, *GROUNDING_TIMES):
            require(row[field] is None or number(row[field]), 'finite_duration_or_null:' + field)
        for field in ('projection_contract_failed', 'checkpoint_installed', *RUNTIME_FLAGS, *GROUNDING_FLAGS):
            require(row[field] is None or type(row[field]) is bool, 'boolean_or_null:' + field)
        require(row['input_tokens'] + row['output_tokens'] == row['known_total_tokens']
                and row['unknown_usage_calls'] <= row['model_calls'], 'token_subtotal_or_attempt_count_differs')
        require(same(row['exact_total_tokens'], row['known_total_tokens'] if row['unknown_usage_calls'] == 0 else None),
                'unknown_usage_is_not_exact')
        if row['cached_input_tokens'] is not None:
            require(row['cached_input_tokens'] <= row['input_tokens'], 'cached_input_exceeds_input')
        require(all(count(row[k]) for k in GROUNDING_COUNTS)
                and row['grounding_repairs'] <= row['grounding_sent_repairs'] <= row['grounding_repair_attempts'] <= row['grounding_write_checks']
                and all(row[k] <= row['grounding_write_checks'] for k in ('grounding_feedback_blocks', 'grounding_incomplete_write_records', 'grounding_pending_notices')),
                'strict_repair_sent_proposal_conservation')
        require(row['grounding_mode'] == 'repair' or row['grounding_repair_attempts'] == 0,
                'repair_counts_only_in_repair_mode')
        require(row['grounding_mode'] == 'feedback' or row['grounding_feedback_blocks'] == 0,
                'unsent_feedback_only_in_feedback_mode')
        require(row['projection_hits'] in (None, 0) and row['automatic_region_partial_hits'] in (None, 0),
                'automatic_region_disabled')
        require(type(row['grounding_contract_failed']) is bool
                and row['grounding_accounting_complete'] is bool(not row['grounding_contract_failed']
                    and row['grounding_incomplete_write_records'] == 0 and row['grounding_pending_notices'] == 0),
                'grounding_accounting_flags_disagree')
    computed = summary_for(rows, error_count)
    for key in ('phase', 'all_conditions', 'by_policy', 'comparison_costs', 'by_replication', 'primary_baseline',
                'auxiliary_baseline', 'independent_tasks', 'repetitions', 'model_seeds', 'audit_error_count'):
        require(same(summary.get(key), computed[key]), 'row_derived_summary_differs:' + key)
    check_subset(computed['audited_criteria'], summary['audited_criteria'], 'fixed_criteria_differs')
    require(summary.get('unknown_usage_is_not_zero') is True and summary.get('general_quality_preservation_claim') is False
            and summary.get('novel_method_claim') is False, 'conservative_scope_required')
    return dict(computed, synthetic=False, development_gate_met=computed['audited_criteria']['development_gate_met'])


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
    require(review.get('status') == 'pass' and review.get('phase') == 'P129_closed_independent_review'
            and review.get('fixed_head') == HEAD and review.get('plan_sha256') == PLAN_SHA
            and review.get('review_script_sha256') == REVIEW_SHA
            and review.get('collector_complete_seen_before_trial_read') is True
            and review.get('collector_end_sha256') == external['collector'], 'fixed_independent_review_pass_required')
    require(same(review.get('planned_rows'), 6) and same(review.get('independent_tasks'), 1)
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
    require(report.get('phase') == session.get('phase') == summary.get('phase') == manifest.get('phase') == 'P129'
            and plan.get('experiment') == 'P129' and same(plan.get('model_seeds'), list(SEEDS))
            and plan.get('grounding_modes') == list(MODES), 'fixed_phase_seeds_modes_required')
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
    require(type(raw) is list and len(raw) == 6 and len({identity(r) for r in raw}) == 6,
            'all_six_audit_rows_required')
    tasks = plan.get('known_tasks')
    require(type(tasks) is list and len(tasks) == 1, 'fixed_one_task_plan_required')
    order = [(rep, m) for rep in (1, 2) for m in (MODES if rep == 1 else MODES[::-1])]
    require([identity(r) for r in raw] == order, 'fixed_ordered_audit_rows_required')
    for r in raw:
        require(r['task_id'] == tasks[0]['task_id'], 'fixed_plan_task_identity')
    raw_index = {identity(r): r for r in raw}
    with bind(MATERIALS + '/conditions.csv').open(newline='') as handle:
        csv_rows = list(csv.DictReader(handle))
    require(len(csv_rows) == 6 and len({r.get('run_id') for r in csv_rows}) == 6, 'six_csv_rows_required')
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
            else:
                wanted = original.get(field)
            require(same(value, wanted), 'audit_public_field_differs:' + field)
    data = validate_rows(rows, summary, len(errors))
    check_subset(data['audited_criteria'], report, 'audit_fixed_criteria_differs')
    check_subset(data['audited_criteria'], review['independent_criteria'], 'independent_fixed_criteria_differs')
    for key in ('all_conditions', 'by_policy', 'by_replication', 'comparison_costs'):
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
    if row.get('projection_contract_failed') is True or row.get('grounding_contract_failed') is True:
        value += '\nContract stop'
    return value


def token_axis(ax):
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f'{v / 1000:,.0f}k'))
    ax.yaxis.set_major_locator(MaxNLocator(nbins=5, integer=True))
    ax.grid(axis='y', alpha=.22)
    ax.set_axisbelow(True)


def legend():
    return [Patch(facecolor=c, edgecolor='#33434b', label=label) for c, label in zip(COLORS, LABELS)] + [
        Patch(facecolor='white', edgecolor='#33434b', hatch='///', label='Official task failure'),
        Line2D([], [], color='#33434b', marker='^', markerfacecolor='white', linestyle='None', label='Unknown total; known subtotal'),
        Line2D([], [], color='#555555', marker='x', linestyle='None', label='Missing measurement (NA)')]


def task_panel(ax, rows, seed):
    maximum = max([r['known_total_tokens'] for r in rows if count(r['known_total_tokens'])] + [1])
    for row in rows:
        arm = MODES.index(row['grounding_mode'])
        exact, known = row['exact_total_tokens'], row['known_total_tokens']
        stopped = row['projection_contract_failed'] is True or row['grounding_contract_failed'] is True
        if exact is not None:
            ax.bar(arm, exact, width=.55, color=COLORS[arm], edgecolor='#a32e2e' if stopped else '#33434b',
                   linewidth=1.7 if stopped else .6, hatch='///' if row['success'] is False else None, zorder=3)
            if exact == 0:
                ax.plot(arm, 0, marker='_', color=COLORS[arm], markersize=10, clip_on=False)
            label, y = f'{exact:,}', exact
        elif known is not None:
            ax.plot(arm, known, marker='^', markersize=9, markerfacecolor='white', markeredgecolor=COLORS[arm],
                    markeredgewidth=1.7, zorder=4)
            label, y = f'Total unknown\n{known:,} known', known
        else:
            ax.plot(arm, .025, transform=ax.get_xaxis_transform(), marker='x', color=COLORS[arm], markersize=8)
            label, y = 'NA\n' + row['record_status'].replace('_', ' '), maximum * .08
        ax.annotate(label + '\n' + outcome(row), (arm, y), xytext=(0, 7), textcoords='offset points',
                    ha='center', va='bottom', fontsize=9, linespacing=1.18)
    ax.set_xticks(range(3), LABELS)
    ax.set_xlim(-.65, 2.65)
    ax.set_ylim(0, maximum * 1.65)
    ax.set_ylabel('Whole-job logical tokens')
    ax.set_title(f'Model seed {seed}: the same known CSV task', loc='left', fontsize=11)
    token_axis(ax)


def cost_panel(ax, comparison, title):
    baseline = comparison['baseline']
    modes = (baseline, 'repair')
    common = comparison['outcome_groups']['common_success']
    groups = (comparison['all_pairs_by_policy'], common['by_policy'])
    maximum = max([v['known_token_subtotal'] for g in groups for v in g.values()] + [1])
    for xgroup, values in enumerate(groups):
        for arm, mode in enumerate(modes):
            item = values[mode]
            x = xgroup + (arm - .5) * .36
            color = COLORS[MODES.index(mode)]
            exact = item['exact_total_tokens']
            if exact is not None:
                ax.bar(x, exact, width=.3, color=color, edgecolor='#33434b', linewidth=.6)
                if exact == 0:
                    ax.plot(x, 0, marker='_', color=color, markersize=10, clip_on=False)
                label, y = f'{exact:,}', exact
            elif item['accounted_conditions']:
                y = item['known_token_subtotal']
                ax.plot(x, y, marker='^', markerfacecolor='white', markeredgecolor=color, markersize=8)
                label = f'Unknown total\n{y:,} known'
            else:
                ax.plot(x, .025, transform=ax.get_xaxis_transform(), marker='x', color=color, markersize=7)
                label, y = ('No common\nsuccess' if item['planned_conditions'] == 0 else 'NA'), maximum * .07
            ax.annotate(label, (x, y), xytext=(0, 5), textcoords='offset points', ha='center', fontsize=8.5)
    ax.set_xticks((0, 1), (f'All {comparison["planned_pairs"]} task-seed pairs', f'Common success\n({common["pairs"]} pairs)'))
    ax.set_xlim(-.57, 1.57)
    ax.set_ylim(0, maximum * 1.5)
    ax.set_title(title, loc='left', fontsize=11)
    ax.set_ylabel('Logical tokens')
    token_axis(ax)
    classes = comparison['outcome_groups']
    ax.text(.5, -.27, 'Pairs: ' + ', '.join(f'{label} {classes[key]["pairs"]}' for key, label in
        [('quality_gain', 'gain'), ('quality_loss', 'loss'), ('both_failed', 'both failed'), ('not_both_evaluated', 'unassessed')]),
        transform=ax.transAxes, ha='center', fontsize=8.5)


MECHANISMS = ('grounding_feedback_blocks', 'grounding_repair_attempts', 'grounding_sent_repairs', 'grounding_repairs')
MECHANISM_LABELS = ('Unsent feedback blocks', 'Repair proposals', 'Content-changing sent repairs', 'Strict successful repairs')
MECHANISM_COLORS = ('#CCBB44', '#AA66AA', '#4477AA', '#228877')


def mechanism_panel(ax, rows, seed):
    maximum = max([r[k] for r in rows for k in MECHANISMS if count(r.get(k))] + [1])
    for row in rows:
        mode = MODES.index(row['grounding_mode'])
        for j, key in enumerate(MECHANISMS):
            x = mode + (j - 1.5) * .19
            value = row[key]
            color = MECHANISM_COLORS[j]
            if value is None:
                ax.plot(x, .025, transform=ax.get_xaxis_transform(), marker='x', color=color, markersize=7)
                label, y = 'NA', maximum * .075
            elif row['grounding_accounting_complete'] is not True:
                ax.plot(x, value, marker='^', markerfacecolor='white', markeredgecolor=color, markersize=8)
                label, y = f'{value}\nknown', value
            else:
                ax.bar(x, value, width=.16, color=color, edgecolor='#33434b', linewidth=.5)
                if value == 0:
                    ax.plot(x, 0, marker='_', color=color, markersize=7, clip_on=False)
                label, y = str(value), value
            ax.annotate(label, (x, y), xytext=(0, 5), textcoords='offset points', ha='center', fontsize=9)
    ax.set_xticks(range(3), LABELS)
    ax.set_xlim(-.6, 2.6)
    ax.set_ylim(0, maximum * 1.48)
    ax.set_title(f'Model seed {seed}', loc='left', fontsize=12)
    ax.set_ylabel('Recorded mechanism events')
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
    title = 'SYNTHETIC PREVIEW — NOT P129 RESULTS' if data['synthetic'] else 'P129 — ordinary output-grounding calibration'
    fig, axes = plt.subplots(2, 2, figsize=(14.3, 11.8))
    for rep in (1, 2):
        task_panel(axes[0, rep - 1], [r for r in data['conditions'] if r['replication'] == rep], SEEDS[rep - 1])
    cost_panel(axes[1, 0], data['comparison_costs']['feedback'], 'Primary: feedback versus repair (both seeds)')
    cost_panel(axes[1, 1], data['comparison_costs']['off'], 'Auxiliary: off versus repair (both seeds)')
    fig.suptitle(title, fontsize=17, y=.985)
    fig.legend(handles=legend(), loc='upper center', bbox_to_anchor=(.5, .949), ncol=3, frameon=False, fontsize=9)
    successes = '; '.join(f'{LABELS[i]} {data["by_policy"][m]["successful_conditions"]}/2 observed successes, '
        f'{2 - data["by_policy"][m]["evaluated_conditions"]} unassessed' for i, m in enumerate(MODES))
    fig.text(.07, .019,
        f'{successes}.\nFixed development gate: {data["development_gate_met"]}; audit errors: {data["audit_error_count"]}. '
        'One previously exposed CSV task, two fixed seeds: not two independent tasks.\n'
        'All six conditions retained. Logical input + output includes actor/focus, summaries, failed work, notices and recovery; cached input is not subtracted.\n'
        'Cheap failures and quality gains are distinct from same-success cost reduction. Official success can coexist with a contract stop.\n'
        'Unknown totals are never zero. Common success requires both compared modes to succeed on the same task and seed. No general quality or novelty claim.',
        fontsize=8.5, linespacing=1.6)
    fig.subplots_adjust(left=.078, right=.98, top=.84, bottom=.22, hspace=.54, wspace=.26)
    save(fig, output / 'p129_tokens_quality')
    fig, axes = plt.subplots(1, 2, figsize=(14.3, 6.7))
    for rep, ax in enumerate(axes, 1):
        mechanism_panel(ax, [r for r in data['conditions'] if r['replication'] == rep], SEEDS[rep - 1])
    fig.suptitle(title, fontsize=17, y=.98)
    handles = [Patch(facecolor=c, edgecolor='#33434b', label=label) for c, label in zip(MECHANISM_COLORS, MECHANISM_LABELS)]
    fig.legend(handles=handles, loc='upper center', bbox_to_anchor=(.5, .915), ncol=2, frameon=False, fontsize=9)
    fig.text(.07, .028,
        'Proposals, sent repairs and strict successful repairs are nested counts; they are shown separately and must not be added.\n'
        'Strict success requires changed content, an actual send, a typed successful return and public-monitor backup support. It is not official task success.\n'
        'Feedback blocks are unsent actions. Incomplete accounting uses an open triangle at the known subtotal; missing measurements use NA, never zero.\n'
        'Counts, API/cache hits and reply bytes do not establish token savings. Overlapping times are not added. One known task; no novelty claim.',
        fontsize=9, linespacing=1.6)
    fig.subplots_adjust(left=.075, right=.98, top=.72, bottom=.29, wspace=.25)
    save(fig, output / 'p129_mechanism_counts')


def synthetic_rows():
    specifications = [(120000, 0, True), (110000, 0, True), (95000, 0, True),
                      (100000, 1, None), (15000, 0, False), (None, None, None)]
    rows = []
    for rep in (1, 2):
        for arm, mode in enumerate(MODES):
            tokens, unknown, success = specifications[(rep - 1) * 3 + arm]
            row = {k: None for k in PUBLIC_FIELDS}
            row.update(replication=rep, model_seed=SEEDS[rep - 1], grounding_mode=mode,
                run_id=f'BOC_P129_R{rep:02d}_01_{mode.upper()}', task_id='SYNTHETIC_CSV_TASK',
                projection_policy='explicit_joined_fields', checkpoint_policy='rolling_separate',
                record_status='not_run' if tokens is None else 'unevaluated' if success is None else 'evaluated', success=success)
            if tokens is not None:
                row.update({k: 0 for k in (*COUNT_FIELDS, *RUNTIME_COUNTS, *GROUNDING_COUNTS)})
                row.update({k: 0.0 for k in (*TIME_FIELDS, *RUNTIME_TIMES, *GROUNDING_TIMES)})
                row.update({k: True for k in RUNTIME_FLAGS})
                row.update(known_total_tokens=tokens, unknown_usage_calls=unknown,
                    exact_total_tokens=tokens if unknown == 0 else None, input_tokens=tokens - 1000,
                    output_tokens=1000, model_calls=5, api_requests=12, checkpoint_installed=False,
                    projection_contract_failed=(rep, mode) == (1, 'repair'),
                    grounding_contract_failed=False, grounding_accounting_complete=True,
                    grounding_write_checks=4, grounding_feedback_blocks=2 if mode == 'feedback' else 0,
                    grounding_repair_attempts=3 if mode == 'repair' else 0,
                    grounding_sent_repairs=2 if mode == 'repair' else 0,
                    grounding_repairs=1 if mode == 'repair' else 0,
                    summary_sha256='0' * 64, usage_sha256='0' * 64,
                    evaluation_sha256='0' * 64 if success is not None else None, grounding_ledger_sha256='0' * 64)
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
        f'python {Path(__file__).name} --repo-root CLOSED_PUBLIC_REPO --closure-record P129_closure_once_end.json '
        '--collector-record P129_report_collector_once_end.json --collector-start P129_report_collector_once_start.json '
        '--pipeline-start P129_pipeline_once_start.json --independent-review AI_P129_closed_independent_review_20261026.json '
        '--output-dir NEW_DIRECTORY')
    note = f'''# P129 scientific figures{' — SYNTHETIC PREVIEW, NOT ACTUAL RESULTS' if data['synthetic'] else ''}

Reproduce with Python {sys.version.split()[0]} and matplotlib {matplotlib.__version__}: `{command}`.
Two standalone figures are saved as PNG and vector PDF. A new output directory is required.

The first figure retains all six conditions of one previously exposed CSV task, three modes and seeds 57/157. Feedback versus repair is primary; off is the auxiliary quality control. Two seeds are not two independent tasks. Failure hatching is the official task outcome; a contract stop is explicitly labeled even with official success. Exact logical token totals alone are bars. An open triangle is positioned at the known subtotal when the total is unknown. NA crosses are missingness symbols, not zero measurements. Aggregate all-pair and common-success costs are separate; quality gains, quality losses, both failures and unassessed pairs are counted separately. Success counts and evaluated denominators are retained.

The second figure separates unsent feedback blocks, repair proposals, content-changing sent repairs, and strict successful repairs. These are nested counts and are not stacked or added. Strict success requires an actual changed-content send, a typed successful return and public-monitor backup support; it is distinct from official task success. Unknown mechanism accounting is shown as a known subtotal, not an exact total. Ordinary cache/explicit-field reuse is shared and is not counted as CSV repair.

The fixed development gate requires all six official evaluations and fully known costs, no success loss against either baseline, lower aggregate and nonempty common-success whole-job tokens versus feedback, actual strict repair activity on primary common success, and intact runtime/grounding contracts. Each seed's result is shown, but lower tokens in each individual seed is not an added gate. Neither a cheap failure nor quality gain establishes same-success cost reduction. This calibration does not establish general quality preservation or method novelty.

Whole-job logical input plus output includes actor/focus roles, summaries, failed work, notices, repairs and recovery. Cached input is not subtracted. Unknown usage keeps nested input/output/cached exact totals null. Bytes and API counts do not establish token savings. Overlapping program/control/grounding/server times are not added.

Actual loading requires completed fixed collector, hash-linked closure/launch records, frozen independent-review PASS, stopped/absent owned-process attestations, six unique fixed cells, matching CSV/public audit bytes, frozen source hashes, and independently row-recomputed aggregates/criteria. The historical absence of owned processes is certified by those closed records; this renderer does not inspect or launch live processes. It never reads prompts, reasoning, generated programs, CSV values or evaluator text, and calls no model, task API, tokenizer or evaluator. Synthetic mode uses handwritten data only. Only relative repository source names and metadata hashes are exported; private metadata paths are not copied.
'''
    (output / 'README.md').write_text(note)
    if not data['synthetic']:
        require(all(sha(public_path(Path(args.repo_root).resolve(), n)) == v for n, v in hashes.items()), 'source_changed_during_render')
    manifest = dict(phase='P129', synthetic_preview=data['synthetic'], actual_results=not data['synthetic'],
        source_sha256=hashes, closure_collector_review_sha256=external, renderer_sha256=sha(__file__),
        fixed_execution_head=HEAD, fixed_plan_sha256=PLAN_SHA, fixed_independent_review_source_sha256=REVIEW_SHA,
        python_version=sys.version.split()[0], matplotlib_version=matplotlib.__version__,
        artifact_sha256={p.name: sha(p) for p in sorted(output.iterdir())}, all_six_slots_retained=True,
        independent_tasks=1, repetitions=2, model_seeds=list(SEEDS), unknown_is_not_zero=True,
        primary_baseline='feedback', auxiliary_baseline='off',
        closed_and_independently_reviewed_public_artifacts_verified=not data['synthetic'],
        general_quality_preservation_claim=False, novel_method_claim=False,
        additional_model_API_evaluator_tokenizer_calls=0, saved_program_execution=0, outcome_based_selection=False)
    (output / 'output_manifest.json').write_text(json.dumps(manifest, indent=2, allow_nan=False) + '\n')
    return dict(synthetic=data['synthetic'], conditions=6, output_directory=str(output))


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
