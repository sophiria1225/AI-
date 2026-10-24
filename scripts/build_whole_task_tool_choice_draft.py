"""Build a separate P99 letter draft only from the closed, audited cohort."""
import argparse
from datetime import datetime, timezone
import re
from pathlib import Path

import build_whole_task_tool_choice_report as evidence
from whole_task_tool_choice import POLICIES, cell_id, run_order
from run_handoff_factors import ROOT, read, sha

FOLDER = 'papers/202610_letter/tool_choice_observed'
PRIOR_DRAFT = 'papers/202610_letter/execution_evidence_cohort/draft.tex'
TEMPLATE = 'papers/202610_letter/templates/tool_choice_letter.tex'
SUPPORT = (PRIOR_DRAFT, TEMPLATE, 'scripts/build_whole_task_tool_choice_report.py',
    'scripts/build_whole_task_tool_choice_draft.py', 'scripts/render_bound_letter_draft.py',
    'docs/experiments/P99_whole_task_tool_choice.md',
    'docs/P99_manuscript_preparation_20261024.md', 'reports/P99_manuscript_sources_20261024.json',
    'reports/P98_recorded_action_agreement.json', 'materials/20261024_p98_results/summary.json')
TASKS = ('写真', '精算', '返金', '書出し')


def number(value, decimals=0):
    return '未計測' if value is None else f'{value:,.{decimals}f}'


def tex_cost(row):
    if row.get('known_total_tokens') is None:
        return '未計測'
    text = f"{row['known_total_tokens']:,}"
    if row.get('unknown_usage_calls'):
        text += '$+?$'
    if row.get('unmeasured'):
        text += '（未計測あり）'
    return text


def abstracts(report):
    evaluated=sum(r['record_status']=='evaluated' for r in report['rows'])
    if not report['all_eight_complete_with_known_usage']:
        ja_result='欠測または未評価が残り，全仕事費用差は確定できなかった.'
        en_result='Missing usage or evaluations prevented a complete cost comparison.'
    elif report['development_gate_met']:
        ja_result='必須提出は課題ごとの成功喪失なく全論理費用を削減した.'
        en_result='Requiring tool submissions reduced aggregate logical cost without per-task success loss.'
    else:
        ja_result='必須提出は品質と全費用の事前採用基準を満たさなかった.'
        en_result='Requiring tool submissions did not satisfy the predefined joint quality and cost criteria.'
    ja=('状態保持型LLMエージェントの通常ツール提出設定を既知４課題８条件で比較した. ' if evaluated==8
        else '状態保持型LLMエージェントの通常ツール提出比較を既知４課題８条件で計画した. ')
    en=('We compared' if evaluated==8 else 'We planned to compare')+' ordinary tool-choice settings across eight conditions on four known tasks in a stateful LLM agent. '
    ja+=ja_result+' 一般的な品質維持は未検証である.'
    en+=en_result+' General quality preservation remains untested.'
    if len(ja)>120 or len(en.split())>50 or any(c in ja for c in ('。','・')):
        raise ValueError('abstract_limits_and_punctuation')
    return ja,en


def table(header, columns, rows, caption):
    lines = [r'\begin{table}[tb]', r'\centering\footnotesize\setlength{\tabcolsep}{3pt}',
        r'\caption{'+caption+'}', r'\begin{tabular}{'+columns+'}', ' & '.join(header)+r' \\ \hline']
    lines += [' & '.join(str(v) for v in row)+r' \\' for row in rows]
    return '\n'.join(lines+[r'\hline\end{tabular}', r'\end{table}'])+'\n'


