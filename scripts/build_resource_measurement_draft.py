"""Integrate closed P80/P81 resource measures without changing earlier drafts."""
from datetime import datetime, timezone
from pathlib import Path

from run_context_comparison import write_json
from run_handoff_factors import ROOT, read, sha

FOLDER = 'papers/202610_letter/resource_measurement'


def build():
    sources = {}
    ledgers = ('reports/P81_interval_manuscript_provenance_20261024.json',
               'reports/P81_resource_accounting_provenance_20261024.json',
               'reports/protocol_prior_exposure_provenance_20261024.json')
    for name in ledgers:
        for source, expected in read(ROOT / name)['source_sha256'].items():
            if sha(ROOT / source) != expected:
                raise ValueError('closed_source_changed:' + source)
            sources[source] = expected
        sources[name] = sha(ROOT / name)
    previous = read(ROOT / 'papers/202610_letter/time_visibility_intervals/build_manifest.json')
    report = read(ROOT / 'materials/20261024_p81_resource_accounting/resource_accounting.json')
    for mapping in (previous['source_sha256'], report['source_sha256']):
        for source, expected in mapping.items():
            if sha(ROOT / source) != expected:
                raise ValueError('bound_dependency_changed:' + source)
            sources[source] = expected
    if (len(report['rows']) != 24 or len(report['partitions']) != 32
            or report['saved_attempts'] != 429 or report['known_receipts'] != 427
            or report['terminal_unknowns_retained'] != 2 or report['missing_usage_imputed']
            or any(report[k] for k in ('additional_generations', 'additional_input_count_requests',
                                      'additional_api_requests', 'additional_evaluations'))):
        raise ValueError('all_closed_resource_rows_required')
    m, h = report['totals']['measured'], report['totals']['not_exposed']
    if not m['terminal_usage_complete'] or h['terminal_usage_complete']:
        raise ValueError('original_missingness_required')
    lines = [r'\begin{table}[tb]', r'\centering\small\setlength{\tabcolsep}{3pt}',
        r'\caption{全24条件の資源・時間指標．Hのtoken欄は終端既知分の下限であり，不明２生成を０に補完していない．時間は実測合計．}',
        r'\begin{tabular}{lrr}', r'指標 & M & H \\ \hline']
    # Keep prefill and decoding separate; neither is a FLOPs estimate.
    for label, key in [('cacheを除く入力', 'known_uncached_input_tokens'), ('出力token', 'output_tokens')]:
        lines.append(f'{label} & {m[key]:,} & $\\geq${h[key]:,}' + r' \\')
    for label, key in [('作業時間（秒）', 'wall_seconds'), ('準備・後片付け込（秒）', 'full_wall_seconds')]:
        lines.append(f'{label} & {m[key]:,.1f} & {h[key]:,.1f}' + r' \\')
    lines += [r'\hline', r'\end{tabular}', r'\end{table}']
    differences = report['differences']
    lines += [
        '論理tokenの条件付き合計がHで小さくても，cacheを除く入力と出力は既知分だけでMの完全合計を上回る．'
        f'増加はそれぞれ少なくとも{differences["known_uncached_input_tokens"]["H_minus_M_percent"]:.2f}\\%，'
        f'{differences["output_tokens"]["H_minus_M_percent"]:.2f}\\%で，'
        f'作業時間は実測{differences["wall_seconds"]["H_minus_M_percent"]:.2f}\\%長かった．',
        '入力処理と出力生成は異なる計算であり，token数をFLOPs，電力量，料金へ換算しない．'
        '時間にはモデル待ち，通知，計数，API等が含まれ，純粋なGPU処理時間ではない．'
        'ホスト負荷と実行経路も異なるため，時間差を通知方式の因果的な速度差とはしない．',
    ]
    parts = {(r['category'], r['time_visibility']): r for r in report['partitions']
             if r['repetition'] == 'combined'}
    sm, sh = parts['both_success', 'measured'], parts['both_success', 'not_exposed']
    fm, fh = parts['both_failure', 'measured'], parts['both_failure', 'not_exposed']
    lines.append(f'両側成功部分ではcacheを除く入力が{sm["known_uncached_input_tokens"]-sh["known_uncached_input_tokens"]:,}，'
        f'出力が{sm["output_tokens"]-sh["output_tokens"]:,} token減り，'
        f'作業時間も{sm["wall_seconds"]-sh["wall_seconds"]:.1f}秒短かった．'
        f'一方，失敗部分は既知分だけでそれぞれ{fh["known_uncached_input_tokens"]-fm["known_uncached_input_tokens"]:,}，'
        f'{fh["output_tokens"]-fm["output_tokens"]:,} token増え，'
        f'作業時間は{fh["wall_seconds"]-fm["wall_seconds"]:.1f}秒長く，成功部分の減少を上回った．')
    shared = report['shared_session_measures']
    lines.append(f'P80/P81の別セッションの推論器滞在は計{shared["wall_seconds"]:,.1f}秒，'
        f'ロード{shared["load_wall_seconds"]:.2f}秒，評価{shared["evaluation_wall_seconds"]:.2f}秒だった．'
        'これらは重なる測定値であり合算しない．共通時間をM/Hへ割り付けず，全件表に残す．')
    folder = ROOT / FOLDER
    path = folder / 'resources.tex'
    text = '\n'.join(lines) + '\n'
    if path.exists() and path.read_text() != text:
        raise ValueError('preserve_generated_resource_table')
    if not path.exists():
        path.write_text(text)
    for name in (FOLDER + '/draft.tex', 'scripts/build_resource_measurement_draft.py',
                 'scripts/render_resource_measurement_draft.py',
                 'papers/202610_letter/time_visibility_intervals/results.tex',
                 'papers/202610_letter/time_visibility_intervals/intervals.tex',
                 'papers/202610_letter/time_visibility_repetitions/stability.tex'):
        sources[name] = sha(ROOT / name)
    manifest = dict(generated_at=datetime.now(timezone.utc).isoformat(), source_sha256=sources,
        builder_sha256=sha(Path(__file__)), generated_sha256={'resources.tex': sha(path)},
        all_planned_rows=24, saved_attempts=429, original_unknown_usage_calls=2,
        old_numeric_tables_unchanged=True, conditional_intervals=True,
        terminal_usage_imputed=False, gpu_compute_measured=False, causal_speed_claim=False,
        primary_manuscript_replaced=False, professor_brief_changed=False,
        authors_confirmed=False, official_journal_class=False, submission_ready=False,
        visual_reviewed=False, novel_method_claim=False, general_quality_preservation_claim=False)
    write_json(folder / 'build_manifest.json', manifest)
    print({'source_files': len(sources), 'rows': 24, 'unknown_usage_calls': 2})


if __name__ == '__main__':
    build()
