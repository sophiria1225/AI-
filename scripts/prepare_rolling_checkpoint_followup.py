"""Review the entire closed P122 cohort and bind the already specified P123 plan.

No generated work or inference is performed here. The next experiment's tasks,
order, controls and budgets do not depend on which P122 outcomes are favorable.
Unknown usage, missing slots, audit errors or an open session prevent binding.
"""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path

from build_required_inline_checkpoint_summary import aggregate
from receipt_reasoning_history import require
from run_handoff_factors import read, sha
from whole_task_checkpoint_replication import (POLICIES as OLD_POLICIES, SEEDS, TASKS,
    cell_id as prior_id, run_order as prior_order, summarize as summarize_prior)
from whole_task_rolling_checkpoint import POLICIES, validate_plan


def review(report, session, overview):
    expected = [(prior_id(rep,n,p),rep,SEEDS[rep-1],TASKS[n-1],p) for rep,n,p in prior_order()]
    require(report['phase']=='P122' and report['owned_processes_absent'] and not report['audit_errors'],
            'clean_closed_P122_audit_required')
    rows=report['rows']
    require([(r['run_id'],r['repetition'],r['model_seed'],r['task_id'],r['checkpoint_policy'])
             for r in rows]==expected, 'all_24_ordered_slots_required')
    require(session['phase']=='P122' and session['status']=='stopped' and session['owned_processes_absent'],
            'closed_P122_session_required')
    recalculated=summarize_prior(rows,[])
    require(all(report.get(k)==v for k,v in recalculated.items()), 'P122_aggregate_recalculation_mismatch')
    require(all(overview.get(k)==v for k,v in aggregate(rows).items()), 'P122_materials_totals_changed')
    require(overview.get('replication_gate_met')==recalculated['replication_gate_met']
            and overview.get('photo_reduction_repeated_with_success')==recalculated['photo_reduction_repeated_with_success']
            and overview.get('task_summaries')==recalculated['task_summaries']
            and overview.get('repetition_summaries')==recalculated['repetition_summaries'],
            'P122_materials_comparisons_changed')
    for row in rows:
        if row['record_status']!='evaluated':
            continue
        calls=row['request_checks']; known=[c for c in calls if c['status']=='ok']
        require(row['model_calls']==len(calls)
                and row['unknown_usage_calls']==len(calls)-len(known)
                and row['known_total_tokens']==sum(c['input_tokens']+c['output_tokens'] for c in known),
                'P122_per_request_accounting_changed')
        roles={role:{'calls':sum(c['role']==role for c in calls),
            'unknown_usage':sum(c['role']==role and c['status']!='ok' for c in calls),
            'input_tokens':sum(c['input_tokens'] for c in known if c['role']==role),
            'output_tokens':sum(c['output_tokens'] for c in known if c['role']==role)}
            for role in ('agent','focus')}
        require(row['usage_by_role']==roles and all(c['role'] in roles for c in calls),
                'P122_role_accounting_changed')
        require(row['model_calls']<=80 and row['known_total_tokens']<=450000
                and row['api_requests']<= (160 if row['task_id']==TASKS[0] else 80),
                'P122_fixed_budget_changed')
    allowed=bool(report['batch_status']=='complete' and recalculated['all_24_complete_with_known_usage'])
    return {'phase':'P122_review_for_fixed_P123', 'all_slots_reviewed':24, 'unique_known_tasks':4,
        'by_policy':{p:aggregate([r for r in rows if r['checkpoint_policy']==p]) for p in OLD_POLICIES},
        'replication_gate_met':recalculated['replication_gate_met'],
        'photo_reduction_repeated_with_success':recalculated['photo_reduction_repeated_with_success'],
        'task_summaries':recalculated['task_summaries'],
        'next_predeclared_comparison_may_be_bound':allowed,
        'decision_rule':'All 24 fixed slots evaluated, exact usage, closed server and matching accounting; '
            'the followup scope does not depend on a favorable outcome or either research gate.',
        'new_model_calls':0,'new_API_requests':0,'new_evaluations':0,'new_tokenizer_counts':0,
        'general_quality_preservation_claim':False,'statistical_significance_claim':False,
        'novel_method_claim':False,'unseen_tasks_read':0,'manuscript_changed':False}


