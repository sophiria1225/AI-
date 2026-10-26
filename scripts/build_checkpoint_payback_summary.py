"""P133 public four-slot reporting; missing usage is never a measured zero."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import re
import shutil
import tempfile

from build_p132_report import (SESSION_MEASURES, integer, number, public_path,
    publish_directory, require, sha, valid_hash)
from whole_task_checkpoint_payback import (ACTIVATION, PLAN, PREFLIGHT, MODES,
    SEEDS, cell_id, run_order, summarize)

ROOT = Path(__file__).resolve().parents[1]
TARGET = 'materials/20261027_p133_results'
AUDIT = 'reports/P133_comparison.json'
SESSION = 'reports/P133_server_session.json'
BUILDER = 'scripts/build_checkpoint_payback_summary.py'
AUDITOR = 'scripts/audit_whole_task_checkpoint_payback.py'
INSPECTOR = 'scripts/inspect_whole_task_checkpoint_payback_session.py'
HELPER = 'scripts/whole_task_checkpoint_payback.py'
COUNTS = ('model_calls', 'known_total_tokens', 'unknown_usage_calls', 'api_requests',
          'input_tokens', 'output_tokens', 'cached_input_tokens')
TIMES = ('setup_wall_seconds', 'wall_seconds', 'cleanup_wall_seconds', 'full_wall_seconds')
PAYBACK_MAP = dict(payback_rejections='skipped_unstarted_summaries',
    payback_existing_screening_rejections='existing_screening_rejections',
    payback_shadow_rejections='shadow_rejected_opportunities',
    payback_evaluated_opportunities='evaluated_opportunities',
    payback_repeated_opportunities='repeated_opportunities',
    payback_dispatched_focus_calls='dispatched_focus_calls',
    payback_unknown_focus_usage_calls='unknown_focus_usage_calls')
FLAGS = ('payback_contract_failed', 'payback_accounting_complete')
IDENTITY = ('replication', 'model_seed', 'payback_mode', 'run_id', 'task_id',
            'checkpoint_policy', 'record_status', 'success')
FIELDS = (*IDENTITY, 'stop_reason', *COUNTS, 'exact_total_tokens', *TIMES,
    'checkpoint_installed', 'checkpoint_opportunity', 'checkpoint_installations',
    *PAYBACK_MAP, *FLAGS, 'payback_events_sha256', 'summary_sha256', 'usage_sha256', 'evaluation_sha256')
STATUSES = ('evaluated', 'unevaluated', 'not_run', 'incomplete_worker', 'audit_error')


def public_row(row):
    result = {key: None for key in FIELDS}
    status = row.get('record_status')
    require(status in STATUSES, 'known_record_status_required')
    require(type(row.get('success')) is bool if status == 'evaluated' else row.get('success') is None,
            'official_success_and_evaluation_disagree')
    require(type(row.get('replication')) is int and row['replication'] in (1, 2)
        and type(row.get('model_seed')) is int and row['model_seed'] == SEEDS[row['replication'] - 1]
        and row.get('payback_mode') in MODES and row.get('checkpoint_policy') == 'rolling_separate',
        'fixed_P133_condition_required')
    result.update({key: row[key] for key in IDENTITY})
    if status not in ('evaluated', 'unevaluated'):
        require(all(row.get(k) is None for k in (*COUNTS, *TIMES, *PAYBACK_MAP, *FLAGS)),
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
    require(all(integer(row.get(k)) for k in PAYBACK_MAP)
        and row.get('payback_contract_failed') is False and row.get('payback_accounting_complete') is True,
        'reconstructed_payback_accounting_required')
    control = row.get('payback_control')
    require(type(control) is dict and control.get('mode') == row['payback_mode']
        and all(control.get(value) == row[key] for key, value in PAYBACK_MAP.items())
        and control.get('contract_failed') is False and control.get('accounting_complete') is True
        and control.get('prediction_guaranteed') is False and control.get('extra_model_calls') == 0
        and control.get('extra_native_counts') == 0, 'payback_summary_and_public_fields_disagree')
    require(row['payback_rejections'] <= row['payback_repeated_opportunities']
        <= row['payback_evaluated_opportunities'] <= row['checkpoint_opportunity']
        and row['payback_dispatched_focus_calls'] + row['payback_rejections'] <= row['payback_evaluated_opportunities']
        and row['payback_unknown_focus_usage_calls'] <= row['payback_dispatched_focus_calls']
        and (row['payback_mode'] != 'rolling_separate' or row['payback_rejections'] == 0),
        'payback_count_conservation_failed')
    reason = row.get('stop_reason')
    require(reason is None or type(reason) is str and bool(re.fullmatch('[a-z][a-z0-9_]*', reason)),
            'public_controller_status_only')
    for key in ('summary_sha256', 'usage_sha256', 'evaluation_sha256', 'payback_events_sha256'):
        value = row.get(key)
        allow_none = (key == 'evaluation_sha256' and status != 'evaluated'
                      or key == 'payback_events_sha256' and row['payback_evaluated_opportunities'] == 0)
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
    for key in ('api_requests', 'model_calls', 'input_tokens', 'output_tokens', 'cached_input_tokens', *TIMES, *PAYBACK_MAP):
        values = [r[key] for r in rows if number(r.get(key))]
        complete = bool(rows) and len(values) == len(rows)
        if key in ('input_tokens', 'output_tokens', 'cached_input_tokens'):
            complete &= exact
        if key in PAYBACK_MAP:
            complete &= all(r.get('payback_accounting_complete') is True for r in rows)
        measures[key] = dict(known_subtotal=sum(values), reported_conditions=len(values),
                            exact_all_condition_total=sum(values) if complete else None)
    return dict(planned_conditions=len(rows), accounted_conditions=len(known),
        evaluated_conditions=sum(r.get('record_status') == 'evaluated' for r in rows),
        successful_conditions=sum(r.get('success') is True for r in rows),
        known_token_subtotal=sum(r['known_total_tokens'] for r in known),
        recorded_unknown_usage_calls=sum(unknowns), unknown_usage_count_missing_conditions=len(rows)-len(unknowns),
        exact_total_tokens=sum(r['known_total_tokens'] for r in known) if exact else None,
        all_condition_usage_known=exact, measures=measures)


def comparison_groups(rows, criteria, replication=None):
    pairs = [p for p in criteria['paired_results'] if replication is None or p['replication'] == replication]
    selected = [r for r in rows if replication is None or r['replication'] == replication]
    groups = {key: [] for key in ('common_success', 'quality_gain', 'quality_loss', 'both_failed', 'not_both_evaluated')}
    for p in pairs:
        key = ('not_both_evaluated' if not p['both_evaluated'] else 'common_success' if p['both_successful']
            else 'quality_loss' if p['success_lost'] else 'quality_gain' if p['payback_success'] else 'both_failed')
        groups[key].append(p['replication'])
    return dict(baseline=MODES[0], treatment=MODES[1], planned_pairs=len(pairs),
        all_pairs_by_policy={mode: aggregate([r for r in selected if r['payback_mode'] == mode]) for mode in MODES},
        outcome_groups={key: dict(pairs=len(reps), by_policy={mode: aggregate([
            r for r in selected if r['payback_mode'] == mode and r['replication'] in reps]) for mode in MODES})
            for key, reps in groups.items()})


README = '''# P133: 有料要約の実測予測による採否、全4条件

既知CSV1課題×rolling_separate/empirical_payback×事前固定seed57/157を全件保持する。P123と同じ通常interface、full receipt、API80、反復要約を共通とし、初回focusは両側で通常許可する。2回目以降だけ、過去の採用済み入力短縮量、paid focus費用、既知actor/focus時間、残call/timeに基づく予測を適用する。予測は償却、将来時間、完了、品質の保証ではなく、通常controller改善の校正である。新規性や一般品質維持を主張しない。

要約、失敗、actor、制御、通知、回復の全logical input+outputを数える。cached inputを差し引かない。未実施、未評価、監査不能、unknown usageを0に置換しない。未知があれば全体だけでなくinput/output/cachedのexact totalsもnull。品質改善、品質損失、共通成功、両失敗を分け、cheap failureを効率改善としない。

payback_rejectionsは共有screen通過後に新規則が実際に未送信としたrepeat focus数。shadow rejectionは通常条件の仮想判定で、実介入ではない。既存call/token/context screenの拒否は別のrolling制御であり、この件数へ加えない。初回共通許可、過去のclosed prefix、count/send入力、未送信に偽usageがないことを監査する。wallはhostの記録された観測と時系列を検査し、独立時計で測り直したとは主張しない。

固定gateは全4条件の評価とknown usage、seedごとの成功損失なし、全体と非空の共通成功のtoken低下、共通成功上の実payback拒否を必要とする。2seedsは独立2課題ではない。予測式固有の優位は、単なる終了間際予約を行う強い通常対照との追加比較も必要になる。

work・要約・制御は重なり、server時間はsetup/work/evaluation/cleanupを含むため加算しない。raw prompt、reasoning、summary、生成code、API値、認証値、private pathを公開しない。

[全条件](conditions.csv)／[集計](summary.json)／[hash](build_manifest.json)／[監査](../../reports/P133_comparison.json)／[server](../../reports/P133_server_session.json)。
'''


def build(root):
    root = Path(root).resolve()
    require(root == ROOT.resolve(), 'executing_repository_root_must_match')
    target = root / TARGET
    if target.exists() or target.is_symlink():
        raise FileExistsError('preserve_all_P133_materials')
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
    require(report.get('phase') == session.get('phase') == plan.get('experiment') == 'P133'
        and report.get('batch_status') in ('complete', 'stopped') and report.get('owned_processes_absent') is True
        and session.get('owned_processes_absent') is True and session.get('status') == 'stopped',
        'closed_audited_P133_records_required')
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
        require(type(mapping) is dict and mapping, 'frozen_public_source_map_required')
        for name, expected in mapping.items():
            require(valid_hash(expected) and sha(public_path(root, name)) == expected, 'frozen_public_source_changed')
    tasks = plan.get('known_tasks')
    require(type(tasks) is list and len(tasks) == 1 and plan.get('payback_modes') == list(MODES)
        and plan.get('model_seeds') == list(SEEDS), 'fixed_P133_task_modes_seeds_required')
    expected = [(cell_id(rep,n,mode), tasks[n-1]['task_id'], mode, rep, SEEDS[rep-1]) for rep,n,mode in run_order()]
    raw = report.get('rows')
    require(type(raw) is list and [(r.get('run_id'), r.get('task_id'), r.get('payback_mode'),
        r.get('replication'), r.get('model_seed')) for r in raw] == expected, 'all_four_ordered_slots_required')
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
    summary = dict(phase='P133', all_conditions=aggregate(rows),
        by_policy={m: aggregate([r for r in rows if r['payback_mode']==m]) for m in MODES},
        primary_baseline=MODES[0], treatment=MODES[1], comparison_costs=comparison_groups(rows,criteria),
        by_replication={str(rep): dict(model_seed=SEEDS[rep-1],
            all_conditions=aggregate([r for r in rows if r['replication']==rep]),
            by_policy={m: aggregate([r for r in rows if r['replication']==rep and r['payback_mode']==m]) for m in MODES},
            comparison_costs=comparison_groups(rows,criteria,rep)) for rep in (1,2)},
        independent_tasks=1, repetitions=2, model_seeds=list(SEEDS), audited_criteria=criteria,
        audit_error_count=len(errors), conditions=rows, server_measures=server, unknown_usage_is_not_zero=True,
        cost_scope='All model roles, failed work, control, recovery and summary costs remain in the whole-job ledger.',
        time_scope='Control and summary time overlap work; work and evaluation overlap server time. Do not add them.',
        forecast_is_guarantee=False, novel_method_claim=False, general_quality_preservation_claim=False,
        timing_superiority_claim=False, manuscript_changed=False, private_task_values_or_program_text_published=False)
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix='.p133-materials-', dir=target.parent))
    try:
        with (staging/'conditions.csv').open('x', newline='') as handle:
            writer = csv.DictWriter(handle, fieldnames=FIELDS); writer.writeheader(); writer.writerows(rows)
        (staging/'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False)+'\n')
        (staging/'README.md').write_text(README)
        manifest = dict(phase='P133', source_sha256=source_hashes, activation_bound_source_count=len(frozen),
            activation_source_mapping_sha256=hashlib.sha256(json.dumps(frozen,sort_keys=True).encode()).hexdigest(),
            artifact_sha256={p.name:sha(p) for p in sorted(staging.iterdir())},
            new_model_calls=0,new_API_requests=0,new_tokenizer_calls=0,new_evaluations=0,
            atomic_exclusive_directory_publication=True)
        (staging/'build_manifest.json').write_text(json.dumps(manifest,indent=2,allow_nan=False)+'\n')
        require(all(sha(public_path(root,n))==h for n,h in {**frozen,**source_hashes}.items()), 'source_changed_during_build')
        publish_directory(staging,target)
    finally:
        if staging.exists(): shutil.rmtree(staging)
    return summary


if __name__ == '__main__':
    p=argparse.ArgumentParser(); p.add_argument('--repo-root',type=Path,default=ROOT)
    print(json.dumps(build(p.parse_args().repo_root),ensure_ascii=False))