def sections(plan, report, session):
    rows = report['rows']; aggregate = [evidence.totals(rows, p) for p in POLICIES]
    data = []
    for n, policy in run_order():
        row = next(r for r in rows if r['run_id'] == cell_id(n, policy))
        result = '成功' if row['success'] is True else ('未達' if row['record_status'] == 'evaluated' else '未評価')
        if row['record_status'] == 'not_run': result = '未実行'
        data.append((TASKS[n-1], 'A' if policy == 'auto' else 'R', result, tex_cost(row),
                     number(row.get('model_calls')), number(row.get('api_requests'))))
    full = table(('課題','条件','成果','論理token','生成','API'), 'lllrrr', data,
        '予定した全８条件．$+?$は既知小計に使用量不明の生成が残ることを表す．')
    full += '成功／評価はAが'+str(aggregate[0]['successes'])+'/'+str(aggregate[0]['evaluated'])+'，Rが'+str(aggregate[1]['successes'])+'/'+str(aggregate[1]['evaluated'])+'であった．'
    full += '課題ごとの成功喪失は'+number(report['paired_success_losses'])+'，成功獲得は'+number(report['paired_success_gains'])+'である．'
    full += 'Aの全仕事tokenは'+tex_cost(aggregate[0])+'，Rは'+tex_cost(aggregate[1])+'であった．\n'
    delta = report['required_minus_auto_whole_task_tokens']
    full += ('全４課題のR−Aは'+f'{delta:+,}'+' tokenであった．' if delta is not None
             else '欠測または未評価があるため，固定した全件比較の費用差は未確定とする．')
    full += ('固定した開発上の採用基準を満たした．' if report['development_gate_met']
             else '固定した開発上の採用基準は満たさなかった．')+'\n'
    parts = evidence.contributions(report)
    full += table(('成否の組合せ','課題数','R−A token'), 'lrr', [
        (label, parts[key]['task_count'], evidence.signed(parts[key]['required_minus_auto_tokens']))
        for key,label in [('both_successful','両側成功'), ('both_failed','両側未達'),
                          ('discordant','成否が異なる'), ('unevaluated','片側以上が未評価')]],
        '全課題の費用寄与．全件既知でないときは全体の寄与を確定しない．')
    csv_rows=[r for r in rows if r['task_id']==plan['known_tasks'][3]['task_id']]
    full += 'CSV課題は'+ '，'.join(('A' if r['tool_choice_policy']=='auto' else 'R')+'が'+('成功' if r['success'] is True else '未達' if r['record_status']=='evaluated' else '未評価') for r in csv_rows)+'であった．'
    full += '未達の費用も残し，成功部分のみの減少を全体の改善としない．未評価・未実行は未達として補完しない．\n'
    resource = table(('計測対象','A','R'), 'lrr', [
        (label, number(aggregate[0][key], digits), number(aggregate[1][key], digits))
        for key,label,digits in [('input_tokens','既知全入力token',0),
            ('cached_input_tokens','既知入力のcache分',0), ('known_uncached_input_tokens','既知cache除外入力',0),
            ('output_tokens','既知出力token',0), ('unknown_usage_calls','使用量不明の生成',0),
            ('wall_seconds','作業秒',2)]], '費用を異なる尺度で記録する．既知小計は不明生成の使用量を含まない．')
    resource += (f"所有推論器の稼働は{session['wall_seconds']:,.2f}秒，うちロードは{session['load_wall_seconds']:,.2f}秒であった．"
        f"全条件の初期化・作業・後片付けは{session['cell_full_wall_seconds']:,.2f}秒，独立評価は{session['evaluation_wall_seconds']:,.2f}秒であり，稼働時間と重複するため加算しない．"
        f"最大実測RSSは{session['sampled_peak_rss_bytes']/2**30:,.2f} GiB，最大システムswapは{session['peak_system_swap_bytes']/2**30:,.2f} GiBであった．"
        'RSSをGPU使用量全体とは解釈しない．\n')
    if report['development_gate_met']:
        conclusion = ('通常の必須提出設定は，この既知４課題では課題ごとの成功喪失なく全論理費用を減らした．'
            'これは新しい制約復号アルゴリズムの提案ではなく，固定した通常対照の開発結果である．')
    elif report['all_eight_complete_with_known_usage']:
        conclusion = ('通常の必須提出設定は，固定した品質と全費用の共同基準を満たさなかった．'
            '提出設定だけで仕事全体の効率改善が成立するとは結論できない．')
    else:
        conclusion = ('使用量の欠測または未評価・未実行を含む全８枠を保持した．'
            '全件比較の費用差は確定せず，通常の必須提出による全仕事改善は未確立である．')
    conclusion += '課題の正しさと，局所的な出力完成，論理token，cache，時間を区別し，一般的な品質維持は今後の独立した確認を要する．\n'
    formats=[evidence.format_totals(rows,p) for p in POLICIES]
    submission=table(('観測単位','A','R'),'lrr',[
        (label,*[number(r[key]) for r in formats]) for key,label in [
            ('known_responses','応答既知の生成'),('unknown_responses','応答不明の生成'),
            ('known_no_tool_generations','既知で提出なし'),('known_length_generations','既知で上限到達'),
            ('format_rejections','形式拒否の記録'),('Python_execution_errors','Python例外の記録'),
            ('not_executed_records','提出後未実行の記録')]],
        '生成数と外側の実行記録数は異なる単位．不明応答を提出なしへ数えない．')
    submission+='出力上限到達と形式拒否は重なり得る．構造化提出にPython例外やAPI送信が含まれる場合があり，形式の改善を最終成果の代替にしない．全生成記録と全API送信の対応を監査した．\n'
    return {'whole_task.tex':full,'resources.tex':resource,'submission.tex':submission,'conclusion.tex':conclusion}




