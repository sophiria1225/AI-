"""Build a separate P88 letter draft only from the closed, audited cohort."""
import argparse
from datetime import datetime, timezone
import re
from pathlib import Path

import build_whole_task_reasoning_budget_report as evidence
from whole_task_reasoning_budget import POLICIES, cell_id, run_order
from run_handoff_factors import ROOT, read, sha

FOLDER = 'papers/202610_letter/reasoning_budget_control'
PRIOR_DRAFT = 'papers/202610_letter/closed_results_final/draft.tex'
SUPPORT = ('reports/output_budget_backend_scope_20261024.json',
           'reports/output_budget_prior_sources_20261024.json',
           'reports/weekend_claim_boundary_sources_20261024.json',
           'docs/weekend_decision_20261024.md',
           'reports/P87_fixed_reasoning_budget_replay.json',
           'reports/P88_start_provenance_20261024.json', PRIOR_DRAFT,
           'scripts/build_whole_task_reasoning_budget_report.py',
           'scripts/build_whole_task_reasoning_budget_draft.py',
           'scripts/render_bound_letter_draft.py')
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
    if not report['all_eight_complete_with_known_usage']:
        ja_result = '使用量の欠測または未評価が残り, 全仕事費用差は確定できなかった.'
        en_result = 'Missing usage or evaluations prevented identifying the complete cohort cost difference.'
    elif report['development_gate_met']:
        ja_result = '固定2,048指定は課題ごとの成功喪失なく全論理費用を削減した.'
        en_result = 'A fixed 2,048-token reasoning-block budget reduced aggregate logical cost without a per-task success loss.'
    else:
        ja_result = '固定2,048指定は品質と全費用の事前採用基準を満たさなかった.'
        en_result = 'A fixed 2,048-token reasoning-block budget did not satisfy the predefined joint quality and cost criteria.'
    ja = '状態保持型LLMエージェントの通常推論予算を既知４課題８条件で比較した. '+ja_result+' 一般的な品質維持は未検証である.'
    en = 'We compared ordinary reasoning budgets across eight conditions on four known tasks in a stateful LLM agent. '+en_result+' These development results do not establish general quality preservation.'
    if len(ja) > 120 or len(en.split()) > 50 or any(c in ja for c in ('。', '・')):
        raise ValueError('abstract_limits_and_punctuation')
    return ja, en


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
        data.append((TASKS[n-1], 'U' if policy == 'unlimited' else 'H', result, tex_cost(row),
                     number(row.get('model_calls')), number(row.get('api_requests'))))
    full = table(('課題','条件','成果','論理token','生成','API'), 'lllrrr', data,
        '予定した全８条件．$+?$は既知小計に使用量不明の生成が残ることを表す．')
    full += '成功／評価はUが'+str(aggregate[0]['successes'])+'/'+str(aggregate[0]['evaluated'])+'，Hが'+str(aggregate[1]['successes'])+'/'+str(aggregate[1]['evaluated'])+'であった．'
    full += '課題ごとの成功喪失は'+number(report['paired_success_losses'])+'，成功獲得は'+number(report['paired_success_gains'])+'である．'
    full += 'Uの全仕事tokenは'+tex_cost(aggregate[0])+'，Hは'+tex_cost(aggregate[1])+'であった．\n'
    delta = report['half_minus_unlimited_whole_task_tokens']
    full += ('全４課題のH−Uは'+f'{delta:+,}'+' tokenであった．' if delta is not None
             else '欠測または未評価があるため，固定した全件比較の費用差は未確定とする．')
    full += ('固定した開発上の採用基準を満たした．' if report['development_gate_met']
             else '固定した開発上の採用基準は満たさなかった．')+'\n'
    parts = evidence.contributions(report)
    full += table(('成否の組合せ','課題数','H−U token'), 'lrr', [
        (label, parts[key]['task_count'], evidence.signed(parts[key]['half_minus_unlimited_tokens']))
        for key,label in [('both_successful','両側成功'), ('both_failed','両側未達'),
                          ('discordant','成否が異なる'), ('unevaluated','片側以上が未評価')]],
        '全課題の費用寄与．全件既知でないときは全体の寄与を確定しない．')
    full += '未達の費用も残し，成功部分のみの減少を全体の改善としない．未評価・未実行は未達として補完しない．\n'
    resource = table(('計測対象','U','H'), 'lrr', [
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
        conclusion = ('通常の固定推論予算は，この既知４課題では課題ごとの成功喪失なく全論理費用を減らした．'
            'これは新しい推論配分アルゴリズムの提案ではなく，固定した通常対照の開発結果である．')
    elif report['all_eight_complete_with_known_usage']:
        conclusion = ('通常の固定推論予算は，固定した品質と全費用の共同基準を満たさなかった．'
            '出力枠への指定だけで仕事全体の効率改善が成立するとは結論できない．')
    else:
        conclusion = ('使用量の欠測または未評価・未実行を含む全８枠を保持した．'
            '全件比較の費用差は確定せず，通常の固定予算による全仕事改善は未確立である．')
    conclusion += '課題の正しさと，局所的な出力完成，論理token，cache，時間を区別し，一般的な品質維持は今後の独立した確認を要する．\n'
    return {'whole_task.tex': full, 'resources.tex': resource, 'conclusion.tex': conclusion}


def bibliography(source):
    wanted = ('codeact','appworld','canonical','costproxy')
    result = []
    for key in wanted:
        matches = re.findall(r'\\bibitem\{'+key+r'\}[^\n]+', source)
        if len(matches) != 1: raise ValueError('one_verified_bibliography_entry_required:'+key)
        result.append(matches[0])
    result += [
        r"\bibitem{s1} N. Muennighoff, Z. Yang, W. Shi, X. L. Li, L. Fei-Fei, H. Hajishirzi, L. Zettlemoyer, P. Liang, E. Cand\`es, and T. Hashimoto, ``s1: Simple test-time scaling,'' arXiv:2501.19393v3, 2025.",
        r"\bibitem{budgettraining} T. A. Lamb, A. Golinski, E. Gualdoni, S. Williamson, and M. Kirchhof, ``Rewards for Budget-Aware Multi-Turn Agents That Adapt to Arbitrary Test-Time Constraints,'' arXiv:2610.28409v1, 2026.",
        r"\bibitem{backend} ggml-org, ``llama.cpp: reasoning budget,'' commit 620d2225cc436ab0b001e3200e590e3b286ef9ab, \url{https://github.com/ggml-org/llama.cpp/blob/620d2225cc436ab0b001e3200e590e3b286ef9ab/common/reasoning-budget.cpp}, accessed Oct. 24, 2026."]
    entries = {re.match(r'\\bibitem\{([^}]+)\}', entry).group(1): entry for entry in result}
    return '\n'.join(entries[key] for key in ('codeact', 'appworld', 's1',
        'budgettraining', 'backend', 'costproxy', 'canonical'))


def draft(ja, en, bib):
    source = r'''% Prepared P88 result template; actual text is emitted only after audited closure.
\documentclass[uplatex,a4paper,twocolumn,10pt]{jsarticle}
\usepackage[margin=20mm]{geometry}
\usepackage{amsmath}
\usepackage{url}
\title{状態保持型LLMエージェントにおける\newline 情報保持と実行制御の評価}
\author{検討用別稿・著者情報未設定}
\date{}
\begin{document}
\raggedbottom
\maketitle
\noindent\textbf{あらまし案}\quad
@@JA@@

\noindent\textbf{キーワード}\quad LLMエージェント，ハーネスエンジニアリング，状態保持，推論予算，費用評価

\section{問題設定}
必要な情報と成果品質を保って仕事全体の費用を減らすため，ハーネスが渡す情報と生成・実行の予算を区別して検討する．
コードを行動に用いるCodeAct\cite{codeact}型エージェントでは，思考が出力枠を消費した後に，実行に必要なコードを完了できるとは限らない．
しかし，短い思考や構文上の完成だけでは，課題達成や失敗を含む全費用の減少を意味しない．
本稿はAppWorld\cite{appworld}の既知４課題を用い，通常の推論ブロック上限指定が課題全体の成否と費用へ与える効果を，固定した８条件で調べる限定的な開発比較である．

思考終了の制御\cite{s1}，予算情報を用いた複数ターンの資源配分の学習\cite{budgettraining}には先行研究がある．
後者は予算内成功と自然な予算遵守を区別し，１方策につき１資源の予算を扱い，token費用は生成分である．
本稿は学習せず，既存backendの設定\cite{backend}を比較する．全論理入力と出力を主費用とするが，token削減と他の費用の不一致\cite{costproxy}自体を独自性とはしない．
新しい予算配分アルゴリズム，学習方式より優れた性能，一般的品質保証を主張する比較ではない．

\section{共通の実行系と比較}
\subsection{出力枠と履歴}
１生成の全出力上限を最大4,096とし，推論ブロック専用上限なしをU，固定2,048指定をHとする．
Uも全出力・全仕事・実時間の上限を持つ．固定backendは推論終了タグを使ってブロックを閉じるため，2,048は操作へ必ず半分を残す予約ではない．
終了タグ，UTF-8境界の待機，新たな推論ブロックの開始があり，ブロック内の正確な生成token配分を本比較では別計測していない．
全仕事の残tokenにより全出力枠が縮む場合も，専用指定2,048は変更しない．

両側とも全返却推論，持続Python，型付きAPI返却，通常のPython例外を保持する．
呼出しと返答の通信参照は構造化された段階で統一してからモデル向けに文章化し，一般本文や業務IDは変更しない．
参照改名感度と正規化には先行研究\cite{canonical}があり，本処理を新規手法とはしない．
残実時間は非表示と明示する一方，実行可否は単調時計の期限で強制する．残token・API・生成回数の通知は共通とし，過去の通知を会話へ蓄積しない．

\subsection{固定した課題と上限}
写真移動，電気代精算，返金，曲情報書出しを新しい初期状態から各条件１回実行する．
課題順はこの順，条件順はU/H，H/U，U/H，H/Uである．
世界seed42，モデルseedは初回57で以後生成ごとに１増やす．Mac Studio M3 Ultra・256 GiB上でAppWorld 0.1.3.post1，MiniMax-M3 IQ4\_XS，llama.cpp b11669を用いる．
温度1.0，top-p 0.95，入力枠65,536，１スロットを共通とする．初回のcache再利用０を確認し，後続は通常のprefix cacheを使う．
初期８入力を計数し，課題ごとの要求が専用予算のフィールド以外一致することを確認してから生成を始める．

各条件は80生成，450,000論理token，作業1,800秒，写真160・他80 APIを上限とする．１生成の待機は600秒と残作業時間の小さい方である．
全体は８条件，640生成，3,600,000予約token，所有推論器21,600秒を上限とする．
公開の要求とAPI仕様を用い，保留12課題は閲覧しない．
先行する保存文脈の局所診断では予定８生成中４件目で停止し，３件既知・１件不明・４件未実行だった．
その後に本開発比較を固定しており，未見確認ではない．局所診断の不足枠を補充せず，専用値・seedを探索しない．

\section{計測と採用条件}
全仕事の論理費用は$T=\sum_j(I_j+O_j)$とし，cache分を含む全入力$I_j$，出力$O_j$，通知，失敗，回復，再取得を含める．
cache除外入力，出力，API回数，作業・準備・評価・推論器稼働時間を別に記録し，金額や計算量へ換算しない．
各最終状態を独立評価器で一度だけ判定し，正解や評価結果をモデルへ返さない．
未知の生成使用量が出た場合はその条件を終了し，応答の実行・再試行をしない．API作用と後片付けが既知で，同じ推論器のidleを確認できた場合のみ評価して固定順を続ける．未知のAPI作用や実行環境・評価の異常は全体を止める．

Hの採用には全８評価・全終端使用量・監査一致，課題ごとの成功喪失０，両側成功１課題以上，全４課題の論理費用がUより小さいことを要求する．
同数成功だけで品質維持とせず，両側成功・両側未達・成否不一致の費用寄与を分ける．
これは開発上の相対基準であり，統計的非劣性の証明ではない．
途中は運用状態と使用量だけを確認し，成否と出力比較は全条件終了後，所有推論器停止とPID不在の確認後に行う．

\section{全件結果}
\input{@@FOLDER@@/whole_task.tex}
\input{@@FOLDER@@/resources.tex}

\section{解釈の範囲}
独立した課題は既知４つであり，８条件や生成数を独立課題数へ読み替えない．
単一モデル・専用上限１値・各１回の比較から，別課題やモデル，予算での品質維持を保証しない．
同じseedでも数値実行とcacheの影響は残る．ホストでは軽量な編集と報告準備も行っており，速度の測定は排他的な負荷条件ではない．
過去の直接API構成の品質を回復したかや，別の強い学習方式に対する優劣は調べていない．
未達や欠測を残した全件の公開集計と固定版を保存する\footnote{\url{https://github.com/sophiria1225/AI-}}．

\section{結論}
\input{@@FOLDER@@/conclusion.tex}
\begin{thebibliography}{99}
\small
\raggedright
@@BIB@@
\end{thebibliography}
\clearpage
\onecolumn
\noindent\textbf{Title}\quad Evaluating Information Retention and Execution Control in Stateful LLM Agents

\noindent\textbf{Authors}\quad 未設定

\noindent\textbf{Keywords}\quad LLM agents, harness engineering, state retention, reasoning budget, cost evaluation

\noindent\textbf{Summary draft}\quad @@EN@@
\end{document}
'''
    for marker, value in [('@@JA@@', ja), ('@@EN@@', en), ('@@BIB@@', bib), ('@@FOLDER@@', FOLDER)]:
        source = source.replace(marker, value)
    return source


def build(root=ROOT):
    folder = root / FOLDER
    if folder.exists(): raise FileExistsError('preserve_P88_draft_attempt')
    plan, report, pre, session, _ = evidence.validated(root)
    sources = dict(pre['source_hashes'])
    sources.update({name: sha(root / name) for name in (*evidence.FILES, *SUPPORT)})
    for name, expected in sources.items():
        if sha(root / name) != expected: raise ValueError('bound_draft_source_changed:'+name)
    output = sections(plan, report, session); ja, en = abstracts(report)
    output['draft.tex'] = draft(ja, en, bibliography((root / PRIOR_DRAFT).read_text()))
    folder.mkdir(parents=True, exist_ok=False)
    for name, text in output.items():
        with (folder / name).open('x') as f: f.write(text)
    manifest = dict(generated_at=datetime.now(timezone.utc).isoformat(), source_sha256=sources,
        generated_sha256={name: sha(folder/name) for name in output}, all_planned_rows=8,
        independent_tasks=4, repetitions=1, development_gate_met=report['development_gate_met'],
        unknown_usage_imputed=False, novel_method_claim=False, general_quality_preservation_claim=False,
        authors_confirmed=False, official_journal_class=False, submission_ready=False,
        professor_brief_changed=False, visual_reviewed=False,
        additional_generations=0, additional_api_requests=0, additional_evaluations=0)
    with (folder / 'build_manifest.json').open('x') as f:
        import json
        json.dump(manifest, f, ensure_ascii=False, indent=2); f.write('\n')
    print(dict(folder=FOLDER, ja_characters=len(ja), en_words=len(en.split()),
               all_planned_rows=8, development_gate_met=report['development_gate_met']))
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--repo-root', type=Path, default=ROOT)
    args = parser.parse_args(); build(args.repo_root)