def make_plan(prior, closure, bound_sources):
    keep=('phase','source_plan','source_runs','known_tasks','max_calls','max_total_tokens','max_wall_seconds',
        'max_setup_seconds','max_cleanup_seconds','max_idle_wait_seconds','max_evaluation_seconds',
        'world_seed','model_seed','reserved_scenarios_read','novel_method_claim','history_policy',
        'catalog_policy','automatic_retries','error_policy','protocol_references','reasoning_budget_tokens',
        'time_visibility','fresh_seed_search','threshold_search','new_task_requirements_read',
        'shared_model_call_and_token_budget','summary_output_cap','summary_temperature',
        'unknown_summary_usage_policy','inline_checkpoint_requirement','same_call_results_summarized',
        'separate_semantic_judge','no_previous_replacement_or_retry','public_runtime_sha256',
        'read_views_enabled','trigger_input_tokens','retained_recent_turns','max_summary_characters','tool_choice')
    plan={k:deepcopy(prior[k]) for k in keep}
    plan.update(experiment='P123',batch_id='P123_batch_v01',checkpoint_policies=list(POLICIES),repetitions=1,
        max_cells=12,max_model_calls=960,max_reserved_tokens=5400000,
        max_reserved_environment_api_requests=1200,server_max_lifetime_seconds=32400,
        primary_question='rolling_inline_whole_task_cost_against_single_and_rolling_separate',
        required_closed_diagnostic='reports/P122_comparison.json',required_predecessor_phase='P122',
        rolling_checkpoint_max_opportunities=3,rolling_min_fresh_turns=3,
        single_checkpoint_max_opportunities=1,max_summary_calls_in_batch=16,
        max_inline_opportunities_in_batch=12,
        invalid_summary_policy='keep_current_view_charge_known_cost_require_three_fresh_turns',
        minimum_repeated_installations_per_rolling_policy=2,
        predecessor_closure=deepcopy(closure),source_sha256=deepcopy(bound_sources),
        scope_document='docs/experiments/P123_whole_task_rolling_checkpoint.md',
        conditions_selected_from_P122_outcomes=False,
        predecessor_review='reports/P122_review_for_fixed_P123.json',
        user_authorized_continuation_until_stop=True,additional_models_started_by_this_preparer=0)
    validate_plan(plan)
    return plan


def findings(report, checked):
    def yes(v):return '成功' if v is True else '失敗' if v is False else '未評価'
    lines=['# P122: 固定３設定の全件確認','',
        '既知４課題×２方式×３設定の24枠を、全実行と所有server閉鎖後に確認した. '
        '次のP123の方式と有限予算は、この結果を読む前の仕様から変更していない.','',
        '反復の採用基準: '+('達成' if checked['replication_gate_met'] else '未達')+'. '
        '写真の全３対で成功を保った削減: '+('確認' if checked['photo_reduction_repeated_with_success'] else '未確認')+'.','',
        '| 設定 | 課題 | 方式 | 最終結果 | 既知token | 不明要求 | 要約採用 |',
        '|---|---|---|---|---:|---:|---|']
    labels=dict(zip(TASKS,('写真','精算','返金','CSV')))
    for r in report['rows']:
        lines.append(f"| {r['model_seed']} | {labels[r['task_id']]} | "
            f"{'別要約' if r['checkpoint_policy']=='single_checkpoint' else '同時要約'} | {yes(r['success'])} | "
            f"{r.get('known_total_tokens')} | {r.get('unknown_usage_calls')} | {r.get('checkpoint_installed')} |")
    lines+=['','既知token欄は未知使用量を含む正確な総費用ではない. 失敗した実行の低費用を品質維持の改善としない. '
        'P120の以前の１組を主解析へ混ぜず、同じseedの差は既存の別表に残す.','',
        '| 課題 | 全３対の差の平均 | 最小 | 最大 | 標本標準偏差 | 全３対とも両側成功 |',
        '|---|---:|---:|---:|---:|---|']
    for task in checked['task_summaries']:
        stats=task['all_three_cost_differences']
        vals=[f'{stats[k]:.2f}' if stats and stats[k] is not None else '未確定'
              for k in ('mean','minimum','maximum','sample_standard_deviation')]
        lines.append('| '+labels[task['task_id']]+' | '+' | '.join(vals)+' | '+str(task['both_successful_in_all_three_pairs'])+' |')
    lines+=['','差は同時要約−別要約の全仕事token. ３対の記述統計で、誤差でないと断定する有意差検定や非劣性の証明ではない. '
        '24実行は４つの既知課題の反復であり、24個の独立課題とは数えない. 新規性、要約の意味保存、未見課題への一般化、採択可能性は未確立.','',
        'P123計画を固定できる運用条件: '+('成立' if checked['next_predeclared_comparison_may_be_bound'] else '未成立')+'. '
        'P123は単発別要約、反復別要約、反復同時要約の既定12条件で、成功の損失を許容せず総費用を比較する. '
        'モデル開始には別途同一headの両CIとnative事前計数が必要.','',
        '[全件資料](../materials/20261025_p122_results/README.md)／'
        '[再計算確認](../reports/P122_review_for_fixed_P123.json)／'
        '[次の固定仕様](experiments/P123_whole_task_rolling_checkpoint.md).','']
    return '\n'.join(lines)


