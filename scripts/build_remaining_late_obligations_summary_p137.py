"""P137 four-slot descriptive reporting; prior P136 outcomes are never pooled."""
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
from whole_task_remaining_late_obligations_p137 import (ACTIVATION, PLAN, PREFLIGHT, MODES,
    SEEDS, cell_id, run_order, summarize)

ROOT = Path(__file__).resolve().parents[1]
TARGET = 'materials/20261027_p137_results'
AUDIT = 'reports/P137_comparison.json'
SESSION = 'reports/P137_server_session.json'
BUILDER = 'scripts/build_remaining_late_obligations_summary_p137.py'
AUDITOR = 'scripts/audit_whole_task_remaining_late_obligations_p137.py'
INSPECTOR = 'scripts/inspect_whole_task_remaining_late_obligations_session_p137.py'
HELPER = 'scripts/whole_task_remaining_late_obligations_p137.py'
COUNTS = ('model_calls', 'known_total_tokens', 'unknown_usage_calls', 'api_requests',
          'input_tokens', 'output_tokens', 'cached_input_tokens')
TIMES = ('setup_wall_seconds', 'wall_seconds', 'cleanup_wall_seconds', 'full_wall_seconds')
OBLIGATION_COUNTS = ('obligation_notice_actor_calls', 'obligation_entity_rows_exposed', 'obligation_field_rows_exposed',
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
    """Bounded regular repository source; seven inherited paths need a frozen hash."""
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
    """Validate the full frozen source map in both builder and regression checks."""
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
        'fixed_P137_condition_required')
    require((row['replication'], 1, row['obligation_mode']) in run_order()
        and row.get('run_id') == cell_id(row['replication'], 1, row['obligation_mode']),
        'only_four_new_P137_identities_allowed')
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
        and control.get('field_rows_exposed') == row['obligation_field_rows_exposed']
        and control.get('version') == 'late_obligation_disclosure_p136_v1'
        and control.get('selection_rule') == 'fixed_max_descriptor_and_mask_same_closed_pending_ID_prefix'
        and control.get('query_interface_exposed') is False
        and control.get('public_snapshot_handle_exposed') is False
        and control.get('prepared') == runtime.get('checkpoint_captures') == row['obligation_checkpoint_captures']
        and runtime.get('queries') == row['obligation_queries']
        and runtime.get('query_rejections') == row['obligation_query_rejections']
        and runtime.get('extra_model_calls') == 0 and runtime.get('extra_environment_API_requests') == 0,
        'obligation_summary_and_public_fields_disagree')
    require(row['obligation_checkpoint_captures'] == row['checkpoint_installations']
        and row['obligation_notice_actor_calls'] <= row['obligation_checkpoint_captures']
        and row['obligation_entity_rows_exposed'] <= 16 * row['obligation_notice_actor_calls']
        and row['obligation_query_rejections'] == row['obligation_queries'] == 0
        and row['obligation_field_rows_exposed'] <= row['obligation_entity_rows_exposed']
        and (row['obligation_field_rows_exposed'] == row['obligation_entity_rows_exposed']
             if row['obligation_mode'] == 'entity_fields' else row['obligation_field_rows_exposed'] == 0)
        and (row['obligation_mode'] != 'raw_anchor' or row['obligation_notice_actor_calls'] == row['obligation_entity_rows_exposed'] == 0),
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
    paired_reps = {p['replication'] for p in pairs}
    selected = [r for r in rows if r['replication'] in paired_reps]
    modes = (comparison['baseline'], comparison['candidate'])
    groups = {key: [] for key in ('common_success', 'quality_gain', 'quality_loss', 'both_failed', 'not_both_evaluated')}
    for pair in pairs:
        groups[pair['quality_transition']].append(pair['replication'])
    return dict(baseline=modes[0], treatment=modes[1], planned_pairs=len(pairs),
        scope='same_cohort_seed157_only', comparable_model_seeds=[157] if pairs else [],
        seed57_unpaired_excluded=True, prior_results_pooled=False,
        all_pairs_by_policy={mode: aggregate([r for r in selected if r['obligation_mode'] == mode]) for mode in modes},
        outcome_groups={key: dict(pairs=len(reps), by_policy={mode: aggregate([
            r for r in selected if r['obligation_mode'] == mode and r['replication'] in reps]) for mode in modes})
            for key, reps in groups.items()})


def all_comparisons(rows, criteria, replication=None):
    return {name: comparison_groups(rows, criteria[key], replication)
            for name,key in [('primary','primary_comparison'),('raw_anchor','raw_anchor_comparison')]}


README = '''# P137: P136で未実施だった4条件の追加観測

既知CSV1課題について、entity_fields/seed57 → entity_fields/seed157 → ids_only/seed157 → raw_anchor/seed157の全4条件を保持する。P136の評価済みraw/seed57と中断したIDs/seed57は再実行せず、P136の6行・欠測・判定を置換しない。P136の値と合算しない。

主比較はseed157のids_only対entity_fields、補助比較は同じseed157のraw_anchor対entity_fieldsだけである。どちらも同一の新cohort内の1組の記述的比較であり、seed57のentity_fieldsは対照のない単独結果として別掲する。方式別の全行集計は不均衡（1/1/2条件）なので、その合計同士を方式間の効果比較に使わない。`comparison_costs`はseed157の1組だけ、`seed57_unpaired`はseed57だけを含む。`by_replication["1"]`の比較は0組で、exact費用はnullとなる。

初期guide、CODE_TOOLS、通常rolling checkpoint、typed monitor、表示規則はP136と同じ。追加query toolや公開handleはない。同じclosed pending-ID列を条件に、共通selectorが最大16行の同じprefixを選び、entity_fieldsだけが各IDの不足fieldを加える。独立runの実際のID列や軌跡が同一とは仮定しない。通知は採用checkpoint後の次actorだけに付け、archiveとfocusへ再注入しない。JSON本文は2048 UTF-8 bytes以下、見出し43 bytesを含む追加上限は2091 bytesで、全入力費用に含む。

全actor/focus、失敗、要約、通知のlogical input+outputを数え、cached inputを差し引かない。未実施・未評価・監査不能・unknown usageをゼロにしない。既知小計と報告件数、unknown件数、欠測条件数を併記し、未知・欠測があれば全体exact費用はnull。共通成功、品質増減、双方失敗、未評価を分け、共通成功が空なら共通成功の費用差はnullとする。

列挙open/closed/unknownを区別する。open/unknownの詳細行0は義務なしや成功を意味しない。capture、実dispatchへの通知、累積ID行、field行を別々に数える。ID行はunique entity数ではなく、field行はentity_fieldsだけにあり、queryは全方式0。観測完備は公式課題成功ではない。保存Python・評価器・モデル・tokenizerはこの集計で再実行しない。

この追加観測では採用判定を行わず、`development_gate_met`と`scientific_adoption_evaluated`は常にfalse。結果が良くてもP136の元gateを修復したことにはしない。単一既知課題、seed157の1組とseed57の単独結果から一般品質維持、新規性、timing優位を主張しない。SIGALRMを通常の記録可能な経路へ戻す修正とworker終了状態の保存は新実行に適用するが、P136の元失敗を変更しない。

観測・要約・入力計数はwork内、work/evaluation/setup/cleanupはserver時間と重なるので加算しない。raw prompt・reasoning・API値・認証・評価本文・private pathを公開しない。

[全4条件](conditions.csv)／[集計](summary.json)／[hash](build_manifest.json)／[監査](../../reports/P137_comparison.json)／[server](../../reports/P137_server_session.json)。
'''



def build(root):
    root = Path(root).resolve()
    require(root == ROOT.resolve(), 'executing_repository_root_must_match')
    target = root / TARGET
    if target.exists() or target.is_symlink():
        raise FileExistsError('preserve_all_P137_materials')
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
    require(report.get('phase') == session.get('phase') == plan.get('experiment') == 'P137'
        and report.get('batch_status') in ('complete', 'stopped') and report.get('owned_processes_absent') is True
        and session.get('owned_processes_absent') is True and session.get('status') == 'stopped',
        'closed_audited_P137_records_required')
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
        and plan.get('model_seeds') == list(SEEDS), 'fixed_P137_task_modes_seeds_required')
    expected = [(cell_id(rep,n,mode), tasks[n-1]['task_id'], mode, rep, SEEDS[rep-1]) for rep,n,mode in run_order()]
    raw = report.get('rows')
    require(type(raw) is list and [(r.get('run_id'), r.get('task_id'), r.get('obligation_mode'),
        r.get('replication'), r.get('model_seed')) for r in raw] == expected, 'all_four_ordered_remaining_slots_required')
    errors = report.get('audit_errors')
    require(type(errors) is list, 'audit_error_list_required')
    criteria = summarize(raw, errors)
    require(criteria.get('planned_rows') == 4 and criteria.get('balanced_repetitions') is False
        and all(criteria.get(k) is False for k in ('development_gate_met',
            'scientific_adoption_evaluated', 'prior_results_pooled', 'original_P136_gate_replaced')),
        'P137_descriptive_scope_must_not_replace_prior_gate')
    require(all(report.get(k) == v for k,v in criteria.items()), 'audited_criteria_differ_from_rows')
    rows = [public_row(r) for r in raw]
    server = {}
    for key in SESSION_MEASURES:
        value = session.get(key)
        require(value is None or number(value), 'finite_server_measurement_required')
        server[key] = value
    summary = dict(phase='P137', all_conditions=aggregate(rows),
        by_policy={m: aggregate([r for r in rows if r['obligation_mode']==m]) for m in MODES},
        primary_baseline='ids_only', treatment='entity_fields', secondary_baseline='raw_anchor', comparison_costs=all_comparisons(rows,criteria),
        by_replication={str(rep): dict(model_seed=SEEDS[rep-1],
            all_conditions=aggregate([r for r in rows if r['replication']==rep]),
            by_policy={m: aggregate([r for r in rows if r['replication']==rep and r['obligation_mode']==m]) for m in MODES},
            comparison_costs=all_comparisons(rows,criteria,rep)) for rep in (1,2)},
        independent_tasks=1, repetitions=2, balanced_repetitions=False, model_seeds=list(SEEDS),
        planned_rows=4, comparison_scope='same_cohort_seed157_only',
        seed57_unpaired=dict(model_seed=57, condition=rows[0], aggregate=aggregate(rows[:1]),
            comparison_performed=False),
        by_policy_totals_are_descriptive_only=True, scientific_adoption_evaluated=False,
        development_gate_met=False, prior_results_pooled=False, original_P136_gate_replaced=False,
        audited_criteria=criteria,
        audit_error_count=len(errors), conditions=rows, server_measures=server, unknown_usage_is_not_zero=True,
        cost_scope='All model roles, failed work, control, recovery and summary costs remain in the whole-job ledger.',
        time_scope='Control and summary time overlap work; work and evaluation overlap server time. Do not add them.',
        observed_fields_are_not_task_success=True, novel_method_claim=False, general_quality_preservation_claim=False,
        timing_superiority_claim=False, manuscript_changed=False, private_task_values_or_program_text_published=False)
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix='.p137-materials-', dir=target.parent))
    try:
        with (staging/'conditions.csv').open('x', newline='') as handle:
            writer = csv.DictWriter(handle, fieldnames=FIELDS); writer.writeheader(); writer.writerows(rows)
        (staging/'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False)+'\n')
        (staging/'README.md').write_text(README)
        manifest = dict(phase='P137', source_sha256=source_hashes, activation_bound_source_count=len(frozen),
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
    completed = build(p.parse_args().repo_root)
    print(json.dumps(dict(phase=completed['phase'], all_conditions=completed['all_conditions'],
        development_gate_met=completed['audited_criteria']['development_gate_met']), ensure_ascii=False))
