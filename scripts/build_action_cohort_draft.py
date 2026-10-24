"""Integrate the closed P98 full-cohort evidence into a fresh letter edition."""
from datetime import datetime, timezone
import json

from build_observed_control_draft import replace_once
from build_recorded_action_summary import summarize
from run_handoff_factors import ROOT, read, sha

PARENT = 'papers/202610_letter/execution_evidence_focus'
FOLDER = 'papers/202610_letter/execution_evidence_cohort'


def section(source, begin, end, text):
    if source.count(begin) != 1 or source.count(end) != 1:
        raise ValueError('unique_section_boundaries_required')
    left = source.index(begin); right = source.index(end, left)
    return source[:left] + text + '\n\n' + source[right:]


def build():
    parent = ROOT / PARENT; target = ROOT / FOLDER
    if target.exists(): raise FileExistsError('preserve_cohort_edition')
    report = read(ROOT / 'reports/P98_recorded_action_agreement.json')
    summary, _ = summarize(report)
    original_summary = read(ROOT / 'materials/20261024_p98_results/summary.json')
    if any(original_summary[k] != v for k, v in summary.items()):
        raise ValueError('closed_cohort_summary_changed')
    old = read(parent / 'build_manifest.json'); sources = dict(old['source_sha256'])
    for name, expected in old['generated_sha256'].items(): sources[PARENT + '/' + name] = expected
    for name in ('build_manifest.json', 'draft.pdf', 'visual_review.json'):
        sources[PARENT + '/' + name] = sha(parent / name)
    for name in ('scripts/build_action_cohort_draft.py', 'scripts/build_recorded_action_summary.py',
                 'scripts/recorded_action_agreement.py', 'scripts/render_bound_letter_draft.py',
                 'reports/P98_recorded_action_agreement.json', 'reports/P98_results_provenance_20261024.json',
                 'materials/20261024_p98_results/summary.json', 'docs/P98_findings.md'):
        sources[name] = sha(ROOT / name)
    sources.update(report['source_sha256'])
    for name, expected in sources.items():
        if sha(ROOT / name) != expected: raise ValueError('closed_source_changed:' + name)
    generated = {name: (parent / name).read_text() for name in old['generated_sha256']}
    source = generated['draft.tex'].replace(PARENT + '/', FOLDER + '/')
    old_ja = source.split('\\textbf{あらまし案}\\quad\n', 1)[1].split('\n\n', 1)[0]
    old_en = source.split('\\textbf{Summary draft}\\quad ', 1)[1].split('\n', 1)[0]
    ja = ('状態保持型LLMエージェントの全24実行を解析した. '
          '同一の公開出力が形式拒否された14生成と，構文が異なっても同じAPI要求列となった４課題37生成を確認した. '
          '表示，実操作，最終成果を区別する必要性を示す.')
    en = ('We analyzed 24 recorded runs of a stateful LLM agent. Matching public outputs included '
          '14 rejected generations; different syntax produced identical API requests in 37 generations '
          'across four known tasks. These observations distinguish output agreement, actual execution, '
          'and task outcomes without establishing general quality or cost improvements.')
    if len(ja) > 120 or len(en.split()) > 50 or any(c in ja for c in ('。', '・')):
        raise ValueError('abstract_limits')
    source = replace_once(replace_once(source, old_ja, ja), old_en, en)
    source = section(source, r'\section{問題設定と関連研究}', r'\section{共通の履歴処理と通知}', r'''\section{問題設定と関連研究}
状態保持型LLMエージェントの費用を減らすには，操作と最終成果を損なわない制御が必要である．しかし，入力表現をそろえて出力が安定しても，有効な操作を提出できたとは限らない．CodeAct\cite{codeact}型のコード行動とAppWorld\cite{appworld}を対象に，表現の一致と実操作の対応を調べる．

時間通知と期限強制\cite{clock}，時間適応\cite{timely}，数値的非決定性\cite{nondeterminism}，ツール列・引数・出力の反復照合\cite{consistency}，ハーネス探索\cite{beyondprompts}，実行形式\cite{localprotocol}と情報提示\cite{delivery}，出典記録\cite{repro}，ID改名と正規化\cite{canonical}は既に扱われている．論理tokenと実費用\cite{costproxy}，cacheと圧縮・遅延\cite{capc,cacheeval}も区別が必要である．

本稿は，不正呼出しの文章化で通信参照が通常文へ移る経路，保存１文脈の全18出力の実行，既知４課題24実行の全426生成の記録解析を結び付ける．一致した出力の形式拒否と，異なる構文から同じ実API要求列が生じる例を示す．正規化の新方式や一般的な高速化を提案するものではない．''')
    source = section(source, r'\section{共通の履歴処理と通知}', r'\section{比較の手順}', r'''\section{共通の履歴処理と通知}
公開履歴と返却済み推論を$h$，呼出しIDと結果IDの対応を保って初出順に統一する処理を$C$，表示処理を$R$とする．不正引数の呼出しを$R$が文章化した後では，構造上の参照欄だけの統一は文章内IDを変更できない．共通履歴を$R(C(h))$とし，通常文，引数，コード，観測，エラー，返却推論は変えず元記録を保持する．重複・欠落・孤立参照は拒否する．長い観測の先頭ページと参照先の表示も全条件で共通とする．これは通常の正規化順序の修正であり，品質維持の保証ではない．

仕事上限$B=1800$秒と，生成直前の実残時間を整数秒にした$r$を用いる．Mは毎回$r$を表示，Hは非表示を通知，Lは$2r>B$ならH，それ以外はMとする．整数化により半分時点より１秒未満早く切り替わり得る．現在の通知だけを要求へ付け，履歴に蓄積せず，過去内容や進行中の生成は変更しない．実期限は全条件で単調時計から強制する．残token・API・生成回数の表示は共通である．

全仕事の論理費用$T=\sum_j(I_j+O_j)$は全入力，出力，制御，失敗，回復，cache入力を含む．cache除外入力，出力，API数，実時間は別に集計し，終端使用量の不明を０や別反復で補わない．''')
    source = section(source, r'\section{比較の手順}', r'\section{全仕事の結果}', r'''\section{比較の手順}
\subsection{通知比較と保存文脈の実行}
写真移動，電気代精算，返金，曲情報書出しの既知４課題をM/H/Lで２回ずつ初期化して実行する．全24条件で履歴処理は共通である．Mac Studio M3 Ultra・256 GiB，AppWorld 0.1.3.post1，MiniMax-M3 IQ4\_XS，llama.cpp b11669を用いる．入力枠65,536，１スロット，持続Python，型付きAPI返却，通常例外とし，温度1.0，top-p 0.95，環境seed42，モデルseed57から生成ごとに１増やす．反復１の課題別順序はMHL/HLM/LMH/LHM，反復２は各組の逆順とする．

各条件80生成，450,000論理token，1,800作業秒，写真160・他80 APIを上限とする．出力上限は4,096と残予算の小さい方，通信待ちは600秒と残時間の小さい方である．初回はcache再利用０を確認し，以後は通常のprefix cacheを使う．最終状態を独立評価器で各１回判定し，基準・結果をモデルへ返さない．Lの固定採用基準は，各反復でM/Hそれぞれに対し全件評価・使用量既知・監査一致，成功喪失０，共通成功１課題以上，全４課題の論理費用減を満たすこととする．全４比較で成立を要求し，閾値探索や成功部分だけの選択はしない．

以前のM/H反復を見た後，書出しで文章化ID差が初めて現れた保存文脈を選んだ．元入力A/B，表示前統一C/D，Aの構造化参照だけを改名したN，診断文を足したXを固定する．token列はC/DとA/Nで一致し，A/BとA/Xで異なる．各３回計18生成をseed70，温度1，出力上限4,096で固定順に測る．全要求をcold入力とし，元のwarm状態は再現しない．空出力，途中切れ，揺れ，欠測を除いて安定と判定しない．

全18出力は新規環境で各１回，先行12コード・28 APIの実要求・返答・標準出力・例外・schemaを保存記録と照合後，通常実行口へ渡す．保存返答による代用や本文からのコード救済をしない．不一致・不明時は停止し補充しない．双方の提出と実行がなければ，空API列同士を有効操作の一致としない．元のDB・プロセス全体の復元ではない．

\subsection{閉じた全24条件の記録解析}
上の24実行の全生成を事後解析する．各課題６実行の全15組，計60組を生成序数で対応付け，片側終了後も残す．公開出力は本文・関数名・引数・終了理由，構文は位置情報だけを外したAST，実API列は送信receiptを持つ全要求の名前・引数を比較する．認証値も保持し，JSON objectのキー順・整形だけを統一する．全Python内API記録を外側の実行記録へ一度だけ対応付け，元監査の費用・欠測を照合する．生成前のAPI要求・返答・例外・schema列が同じ範囲も別集計するが，Python変数やDB全体の一致とはしない．両方空のAPI列は非空要求の一致へ数えず，記録を読み直すだけでモデル・API・コード・評価を再実行しない．''')
    marker = r'\section{考察と適用範囲}'
    source = replace_once(source, marker, r'\section{全生成における表示と実要求}' + '\n' +
        r'\input{' + FOLDER + '/cohort.tex}\n\n' + marker)
    source = section(source, marker, r'\section{結論}', r'''\section{考察と適用範囲}
出力一致には実行口で拒否された生成が含まれ，構文差だけでは実API要求の差を判定できなかった．公開出力や構文の比較には，提出・実行状態と実要求を添える必要がある．API列の一致自体も正常完了や正解を保証しない．既存研究が区別する行動再現性指標を新方式とせず，本実装での対応と失敗の具体的なデータとして位置付ける．

独立した課題は調整に用いた既知４つで，24実行，60組，生成数を独立課題数へ読み替えない．保存文脈は事後に選んだ１つで，全群解析もその観察後の二次解析である．入力・API履歴の一致は完全な実行状態の復元でなく，同じseedにも数値実行，cache，ホスト負荷の変動が残る．通知文の長さと情報の効果は分離していない．非表示は生成コードの時刻参照を禁じず，表示開始に至らないLも残す．参照統一は全条件共通なので，その因果的な品質効果は識別できない．局所API差を全仕事の削減にせず，未達・欠測と再構成費を残す．全条件と出典を公開する\footnote{\url{https://github.com/sophiria1225/AI-}}．''')
    generated['draft.tex'] = source
    # Fixed closed counts are checked against the recomputed public summary.
    expected = [(19, 14, 4, 1), (19, 14, 4, 1), (33, 37, 16, 4), (19, 26, 9, 3)]
    actual = [(p['dependent_comparison_slots'], p['distinct_recorded_calls'], p['distinct_runs'], p['distinct_known_tasks']) for p in summary['patterns']]
    if actual != expected: raise ValueError('closed_pattern_values_changed')
    generated['cohort.tex'] = r'''全426生成では，提出した全ツールの実行記録あり397，提出なし21，構造化提出後の未完了４，出力不明４だった．397にはPython通常例外を含み，課題成功数ではない．
全1,132対応枠は両側記録998，片側終了後134であった．公開出力は992比較中441一致，構文は932中441一致，非空API列は861中446一致だった．分母の違う一致率を指標の優劣にしない．
\begin{table}[tb]
\centering\footnotesize\setlength{\tabcolsep}{3pt}
\caption{構文が異なるが非空API列が同じ比較位置．右列は生成前のAPI履歴も同じ範囲．組数は独立標本ではない．}
\begin{tabular}{lrr}
課題 & 全対応 & 前史一致 \\ \hline
写真移動 & 21 & 16 \\
電気代精算 & 1 & 0 \\
返金 & 10 & 2 \\
曲情報書出し & 1 & 1 \\
全体 & 33 & 19 \\
\hline\end{tabular}
\end{table}
同じ公開出力でも形式拒否された比較位置は19組で，全てCSVの４実行・14生成に対応した．10生成は提出なし，４生成は引数JSONが不正だった．全19組で生成前のAPI履歴も同じだった．
異なる構文・同じ非空API列の33組は，４課題16実行37生成に対応した．前史も同じ19組は３課題９実行26生成だった．37生成中30生成はPython正常終了，７生成は通常例外であり，同じ要求列を送信したことと正常完了を区別する．API履歴の一致には初回の空prefixも含む．全記録の解析は2.940039秒，追加生成・API・コード実行・評価０だった．
'''
    generated['conclusion.tex'] = (
        '状態保持型LLMエージェントの表現と実操作を，保存文脈の実行と全24実行の記録から評価した．'
        '公開出力が同じでも形式拒否された14生成と，構文が異なっても実API列が同じだった４課題37生成を確認した．'
        '通知比較の全４採用基準は未達だった．出力や構文の一致だけを有効操作や費用改善の代理にせず，'
        '実行状態，最終成果，失敗を含む総費用を分けて報告する必要がある．'
        '他課題への広がりと一般的な品質・費用改善，新方式の成立は未検証である．\n')
    target.mkdir(parents=True, exist_ok=False)
    for name, value in generated.items(): (target / name).write_text(value)
    manifest = {**old, 'generated_at': datetime.now(timezone.utc).isoformat(), 'source_sha256': sources,
        'generated_sha256': {n: sha(target / n) for n in generated}, 'parent_draft': PARENT,
        'editorial_focus_only': False, 'closed_P98_evidence_added': True,
        'all_numeric_result_sections_byte_unchanged': [n for n in old['generated_sha256'] if n not in ('draft.tex', 'conclusion.tex')],
        'new_model_generations': 0, 'new_environment_api_requests': 0, 'new_evaluations': 0,
        'reserved_scenarios_read': 0, 'P97_intermediate_results_used': False,
        'visual_reviewed': False, 'submission_ready': False}
    for key in ('pdf_sha256', 'renderer_sha256', 'pages', 'body_pages', 'visual_reviewed_pages', 'visual_review_sha256'):
        manifest.pop(key, None)
    (target / 'build_manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    print(dict(folder=FOLDER, ja_characters=len(ja), en_words=len(en.split())))


if __name__ == '__main__': build()
