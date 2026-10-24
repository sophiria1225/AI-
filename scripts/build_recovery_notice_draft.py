"""Prepare a fresh paper edition only from the closed, audited P97 cohort."""
import argparse
from datetime import datetime, timezone
from pathlib import Path

import build_recovery_notice_report as evidence
from build_whole_task_reasoning_budget_draft import number, table, tex_cost
from recovery_notice_comparison import POLICIES, cell_id, run_order
from run_context_comparison import write_json
from run_handoff_factors import ROOT, read, sha

FOLDER = 'papers/202610_letter/recovery_notice_observed'
LABEL = dict(none='N',generic='G',factual='F')
TASKS = ('写真','精算','返金','書出し')
SUPPORT = ('scripts/build_recovery_notice_draft.py','scripts/build_recovery_notice_report.py',
           'scripts/build_whole_task_reasoning_budget_draft.py','scripts/render_bound_letter_draft.py',
           'docs/experiments/P97_recovery_notice_comparison.md',
           'docs/P97_manuscript_preparation_20261024.md',
           'reports/P97_manuscript_sources_20261024.json',
           'reports/P96_auth_origin_observations.json',
           'docs/auth_origin_repeat_scope_20261024.md',
           'docs/ordinary_completion_literature_20261023.md')


def abstracts(report):
    evaluated=sum(r['record_status']=='evaluated' for r in report['rows'])
    if not report['all_twelve_evaluated_with_known_usage']:
        ja_result='欠測または未評価が残り，全件の費用差は確定できなかった.'
        en_result='Missing usage or evaluations prevented a complete cost comparison.'
    elif report['factual_notice_benefit_gate_met']:
        ja_result='事実通知は両対照に対する成功と全費用の固定基準を満たした.'
        en_result='The factual notice met the fixed joint outcome and cost criteria against both controls.'
    else:
        ja_result='事実通知は成功と全費用の固定基準を満たさなかった.'
        en_result='The factual notice did not meet the fixed joint outcome and cost criteria.'
    ja=('状態保持型LLMエージェントの通常回復通知を既知４課題12条件で比較した. ' if evaluated==12
        else '状態保持型LLMエージェントの通常回復通知比較を既知４課題12条件で計画した. ')
    en=('We compared' if evaluated==12 else 'We planned to compare')+' ordinary recovery notices across twelve conditions on four known tasks in a stateful LLM agent. '
    ja+=ja_result+' 検出対象は１課題で，一般的な品質維持は未検証である.'
    en+=en_result+' Only one task contained monitored APIs; general quality preservation remains untested.'
    if len(ja)>120 or len(en.split())>50 or any(c in ja for c in ('。','・')):
        raise ValueError('abstract_limits_or_punctuation')
    return ja,en


def signed(value):
    return '未確定' if value is None else f'{value:+,}'


def outcome(row):
    if row['record_status']=='not_run':return '未実行'
    if row['record_status']!='evaluated':return '未評価'
    return '成功' if row['success'] else '未達'


def quality_status(pair):
    if any(r['left_success'] is True and r['right_success'] is False for r in pair['tasks']):
        return '喪失あり'
    if any(type(r['left_success']) is not bool or type(r['right_success']) is not bool for r in pair['tasks']):
        return '未確認'
    return '喪失なし'


