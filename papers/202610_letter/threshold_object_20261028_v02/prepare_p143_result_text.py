"""Generate reviewable result table/text only after closed P143 input approval.

Does not modify manuscript, abstract, conclusion or figures. Does not decide
acceptance: fixed summary criteria are reproduced and independently recomputed
scalar comparisons are checked. Root reviews before any manuscript insertion.
"""
import argparse
import hashlib
import json
from pathlib import Path
from figures.p143_cost_source import load_closed, require, TASKS, LABELS, MODES

JAPANESE_TASKS = ('写真操作', '精算', '返金', 'CSV処理')


def total(values):
    return sum(values) if all(type(v) is int for v in values) else None


def text_number(value):
    return '未確定' if value is None else f'{value:,}'


def derive(summary, rows):
    comparison = summary['comparisons']
    require(type(comparison) is list and len(comparison) == 1, 'one_fixed_comparison_required')
    comparison = comparison[0]
    require(comparison['baseline'] == MODES[0] and comparison['candidate'] == MODES[1], 'comparison_mode_mismatch')
    complete = all(r['exact_total'] is not None for r in rows)
    sums = {mode: total([r['exact_total'] for r in rows if r['mode'] == mode]) for mode in ('TR','TDO')}
    known = {mode:sum(r['known_subtotal'] for r in rows if r['mode'] == mode and r['known_subtotal'] is not None)
             for mode in ('TR','TDO')}
    success = {mode:sum(r['outcome'] == 'Success' for r in rows if r['mode'] == mode) for mode in ('TR','TDO')}
    evaluated = {mode:sum(r['record_status'] == 'evaluated' for r in rows if r['mode'] == mode) for mode in ('TR','TDO')}
    losses, common = [], []
    for task_id,label in zip(TASKS,LABELS):
        a,b=[r for r in rows if r['task'] == label]
        if a['outcome'] == 'Success' and b['outcome'] == 'Failed':losses.append(task_id)
        if a['outcome'] == b['outcome'] == 'Success':common.append(task_id)
    difference = sums['TDO']-sums['TR'] if complete else None
    common_difference = sum(b['exact_total']-a['exact_total'] for t,a,b in
        [(t,rows[2*i],rows[2*i+1]) for i,t in enumerate(TASKS)] if t in common) if complete and common else None
    require(summary['all_eight_complete_with_known_usage'] is complete
        and comparison['all_task_token_difference'] == difference
        and comparison['common_success_token_difference'] == common_difference
        and comparison['success_loss_tasks'] == losses
        and comparison['common_success_tasks'] == common, 'fixed_summary_comparison_mismatch')
    require(summary['success_counts'] == dict(zip(MODES,(success['TR'],success['TDO']))), 'success_count_mismatch')
    for key in ('observed_utility_criteria_met','comparison_gate_met'):
        require(type(comparison.get(key)) is bool, 'fixed_boolean_criterion_required')
    require(summary['development_gate_met'] is comparison['comparison_gate_met'], 'fixed_gate_mismatch')
    pct = 100*difference/sums['TR'] if complete and sums['TR'] else None
    reported_pct = comparison['all_task_token_difference_pct']
    require((pct is None and reported_pct is None) or
        (type(reported_pct) in (int,float) and abs(pct-reported_pct)<1e-9), 'percentage_mismatch')
    source_rows = summary['conditions']
    candidate = [r for r in source_rows if r['object_timing_mode'] == MODES[1]]
    activity = {key:total([r.get(key) for r in candidate]) for key in
        ('object_prompt_known_focus_calls','actual_delta_known_actor_calls','delta_installations')}
    activated = [r['task_id'] for r in candidate if type(r.get('actual_delta_known_actor_calls')) is int and r['actual_delta_known_actor_calls'] > 0]
    return dict(activated_tasks=activated,complete=complete,evaluated=evaluated,success=success,
        exact_totals=(sums if complete else {'TR':None,'TDO':None}),known_subtotals=known,unknown_calls=total([r['unknown_calls'] for r in rows]),
        recorded_unknown_calls=sum(r['unknown_calls'] for r in rows if r['unknown_calls'] is not None),
        missing_usage_conditions=sum(r['known_subtotal'] is None for r in rows),
        observed_success_losses=losses,common_success_tasks=common,all_task_difference=difference,
        all_task_difference_pct=pct,common_success_difference=common_difference,activity=activity,
        observed_utility_criteria_met=comparison['observed_utility_criteria_met'],
        development_gate_met=summary['development_gate_met'],rows=rows)


