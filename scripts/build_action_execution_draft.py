"""Create a fresh paper edition using the closed P94 execution comparison."""
from datetime import datetime, timezone
import json

from build_observed_control_draft import replace_once
from run_handoff_factors import ROOT, read, sha

PARENT = 'papers/202610_letter/closed_results_action_structure'
FOLDER = 'papers/202610_letter/closed_results_action_execution'
REPORT = 'reports/P94_saved_action_execution.json'
COMPARISON = 'materials/20261024_p94_results/comparison.json'


def build():
    target = ROOT / FOLDER
    if target.exists():
        raise FileExistsError('preserve_action_execution_edition')
    parent = ROOT / PARENT
    old = read(parent / 'build_manifest.json')
    sources = dict(old['source_sha256'])
    for name, expected in old['generated_sha256'].items():
        sources[PARENT + '/' + name] = expected
    report, comparison = read(ROOT / REPORT), read(ROOT / COMPARISON)
    if (report['status'] != 'complete' or report['completed_conditions'] != 18
            or len(report['conditions']) != 18
            or comparison['source_report_sha256'] != sha(ROOT / REPORT)
            or not comparison['all_eighteen_completed']
            or not comparison['all_prefixes_match']
            or comparison['prefix_API_trace_hashes'] != 1
            or comparison['total_api_requests'] != 546
            or comparison['total_program_executions'] != 228
            or comparison['model_generations'] != 0
            or comparison['evaluator_calls'] != 0
            or comparison['task_quality_measured']
            or comparison['original_full_state_restored']
            or comparison['new_method_claim']):
        raise ValueError('closed_P94_all_eighteen_required')
    cross = {(p['left'], p['right']): p for p in comparison['cross']}
    expectations = [
        ('P83_P80_ORIGINAL', 'P83_R2_ORIGINAL', 9, 0, 0),
        ('P83_P80_ORIGINAL', 'P83_NATIVE_IDS_CONTROL', 9, 9, 9),
        ('P83_P80_ORIGINAL', 'P83_CONTENT_CONTROL', 9, 9, 0),
        ('P83_P80_NORMALIZED', 'P83_R2_NORMALIZED', 0, 0, 0),
    ]
    if len(cross) != 15 or len(comparison['within']) != 6:
        raise ValueError('complete_comparison_groups_required')
    for left, right, available, requests, results in expectations:
        p = cross[left, right]
        if (p['pairs'], p['comparable_executed_pairs'], p['request_sequence_equal'],
                p['public_execution_result_equal']) != (9, available, requests, results):
            raise ValueError('fixed_P94_comparison_required')
    structure = read(ROOT / 'reports/P93_public_action_structure.json')
    structure_pairs = {(p['left'], p['right']): p for p in structure['comparison']['cross']}
    ax = structure_pairs['P83_P80_ORIGINAL', 'P83_CONTENT_CONTROL']
    if ax['public_output']['different'] != 9 or ax['syntax_actions']['different'] != 9:
        raise ValueError('P93_AX_syntax_and_public_difference_required')
    for name in (REPORT, COMPARISON, 'configs/P94_saved_action_execution_v01.json',
                 'docs/experiments/P94_saved_action_execution.md',
                 'scripts/build_action_execution_draft.py',
                 'scripts/matched_live_prefix.py', 'scripts/run_saved_action_execution.py',
                 'reports/P94_results_provenance_20261024.json',
                 PARENT + '/build_manifest.json', PARENT + '/draft.pdf',
                 PARENT + '/visual_review.json'):
        sources[name] = sha(ROOT / name)
    for name, expected in sources.items():
        if sha(ROOT / name) != expected:
            raise ValueError('bound_source_changed:' + name)
    generated = {name: (parent / name).read_text() for name in old['generated_sha256']}
    source = generated['draft.tex'].replace(PARENT + '/', FOLDER + '/')
    source = replace_once(source,
        '状態保持型LLMエージェントの通知と参照表現を評価した. 既知４課題24条件で後半通知の全仕事費用改善は示せなかった. １保存文脈でID差に伴うコード構文差を確認したが，統一入力の同一出力はツール提出を伴わなかった.',
        '状態保持型LLMエージェントの通知と参照表現を評価した. 既知４課題24条件で全仕事費用の改善は示せなかった. 保存18出力の実行検査では，公開出力，コード構文，API要求の一致を区別する必要が確認された.')
    source = replace_once(source,
        'We evaluated notices and references in stateful LLM agents. Late notices did not demonstrate whole-task cost improvement across 24 conditions. Reference-ID variants produced different code syntax in one saved context. Canonicalized inputs yielded identical text without tool submissions. Output agreement alone does not establish execution repair or task quality.',
        'We evaluated notices and references in stateful LLM agents. Late notices did not demonstrate whole-task cost improvement across 24 conditions. Testing saved outputs after matched public prefixes distinguished text agreement, code syntax, and API requests. Text agreement alone did not establish valid action agreement or task quality.')
    source = replace_once(source, '\\section{二つの比較}', '\\section{比較の手順}')
    source = replace_once(source,
        '全要求で入力cacheを無効化し，元のwarm状態を再現したとはしない．生成コード・環境API・課題評価は実行しない．',
        '全要求で入力cacheを無効化し，元のwarm状態を再現したとはしない．この生成時にはコード・環境API・課題評価を実行しない．')
    marker = '\\section{全仕事の結果}'
    method = (
        '\\subsection{保存出力の実行照合}\n'
        '全18出力を新規初期化した環境で各１回検査する．毎条件で先行12コードを同順に実行し，'
        '28 APIの要求・実返答とコードの標準出力・例外を保存記録に照合する．'
        '保存返答による代用は行わず，不一致・結果不明時は停止し補充しない．'
        '照合後，保存した次出力を通常の実行口へ渡す．本文からコードを取り出す救済は行わない．'
        '公開出力，JSON整形と位置情報を除いたコード構文，実API要求列，公開実行結果を区別する．'
        'API列・実行結果の比較には双方のツール提出と実行を必要とし，空列同士を有効な操作一致としない．'
        '元のDB・プロセス全体の保存像はないため，同じ公開履歴を作った新規状態での局所比較である．\n\n')
    source = replace_once(source, marker, method + marker)
    source = replace_once(source, '\\section{保存文脈の次出力}', '\\section{保存文脈の出力と実操作}')
    source = replace_once(source,
        '参照表現をそろえて出力が一致しても，その正しさ，続く仕事の完成，費用削減を保証しない．',
        '公開履歴の一致は元の完全状態・cache・残時間の復元ではない．次操作の４対２ APIを全仕事の削減とせず，追加の独立課題評価も行っていない．')
    generated['draft.tex'] = source
    generated['local_replay.tex'] = r'''\begin{table}[tb]
\centering\footnotesize\setlength{\tabcolsep}{3pt}
\caption{一致数／比較可能対数．各９対は３出力ずつの組合せで，独立９課題ではない．---は双方ツール提出なし．}
\begin{tabular}{lrrrr}
入力対 & 公開出力 & コード構文 & API要求列 & 実行結果 \\ \hline
A/B & 0/9 & 0/9 & 0/9 & 0/9 \\
A/N & 9/9 & 9/9 & 9/9 & 9/9 \\
A/X & 0/9 & 0/9 & 9/9 & 0/9 \\
C/D & 9/9 & --- & --- & --- \\
\hline\end{tabular}
\end{table}
全６入力で各３出力が完全・非空で安定し，全18生成は既知422,475論理token，使用量不明０，推論器稼働4,386.052秒だった．全15入力間比較と返却messageの不透明hashを保持し，内部推論の意味内容は読まない．
全18条件で先行履歴の照合が成立した．A/N/Xの次操作はログインと曲・アルバム・プレイリスト一覧の各４ API，Bはログインと曲一覧の各２ APIだった．C/Dの６出力は本文だけでツール提出がなく，通常の実行口は形式エラーを返した．
A/Bの構文差は実API要求の差を伴った．一方，A/Xは構文が違っても引数を含むAPI要求列は同じで，標準出力は各521文字と488文字だった．構文差はAPI差と同義でなく，本文の一致も有効な操作の一致とは限らない．
実行診断は再構成504＋次42＝546 API，228コード，64.561853秒を要した．追加生成・評価は０，全所有資源を終了した．この再構成費を除いて削減率を作らず，局所操作の比較を課題成功へ広げない．
'''
    generated['conclusion.tex'] = (
        '後半通知は全４採用基準未達で，全仕事費用の改善として採用しない．'
        '１保存文脈の診断では，統一入力の同一本文がツール提出を伴わず，'
        '異なる構文から同じAPI要求列が実行される場合もあった．'
        '出力・構文・実操作・課題成否を分けて評価する必要がある．'
        '既知４課題と１保存文脈から，一般的な品質維持や新規手法の有効性は結論できない．\n')
    target.mkdir(parents=True, exist_ok=False)
    for name, content in generated.items():
        (target / name).write_text(content)
    manifest = {**old, 'generated_at': datetime.now(timezone.utc).isoformat(),
        'source_sha256': sources, 'generated_sha256': {n: sha(target / n) for n in generated},
        'parent_draft': PARENT, 'P94_execution_comparison_included': True,
        'P94_conditions': 18, 'P94_environment_api_requests': 546,
        'P94_saved_program_executions': 228,
        'P94_original_full_state_restored': False, 'P94_task_quality_measured': False,
        'visual_reviewed': False, 'submission_ready': False}
    for key in ('pdf_sha256', 'renderer_sha256', 'pages', 'body_pages',
                'visual_reviewed_pages', 'visual_review_sha256'):
        manifest.pop(key, None)
    (target / 'build_manifest.json').write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    print({'folder': FOLDER, 'P94_conditions': 18, 'additional_generations': 0})


if __name__ == '__main__':
    build()
