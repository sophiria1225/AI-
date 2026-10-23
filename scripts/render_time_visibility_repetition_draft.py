"""Render only the separate P80/P81 repetition draft; preserve the primary paper."""
import argparse
from datetime import datetime, timezone
import os
from pathlib import Path
import re
import shutil
import subprocess

import pymupdf

from run_context_comparison import write_json
from run_handoff_factors import ROOT, read, sha


def render(tex_bin, output):
    folder = ROOT / 'papers/202610_letter/time_visibility_repetitions'
    manifest = read(folder / 'build_manifest.json')
    for name, expected in manifest['source_sha256'].items():
        if sha(ROOT / name) != expected: raise ValueError('draft_source_changed:' + name)
    if any(sha(folder / name) != expected for name, expected in manifest['generated_sha256'].items()):
        raise ValueError('full_cohort_table_changed')
    text = (folder / 'draft.tex').read_text()
    ja = text.split('\\textbf{あらまし案}\\quad\n', 1)[1].split('\n\n', 1)[0]
    en = text.split('\\textbf{Summary draft}\\quad ', 1)[1].split('\n', 1)[0]
    if len(ja) > 120 or len(en.split()) > 50 or any(c in ja for c in ('。', '・')):
        raise ValueError('abstract_format_changed')
    output.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, SOURCE_DATE_EPOCH=str(int(datetime(2026, 10, 24,
               tzinfo=timezone.utc).timestamp())), FORCE_SOURCE_DATE='1')
    for number in (1, 2):
        result = subprocess.run([str(tex_bin / 'uplatex'), '-no-shell-escape',
            '-interaction=nonstopmode', '-halt-on-error', '-output-directory=' + str(output),
            str(folder / 'draft.tex')], cwd=ROOT, env=env, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True, timeout=60)
        (output / f'pass_{number}.log').write_text(result.stdout); result.check_returncode()
    result = subprocess.run([str(tex_bin / 'dvipdfmx'), '-o', str(output / 'draft.pdf'),
        str(output / 'draft.dvi')], cwd=ROOT, env=env, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, text=True, timeout=60)
    (output / 'pdf.log').write_text(result.stdout); result.check_returncode()
    log = (output / 'draft.log').read_text()
    layout = {'overfull_boxes': log.count('Overfull \\hbox') + log.count('Overfull \\vbox'),
        'underfull_boxes': log.count('Underfull \\hbox') + log.count('Underfull \\vbox'),
        'undefined_citations': len(re.findall(r'Citation .*? undefined', log)),
        'undefined_references': len(re.findall(r'Reference .*? undefined', log)),
        'outside_page': [], 'visual_reviewed_pages': [], 'pdf_sha256': sha(output / 'draft.pdf'),
        'ja_abstract_characters': len(ja), 'en_summary_words': len(en.split()),
        'toolchain': 'TinyTeX v2026.10 / uplatex / dvipdfmx; shell escape disabled',
        'official_journal_class': False, 'renderer_sha256': sha(Path(__file__))}
    with pymupdf.open(output / 'draft.pdf') as pdf:
        layout['pages'] = len(pdf)
        layout['body_pages'] = len(pdf) - 1
        for number, page in enumerate(pdf, 1):
            for block in page.get_text('blocks'):
                if (block[0] < -.5 or block[1] < -.5 or block[2] > page.rect.width + .5
                        or block[3] > page.rect.height + .5):
                    layout['outside_page'].append({'page': number, 'bbox': list(block[:4])})
            page.get_pixmap(matrix=pymupdf.Matrix(1.4, 1.4)).save(output / f'page_{number}.png')
    write_json(output / 'layout.json', layout)
    if (not 1 <= layout['body_pages'] <= 4 or any(layout[k] for k in
            ('overfull_boxes', 'outside_page', 'undefined_citations', 'undefined_references'))):
        raise ValueError('draft_layout_needs_correction')
    shutil.copyfile(output / 'draft.pdf', folder / 'draft.pdf')
    write_json(folder / 'layout.json', layout)
    manifest.update(pdf_sha256=layout['pdf_sha256'], renderer_sha256=layout['renderer_sha256'],
                    pages=layout['pages'], body_pages=layout['body_pages'], visual_reviewed=False)
    write_json(folder / 'build_manifest.json', manifest)
    print({k: layout[k] for k in ('pages', 'body_pages', 'overfull_boxes', 'outside_page')})


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--tex-bin', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, default=ROOT / '.runtime/time-visibility-repetitions-draft')
    args = parser.parse_args()
    render(args.tex_bin.resolve(), args.output_dir.resolve())
