"""Add conditional cost intervals to a separate draft, preserving closed results."""
from datetime import datetime, timezone
from pathlib import Path

from run_context_comparison import write_json
from run_handoff_factors import ROOT, read, sha

FOLDER = 'papers/202610_letter/time_visibility_intervals'


def bounds(values):
    lo, hi = values
    return f'{lo:+,}' if lo == hi else f'{lo:+,}〜{hi:+,}'


def build():
    sources = {}
    for name in ('reports/P81_P83_results_provenance_20261024.json',
                 'reports/P81_usage_interval_provenance_20261024.json'):
        ledger = read(ROOT / name)
        for source, expected in ledger['source_sha256'].items():
            if sha(ROOT / source) != expected:
                raise ValueError('closed_source_changed:' + source)
            sources[source] = expected
        sources[name] = sha(ROOT / name)
    report_path = 'reports/P81_usage_intervals_20261024.json'
    report = read(ROOT / report_path)
    if (len(report['rows']) != 429 or report['original_unknown_usage_preserved'] != 2
            or report['complete_terminal_usage_recovered']
            or sum(s['known_receipts_checked'] for s in report['sessions']) != 427
            or any(report[k] for k in ('additional_generations', 'additional_input_count_requests',
                                      'additional_api_requests', 'additional_evaluations'))):
        raise ValueError('complete_unchanged_conditional_interval_analysis_required')
    lines = [r'\begin{table}[tb]', r'\centering\small\setlength{\tabcolsep}{4pt}',
        r'\caption{全４課題のH−M費用差（論理token）．反復２以外は順序対応と固定推論器の計数に基づく区間であり，統計的信頼区間ではない．元の不明生成は残す．}',
        r'\begin{tabular}{lr}', r'集計 & H−M \\ \hline']
    for rep in ('1', '2', '3'):
        lines.append(f'反復{rep} & {bounds(report["repetitions"][rep]["total"]["H_minus_M"])}' + r' \\')
    total = report['combined']['total']
    lines.extend(['合計 & ' + bounds(total['H_minus_M']) + r' \\', r'\hline', r'\end{tabular}', r'\end{table}'])
    lines.extend([
        '事後の補助解析では，P80とP81の所有推論器の完全な直列ログを全429生成へ順序対応させた．'
        '既知427件すべてで，入力処理数＝終端入力−cache入力，生成数＝終端出力，送信前計数＝終端入力が一致した．',
        r'不明要求$j$について，同一送信の入力計数を$\widehat I_j$，ログに残った最大生成進捗を$g_j$，'
        r'要求の出力上限を$B_j$とすると，固定推論器の計数・停止実装を前提に',
        r'\begin{equation}\widehat I_j+g_j\leq T_j\leq\widehat I_j+B_j\end{equation}',
        'を得る．生成数は入力処理完了後に増加し，要求上限で停止する．'
        '全保存要求のhashと上限を照合し，別名による上書きがないことを確認した．'
        '不明２件の区間は順に39,657〜41,623，40,971〜44,699 tokenである．',
        'この順序対応は既知427件の一致で裏付けられるが，要求hashとサーバtask IDを暗号学的に結合したものではない．'
        '記録外の生成がないこと，入力計数と生成が同じmessages/toolsを使うこと，固定実装どおりに処理されることを前提とする．'
        '終端使用量の補完ではなく，cache入力と取消し後の処理を含む論理tokenの範囲である．'
        'GPU演算量，投機生成の未受理作業，料金や実時間の区間ではない．',
    ])
    m = total['measured'][0]
    percentages = [-total['H_minus_M'][1] / m * 100, -total['H_minus_M'][0] / m * 100]
    success = report['combined']['both_success']['H_minus_M'][0]
    failures = report['combined']['both_failure']['H_minus_M']
    lines.append(f'３反復合計ではHが条件付きで{-total["H_minus_M"][1]:,}〜{-total["H_minus_M"][0]:,} token，'
        f'約{percentages[0]:.2f}〜{percentages[1]:.2f}\\%少ない．'
        f'ただし両条件で成功した３課題の減少{-success:,} tokenに対し，'
        f'両条件で失敗した書出し課題は{failures[0]:,}〜{failures[1]:,} token増えている．'
        '反復ごとの全費用差も増加・増加・減少であり，安定した改善とはいえない．'
        '第３反復の書出し費用差は双方の未達で停止した差であり，完成に必要な費用の削減ではない．'
        '元の不明２件と採用基準未達は保持する．')
    folder = ROOT / FOLDER
    original_results = (ROOT / 'papers/202610_letter/time_visibility_repetitions/results.tex').read_text()
    before, old_bound = original_results.split('元のP80にはHの書出し中断による使用量不明１生成がある．', 1)
    _, after = old_bound.split('追加P81の推論器滞在は', 1)
    results = (before + '追加P81の推論器滞在は' + after).replace(
        r'\centering\scriptsize\setlength{\tabcolsep}{2pt}',
        r'\centering\footnotesize\setlength{\tabcolsep}{1pt}')
    results_path = folder / 'results.tex'
    if results_path.exists() and results_path.read_text() != results:
        raise ValueError('preserve_all_24_numeric_rows')
    if not results_path.exists():
        results_path.write_text(results)
    generated = folder / 'intervals.tex'
    content = '\n'.join(lines) + '\n'
    if generated.exists() and generated.read_text() != content:
        raise ValueError('preserve_generated_numeric_table')
    if not generated.exists():
        generated.write_text(content)
    for name in (FOLDER + '/draft.tex', 'scripts/build_time_visibility_interval_draft.py',
                 'scripts/render_time_visibility_interval_draft.py',
                 'docs/fallback_output_diagnostic_scope_20261024.md'):
        sources[name] = sha(ROOT / name)
    manifest = dict(generated_at=datetime.now(timezone.utc).isoformat(), source_sha256=sources,
        builder_sha256=sha(Path(__file__)), generated_sha256={'intervals.tex': sha(generated), 'results.tex': sha(results_path)},
        all_planned_rows=24, dependent_pairs=24, independent_tasks=4, original_unknown_usage_calls=2,
        complete_terminal_usage_recovered=False, conditional_intervals=True,
        primary_manuscript_replaced=False, professor_brief_changed=False, authors_confirmed=False,
        submission_ready=False, visual_reviewed=False, novel_method_claim=False,
        general_quality_preservation_claim=False)
    write_json(folder / 'build_manifest.json', manifest)
    print({'source_files': len(sources), 'rows': 24, 'original_unknown_usage_calls': 2})


if __name__ == '__main__':
    build()
