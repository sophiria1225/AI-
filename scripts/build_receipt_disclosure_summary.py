"""Publish all sixteen audited P128 slots, without reading private task records.

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

from whole_task_receipt_disclosure import MODES as POLICIES, SEEDS, cell_id, run_order, summarize


ROOT = Path(__file__).resolve().parents[1]
TARGET = 'materials/20261026_p128_results'
AUDIT = 'reports/P128_comparison.json'
SESSION = 'reports/P128_server_session.json'
PLAN = 'configs/P128_whole_task_receipt_disclosure_v01.json'
ACTIVATION = 'reports/P128_activation_v01.json'
PREFLIGHT = 'reports/P128_initial_checks.json'
BUILDER = 'scripts/build_receipt_disclosure_summary.py'
AUDITOR = 'scripts/audit_whole_task_receipt_disclosure.py'
INSPECTOR = 'scripts/inspect_whole_task_receipt_disclosure_session.py'
HELPER = 'scripts/whole_task_receipt_disclosure.py'
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
RECEIPT_COUNTS = ('receipt_disclosures', 'receipt_disclosed_turns', 'receipt_eligible_turns', 'receipt_read_span_actions',
    'receipt_read_span_returned_characters', 'removed_receipt_UTF8_bytes')
RECEIPT_FLAGS = ('receipt_disclosure_contract_failed', 'receipt_disclosure_contract_intact',
                 'receipt_disclosure_audit_complete')
FIELDS = ('replication', 'model_seed', 'receipt_mode', 'run_id', 'task_id', 'projection_policy', 'checkpoint_policy', 'record_status',
          'success', 'stop_reason', *COUNT_FIELDS, 'exact_total_tokens', *TIME_FIELDS,
          'checkpoint_installed', 'checkpoint_opportunity', 'checkpoint_installations', 'projection_contract_failed',
          *RUNTIME_COUNTS, *RUNTIME_TIMES, *RUNTIME_FLAGS,
          *RECEIPT_COUNTS, *RECEIPT_FLAGS, 'receipt_snapshot_sha256',
          'summary_sha256', 'usage_sha256', 'evaluation_sha256')
STATUSES = {'evaluated', 'unevaluated', 'not_run', 'incomplete_worker', 'audit_error'}
SESSION_MEASURES = ('wall_seconds', 'load_wall_seconds', 'pipeline_wall_seconds',
    'evaluation_wall_seconds', 'cell_full_wall_seconds', 'idle_recovery_seconds',
    'known_evaluation_wall_seconds', 'unknown_evaluation_wall_count',
    'known_idle_recovery_seconds', 'unknown_idle_recovery_count',
    'known_cell_full_wall_seconds', 'unknown_cell_full_wall_count',
    'batch_other_wall_seconds', 'sampled_peak_rss_bytes', 'peak_system_swap_bytes',
    'baseline_system_swap_bytes', 'evaluations_completed', 'evaluation_attempts_measured')


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
    for key in ('replication', 'model_seed', 'receipt_mode', 'run_id', 'task_id', 'projection_policy', 'checkpoint_policy', 'record_status', 'success'):
        result[key] = row[key]
    require(type(row['replication']) is int and row['replication'] in (1, 2)
            and type(row['model_seed']) is int and row['model_seed'] == SEEDS[row['replication'] - 1]
            and row['receipt_mode'] in POLICIES and row['projection_policy'] == 'explicit_joined_fields',
            'fixed_receipt_mode_replication_seed_runtime_required')
    if status not in ('evaluated', 'unevaluated'):
        require(all(row.get(k) is None for k in (
            'known_total_tokens', 'unknown_usage_calls', 'projection_hits', 'projection_contract_failed',
            'receipt_disclosures', 'receipt_disclosure_contract_failed')),
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
    require(integer(row.get('checkpoint_installations')), 'rolling_checkpoint_installation_count_required')
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
    receipt = row.get('receipt_disclosure')
    require(type(receipt) is dict and receipt.get('mode') == row['receipt_mode']
            and receipt.get('disclosure_contract_intact') is True
            and receipt.get('sidecar_complete') is True,
            'audited_complete_receipt_sidecar_required')
    receipt_values = dict(receipt_disclosures=row.get('receipt_disclosures'),
        receipt_disclosed_turns=receipt.get('disclosed_turns'),
        receipt_eligible_turns=receipt.get('eligible_turns'),
        receipt_read_span_actions=receipt.get('receipt_read_span_actions'),
        receipt_read_span_returned_characters=receipt.get('receipt_read_span_returned_characters'),
        removed_receipt_UTF8_bytes=receipt.get('removed_receipt_UTF8_bytes'))
    require(all(integer(v) for v in receipt_values.values())
            and receipt_values['receipt_disclosures'] <= receipt_values['receipt_disclosed_turns']
            and receipt_values['receipt_disclosed_turns'] <= receipt_values['receipt_eligible_turns']
            and receipt_values['receipt_eligible_turns'] <= receipt.get('closed_turns', -1)
            and (row['receipt_mode'] != 'full' or receipt_values['receipt_disclosed_turns'] == 0)
            and row.get('receipt_disclosed_turns') == receipt_values['receipt_disclosed_turns']
            and row.get('receipt_disclosure_contract_failed') is False
            and row.get('receipt_disclosure_contract_intact') is True
            and row.get('receipt_disclosure_audit_complete') is True,
            'receipt_counts_flags_or_mode_disagree')
    require(valid_hash(receipt.get('snapshot_sha256')), 'bound_receipt_snapshot_required')
    result.update(receipt_values)
    result.update({k: row[k] for k in RECEIPT_FLAGS})
    result['receipt_snapshot_sha256'] = receipt['snapshot_sha256']
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
                'cached_input_tokens', *TIME_FIELDS, *RUNTIME_COUNTS, *RUNTIME_TIMES, *RECEIPT_COUNTS):
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
        raise FileExistsError('preserve_all_P128_materials')
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
    require(report.get('phase') == session.get('phase') == plan.get('experiment') == 'P128'
            and report.get('batch_status') in ('complete', 'stopped')
            and report.get('owned_processes_absent') is True and session.get('owned_processes_absent') is True
            and session.get('status') == 'stopped', 'closed_audited_P128_records_required')
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
    require(type(tasks) is list and len(tasks) == 4 and plan.get('receipt_modes') == list(POLICIES) and plan.get('model_seeds') == list(SEEDS),
            'fixed_four_tasks_two_policies_required')
    expected = [(cell_id(rep, n, p), tasks[n - 1]['task_id'], p, rep, SEEDS[rep - 1])
                for rep, n, p in run_order()]
    raw_rows = report.get('rows')
    require(type(raw_rows) is list and [(r.get('run_id'), r.get('task_id'), r.get('receipt_mode'), r.get('replication'), r.get('model_seed'))
            for r in raw_rows] == expected, 'all_sixteen_ordered_slots_required')
    require(all(r.get('checkpoint_policy') == 'rolling_separate' for r in raw_rows), 'same_checkpoint_required')
    errors = report.get('audit_errors')
    require(type(errors) is list, 'audit_error_list_required')
    criteria = summarize(raw_rows, errors)
    require(all(key in report and report[key] == value for key, value in criteria.items()),
            'audited_criteria_or_claims_differ_from_rows')
    rows = [public_row(row) for row in raw_rows]
    common = {(pair['replication'], pair['task_id']) for pair in criteria['paired_results']
              if pair['both_successful'] is True}
    server_measures = {}
    for key in SESSION_MEASURES:
        value = session.get(key)
        require(value is None or number(value), 'invalid_server_measurement')
        server_measures[key] = value
    summary = {'phase': 'P128', 'all_conditions': aggregate(rows),
        'by_policy': {p: aggregate([r for r in rows if r['receipt_mode'] == p]) for p in POLICIES},
        'common_successful_task_seed_pairs': len(common),
        'common_success_costs_by_policy': {p: aggregate([r for r in rows
            if r['receipt_mode'] == p and (r['replication'], r['task_id']) in common]) for p in POLICIES},
        'by_replication': {str(rep): dict(model_seed=SEEDS[rep - 1],
            all_conditions=aggregate([r for r in rows if r['replication'] == rep]),
            by_policy={p: aggregate([r for r in rows if r['replication'] == rep and r['receipt_mode'] == p]) for p in POLICIES},
            common_success_task_pairs=sum(key[0] == rep for key in common),
            common_success_costs_by_policy={p: aggregate([r for r in rows if r['replication'] == rep
                and r['receipt_mode'] == p and (rep, r['task_id']) in common]) for p in POLICIES})
            for rep in (1, 2)},
        'independent_tasks': 4, 'repetitions': 2, 'model_seeds': list(SEEDS),
        'audited_criteria': criteria, 'audit_error_count': len(errors), 'conditions': rows,
        'server_measures': server_measures, 'unknown_usage_is_not_zero': True,
        'cost_scope': 'All roles, failed work, control, recovery and checkpoint costs stay in the audited whole-job ledger.',
        'time_scope': 'Work, program, lookup and control durations overlap; server time includes cells and evaluation. Do not add these measures.',
        'byte_scope': 'Control bytes are interpreter-host traffic, not model input tokens.',
        'general_quality_preservation_claim': False, 'novel_method_claim': False,
        'manuscript_changed': False, 'private_task_values_or_program_text_published': False}
    parent = target.parent
    parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix='.p128-materials-', dir=parent))
    try:
        with (staging / 'conditions.csv').open('x', newline='') as handle:
            writer = csv.DictWriter(handle, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerows(rows)
        (staging / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
        (staging / 'README.md').write_text('''# P128: 全16条件の監査済み集計

既知4課題 × full/disclose × 固定seed57/157の全枠を残す。2seedは独立課題数を増やさない。共通guide・join/明示field/完全cache・rolling separateを維持し、自動region変換は無効。通常receipt開示の効率校正であり新規手法の成立ではない。

全jobのagent/focus・要約・失敗・修復・明示read_span再取得を含むtokenを使用する。whole cohort、seed別、同seed共通成功の費用は別集計。cheap failureは品質維持した削減ではない。unknown/nullを0補完しない。input/output/cachedのexact component totalもunknown usageがあればnull。cached inputをlogical inputから差し引かない。

receipt_disclosuresは実dispatchしたagent/focus入力へ露出した固有receipt数、receipt_disclosed_turnsは終了後を含むfinal表示可能数であり区別する。最終turnだけで後続入力がなければ露出0。receipt byte差は最終表示1回のindex差でありtokenや累積節約ではない。API/cache/field/schema/controlも異なる尺度である。work/program/control/lookupおよびserver/cell/evaluation時間は重なるので加算しない。各seedで全体と共通成功のtoken減・成功損失なしを要求する固定gateを維持する。契約失敗・不完全記録・監査エラーも全16枠に残す。

[全条件](conditions.csv)／[集計](summary.json)／[sourceと生成物hash](build_manifest.json)／[監査](../../reports/P128_comparison.json)／[server](../../reports/P128_server_session.json)。raw prompt/reasoning/code/課題値を公開しない。原稿への採用・一般品質・新規性の判断は別である。
''')
        manifest = {'phase': 'P128', 'source_sha256': source_hashes,
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
