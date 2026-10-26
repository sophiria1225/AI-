"""P135 public six-slot reporting; missing usage is never a measured zero."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import re
import shutil
import tempfile

from build_p132_report import (SESSION_MEASURES, integer, number,
    publish_directory, require, sha, valid_hash)
from whole_task_observed_obligations_p135 import (ACTIVATION, PLAN, PREFLIGHT, MODES,
    SEEDS, cell_id, run_order, summarize)

ROOT = Path(__file__).resolve().parents[1]
TARGET = 'materials/20261027_p135_results'
AUDIT = 'reports/P135_comparison.json'
SESSION = 'reports/P135_server_session.json'
BUILDER = 'scripts/build_observed_obligations_summary_p135.py'
AUDITOR = 'scripts/audit_whole_task_observed_obligations_p135.py'
INSPECTOR = 'scripts/inspect_whole_task_observed_obligations_session_p135.py'
HELPER = 'scripts/whole_task_observed_obligations_p135.py'
COUNTS = ('model_calls', 'known_total_tokens', 'unknown_usage_calls', 'api_requests',
          'input_tokens', 'output_tokens', 'cached_input_tokens')
TIMES = ('setup_wall_seconds', 'wall_seconds', 'cleanup_wall_seconds', 'full_wall_seconds')
OBLIGATION_COUNTS = ('obligation_notice_actor_calls', 'obligation_entity_rows_exposed',
    'obligation_checkpoint_captures', 'obligation_queries', 'obligation_query_rejections')
FLAGS = ('obligation_contract_failed', 'obligation_accounting_complete')
IDENTITY = ('replication', 'model_seed', 'obligation_mode', 'run_id', 'task_id',
            'checkpoint_policy', 'record_status', 'success')
FIELDS = (*IDENTITY, 'stop_reason', *COUNTS, 'exact_total_tokens', *TIMES,
    'checkpoint_installed', 'checkpoint_opportunity', 'checkpoint_installations',
    *OBLIGATION_COUNTS, *FLAGS, 'obligation_runtime_wall_seconds', 'obligation_final_enumeration', 'obligation_audit_hashes_sha256', 'summary_sha256', 'usage_sha256', 'evaluation_sha256')
STATUSES = ('evaluated', 'unevaluated', 'not_run', 'incomplete_worker', 'audit_error')


# P134's immutable plan already includes precisely these seven public files.
# The recovery does not permit arbitrary materials/papers or private records.
RECOVERED_PUBLIC_SOURCE_PATHS = frozenset((
    'materials/20261024_p97_results/visual_review.json',
    'materials/20261024_p98_results/summary.json',
    'materials/20261025_p112_preparation/README.md',
    'materials/20261025_p115_preparation/README.md',
    'materials/20261025_p122_results/build_manifest.json',
    'materials/20261025_p122_results/summary.json',
    'papers/202610_letter/templates/tool_choice_letter.tex',
))


def public_path(root, name, *, source_sha256=None):
    """Bounded regular repository source; seven extra paths need a frozen hash."""
    root = Path(root).resolve()
    require(type(name) is str and name and '\\' not in name and '\x00' not in name
        and not Path(name).is_absolute() and all(part not in ('', '.', '..') for part in name.split('/')),
        'repository_relative_public_source_required')
    ordinary = name.split('/')[0] in ('scripts', 'tests', 'configs', 'docs', 'reports')
    require(ordinary or name in RECOVERED_PUBLIC_SOURCE_PATHS, 'repository_public_source_scope_required')
    cursor = root
    for part in Path(name).parts:
        cursor = cursor / part
        require(not cursor.is_symlink(), 'public_source_symlink_forbidden')
    require(cursor.resolve().is_relative_to(root), 'public_source_escapes_repository')
    require(cursor.is_file(), 'regular_existing_public_source_required')
    if not ordinary:
        require(type(source_sha256) is dict and valid_hash(source_sha256.get(name)),
            'extra_public_source_requires_frozen_membership')
        require(sha(cursor) == source_sha256[name], 'extra_public_source_hash_changed')
    return cursor


def validate_source_map(root, mapping, *, frozen_scope):
    """Use the same full-map check in the builder and in the 1483-source regression."""
    require(type(mapping) is dict and bool(mapping), 'frozen_public_source_map_required')
    require(type(frozen_scope) is dict and bool(frozen_scope), 'frozen_public_scope_required')
    for name, expected in mapping.items():
        require(valid_hash(expected)
            and sha(public_path(root, name, source_sha256=frozen_scope)) == expected,
            'frozen_public_source_changed')
    return len(mapping)


def public_row(row):
    result = {key: None for key in FIELDS}
    status = row.get('record_status')
    require(status in STATUSES, 'known_record_status_required')
    require(type(row.get('success')) is bool if status == 'evaluated' else row.get('success') is None,
            'official_success_and_evaluation_disagree')
    require(type(row.get('replication')) is int and row['replication'] in (1, 2)
        and type(row.get('model_seed')) is int and row['model_seed'] == SEEDS[row['replication'] - 1]
        and row.get('obligation_mode') in MODES and row.get('checkpoint_policy') == 'rolling_separate',
        'fixed_P135_condition_required')
    result.update({key: row[key] for key in IDENTITY})
    if status not in ('evaluated', 'unevaluated'):
        require(all(row.get(k) is None for k in (*COUNTS, *TIMES, *OBLIGATION_COUNTS, *FLAGS)),
                'unaccounted_condition_cannot_gain_measurements')
        return result
    require(all(integer(row.get(k)) for k in COUNTS if k != 'cached_input_tokens')
        and row['input_tokens'] + row['output_tokens'] == row['known_total_tokens']
        and row['unknown_usage_calls'] <= row['model_calls'], 'known_subtotal_and_attempt_counts_required')
    require(row.get('cached_input_tokens') is None or integer(row['cached_input_tokens'])
        and row['cached_input_tokens'] <= row['input_tokens'], 'invalid_cached_input')
    require(all(number(row.get(k)) for k in TIMES), 'finite_task_times_required')
    require(type(row.get('checkpoint_installed')) is bool
        and integer(row.get('checkpoint_installations')) and integer(row.get('checkpoint_opportunity'))
        and row['checkpoint_installations'] <= row['checkpoint_opportunity'] <= 3
        and row['checkpoint_installed'] is (row['checkpoint_installations'] > 0), 'bounded_checkpoint_counts_required')
    require(all(integer(row.get(k)) for k in OBLIGATION_COUNTS)
        and row.get('obligation_contract_failed') is False and row.get('obligation_accounting_complete') is True,
        'reconstructed_obligation_accounting_required')
    control = row.get('obligation_control'); runtime = control.get('runtime') if type(control) is dict else None
    require(type(control) is dict and type(runtime) is dict and control.get('mode') == row['obligation_mode']
        and control.get('contract_failed') is False and runtime.get('contract_failed') is False
        and control.get('actual_obligation_exposures') == row['obligation_notice_actor_calls']
        and control.get('entity_rows_exposed') == row['obligation_entity_rows_exposed']
        and control.get('prepared') == runtime.get('checkpoint_captures') == row['obligation_checkpoint_captures']
        and runtime.get('queries') == row['obligation_queries']
        and runtime.get('query_rejections') == row['obligation_query_rejections']
        and runtime.get('extra_model_calls') == 0 and runtime.get('extra_environment_API_requests') == 0,
        'obligation_summary_and_public_fields_disagree')
    require(row['obligation_checkpoint_captures'] == row['checkpoint_installations']
        and row['obligation_notice_actor_calls'] <= row['obligation_checkpoint_captures']
        and row['obligation_entity_rows_exposed'] <= 16 * row['obligation_notice_actor_calls']
        and row['obligation_query_rejections'] <= row['obligation_queries']
        and (row['obligation_mode'] == 'entity_fields' or row['obligation_entity_rows_exposed'] == 0)
        and (row['obligation_mode'] != 'raw_anchor' or row['obligation_notice_actor_calls'] == row['obligation_queries'] == 0),
        'obligation_count_conservation_failed')
    require(number(row.get('obligation_runtime_wall_seconds'))
        and runtime.get('wall_seconds') == row['obligation_runtime_wall_seconds']
        and row['obligation_runtime_wall_seconds'] <= row['wall_seconds']
        and row.get('obligation_final_enumeration') in ('open','closed','unknown'), 'obligation_time_or_enumeration_changed')
    mapping = row.get('obligation_audit_hashes')
    require(type(mapping) is dict and len(mapping) == 5 and all(valid_hash(h) for h in mapping.values()),
        'obligation_reconstruction_hashes_required')
    result['obligation_audit_hashes_sha256'] = hashlib.sha256(json.dumps(mapping, sort_keys=True,
        separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()).hexdigest()
    reason = row.get('stop_reason')
    require(reason is None or type(reason) is str and bool(re.fullmatch('[a-z][a-z0-9_]*', reason)),
            'public_controller_status_only')
    for key in ('summary_sha256', 'usage_sha256', 'evaluation_sha256'):
        value = row.get(key)
        allow_none = key == 'evaluation_sha256' and status != 'evaluated'
        require(value is None and allow_none or valid_hash(value), 'audited_row_hash_required')
    for key in FIELDS:
        if key in row:
            result[key] = row[key]
    result['exact_total_tokens'] = row['known_total_tokens'] if row['unknown_usage_calls'] == 0 else None
    return result


def aggregate(rows):
    known = [r for r in rows if integer(r.get('known_total_tokens'))]
    unknowns = [r['unknown_usage_calls'] for r in rows if integer(r.get('unknown_usage_calls'))]
    exact = bool(rows) and len(known) == len(rows) == len(unknowns) and sum(unknowns) == 0
    measures = {}
    for key in ('api_requests', 'model_calls', 'input_tokens', 'output_tokens', 'cached_input_tokens', *TIMES, 'obligation_runtime_wall_seconds', *OBLIGATION_COUNTS):
        values = [r[key] for r in rows if number(r.get(key))]
        complete = bool(rows) and len(values) == len(rows)
        if key in ('input_tokens', 'output_tokens', 'cached_input_tokens'):
            complete &= exact
        if key in OBLIGATION_COUNTS:
            complete &= all(r.get('obligation_accounting_complete') is True for r in rows)
        measures[key] = dict(known_subtotal=sum(values), reported_conditions=len(values),
                            exact_all_condition_total=sum(values) if complete else None)
    return dict(planned_conditions=len(rows), accounted_conditions=len(known),
        evaluated_conditions=sum(r.get('record_status') == 'evaluated' for r in rows),
        successful_conditions=sum(r.get('success') is True for r in rows),
        known_token_subtotal=sum(r['known_total_tokens'] for r in known),
        recorded_unknown_usage_calls=sum(unknowns), unknown_usage_count_missing_conditions=len(rows)-len(unknowns),
        exact_total_tokens=sum(r['known_total_tokens'] for r in known) if exact else None,
        all_condition_usage_known=exact, measures=measures)


def comparison_groups(rows, comparison, replication=None):
    pairs = [p for p in comparison['paired_results'] if replication is None or p['replication'] == replication]
    selected = [r for r in rows if replication is None or r['replication'] == replication]
    modes = (comparison['baseline'], comparison['candidate'])
    groups = {key: [] for key in ('common_success', 'quality_gain', 'quality_loss', 'both_failed', 'not_both_evaluated')}
    for pair in pairs:
        groups[pair['quality_transition']].append(pair['replication'])
    return dict(baseline=modes[0], treatment=modes[1], planned_pairs=len(pairs),
        all_pairs_by_policy={mode: aggregate([r for r in selected if r['obligation_mode'] == mode]) for mode in modes},
        outcome_groups={key: dict(pairs=len(reps), by_policy={mode: aggregate([
            r for r in selected if r['obligation_mode'] == mode and r['replication'] in reps]) for mode in modes})
            for key, reps in groups.items()})


def all_comparisons(rows, criteria, replication=None):
    return {name: comparison_groups(rows, criteria[key], replication)
            for name,key in [('primary','primary_comparison'),('raw_anchor','raw_anchor_comparison')]}


README = '''# P135: 観測済み対象と未充足fieldの提示、全6条件

P134のqueue失敗・モデル未起動の記録を残し、同じ科学条件を新しいP135名前空間で実施する運用復旧である。旧試行の成否や費用へ混ぜない。

既知CSV1課題×固定seed57/157×raw_anchor/counts_only/entity_fieldsを全件保持する。主比較のcounts_onlyとentity_fieldsは同じguide、明示query、API/モデル予算と証拠を持ち、採用checkpoint直後の次actorへの一度の自動提示だけを変える。raw_anchorは元P123のguide/toolsを保ち、同じ観測とcapture費用を負担する。追加API・値の補完・書込み・削除は自動実行しない。

全actor/focus、失敗、問い合わせ返答、通知を含むlogical input+outputを数え、cached inputを差し引かない。未実施・未評価・監査不能・unknown usageはゼロにしない。未知があればinput/output/cachedを含むexact totalsはnull。全体と共通成功の費用、品質増減と両失敗を分ける。安い失敗を効率改善とはしない。

対象列挙はopen/closed/unknownを分ける。open/unknownの不足件数はnullであり、空の不足一覧や成功を意味しない。件数・entity行は観測typed返答のみから再構成し、古いhandle・別実行・別要件を受理しない。capture件数、実dispatch actorへの提示、提示entity行、明示queryを区別する。提示の内容・値・生成codeは公開しない。原Python状態を再実行せず、保存native要求・typed event・sidecarを突合する監査である。archive/focus不変は同arm通常履歴にtransient noticeを混入しない意味であり、raw対照とのfocus bytes一致ではない。明示query返答は通常有料履歴としてfocusへ入り得る。各armのrun_idが異なるため、scopeに束縛したsnapshot handleも異なる。初期main pairの同一入力を、checkpoint後の通知共通部分まで同じバイト列であるという主張へ広げない。最初の入力差をentity内容だけへ因果帰属しない。

固定gateは全6評価とknown usage、主比較とraw対照の両方で成功損失なし、主比較の全体と非空共通成功のtoken低下、raw対照の全体token低下、主比較共通成功上の実entity提示を必要とする。全契約・会計の成立も必須。1課題・2seedsで一般品質や新規技術を証明したとはしない。

観測・問い合わせ・要約・入力計数はworkに含まれ、work/evaluation/setup/cleanupはserver時間と重なる。加算しない。raw prompt・reasoning・API値・認証・評価本文・private pathを公開しない。

[全条件](conditions.csv)／[集計](summary.json)／[hash](build_manifest.json)／[監査](../../reports/P135_comparison.json)／[server](../../reports/P135_server_session.json)。
'''



def build(root):
    root = Path(root).resolve()
    require(root == ROOT.resolve(), 'executing_repository_root_must_match')
    target = root / TARGET
    if target.exists() or target.is_symlink():
        raise FileExistsError('preserve_all_P135_materials')
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
    require(report.get('phase') == session.get('phase') == plan.get('experiment') == 'P135'
        and report.get('batch_status') in ('complete', 'stopped') and report.get('owned_processes_absent') is True
        and session.get('owned_processes_absent') is True and session.get('status') == 'stopped',
        'closed_audited_P135_records_required')
    require(session.get('audit_source_sha256') == source_hashes[AUDIT]
        and report.get('plan_sha256') == source_hashes[PLAN] and report.get('activation_sha256') == source_hashes[ACTIVATION]
        and report.get('auditor_sha256') == source_hashes[AUDITOR] and session.get('inspector_sha256') == source_hashes[INSPECTOR]
        and activation.get('preflight_sha256') == source_hashes[PREFLIGHT]
        and valid_hash(report.get('pipeline_status_sha256')) and valid_hash(report.get('server_final_sha256'))
        and session.get('pipeline_source_sha256') == report['pipeline_status_sha256']
        and session.get('source_sha256') == report['server_final_sha256'], 'report_session_source_binding_differs')
    frozen = activation.get('source_hashes')
    require(type(frozen) is dict and all(n in frozen for n in (BUILDER, AUDITOR, INSPECTOR, HELPER)),
            'frozen_reporting_sources_required')
    for mapping in (frozen, plan.get('source_sha256')):
        validate_source_map(root, mapping, frozen_scope=plan.get('source_sha256'))
    tasks = plan.get('known_tasks')
    require(type(tasks) is list and len(tasks) == 1 and plan.get('obligation_modes') == list(MODES)
        and plan.get('model_seeds') == list(SEEDS), 'fixed_P135_task_modes_seeds_required')
    expected = [(cell_id(rep,n,mode), tasks[n-1]['task_id'], mode, rep, SEEDS[rep-1]) for rep,n,mode in run_order()]
    raw = report.get('rows')
    require(type(raw) is list and [(r.get('run_id'), r.get('task_id'), r.get('obligation_mode'),
        r.get('replication'), r.get('model_seed')) for r in raw] == expected, 'all_six_ordered_slots_required')
    errors = report.get('audit_errors')
    require(type(errors) is list, 'audit_error_list_required')
    criteria = summarize(raw, errors)
    require(all(report.get(k) == v for k,v in criteria.items()), 'audited_criteria_differ_from_rows')
    rows = [public_row(r) for r in raw]
    server = {}
    for key in SESSION_MEASURES:
        value = session.get(key)
        require(value is None or number(value), 'finite_server_measurement_required')
        server[key] = value
    summary = dict(phase='P135', all_conditions=aggregate(rows),
        by_policy={m: aggregate([r for r in rows if r['obligation_mode']==m]) for m in MODES},
        primary_baseline='counts_only', treatment='entity_fields', secondary_baseline='raw_anchor', comparison_costs=all_comparisons(rows,criteria),
        by_replication={str(rep): dict(model_seed=SEEDS[rep-1],
            all_conditions=aggregate([r for r in rows if r['replication']==rep]),
            by_policy={m: aggregate([r for r in rows if r['replication']==rep and r['obligation_mode']==m]) for m in MODES},
            comparison_costs=all_comparisons(rows,criteria,rep)) for rep in (1,2)},
        independent_tasks=1, repetitions=2, model_seeds=list(SEEDS), audited_criteria=criteria,
        audit_error_count=len(errors), conditions=rows, server_measures=server, unknown_usage_is_not_zero=True,
        cost_scope='All model roles, failed work, control, recovery and summary costs remain in the whole-job ledger.',
        time_scope='Control and summary time overlap work; work and evaluation overlap server time. Do not add them.',
        observed_fields_are_not_task_success=True, novel_method_claim=False, general_quality_preservation_claim=False,
        timing_superiority_claim=False, manuscript_changed=False, private_task_values_or_program_text_published=False)
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix='.p135-materials-', dir=target.parent))
    try:
        with (staging/'conditions.csv').open('x', newline='') as handle:
            writer = csv.DictWriter(handle, fieldnames=FIELDS); writer.writeheader(); writer.writerows(rows)
        (staging/'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False)+'\n')
        (staging/'README.md').write_text(README)
        manifest = dict(phase='P135', source_sha256=source_hashes, activation_bound_source_count=len(frozen),
            activation_source_mapping_sha256=hashlib.sha256(json.dumps(frozen,sort_keys=True).encode()).hexdigest(),
            artifact_sha256={p.name:sha(p) for p in sorted(staging.iterdir())},
            new_model_calls=0,new_API_requests=0,new_tokenizer_calls=0,new_evaluations=0,
            atomic_exclusive_directory_publication=True)
        (staging/'build_manifest.json').write_text(json.dumps(manifest,indent=2,allow_nan=False)+'\n')
        validate_source_map(root, {**frozen, **source_hashes}, frozen_scope=plan['source_sha256'])
        publish_directory(staging,target)
    finally:
        if staging.exists(): shutil.rmtree(staging)
    return summary


if __name__ == '__main__':
    p=argparse.ArgumentParser(); p.add_argument('--repo-root',type=Path,default=ROOT)
    print(json.dumps(build(p.parse_args().repo_root),ensure_ascii=False))
