"""Render a hash-bound letter draft into a fresh private build directory."""
import argparse
from datetime import datetime, timezone
import os
from pathlib import Path
import re
import shutil
import subprocess

import pymupdf

from run_handoff_factors import ROOT, read, sha
from run_context_comparison import write_json


def render(root, folder_name, tex_bin, output):
    root = root.resolve()
    folder = (root / folder_name).resolve()
    if not folder.is_relative_to(root / 'papers') or (folder / 'draft.pdf').exists():
        raise ValueError('new_draft_under_papers_required')
    manifest = read(folder / 'build_manifest.json')
    for name, expected in manifest['source_sha256'].items():
        if sha(root / name) != expected:
            raise ValueError('bound_draft_source_changed:' + name)
    for name, expected in manifest['generated_sha256'].items():
        if sha(folder / name) != expected:
            raise ValueError('generated_draft_table_changed:' + name)
    source = (folder / 'draft.tex').read_text()
    ja = source.split('\\textbf{あらまし案}\\quad\n', 1)[1].split('\n\n', 1)[0]
    en = source.split('\\textbf{Summary draft}\\quad ', 1)[1].split('\n', 1)[0]
    if len(ja) > 120 or len(en.split()) > 50 or any(c in ja for c in ('。', '・')):
        raise ValueError('abstract_length_or_punctuation_invalid')
    output.mkdir(parents=True, exist_ok=False)
    env = dict(os.environ, SOURCE_DATE_EPOCH=str(int(datetime(2026, 10, 24,
               tzinfo=timezone.utc).timestamp())), FORCE_SOURCE_DATE='1')
    for number in (1, 2):
        run = subprocess.run([str(tex_bin / 'uplatex'), '-no-shell-escape',
            '-interaction=nonstopmode', '-halt-on-error', '-output-directory=' + str(output),
            str(folder / 'draft.tex')], cwd=root, env=env, capture_output=True,
            text=True, timeout=60)
        (output / f'pass_{number}.log').write_text(run.stdout + run.stderr)
        run.check_returncode()
    run = subprocess.run([str(tex_bin / 'dvipdfmx'), '-o', str(output / 'draft.pdf'),
        str(output / 'draft.dvi')], cwd=root, env=env, capture_output=True, text=True, timeout=60)
    (output / 'pdf.log').write_text(run.stdout + run.stderr)
    run.check_returncode()
    log = (output / 'draft.log').read_text()
    layout = dict(overfull_boxes=log.count('Overfull \\hbox') + log.count('Overfull \\vbox'),
        underfull_boxes=log.count('Underfull \\hbox') + log.count('Underfull \\vbox'),
        undefined_citations=len(re.findall(r'Citation .*? undefined', log)),
        undefined_references=len(re.findall(r'Reference .*? undefined', log)),
        outside_page=[], visual_reviewed_pages=[], pdf_sha256=sha(output / 'draft.pdf'),
        ja_abstract_characters=len(ja), en_summary_words=len(en.split()),
        toolchain='TinyTeX v2026.10 / uplatex / dvipdfmx; shell escape disabled',
        official_journal_class=False, renderer_sha256=sha(Path(__file__)),
        synthetic_only=manifest.get('synthetic_only', False))
    with pymupdf.open(output / 'draft.pdf') as pdf:
        layout.update(pages=len(pdf), body_pages=len(pdf)-1)
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
    print({key: layout[key] for key in ('pages', 'body_pages', 'overfull_boxes',
                                       'outside_page', 'synthetic_only')})
    return layout


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo-root', type=Path, default=ROOT)
    parser.add_argument('--folder', default='papers/202610_letter/closed_control_integration')
    parser.add_argument('--tex-bin', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    render(args.repo_root, args.folder, args.tex_bin.resolve(), args.output_dir.resolve())