def bibliography(source):
    retained={}
    for key in ('codeact','appworld','canonical','costproxy','consistency'):
        found=re.findall(r'\\bibitem\{'+key+r'\}[^\n]+',source)
        if len(found)!=1:raise ValueError('one_verified_bibliography_entry_required:'+key)
        retained[key]=found[0]
    retained.update(gcd=r"\bibitem{gcd} S. Geng, M. Josifoski, M. Peyrard, and R. West, ``Grammar-constrained decoding for structured NLP tasks without finetuning,'' Proc. EMNLP, pp.10932--10952, Singapore, Dec. 2023, doi:10.18653/v1/2023.emnlp-main.674.",
        gad=r"\bibitem{gad} K. Park, J. Wang, T. Berg-Kirkpatrick, N. Polikarpova, and L. D'Antoni, ``Grammar-aligned decoding,'' Advances in Neural Information Processing Systems, vol.37, 2024, doi:10.52202/079017-0774.",
        backend=r"\bibitem{backend} ggml-org, ``llama.cpp: MiniMax-M3 parser,'' commit 620d2225cc436ab0b001e3200e590e3b286ef9ab, \url{https://github.com/ggml-org/llama.cpp/blob/620d2225cc436ab0b001e3200e590e3b286ef9ab/common/parsers/minimax-m3.cpp}, accessed Oct. 24, 2026.")
    return '\n'.join(retained[k] for k in ('codeact','appworld','gcd','gad','backend','canonical','costproxy','consistency'))


def build(root=ROOT):
    folder=root/FOLDER
    if folder.exists():raise FileExistsError('preserve_P99_draft_attempt')
    plan,report,pre,session,_=evidence.validated(root)
    prior=read(root/'reports/P98_recorded_action_agreement.json')
    inventory=read(root/'materials/20261024_p98_results/summary.json')
    expected=dict(total_recorded_calls=426,unknown_response_calls=4,no_structured_tool_calls=21,
                  structured_but_not_completed_calls=4,completed_submission_calls=397,independent_known_tasks=4)
    if (prior['status']!='complete' or len(prior['rows'])!=24
            or inventory['source_sha256']!=sha(root/'reports/P98_recorded_action_agreement.json')
            or any(inventory.get(k)!=v for k,v in expected.items())):
        raise ValueError('closed_P98_motivation_required')
    generated=sections(plan,report,session);ja,en=abstracts(report)
    text=(root/TEMPLATE).read_text()
    for marker,value in [('@@JA@@',ja),('@@EN@@',en),('@@BIB@@',bibliography((root/PRIOR_DRAFT).read_text()))]:
        if text.count(marker)!=1:raise ValueError('one_template_marker_required')
        text=text.replace(marker,value)
    text=text.replace('@@FOLDER@@',FOLDER);generated['draft.tex']=text
    sources=dict(pre['source_hashes'])
    sources.update({n:sha(root/n) for n in (*evidence.FILES,*SUPPORT)})
    for n,h in sources.items():
        if sha(root/n)!=h:raise ValueError('closed_source_changed:'+n)
    folder.mkdir(parents=True,exist_ok=False)
    for name,value in generated.items():(folder/name).write_text(value)
    manifest=dict(generated_at=datetime.now(timezone.utc).isoformat(),source_sha256=sources,
        generated_sha256={n:sha(folder/n) for n in generated},all_planned_rows=8,independent_tasks=4,repetitions=1,
        development_gate_met=report['development_gate_met'],P98_motivation_records=426,P99_results_closed=True,
        unknown_usage_imputed=False,novel_method_claim=False,general_quality_preservation_claim=False,
        authors_confirmed=False,official_journal_class=False,submission_ready=False,professor_brief_changed=False,
        visual_reviewed=False,additional_generations=0,additional_api_requests=0,additional_evaluations=0,reserved_scenarios_read=0)
    import json
    (folder/'build_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    print(dict(folder=FOLDER,ja_characters=len(ja),en_words=len(en.split()),all_planned_rows=8,development_gate_met=report['development_gate_met']))
    return manifest


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--repo-root',type=Path,default=ROOT)
    args=p.parse_args();build(args.repo_root.resolve())