def prepare(root, storage):
    # All reads below concern already closed, source-bound records.
    from run_whole_task_rolling_checkpoint import predecessor_closed
    closure=predecessor_closed(storage,root)
    report=read(root/'reports/P122_comparison.json')
    session=read(root/'reports/P122_server_session.json')
    overview=read(root/'materials/20261025_p122_results/summary.json')
    checked=review(report,session,overview)
    outputs=('reports/P122_review_for_fixed_P123.json','docs/P122_findings.md',
             'configs/P123_whole_task_rolling_checkpoint_v01.json')
    require(not any((root/n).exists() for n in outputs),'preserve_followup_preparation_attempt')
    manifest=read(root/'materials/20261025_p122_results/build_manifest.json')
    for rel,expected in manifest['source_sha256'].items():
        require(sha(root/rel)==expected,'P122_materials_source_changed')
    for name,expected in manifest['artifact_sha256'].items():
        require(sha(root/'materials/20261025_p122_results'/name)==expected,'P122_artifact_changed')
    sources=('reports/P122_comparison.json','reports/P122_server_session.json',
        'materials/20261025_p122_results/summary.json','materials/20261025_p122_results/build_manifest.json',
        'scripts/prepare_rolling_checkpoint_followup.py')
    checked.update(created_at=datetime.now(timezone.utc).isoformat(),predecessor_closure=closure,
                   source_sha256={n:sha(root/n) for n in sources})
    def new(rel,value):
        with (root/rel).open('x') as f:
            f.write(value if isinstance(value,str) else json.dumps(value,ensure_ascii=False,indent=2)+'\n')
    new(outputs[0],checked);new(outputs[1],findings(report,checked))
    if not checked['next_predeclared_comparison_may_be_bound']:
        return checked
    prior=read(root/'configs/P120_whole_task_required_inline_checkpoint_v01.json')
    paths=set(prior['source_sha256'])
    for base in ('scripts','tests'):
        paths.update(str(p.relative_to(root)) for p in (root/base).glob('*.py'))
    paths.update(sources)
    paths.update((*outputs[:2], 'configs/P120_whole_task_required_inline_checkpoint_v01.json',
        'configs/P122_checkpoint_replication_v01.json','reports/P120_pair_controls.json',
        'reports/rolling_checkpoint_core_preparation_20261025.json',
        'reports/rolling_checkpoint_live_preparation_20261025.json',
        'docs/experiments/P123_whole_task_rolling_checkpoint.md'))
    plan=make_plan(prior,closure,{n:sha(root/n) for n in sorted(paths)})
    new(outputs[2],plan)
    return checked


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--repo-root',type=Path,required=True)
    parser.add_argument('--storage-root',type=Path,required=True);args=parser.parse_args()
    value=prepare(args.repo_root,args.storage_root)
    print(json.dumps({k:value[k] for k in ('all_slots_reviewed','replication_gate_met',
        'photo_reduction_repeated_with_success','next_predeclared_comparison_may_be_bound')}))
