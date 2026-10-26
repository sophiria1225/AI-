"""Publish all four audited P130 slots, without reading private task records.

Missing usage remains missing. This is a deterministic reporting step, never an
experiment, a new success judgement, or a conversion of API/byte savings to tokens.
"""
import argparse
import csv
import ctypes
import errno
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile

from whole_task_checkpoint_inventory import MODES as POLICIES, SEEDS, cell_id, run_order, summarize


ROOT = Path(__file__).resolve().parents[1]
TARGET = 'materials/20261026_p130_results'
AUDIT = 'reports/P130_comparison.json'
SESSION = 'reports/P130_server_session.json'
PLAN = 'configs/P130_whole_task_checkpoint_inventory_v01.json'
ACTIVATION = 'reports/P130_activation_v01.json'
PREFLIGHT = 'reports/P130_initial_checks.json'
BUILDER = 'scripts/build_p130_report.py'
AUDITOR = 'scripts/audit_whole_task_checkpoint_inventory.py'
INSPECTOR = 'scripts/summarize_p130_session.py'
HELPER = 'scripts/whole_task_checkpoint_inventory.py'
COUNT_FIELDS = ('model_calls', 'known_total_tokens', 'unknown_usage_calls', 'api_requests',
                'input_tokens', 'output_tokens', 'cached_input_tokens', 'projection_hits')
TIME_FIELDS = ('setup_wall_seconds', 'wall_seconds', 'cleanup_wall_seconds', 'full_wall_seconds')
RUNTIME_COUNTS = ('program_attempts', 'program_evidence_records', 'static_eligible_programs',
    'transformed_programs', 'ordinary_complete_cache_hits', 'projection_lookup_requests',
    'projection_partial_hits', 'projection_complete_lookup_hits', 'projection_lookup_misses',
    'projection_failure_events', 'explicit_field_requests', 'explicit_field_partial_hits',
    'automatic_region_partial_hits', 'known_control_requests', 'known_control_request_bytes',
    'known_control_reply_bytes', 'schema_deliveries', 'known_schema_reply_wire_bytes')
RUNTIME_TIMES = ('program_wall_seconds', 'control_wall_seconds_including_backend',
                 'projection_lookup_wall_seconds')
RUNTIME_FLAGS = ('control_accounting_complete', 'schema_accounting_complete', 'execution_trace_accounting_complete')
GROUNDING_COUNTS = ('grounding_write_checks', 'grounding_feedback_blocks',
    'grounding_repair_attempts', 'grounding_sent_repairs', 'grounding_repairs',
    'grounding_incomplete_write_records', 'grounding_pending_notices')
GROUNDING_FLAGS = ('grounding_contract_failed', 'grounding_accounting_complete')
GROUNDING_TIMES = ('grounding_wall_seconds',)
GROUNDING_MAP = dict(grounding_write_checks='write_checks',
    grounding_feedback_blocks='feedback_blocks', grounding_repair_attempts='repair_attempts',
    grounding_sent_repairs='grounding_sent_repairs', grounding_repairs='grounding_repairs',
    grounding_incomplete_write_records='incomplete_write_records',
    grounding_pending_notices='pending_notices', grounding_wall_seconds='wall_seconds',
    grounding_ledger_sha256='ledger_sha256')
INVENTORY_COUNTS = ('inventory_notice_actor_calls', 'inventory_captures',
    'inventory_request_bytes', 'inventory_response_bytes')
INVENTORY_FLAGS = ('inventory_contract_failed', 'inventory_accounting_complete')
INVENTORY_TIMES = ('inventory_capture_wall_seconds',)
FIELDS = ('replication', 'model_seed', 'inventory_mode', 'grounding_mode', 'run_id', 'task_id', 'projection_policy', 'checkpoint_policy', 'record_status',
          'success', 'stop_reason', *COUNT_FIELDS, 'exact_total_tokens', *TIME_FIELDS,
          'checkpoint_installed', 'checkpoint_opportunity', 'checkpoint_installations', 'projection_contract_failed',
          *RUNTIME_COUNTS, *RUNTIME_TIMES, *RUNTIME_FLAGS,
          *GROUNDING_COUNTS, *GROUNDING_FLAGS, *GROUNDING_TIMES, 'grounding_ledger_sha256',
          *INVENTORY_COUNTS, *INVENTORY_FLAGS, *INVENTORY_TIMES,
          'summary_sha256', 'usage_sha256', 'evaluation_sha256')