def sections(report,session,notices):
    rows=report['rows'];aggregate=[evidence.totals(rows,p) for p in POLICIES]
    cells={r['run_id']:r for r in rows}
    full=table(('課題','条件','成果','論理token','生成','API'),'lllrrr',[
        (TASKS[n-1],LABEL[p],outcome(cells[cell_id(n,p)]),tex_cost(cells[cell_id(n,p)]),
         number(cells[cell_id(n,p)].get('model_calls')),number(cells[cell_id(n,p)].get('api_requests')))
        for n,p in run_order()],
        '固定した全12条件．$+?$は既知小計に使用量不明の生成が残ることを示す．')
    full+='各条件の成功／評価は'+ '，'.join(LABEL[a['notice_policy']]+'が'+str(a['successes'])+'/'+str(a['evaluated']) for a in aggregate)+'であった．\n'
    full+='CSVの最終結果は'+ '，'.join(LABEL[p]+'が'+outcome(cells[cell_id(4,p)]) for p in POLICIES)+'であった．\n'
    full+=table(('比較','課題別成功','全論理token差','固定基準'),'llrl',[
        (LABEL[p['right']]+'−'+LABEL[p['left']],
         quality_status(p),signed(p['aggregate_token_difference']),
         '達成' if p['ordinary_control_gate_met'] else '未達') for p in report['pairs']],
        '全４課題を含む３対照．欠測時は既知分だけで全費用差を確定しない．')
    matched=len(report['matched_before_notice_tasks'])
    full+='G/Fの通知前の入力と予算が一致し，両側で送信を試行した課題数は'+str(matched)+'であった．'
    full+='事実通知の便益候補の固定基準は'+('達成した' if report['factual_notice_benefit_gate_met'] else '未達だった')+'．これは新手法の優位性や統計的な非劣性の判定ではない．\n'
    groups=dict(both_successful='両成功',both_failed='両未達',discordant='成否差',unevaluated='未評価あり')
    full+=table(('比較','成否の組合せ','課題数','論理token差'),'llrr',[
        (LABEL[p['right']]+'−'+LABEL[p['left']],groups[p['group']],p['task_count'],signed(p['right_minus_left_tokens']))
        for p in evidence.contributions(report)],
        '失敗を含む費用寄与．全12条件の使用量が確定したときだけ全体差を分解する．')
    full+='未達を安く終えた差を，完了した仕事の効率改善に読み替えない．未実行・未評価を未達で補完せず，欠測は残した．\n'
    monitor={r['run_id']:r for r in notices['rows']}
    detection=table(('課題','条件','候補境界 E/S/O','通知の送信試行'),'llll',[
        (TASKS[n-1],LABEL[p],
         '/'.join(str(monitor[cell_id(n,p)]['candidate_counts'][m]) for m in
                  ('exact','drop_auth_argument','login_request_origin'))
             if monitor[cell_id(n,p)].get('record_present') else '未計測',
         ','.join(x['next_call_id'].replace('call_','') for x in monitor[cell_id(n,p)].get('offers',[]) if x['model_attempted']) or 'なし')
        for n,p in run_order()],
        '全12枠の候補と送信試行．Eは完全一致，Sは認証引数除外，Oはlogin要求の由来群．')
    detection+='入力計数だけを行って予算で拒否された通知は送信試行へ数えない．試行したという記録と，推論器が返答を完了したことも区別する．観測処理の小計は保存・通知構成を含む全制御費用ではない．\n'
    resource=table(('計測','N','G','F'),'lrrr',[
        (label,*[number(a[key]) for a in aggregate]) for key,label in
        [('known_total_tokens','既知論理token'),('cached_input_tokens','既知cache入力'),
         ('known_uncached_input_tokens','既知cache除外入力'),('output_tokens','既知出力token'),
         ('unknown_usage_calls','使用量不明生成'),('model_calls','生成試行'),('api_requests','API送信')]],
        '通知・失敗・回復を含む既知小計．不明使用量を０とはしない．')
    resource+='所有推論器は'+number(session['wall_seconds'],3)+'秒稼働し，うちロード'+number(session['load_wall_seconds'],3)+'秒，独立評価'+number(session['evaluation_wall_seconds'],3)+'秒だった．'
    resource+='計測済みセルの準備・作業・後片付けは'+number(session['cell_full_wall_seconds'],3)+'秒，未計測セルは'+number(session['unmeasured_condition_count'])+'件だった．'
    resource+='推論器の最大実測RSSは'+number(session['sampled_peak_rss_bytes']/2**30,2)+' GiB，最大システムswapは'+number(session['peak_system_swap_bytes']/2**30,2)+' GiBであった．'
    resource+='重なる時間を二重加算せず，論理tokenやRSSをFLOPs・料金・GPU全体の使用量へ換算しない．\n'
    return dict(whole_task=full,detection=detection,resources=resource)


def build(root=ROOT):
    target=root/FOLDER
    if target.exists():raise FileExistsError('preserve_recovery_notice_paper')
    plan,report,pre,activation,session,notices=evidence.validated(root)
    ja,en=abstracts(report);generated={k+'.tex':v for k,v in sections(report,session,notices).items()}
    template='papers/202610_letter/templates/recovery_notice_letter.tex'
    source=(root/template).read_text()
    if any(source.count(marker)!=1 for marker in ('@@JA@@','@@EN@@','@@CONCLUSION@@')):
        raise ValueError('unique_abstract_placeholders_required')
    evaluated=sum(r['record_status']=='evaluated' for r in report['rows'])
    conclusion=('再観測の事実を用いる通知を，通知なし・一般的な見直し通知と比較する全12条件を計画し，'
        +str(evaluated)+'条件の独立評価を得た．'
        +'全予定枠を残し，全仕事の成否・費用，成功と未達の寄与，検出候補と送信試行を区別した．'
        +'事実通知の便益候補の固定基準は'+('達成した' if report['factual_notice_benefit_gate_met'] else '未達だった')+'．'
        +'通常対照の結果を新手法の成立へ置き換えず，既知４課題の結果を他課題の品質保証へ一般化しない．')
    source=source.replace('@@JA@@',ja).replace('@@EN@@',en).replace('@@FOLDER@@',FOLDER).replace('@@CONCLUSION@@',conclusion)
    generated['draft.tex']=source
    sources=dict(pre['source_hashes'])
    for name in (*evidence.FILES,*SUPPORT,template):
        sources[name]=sha(root/name)
    for name,expected in sources.items():
        if sha(root/name)!=expected:raise ValueError('closed_source_changed:'+name)
    target.mkdir(parents=True,exist_ok=False)
    for name,value in generated.items():(target/name).write_text(value)
    write_json(target/'build_manifest.json',dict(generated_at=datetime.now(timezone.utc).isoformat(),
        source_sha256=sources,generated_sha256={n:sha(target/n) for n in generated},
        all_planned_rows=12,independent_tasks=4,detector_in_scope_tasks=1,repetitions=1,
        factual_notice_benefit_gate_met=report['factual_notice_benefit_gate_met'],
        additional_model_generations=0,additional_environment_api_requests=0,additional_evaluations=0,
        reserved_scenarios_read=0,novel_method_established=False,general_quality_preservation_established=False,
        P97_results_closed=True,visual_reviewed=False,official_class_verified=False,submission_ready=False))
    print(dict(folder=FOLDER,all_planned_rows=12,ja_characters=len(ja),en_words=len(en.split())))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--repo-root',type=Path,default=ROOT)
    args=parser.parse_args();build(args.repo_root.resolve())
