"""Correct P97 spacing and separate known task outcomes from unknown costs."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import shutil

import build_budget_report
import build_recovery_notice_report as evidence
from build_recovery_notice_draft import quality_status
from run_context_comparison import write_json
from run_handoff_factors import ROOT, read, sha

CSS = '''<style id="P97-layout-v03">
.results{margin-top:12px;line-height:1.22}
.results td,.results th{font-size:15px;padding:4px 10px}
.slide:has(.results) .takeaway{font-size:20px;padding:11px 16px}
</style>'''


def render(root, source, output):
    root, source, output = root.resolve(), source.resolve(), output.resolve()
    _, report, *_ = evidence.validated(root)
    if output.exists() or not output.is_relative_to(root / 'materials'):
        raise ValueError('fresh_report_under_materials_required')
    original = read(source / 'build_manifest.json')
    layout = read(source / 'layout_checks.json')
    if layout != {'pages': 8, 'errors': [
        {'slide': n, 'tag': 'results', 'reason': 'overlaps-takeaway'} for n in (2, 5, 7)
    ]}:
        raise ValueError('preserved_initial_P97_layout_failure_required')
    if (original['pages'] != 8 or original['all_planned_rows'] != 12
            or original['builder_sha256'] != sha(root / 'scripts/build_recovery_notice_report.py')
            or original['summary_sha256'] != sha(source / 'whole_cohort_summary.json')):
        raise ValueError('original_P97_content_manifest_required')
    for name, digest in original['source_sha256'].items():
        if sha(root / name) != digest:
            raise ValueError('closed_report_source_changed:' + name)
    allowed = {'index.html', 'slides.json', 'build_manifest.json', 'layout_checks.json',
        'whole_cohort_summary.json', 'all_twelve_conditions.csv',
        'all_twelve_task_pairs.csv', 'cost_contributions.csv',
        'figures/P97_whole_task_costs.svg', 'figures/P97_whole_task_costs.png',
        'figures/P97_whole_task_costs.pdf'}
    paths = [p for p in source.rglob('*') if p.is_file()]
    if {p.relative_to(source).as_posix() for p in paths} != allowed or any(p.is_symlink() for p in source.rglob('*')):
        raise ValueError('only_original_public_report_files_permitted')
    document = (source / 'index.html').read_text()
    if document.count('</head>') != 1 or 'P97-layout-v03' in document:
        raise ValueError('one_original_HTML_head_required')
    shutil.copytree(source, output, ignore=shutil.ignore_patterns('layout_checks.json'))
    slides = read(source / 'slides.json')
    old_body = slides[3]['body']
    new_body = old_body.replace('課題ごとの成功喪失なし', '課題別の成功評価')
    for pair in report['pairs']:
        label = '確認' if pair['no_per_task_success_loss'] else '未確認／非該当'
        old_cell = '<td>' + label + '</td>'
        if old_cell not in new_body:
            raise ValueError('original_quality_display_cell_missing')
        new_body = new_body.replace(old_cell, '<td>' + quality_status(pair) + '</td>', 1)
    if document.count(old_body) != 1 or new_body == old_body:
        raise ValueError('single_quality_table_correction_required')
    revised = document.replace(old_body, new_body)
    slides[3]['body'] = new_body
    write_json(output / 'slides.json', slides)
    (output / 'index.html').write_text(revised.replace('</head>', CSS + '</head>'))
    preserved = {p.relative_to(source).as_posix(): sha(p) for p in paths
        if p.name not in ('index.html', 'slides.json', 'layout_checks.json', 'build_manifest.json')}
    for name, digest in preserved.items():
        if sha(output / name) != digest:
            raise ValueError('report_data_not_preserved:' + name)
    if (output / 'index.html').read_text().replace(CSS, '') != revised:
        raise ValueError('only_spacing_and_declared_quality_table_may_change')
    manifest = dict(original, layout_edition=3, layout_corrected_at=datetime.now(timezone.utc).isoformat(),
        initial_manifest_sha256=sha(source / 'build_manifest.json'),
        initial_layout_sha256=sha(source / 'layout_checks.json'),
        initial_HTML_sha256=sha(source / 'index.html'),
        initial_slides_sha256=sha(source / 'slides.json'),
        quality_display_rule='Per-task success status is derived from final Boolean evaluations independently of usage completeness. Frozen adoption gates and all numeric records are unchanged.',
        quality_display_source_sha256=sha(root / 'scripts/build_recovery_notice_draft.py'),
        preserved_report_content_sha256=preserved,
        layout_renderer_sha256=sha(Path(__file__)), visual_reviewed=False,
        model_generations_added_by_layout_repair=0,
        environment_API_requests_added_by_layout_repair=0, evaluations_added_by_layout_repair=0)
    write_json(output / 'build_manifest.json', manifest)
    build_budget_report.STEM = evidence.STEM
    build_budget_report.export(output)
    print({'pages': 8, 'layout_edition': 3, 'preserved_content_files': len(preserved)})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo-root', type=Path, default=ROOT)
    parser.add_argument('--source-report', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    render(args.repo_root, args.source_report, args.output)