def make_tex(data):
    lines = [r'\subsection{課題別の成否と費用}',
        r'表\ref{tab:p143-cells}と図\ref{fig:p143-cost}に全8条件を示す．',
        r'\begin{table*}[t]',r'\caption{課題別の成否と論理入出力．不明使用量は既知小計と区別する．}',
        r'\ecaption{Task outcomes and logical input/output. Known subtotals are distinguished from unknown usage.}',
        r'\label{tab:p143-cells}',r'\centering',r'\begin{tabular}{llrrrl}',r'\hline',
        (r'課題 & 方式 & 最終成否 & 既知token小計 & 不明呼出し & 差分付きactor \\ \hline' if data['complete'] else r'課題 & 方式 & 最終成否 & 既知token小計 & 不明呼出し & 評価・会計 \\ \hline')]
    for n,r in enumerate(data['rows']):
        task=JAPANESE_TASKS[n//2]
        outcome={'Success':'成功','Failed':'失敗','Unevaluated':'未評価'}[r['outcome']]
        usage = '未測定' if r['known_subtotal'] is None else text_number(r['known_subtotal'])
        unknown = '未確認' if r['unknown_calls'] is None else str(r['unknown_calls'])
        state = '確定' if r['exact_total'] is not None else ('未完・未測定' if r['known_subtotal'] is None else '既知小計')
        last = text_number(r.get('delta_known_actor_calls')) if data['complete'] else state
        lines.append(f"{task} & {r['mode']} & {outcome} & {usage} & {unknown} & {last}"+r'\\')
    lines += [r'\hline',r'\end{tabular}',r'\end{table*}',
        r'\begin{figure*}[t]',r'\centering',r'\includegraphics[width=130mm]{figures/p143_cost.pdf}',
        r'\caption{全8条件のactor・focus別論理入出力と最終成否．斜線は確定総費用ではない既知小計を示す．}',
        r'\ecaption{Logical input/output by role and final outcomes. Hatched bars denote known lower bounds.}',
        r'\label{fig:p143-cost}',r'\end{figure*}',r'\subsection{品質と全費用の比較}']
    lines.append(f"成功はTRが{data['success']['TR']}/4課題（評価{data['evaluated']['TR']}件），"
                 f"TDOが{data['success']['TDO']}/4課題（評価{data['evaluated']['TDO']}件）だった．")
    if sum(data['evaluated'].values()) == 8:
        lines.append(f"TRの成功をTDOが失った課題は{len(data['observed_success_losses'])}件，"
                     f"共通成功は{len(data['common_success_tasks'])}件だった．")
    else:
        lines.append(f"観測された成功喪失は{len(data['observed_success_losses'])}件，共通成功は"
                     f"{len(data['common_success_tasks'])}件である．未評価を含むため全4対の品質保持は確定しない．")
    if data['complete']:
        delta = data['all_task_difference'];pct = data['all_task_difference_pct']
        direction = '増加' if delta > 0 else '減少' if delta < 0 else '差なし'
        percentage = '' if pct is None else f"（{abs(pct):.2f}\\%）"
        lines.append(f"全4課題の費用はTR {data['exact_totals']['TR']:,}，TDO {data['exact_totals']['TDO']:,}トークンで，"
                     f"TDOは{abs(delta):,}トークン{percentage}の{direction}だった．")
        if data['common_success_tasks']:
            lines.append(f"共通成功課題のTDO$-$TR費用差は{data['common_success_difference']:+,}トークンだった．")
        else:
            lines.append('共通成功課題がないため，その費用差は定義しない．')
    else:
        lines.append(f"既知小計はTR {data['known_subtotals']['TR']:,}，TDO {data['known_subtotals']['TDO']:,}トークンである．"
                     f"記録上の使用量不明は{data['recorded_unknown_calls']}呼出し，費用未測定は{data['missing_usage_conditions']}条件あり，"
                     '全体および共通成功集合の確定費用差・削減率は算出しない．')
    lines.append(r'\subsection{処置への到達と解釈}')
    a=data['activity']
    lines.append(f"TDOの既知object focus送信は{text_number(a['object_prompt_known_focus_calls'])}件，"
                 f"差分採用は{text_number(a['delta_installations'])}件，差分を含む既知actor呼出しは"
                 f"{text_number(a['actual_delta_known_actor_calls'])}件だった．")
    names = '，'.join(JAPANESE_TASKS[TASKS.index(t)] for t in data['activated_tasks']) or '該当なし'
    lines.append(f"差分を含む既知actor入力が観測された課題は{len(data['activated_tasks'])}/4件（{names}）である．非発動課題の成功を差分処置の効果例には数えない．")
    utility='成立' if data['observed_utility_criteria_met'] else '不成立'
    gate='成立' if data['development_gate_met'] else '不成立'
    lines.append(f"固定した集計上の効用条件は{utility}，介入確認を含む開発条件は{gate}だった．")
    lines.append('% ROOT REVIEW: Add source-bound explanation of role costs, prefix evidence and failures here.\n'
                 '% This generated text does not certify the audit or establish general efficacy/novelty.')
    return '\n'.join(lines)+'\n'


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input-dir',type=Path,required=True)
    p.add_argument('--manifest-sha256',required=True);p.add_argument('--summary-sha256',required=True)
    p.add_argument('--closed-inputs-approved',action='store_true')
    p.add_argument('--output-dir',type=Path,required=True)
    args=p.parse_args()
    rows,inputs,summary=load_closed(args.input_dir,args.manifest_sha256,args.summary_sha256,args.closed_inputs_approved)
    data=derive(summary,rows);tex=make_tex(data)
    args.output_dir.mkdir(parents=True,exist_ok=False)
    for name,value in [('results_p143.tex',tex),('result_table_data.json',json.dumps(data,ensure_ascii=False,indent=2,allow_nan=False)+'\n')]:
        with (args.output_dir/name).open('x') as f:f.write(value)
    record=dict(inputs=inputs,generator_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        loader_sha256=hashlib.sha256((Path(__file__).parent/'figures/p143_cost_source.py').read_bytes()).hexdigest(),
        artifacts={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in args.output_dir.iterdir()},
        manuscript_not_modified=True,abstract_conclusion_require_root_review=True,
        scientific_audit_recertified=False,additional_model_calls=0)
    with (args.output_dir/'text_generation_manifest.json').open('x') as f:json.dump(record,f,indent=2);f.write('\n')
    print(json.dumps({'status':'prepared_for_review','conditions':len(rows)}))

if __name__ == '__main__':main()
