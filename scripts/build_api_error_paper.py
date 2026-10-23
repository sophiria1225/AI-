"""Add the full closed P78 comparison to the checked empirical manuscript."""
import argparse
from pathlib import Path

import build_reasoning_comparison_paper as previous
from build_api_error_report import validated, totals, STEM
from build_public_completion_paper import save
from api_error_comparison import ARMS
from run_handoff_factors import ROOT, read, sha

PAPER = previous.PAPER
COMPONENT = 'papers/202610_letter/api_error_comparison_component.tex'


def paper_component(plan, report, session):
    rows = []
    for name, task in zip(('写真', '精算', '返金', '書出'), plan['known_tasks'], strict=True):
        cells = {r['arm']: r for r in report['rows'] if r['task_id'] == task['task_id']}
        values = [('成功' if cells[a]['success'] else '未達') + f' {cells[a]["known_total_tokens"]:,}' for a in ARMS]
        errors = '/'.join(str(cells[a]['invocation_exceptions']) for a in ARMS)
        rows.append(' & '.join((name, *values, errors)) + r'\\')
    ts = [totals(report['rows'], a) for a in ARMS]
    return '\n'.join([
        '% Generated from all eight audited P78 conditions; no outcome exclusions.',
        r'\section{API失敗通知の通常対照}',
        '同じ４課題を開始から各１回，実API例外を文字列値で返すVとPython例外で通知するEを比較した．',
        '型付き正常値，最初からの推論保持，持続Python，公開名と予算は共通である．',
        '各80生成・450,000 token・1,800秒，APIは写真160・他80とし，過去比較の再現とはしない．',
        r'\begin{center}\begin{minipage}{\columnwidth}\centering',
        r'\small 失敗通知の全８条件：成否・仕事token\par\smallskip',
        r'\begin{tabular}{lrrc}\hline 課題 & V：文字列 & E：例外 & 実例外V/E\\\hline',
        *rows, r'\hline',
        f'合計 & {ts[0]["known_total_tokens"]:,} & {ts[1]["known_total_tokens"]:,} & '
        f'{ts[0]["invocation_exceptions"]}/{ts[1]["invocation_exceptions"]}' + r'\\',
        r'\hline\end{tabular}\end{minipage}\end{center}',
        f'両方3/4成功，全使用量既知で，E$-$Vは{report["exception_minus_value_whole_task_tokens"]:+,} tokenだった．',
        '全件評価・監査・費用既知の下，実例外と双方成功があり，成功を失わずEの合計費用が減る採用条件は未達だった．',
        '初回の実送信要求は全対一致した．参照IDだけをそろえた事後照合では，写真・精算は第３回の例外後，第４回に入力が分かれた．',
        '返金・書出しは第６回に残時間通知だけが１秒異なり，公開出力も分かれた．返金には実例外がなく，書出しEの最初の例外は第19回だった．',
        'ID置換後のJSON照合に限り，通知前の差を通知方法の効果にしない．残時間１秒の因果効果も未特定である．',
        f'全{sum(t["model_calls"] for t in ts)}生成・{sum(t["api_requests"] for t in ts)} API・８評価，'
        f'推論器全稼働{session["wall_seconds"]:,.3f}秒を記録した．',
    ]) + '\n'


def build(tex_bin, output):
    plan, report, pre, session, sources = validated()
    provenance = read(ROOT / 'reports/P78_results_provenance_20261023.json')
    for name, expected in provenance['source_sha256'].items():
        if sha(ROOT / name) != expected:
            raise ValueError('published_P78_source_changed: ' + name)
    material_path = ROOT / 'materials/20261023_p78/build_manifest.json'
    material = read(material_path)
    if (material['source_sha256'] != sources or not material['visual_reviewed']
            or material['visual_reviewed_pages'] != list(range(1, 8))
            or material['pdf_sha256'] != sha(material_path.parent / (STEM + '.pdf'))
            or material['builder_sha256'] != sha(ROOT / 'scripts/build_api_error_report.py')
            or any(r['record_status'] != 'evaluated' or r['unknown_usage_calls'] for r in report['rows'])):
        raise ValueError('reviewed_all_eight_P78_results_required')
    if sha(ROOT / 'scripts/build_reasoning_comparison_paper.py') != '167b05a91b352cbaab96fdf31c75f8e26590e0783092283c61075a9865356c01':
        raise ValueError('previous_closed_evidence_checker_changed')
    if (PAPER / 'candidate_cost_completion.tex').read_text().count('\\input{' + COMPONENT + '}') != 1:
        raise ValueError('include_all_eight_P78_conditions_exactly_once')
    integration = ROOT / 'docs/P78_manuscript_integration.md'
    if not integration.is_file(): raise ValueError('document_manuscript_scope')
    (ROOT / COMPONENT).write_text(paper_component(plan, report, session))
    previous.build(tex_bin, output)
    path = PAPER / 'cost_completion_source_map.json'; manifest = read(path)
    manifest['sources'].update(sources)
    manifest['sources']['reports/P78_results_provenance_20261023.json'] = sha(ROOT / 'reports/P78_results_provenance_20261023.json')
    manifest['rendering_sources'].update({p: sha(ROOT / p) for p in (
        COMPONENT, 'docs/P78_findings.md', 'docs/P78_manuscript_integration.md',
        'materials/20261023_p78/build_manifest.json', 'scripts/build_api_error_report.py')})
    manifest['previous_reasoning_comparison_checker_sha256'] = manifest['builder_sha256']
    manifest['builder_sha256'] = sha(Path(__file__))
    manifest['data_checks']['api_error_comparison'] = {k: report[k] for k in (
        'batch_status', 'all_eight_complete_with_known_usage', 'paired_results',
        'paired_success_losses', 'paired_success_gains', 'paired_successful_tasks',
        'exception_minus_value_whole_task_tokens', 'invocation_exceptions_observed',
        'development_gate_met', 'general_quality_preservation_claim', 'novel_method_claim')}
    manifest['data_checks']['api_error_comparison']['totals'] = [totals(report['rows'], a) for a in ARMS]
    manifest['data_checks']['api_error_comparison']['content_divergence'] = read(
        ROOT / 'reports/P78_input_content_divergence.json')['pairs']
    manifest['separate_api_error_conditions'] = 8
    manifest['P78_is_concurrent_control_for_previous_comparisons'] = False
    manifest['P78_results_included'] = True
    save(path, manifest)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--tex-bin', type=Path, required=True)
    p.add_argument('--output-dir', type=Path, default=ROOT / '.runtime/api-error-paper')
    a = p.parse_args(); build(a.tex_bin.resolve(), a.output_dir.resolve())
