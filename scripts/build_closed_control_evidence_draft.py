"""Add the closed ordinary-choice control and pinned prior code to a fresh letter."""
from datetime import datetime, timezone
import json

from build_action_cohort_draft import section
from build_observed_control_draft import replace_once
import build_whole_task_tool_choice_report as evidence
from run_handoff_factors import ROOT, read, sha

PARENT='papers/202610_letter/execution_evidence_cohort'
FOLDER='papers/202610_letter/execution_evidence_controls_v01'


def build():
    parent=ROOT/PARENT;target=ROOT/FOLDER
    if target.exists():raise FileExistsError('preserve_closed_control_edition')
    plan,report,pre,session,_=evidence.validated(ROOT)
    totals=[evidence.totals(report['rows'],p) for p in ('auto','required')]
    if (any(t['evaluated']!=4 or t['successes']!=3 for t in totals)
            or [t['known_total_tokens'] for t in totals]!=[769281,882557]
            or [t['unknown_usage_calls'] for t in totals]!=[1,0]
            or report['development_gate_met'] is not False):
        raise ValueError('closed_P99_observations_changed')
    successful=[]
    for task in plan['known_tasks']:
        pair=[r for r in report['rows'] if r['task_id']==task['task_id']]
        if all(r['success'] for r in pair):
            if pair[0]['known_total_tokens']!=pair[1]['known_total_tokens']:
                raise ValueError('successful_pair_costs_changed')
            successful.append(pair[0]['known_total_tokens'])
    if len(successful)!=3 or sum(successful)!=448825:raise ValueError('successful_stratum_changed')
    old=read(parent/'build_manifest.json');sources=dict(old['source_sha256'])
    for name,expected in old['generated_sha256'].items():sources[PARENT+'/'+name]=expected
    for name in ('build_manifest.json','draft.pdf','visual_review.json'):sources[PARENT+'/'+name]=sha(parent/name)
    added=list(evidence.FILES)+[
        'scripts/build_closed_control_evidence_draft.py','scripts/build_whole_task_tool_choice_report.py',
        'scripts/whole_task_tool_choice.py','reports/P99_results_provenance_20261024.json',
        'materials/20261024_p99_results/whole_cohort_summary.json','docs/P99_findings.md',
        'reports/external_history_identifier_sources_20261024.json',
        'reports/external_identifier_prior_fixes_sources_20261024.json',
        'docs/external_history_identifier_review_20261024.md',
        'docs/external_identifier_prior_fixes_20261024.md']
    for name in added:sources[name]=sha(ROOT/name)
    for name,expected in sources.items():
        if sha(ROOT/name)!=expected:raise ValueError('bound_source_changed:'+name)
    generated={n:(parent/n).read_text() for n in old['generated_sha256']}
    source=generated['draft.tex'].replace(PARENT+'/',FOLDER+'/')
    source=replace_once(source,'状態保持，時間通知，費用評価','状態保持，実行再現性，費用評価')
    source=replace_once(source,'state retention, time notices, cost evaluation',
                        'state retention, execution reproducibility, cost evaluation')
    # Keep the archived numerical files, and identify the two sections deferred to the supplement.
    for name in ('trajectories.tex','cross_cohort.tex'):
        source=replace_once(source,'\\input{'+FOLDER+'/'+name+'}\n','')
    source=section(source,r'\section{問題設定と関連研究}',r'\section{共通の履歴処理と通知}',r'''\section{問題設定と関連研究}
状態保持型LLMエージェントのハーネスを評価する際，出力の安定性は実操作の再現性をどこまで表すか．必要な操作と最終成果を残した費用削減のため，CodeAct\cite{codeact}型のコード行動とAppWorld\cite{appworld}で，公開出力，実行口での受理，実API列の対応を調べる．

時間制御\cite{clock,timely}，数値的非決定性\cite{nondeterminism}，行動段階別の反復照合\cite{consistency}，ハーネス探索\cite{beyondprompts}，実行形式\cite{localprotocol}，情報提示\cite{delivery}，出典記録\cite{repro}，ID正規化\cite{canonical}には先行研究がある．論理tokenと実費用\cite{costproxy}，cacheと圧縮・遅延\cite{capc,cacheeval}も同一ではない．

公開実装smolagentsにも接続IDを履歴本文へ含む経路があり\cite{smolmemory}，ID欠落・重複による実行欠落や，ID順と呼出し順の違いを扱う既存修正がある\cite{smolids}．本稿ではこれらを新方式とせず，保存１文脈の全18出力の実行と，既知４課題24実行の全426生成の事後解析を結び付ける．一致出力の形式拒否と，異なる構文から同じ実API要求が生じる事例を示し，通常の提出設定による全仕事比較も併記する．''')
    source=section(source,r'\section{比較の手順}',r'\section{全仕事の結果}',r'''\section{比較の手順}
\subsection{通知比較と保存文脈の実行}
写真移動，電気代精算，返金，曲情報書出しの既知４課題をM/H/Lで各２回実行する．Mac Studio M3 Ultra・256 GiB，AppWorld 0.1.3.post1，MiniMax-M3 IQ4\_XS，llama.cpp b11669を用いる．入力枠65,536，１スロット，持続Python，型付きAPI返却，温度1.0，top-p 0.95，環境seed42，モデルseed57から生成ごとに１増加とする．課題別順序は反復１がMHL/HLM/LMH/LHM，反復２がその逆順である．

各条件80生成，450,000論理token，1,800作業秒，写真160・他80 APIを上限とする．出力上限は4,096と残予算，通信待ちは600秒と残時間の小さい方である．初回cache再利用０を確認し，以後は通常のprefix cacheを使う．最終状態を独立評価器で各１回判定し，基準・結果をモデルへ返さない．Lの採用には，両反復でM/Hの各対照に対し全件評価・使用量既知・監査一致，成功喪失０，共通成功１課題以上，全４課題の論理費用減を要求する．全４比較の成立を条件とし，成功部分だけを選ばない．

以前のM/H反復を見た後，書出しで文章化ID差が初めて現れた保存文脈を選んだ．元入力A/B，表示前統一C/D，Aの構造化参照だけを改名したN，診断文を足したXを固定した．token列はC/DとA/Nで同じ，A/BとA/Xで異なる．各３回計18生成をseed70，温度1，出力上限4,096の固定順で測る．全要求cold入力で元のwarm状態は再現しない．空出力，途中切れ，揺れ，欠測を除いて安定と判定しない．

全18出力を新規環境で各１回，先行12コード・28 APIの実要求・返答・標準出力・例外・schemaを照合後，通常実行口へ渡す．保存返答による代用や本文からのコード救済をしない．不一致・不明時は停止し補充しない．双方の提出・実行がなければ空API列同士を有効操作の一致としない．元のDB・プロセス全体の復元ではない．

\subsection{全24条件の記録解析と通常設定の対照}
全426生成を事後解析する．各課題６実行の全15組，計60組を生成序数で対応付け，片側終了後も残す．公開出力は本文・関数名・引数・終了理由，構文は位置情報だけを外したAST，実API列は送信receiptがある全要求の名前・引数を比較する．認証値は保持し，JSON objectのキー順・整形だけを統一する．Python内APIを外側の実行記録へ一度だけ対応付け，費用・欠測を元監査と照合する．生成前のAPI要求・返答・例外・schema列が同じ範囲も別集計する．両方空のAPI列を非空要求の一致に含めず，再生成・再実行・再評価はしない．

補助対照では同じ既知４課題を通常の\texttt{tool\_choice=auto/required}で各１回，計８条件実行した．初期履歴，推論設定，seed，予算と評価をそろえ，課題順は同じで，設定順はauto/required，逆順，順方向，逆順とした．表示設定はH，反復回復通知は付けない．条件・順序・採用基準を生成前に固定し，全４課題の成功喪失なく論理費用が減ることを求めた．保存文脈の次出力だけの介入とは別の全仕事比較である．''')
    source=replace_once(source,r'\section{考察と適用範囲}',
        r'\section{通常の提出設定による全仕事比較}'+'\n'+r'\input{'+FOLDER+'/ordinary_control.tex}\n\n'+r'\section{考察と適用範囲}')
    source=section(source,r'\section{考察と適用範囲}',r'\section{結論}',r'''\section{考察と適用範囲}
出力一致には形式拒否が含まれ，構文差だけでは実API要求の差を判定できなかった．提出・実行状態と実要求を添えることが有用だが，API列一致自体も正常完了や正解を保証しない．通常の必須提出も今回のCSV課題を成功させなかった．ただし異なる軌跡を持つ全仕事比較から，個々の形式拒否を必須提出が必ず防げる／防げないとはいえない．

独立した課題は調整に用いた既知４つで，追加対照も同じ課題である．24実行，60組，生成数を独立課題数に読み替えない．保存文脈は事後選定した１つ，全群解析も二次解析である．API履歴一致は全状態の復元でなく，同じseedにも数値実行，cache，ホスト負荷の変動が残る．通知の長さと情報効果は分離していない．Hはコードの時刻参照を禁じず，表示開始に至らないLも残す．参照統一は全条件共通で，その品質効果は識別できない．外部公開コードは経路と既存修正の読取確認で，外部モデルの性能追試ではない．全条件・補助的な反復照合・資源記録・固定版の出典を公開する\footnote{\url{https://github.com/sophiria1225/AI-}}．''')
    references=r'''\bibitem{smolmemory} Hugging Face, ``smolagents, memory.py,'' source commit 96f33fa, 2026. \url{https://github.com/huggingface/smolagents/blob/96f33faaf028479119ec8d34507b47694cf14e34/src/smolagents/memory.py}
\bibitem{smolids} smolagents contributors, ``Tool-call ID and ordering fixes,'' pull requests 2684 and 2999, heads bd00a93 and c410924, inspected Oct. 24, 2026. \url{https://github.com/huggingface/smolagents/pull/2684}; \url{https://github.com/huggingface/smolagents/pull/2999}
'''
    source=replace_once(source,r'\end{thebibliography}',references+r'\end{thebibliography}')
    generated['draft.tex']=source
    generated['ordinary_control.tex']=r'''\begin{table}[tb]
\centering\footnotesize\setlength{\tabcolsep}{3pt}
\caption{通常設定の全４課題．全８条件を評価済み．$+?$は既知小計に使用量不明１生成が残ることを示す．}
\begin{tabular}{lrrrr}
設定 & 成功 & 論理token & 生成試行 & API \\ \hline
auto & 3/4 & $769,281+?$ & 73 & 179 \\
required & 3/4 & 882,557 & 75 & 197 \\
\hline\end{tabular}
\end{table}
成功した写真・精算・返金の各対は費用差０で，両設定とも合計448,825論理tokenだった．書出しは両方未達で，autoは作業期限中の生成に使用量不明１件，requiredはtoken予約上限で停止した．全仕事費用差は未確定，採用基準は未達である．全148生成試行，既知1,651,838論理token，376 API，８評価を残した．作業秒はauto 2,976.265，required 2,698.152，所有推論器5,739.315秒，条件の準備・作業・後片付け5,698.734秒だった．重なる時間は加算せず，未達の早い終了を品質維持や高速化とはしない．
'''
    generated['conclusion.tex']=(
        '状態保持型LLMエージェントの保存文脈と全24実行から，公開出力が同じでも形式拒否された14生成と，'
        '構文が異なっても実API列が同じだった４課題37生成を確認した．通常設定の追加８条件でも成功獲得はなく，'
        '全仕事費用の改善は確認できなかった．出力・構文の一致に実行状態と実要求を添え，最終成果と失敗を含む総費用を分けて評価する．'
        '未知課題への広がり，新手法，一般的な品質・費用改善は未確立である．\n')
    target.mkdir()
    for name,text in generated.items():(target/name).write_text(text)
    manifest={**old,'generated_at':datetime.now(timezone.utc).isoformat(),'source_sha256':sources,
        'generated_sha256':{n:sha(target/n) for n in generated},'parent_draft':PARENT,
        'closed_P99_evidence_added':True,'P99_evaluated_conditions':8,'P99_successes_per_policy':[3,3],
        'P99_unknown_usage_calls':1,'P99_adoption_gate_met':False,'P101_intermediate_results_used':False,
        'external_pinned_code_review_included':True,'external_performance_replication':False,
        'body_sections_deferred_to_supplement':['trajectories.tex','cross_cohort.tex'],
        'all_numeric_result_sections_byte_unchanged':[n for n in old['generated_sha256'] if n not in ('draft.tex','conclusion.tex')],
        'visual_reviewed':False,'submission_ready':False}
    for key in ('pdf_sha256','renderer_sha256','pages','body_pages','visual_reviewed_pages','visual_review_sha256'):
        manifest.pop(key,None)
    (target/'build_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    print(dict(folder=FOLDER,P99_all_eight_evaluated=True,new_model_API_evaluation_calls=0,source_bindings=len(sources)))


if __name__=='__main__':build()