STATUSES = {'evaluated', 'unevaluated', 'not_run', 'incomplete_worker', 'audit_error'}
SESSION_MEASURES = ('wall_seconds', 'load_wall_seconds', 'pipeline_wall_seconds',
    'evaluation_wall_seconds', 'cell_full_wall_seconds', 'idle_recovery_seconds',
    'known_evaluation_wall_seconds', 'unknown_evaluation_wall_count',
    'known_idle_recovery_seconds', 'unknown_idle_recovery_count',
    'known_cell_full_wall_seconds', 'unknown_cell_full_wall_count',
    'batch_other_wall_seconds', 'sampled_peak_rss_bytes', 'peak_system_swap_bytes',
    'baseline_system_swap_bytes', 'evaluations_completed', 'evaluation_attempts_measured',
    'memory_sample_count', 'missing_rss_samples', 'missing_swap_samples',
    'observed_rss_peak_or_null', 'observed_swap_peak_or_null')


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def integer(value):
    return type(value) is int and value >= 0


def number(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def valid_hash(value):
    return type(value) is str and bool(re.fullmatch('[0-9a-f]{64}', value))


def sha(path):
    path = Path(path)
    require(path.is_file() and not path.is_symlink() and path.stat().st_size <= 64 * 1024 * 1024,
            'bounded_regular_public_source_required')
    return hashlib.sha256(path.read_bytes()).hexdigest()


def public_path(root, name):
    require(type(name) is str and name.split('/')[0] in ('scripts', 'tests', 'configs', 'docs', 'reports')
            and not Path(name).is_absolute() and '..' not in Path(name).parts,
            'repository_public_source_path_required')
    path = root / name
    require(path.resolve().is_relative_to(root), 'public_source_escapes_repository')
    return path


def public_row(row):
    status = row.get('record_status')
    require(status in STATUSES, 'known_record_status_required')
    require(type(row.get('success')) is bool if status == 'evaluated' else row.get('success') is None,
            'evaluation_status_and_success_disagree')
    result = {key: None for key in FIELDS}
    for key in ('replication', 'model_seed', 'inventory_mode', 'grounding_mode', 'run_id', 'task_id', 'projection_policy', 'checkpoint_policy', 'record_status', 'success'):
        result[key] = row[key]
    require(type(row['replication']) is int and row['replication'] in (1, 2)
            and type(row['model_seed']) is int and row['model_seed'] == SEEDS[row['replication'] - 1]
            and row['inventory_mode'] in POLICIES and row['grounding_mode'] == 'feedback'
            and row['projection_policy'] == 'explicit_joined_fields',
            'fixed_inventory_mode_replication_seed_common_feedback_required')
    if status not in ('evaluated', 'unevaluated'):
        require(all(row.get(k) is None for k in (
            *COUNT_FIELDS, *TIME_FIELDS, 'projection_contract_failed',
            *GROUNDING_COUNTS, *GROUNDING_FLAGS, *GROUNDING_TIMES,
            *INVENTORY_COUNTS, *INVENTORY_FLAGS, *INVENTORY_TIMES)),
            'unaccounted_condition_cannot_gain_measurements')
        return result
    require(all(integer(row.get(k)) for k in COUNT_FIELDS if k not in ('cached_input_tokens', 'projection_hits')),
            'accounted_condition_requires_known_subtotal_and_attempt_counts')
    require(row['input_tokens'] + row['output_tokens'] == row['known_total_tokens']
            and row['unknown_usage_calls'] <= row['model_calls'], 'token_subtotal_or_attempt_count_differs')
    require(row.get('cached_input_tokens') is None or integer(row['cached_input_tokens'])
            and row['cached_input_tokens'] <= row['input_tokens'], 'invalid_cached_input_measurement')
    require(all(number(row.get(k)) for k in TIME_FIELDS), 'finite_task_durations_required')
    require(row.get('projection_contract_failed') is None or type(row['projection_contract_failed']) is bool,
            'explicit_contract_failure_flag_or_unstarted_runtime_required')
    require(row.get('projection_hits') is None or integer(row['projection_hits']), 'invalid_projection_hit_count')
    require(type(row.get('checkpoint_installed')) is bool, 'explicit_checkpoint_flag_required')
    opportunities = row.get('checkpoint_opportunity')
    require(integer(opportunities) and opportunities <= 3, 'bounded_rolling_opportunity_count_required')
    result['checkpoint_opportunity'] = opportunities
    for key in ('stop_reason',):
        value = row.get(key)
        require(value is None or type(value) is str and bool(re.fullmatch('[a-z][a-z0-9_]*', value)),
                'public_controller_status_only')
        result[key] = value
    require(integer(row.get('checkpoint_installations'))
            and row['checkpoint_installations'] <= opportunities
            and row['checkpoint_installed'] == (row['checkpoint_installations'] > 0),
            'rolling_checkpoint_installation_count_required')
    result['checkpoint_installations'] = row['checkpoint_installations']
    for key in COUNT_FIELDS + TIME_FIELDS + ('projection_contract_failed', 'checkpoint_installed'):
        result[key] = row[key]
    result['exact_total_tokens'] = row['known_total_tokens'] if row['unknown_usage_calls'] == 0 else None
    runtime = row.get('projection_runtime')
    if runtime is None:
        require(row['projection_hits'] is None and row['projection_contract_failed'] is None,
                'unstarted_runtime_has_no_mechanism_measurement')
    else:
        require(type(runtime) is dict and runtime.get('policy') == row['projection_policy']
                and type(row['projection_contract_failed']) is bool
                and runtime.get('projection_failed') is row['projection_contract_failed']
                and runtime.get('projection_partial_hits') == row['projection_hits']
                and runtime.get('automatic_region_partial_hits') == row['projection_hits']
                and runtime.get('explicit_field_interface_shared_between_policies') is True
                and runtime.get('joined_provider_shared_between_policies') is True, 'runtime_and_public_fields_disagree')
        require(all(integer(runtime.get(k)) for k in RUNTIME_COUNTS)
                and all(number(runtime.get(k)) for k in RUNTIME_TIMES)
                and all(type(runtime.get(k)) is bool for k in RUNTIME_FLAGS), 'runtime_cost_fields_required')
        require(runtime['projection_lookup_requests'] == sum(runtime[k] for k in (
            'projection_partial_hits', 'projection_complete_lookup_hits', 'projection_lookup_misses'))
            and runtime['transformed_programs'] <= runtime['program_attempts']
            and runtime['program_evidence_records'] <= runtime['program_attempts']
            and runtime['explicit_field_partial_hits'] <= runtime['explicit_field_requests'], 'runtime_count_conservation_failed')
        for key in RUNTIME_COUNTS + RUNTIME_TIMES + RUNTIME_FLAGS:
            result[key] = runtime[key]
    require(all(integer(row.get(k)) for k in GROUNDING_COUNTS)
            and all(type(row.get(k)) is bool for k in GROUNDING_FLAGS)
            and all(number(row.get(k)) for k in GROUNDING_TIMES),
            'audited_grounding_measurements_required')
    require(row['grounding_repairs'] <= row['grounding_sent_repairs']
            <= row['grounding_repair_attempts'] <= row['grounding_write_checks']
            and row['grounding_feedback_blocks'] <= row['grounding_write_checks']
            and row['grounding_incomplete_write_records'] <= row['grounding_write_checks']
            and row['grounding_pending_notices'] <= row['grounding_write_checks'],
            'grounding_count_conservation_failed')
    require((row['grounding_mode'] == 'repair' or row['grounding_repair_attempts'] == 0)
            and (row['grounding_mode'] == 'feedback' or row['grounding_feedback_blocks'] == 0),
            'grounding_mode_and_interventions_disagree')
    require(valid_hash(row.get('grounding_ledger_sha256')), 'bound_grounding_ledger_required')
    grounding = row.get('grounding_runtime')
    require(type(grounding) is dict and grounding.get('mode') == row['grounding_mode']
            and type(grounding.get('contract_intact')) is bool
            and all(row[k] == grounding.get(v) for k, v in GROUNDING_MAP.items())
            and row['grounding_contract_failed'] is (not grounding['contract_intact'])
            and row['grounding_accounting_complete'] is bool(grounding['contract_intact']
                and grounding['incomplete_write_records'] == 0 and grounding['pending_notices'] == 0),
            'grounding_runtime_and_public_fields_disagree')
    result.update({k: row[k] for k in GROUNDING_COUNTS + GROUNDING_FLAGS + GROUNDING_TIMES
                   + ('grounding_ledger_sha256',)})
    inventory = row.get('inventory_runtime')
    if inventory is None:
        require(all(row.get(k) is None for k in INVENTORY_COUNTS + INVENTORY_FLAGS + INVENTORY_TIMES),
                'unstarted_inventory_has_no_measurements')
    else:
        require(type(inventory) is dict and inventory.get('mode') == row['inventory_mode']
                and all(integer(row.get(k)) for k in INVENTORY_COUNTS)
                and all(type(row.get(k)) is bool for k in INVENTORY_FLAGS)
                and all(number(row.get(k)) for k in INVENTORY_TIMES), 'audited_inventory_measurements_required')
        capture = inventory.get('capture')
        require(type(capture) is dict and type(inventory.get('contract_failed')) is bool
                and type(capture.get('capture_accounting_complete')) is bool
                and row['inventory_contract_failed'] is inventory['contract_failed']
                and row['inventory_accounting_complete'] is bool(not inventory['contract_failed']
                    and capture['capture_accounting_complete']), 'inventory_contract_flags_disagree')
        require(row['inventory_notice_actor_calls'] == inventory.get('actual_inventory_exposures')
                and row['inventory_captures'] == capture.get('captures')
                and row['inventory_request_bytes'] == capture.get('known_request_bytes')
                and row['inventory_response_bytes'] == capture.get('known_response_bytes')
                and row['inventory_capture_wall_seconds'] == capture.get('capture_wall_seconds'),
                'inventory_runtime_and_public_costs_disagree')
        require(integer(capture.get('successful_captures'))
                and integer(inventory.get('dispatched_actor_views'))
                and row['inventory_notice_actor_calls'] <= capture['successful_captures'] <= row['inventory_captures']
                <= row['checkpoint_installations'] <= 3
                and row['inventory_notice_actor_calls'] <= inventory['dispatched_actor_views']
                and row['inventory_capture_wall_seconds'] <= row['wall_seconds']
                and (row['inventory_mode'] != 'off' or row['inventory_notice_actor_calls'] == 0),
                'inventory_activity_requires_capture_and_actual_actor_dispatch')
        require(inventory.get('raw_archive_unchanged') is True
                and inventory.get('focus_requests_unchanged') is True
                and inventory.get('all_model_roles_and_inventory_input_share_budget') is True
                and inventory.get('disclosure_activity_requires_actual_dispatch') is True
                and capture.get('values_disclosed') is False
                and capture.get('scalar_lengths_disclosed') is False
                and capture.get('environment_API_requests') == 0 and type(capture.get('environment_API_requests')) is int
                and capture.get('model_calls') == 0 and type(capture.get('model_calls')) is int,
                'inventory_scope_or_shared_cost_contract_changed')
        result.update({k:row[k] for k in INVENTORY_COUNTS + INVENTORY_FLAGS + INVENTORY_TIMES})
    for key in ('summary_sha256', 'usage_sha256', 'evaluation_sha256'):

        value = row.get(key)
        require(valid_hash(value) if key != 'evaluation_sha256' or status == 'evaluated' else value is None,
                'audited_row_hash_required')
        result[key] = value
    return result


def aggregate(rows):
    known = [r for r in rows if integer(r.get('known_total_tokens'))]
    unknown_known = [r['unknown_usage_calls'] for r in rows if integer(r.get('unknown_usage_calls'))]
    exact = bool(rows) and len(known) == len(rows) and len(unknown_known) == len(rows) and not sum(unknown_known)
    measures = {}
    for key in ('api_requests', 'model_calls', 'input_tokens', 'output_tokens',
                'cached_input_tokens', *TIME_FIELDS, *RUNTIME_COUNTS, *RUNTIME_TIMES, *GROUNDING_COUNTS, *GROUNDING_TIMES,
                *INVENTORY_COUNTS, *INVENTORY_TIMES):
        values = [r[key] for r in rows if number(r.get(key))]
        complete = bool(rows) and len(values) == len(rows)
        if key in ('input_tokens', 'output_tokens', 'cached_input_tokens'):
            complete &= exact
        if key in INVENTORY_COUNTS + INVENTORY_TIMES:
            complete &= all(r.get('inventory_accounting_complete') is True for r in rows)
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


def comparison_groups(rows, comparison, *, replication=None):
    """Keep all quality transitions; gains and cheap failures are not common-success savings."""
    pairs = [p for p in comparison['paired_results']
             if replication is None or p['replication'] == replication]
    conditions = [r for r in rows if replication is None or r['replication'] == replication]
    classes = {'common_success': [], 'quality_gain': [], 'quality_loss': [],
               'both_failed': [], 'not_both_evaluated': []}
    for pair in pairs:
        key = ('not_both_evaluated' if not pair['both_evaluated'] else
               'common_success' if pair['both_successful'] else
               'quality_gain' if pair['success_gained'] else
               'quality_loss' if pair['success_lost'] else 'both_failed')
        classes[key].append((pair['replication'], pair['task_id']))
    return dict(baseline='off', treatment='checkpoint_inventory', planned_pairs=len(pairs),
        all_pairs_by_policy={mode: aggregate([r for r in conditions if r['inventory_mode'] == mode])
                             for mode in POLICIES},
        outcome_groups={label: dict(pairs=len(keys), by_policy={mode: aggregate([
            r for r in conditions if r['inventory_mode'] == mode
            and (r['replication'], r['task_id']) in keys]) for mode in POLICIES})
            for label, keys in classes.items()})


README = '''# P130: 全4条件の監査済み集計

既知CSV課題1件 × off/checkpoint_inventory × 固定seed57/157を全件保持する。両条件に同じfeedback検査、explicit joined fields、通常cache、full compact receipts、rolling checkpointを使う。accepted checkpoint直後の同じinventory取得を両条件に課し、表示条件だけ次のactor入力へ1回加える。通常inventoryの限定的な有用性比較であり、新規機構・一般的品質維持・提示時機の優越を主張しない。

全役割の論理input+output、要約、失敗、通知と回復を含める。cached inputは差し引かない。unknown/nullを0に置換せず、input/output/cachedのexact totalもunknown usageがあればnull。全体、seed、共通成功・品質改善・品質損失・両失敗・未評価を分ける。品質改善を同じ成功の費用削減と読み替えない。

inventory_notice_actor_callsはinventoryを含む実dispatch済みactor入力数であり、snapshot作成やtokenizer計数だけでは増えない。paid unknown dispatchも露出として残すが、費用不明のため採用gateは通らない。capture件数、host wall、request/reply bytesは別に示し、取得や保存の不完全性を0補完しない。metadataは固定trusted collectorの返答と境界hashから監査する。保存Pythonを再実行して値を独立証明したものではない。

grounding feedbackは両条件共通で、repairは無効。unsent feedback、actual API結果、公式task success、inventory/grounding/projectionの契約状態を別に残す。固定gateは全4評価・既知費用、offからの成功損失なし、全体および非空の共通成功費用減、共通成功上の実inventory露出、全機構契約の維持を必要とする。seed別差を示すが各seed費用減を追加条件にはしない。

control bytesはmodel tokensではない。work/program/control/capture/groundingとserver/cell/evaluation時間は重なるため加算しない。raw binding names、値、prompt/reasoning/code、CSV、認証値、private pathは公開しない。

[全条件](conditions.csv)／[集計](summary.json)／[hash](build_manifest.json)／[監査](../../reports/P130_comparison.json)／[server](../../reports/P130_server_session.json)。
''' 


def publish_directory(staging, target):
    """Atomic directory publication that refuses even an existing empty target."""
    library = ctypes.CDLL(None, use_errno=True)
    if sys.platform == 'darwin':
        rename = library.renamex_np
        rename.argtypes = (ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint)
        result = rename(os.fsencode(staging), os.fsencode(target), 0x00000004)  # RENAME_EXCL
    elif sys.platform.startswith('linux') and hasattr(library, 'renameat2'):
        rename = library.renameat2
        rename.argtypes = (ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint)
        result = rename(-100, os.fsencode(staging), -100, os.fsencode(target), 1)  # RENAME_NOREPLACE
    else:
        raise OSError(errno.ENOSYS, 'atomic exclusive directory publication unavailable')
    if result:
        code = ctypes.get_errno()
        raise OSError(code, os.strerror(code), str(target))


def build(root):
    root = Path(root).resolve()
    require(root == ROOT.resolve(), 'executing_repository_root_must_match')
    target = root / TARGET
    if target.exists() or target.is_symlink():
        raise FileExistsError('preserve_all_P130_materials')
    source_hashes = {}
    def load(name):
        path = public_path(root, name)
        source_hashes[name] = sha(path)
        value = json.loads(path.read_text())
        require(type(value) is dict, 'public_record_object_required')
        return value
    report, session, plan, activation = (load(name) for name in (AUDIT, SESSION, PLAN, ACTIVATION))
    for name in (PREFLIGHT, BUILDER, AUDITOR, INSPECTOR, HELPER):
        source_hashes[name] = sha(public_path(root, name))
    require(report.get('phase') == session.get('phase') == plan.get('experiment') == 'P130'
            and report.get('batch_status') in ('complete', 'stopped')
            and report.get('owned_processes_absent') is True and session.get('owned_processes_absent') is True
            and session.get('status') == 'stopped', 'closed_audited_P130_records_required')
    require(session.get('audit_source_sha256') == source_hashes[AUDIT]
            and report.get('plan_sha256') == source_hashes[PLAN]
            and report.get('activation_sha256') == source_hashes[ACTIVATION]
            and report.get('auditor_sha256') == source_hashes[AUDITOR]
            and session.get('inspector_sha256') == source_hashes[INSPECTOR]
            and activation.get('preflight_sha256') == source_hashes[PREFLIGHT], 'report_session_source_binding_differs')
    require(valid_hash(report.get('pipeline_status_sha256')) and valid_hash(report.get('server_final_sha256'))
            and session.get('pipeline_source_sha256') == report['pipeline_status_sha256']
            and session.get('source_sha256') == report['server_final_sha256'], 'pipeline_server_binding_differs')
    frozen = activation.get('source_hashes')
    require(type(frozen) is dict and all(name in frozen for name in (BUILDER, AUDITOR, INSPECTOR, HELPER)),
            'frozen_reporting_and_auditing_sources_required')
    for mapping in (frozen, plan.get('source_sha256')):
        require(type(mapping) is dict and mapping, 'frozen_public_source_map_required')
        for name, expected in mapping.items():
            require(valid_hash(expected) and sha(public_path(root, name)) == expected, 'frozen_public_source_changed')
    tasks = plan.get('known_tasks')
    require(type(tasks) is list and len(tasks) == 1 and plan.get('inventory_modes') == list(POLICIES) and plan.get('grounding_mode') == 'feedback' and plan.get('model_seeds') == list(SEEDS),
            'fixed_one_task_two_inventory_modes_required')
    expected = [(cell_id(rep, n, p), tasks[n - 1]['task_id'], p, rep, SEEDS[rep - 1])
                for rep, n, p in run_order()]
    raw_rows = report.get('rows')
    require(type(raw_rows) is list and [(r.get('run_id'), r.get('task_id'), r.get('inventory_mode'), r.get('replication'), r.get('model_seed'))
            for r in raw_rows] == expected, 'all_four_ordered_slots_required')
    require(all(r.get('checkpoint_policy') == 'rolling_separate' for r in raw_rows), 'same_checkpoint_required')
    errors = report.get('audit_errors')
    require(type(errors) is list, 'audit_error_list_required')
    criteria = summarize(raw_rows, errors)
    require(all(key in report and report[key] == value for key, value in criteria.items()),
            'audited_criteria_or_claims_differ_from_rows')
    rows = [public_row(row) for row in raw_rows]
    comparison_costs = comparison_groups(rows, criteria)
    server_measures = {}
    for key in SESSION_MEASURES:
        value = session.get(key)
        require(value is None or number(value), 'invalid_server_measurement')
        server_measures[key] = value
    summary = {'phase': 'P130', 'all_conditions': aggregate(rows),
        'by_policy': {p: aggregate([r for r in rows if r['inventory_mode'] == p]) for p in POLICIES},
        'primary_baseline': 'off', 'treatment': 'checkpoint_inventory', 'shared_grounding_mode': 'feedback',
        'comparison_costs': comparison_costs,
        'by_replication': {str(rep): dict(model_seed=SEEDS[rep - 1],
            all_conditions=aggregate([r for r in rows if r['replication'] == rep]),
            by_policy={p: aggregate([r for r in rows if r['replication'] == rep
                                    and r['inventory_mode'] == p]) for p in POLICIES},
            comparison_costs=comparison_groups(rows, criteria, replication=rep)) for rep in (1, 2)},
        'independent_tasks': 1, 'repetitions': 2, 'model_seeds': list(SEEDS),
        'audited_criteria': criteria, 'audit_error_count': len(errors), 'conditions': rows,
        'server_measures': server_measures, 'unknown_usage_is_not_zero': True,
        'cost_scope': 'All roles, failed work, control, recovery and checkpoint costs stay in the audited whole-job ledger.',
        'time_scope': 'Work, program, lookup and control durations overlap; server time includes cells and evaluation. Do not add these measures.',
        'byte_scope': 'Control bytes are interpreter-host traffic, not model input tokens.',
        'general_quality_preservation_claim': False, 'novel_method_claim': False,
        'timing_superiority_claim': False, 'inventory_capture_metadata_recomputed_from_program_values': False,
        'manuscript_changed': False, 'private_task_values_or_program_text_published': False}
    parent = target.parent
    parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix='.p130-materials-', dir=parent))
    try:
        with (staging / 'conditions.csv').open('x', newline='') as handle:
            writer = csv.DictWriter(handle, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerows(rows)
        (staging / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
        (staging / 'README.md').write_text(README)
        manifest = {'phase': 'P130', 'source_sha256': source_hashes,
            'activation_bound_source_count': len(frozen),
            'activation_source_mapping_sha256': hashlib.sha256(json.dumps(frozen, sort_keys=True).encode()).hexdigest(),
            'artifact_sha256': {p.name: sha(p) for p in sorted(staging.iterdir())},
            'new_model_calls': 0, 'new_API_requests': 0, 'new_tokenizer_calls': 0, 'new_evaluations': 0,
            'atomic_exclusive_directory_publication': True}
        (staging / 'build_manifest.json').write_text(json.dumps(manifest, indent=2, allow_nan=False) + '\n')
        require(all(sha(public_path(root, name)) == value for name, value in {**frozen, **source_hashes}.items()),
                'public_source_changed_during_build')
        publish_directory(staging, target)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--repo-root', type=Path, default=ROOT)
    print(json.dumps(build(parser.parse_args().repo_root), ensure_ascii=False))
