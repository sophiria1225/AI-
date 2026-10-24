"""Re-export the preserved P82 report with shorter table rows; no analysis rerun."""
import argparse
import shutil
from pathlib import Path

import build_budget_report
from build_late_clock_report_v02 import STEM
from run_handoff_factors import ROOT, read, sha
from run_context_comparison import write_json


def run(source, output):
    manifest = read(source / 'build_manifest.json')
    for name, expected in manifest['source_sha256'].items():
        if sha(ROOT / name) != expected:
            raise ValueError('closed_report_source_changed:' + name)
    if read(source / 'layout_checks.json')['errors'] != [
            {'slide': 2, 'tag': 'results', 'reason': 'overlaps-takeaway'},
            {'slide': 3, 'tag': 'results', 'reason': 'overlaps-takeaway'}]:
        raise ValueError('preserved_original_layout_failure_required')
    if output.exists():
        raise FileExistsError('preserve_previous_presentation_versions')
    original_hashes = {str(p.relative_to(source)): sha(p)
                       for p in sorted(source.rglob('*')) if p.is_file()}
    shutil.copytree(source, output)
    path = output / 'index.html'
    text = path.read_text()
    if text.count('</style>') != 1:
        raise ValueError('one_stylesheet_required')
    css = '.results td,.results th{font-size:14px;line-height:1.25;padding:3px 9px}'
    path.write_text(text.replace('</style>', css + '</style>'))
    for name, expected in original_hashes.items():
        if name not in ('index.html', 'build_manifest.json', 'layout_checks.json') and sha(output / name) != expected:
            raise ValueError('presentation_data_must_remain_byte_identical')
    manifest.update(layout_revision='Shorter rows on all results tables; original failed export retained.',
        initial_presentation_sha256=original_hashes, layout_fixer_sha256=sha(Path(__file__)),
        html_sha256=sha(path), visual_reviewed=False)
    write_json(output / 'build_manifest.json', manifest)
    build_budget_report.STEM = STEM
    build_budget_report.export(output)
    print({'output': str(output), 'csv_and_slides_unchanged': True,
           'layout_errors': read(output / 'layout_checks.json')['errors']})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=ROOT / 'materials/20261024_p82_results')
    parser.add_argument('--output', type=Path, default=ROOT / 'materials/20261024_p82_results_v02')
    args = parser.parse_args()
    run(args.source, args.output)
