"""Typeset an explicitly unofficial preview with the already checked mirror class.

No archive download, class redistribution, author inference, or publication.
The current manuscript and its generic-class PDF are left intact.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

import pymupdf

ROOT = Path(__file__).resolve().parents[1]
PAPER = ROOT / 'papers/202610_letter'
CHECK = 'reports/ieice_mirror_check_20261023.json'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')


def build(mirror, tex_bin, output):
    check = json.loads((ROOT / CHECK).read_text())
    for name, expected in check['files'].items():
        if sha(mirror / name) != expected['sha256']: raise ValueError('mirror_file_changed:' + name)
    source_map = json.loads((PAPER / 'cost_completion_source_map.json').read_text())
    for group in ('sources', 'rendering_sources'):
        for name, digest in source_map[group].items():
            if sha(ROOT / name) != digest: raise ValueError('manuscript_source_changed:' + name)
    if sha(PAPER / 'candidate_cost_completion.pdf') != source_map['pdf_sha256']:
        raise ValueError('checked_current_manuscript_required')
    if output.exists(): raise FileExistsError('use_a_new_preview_directory_to_preserve_prior_attempts')
    output.mkdir(parents=True); (output / 'build').mkdir()
    (output / 'ieicej.cls').write_bytes((mirror / 'ieicej.cls').read_bytes())
    source = (PAPER / 'candidate_cost_completion.tex').read_text()
    body = source[source.index(r'\section{目的と検証する問い}'):source.index(r'\input{papers/202610_letter/english_endmatter.tex}')]
    metadata = json.loads((PAPER / 'submission_metadata.json').read_text())
    preamble = r'''% Unofficial mirror-class typesetting preview; not a submission-ready manuscript.
\documentclass[letter]{ieicej}
\usepackage[dvipdfmx]{graphicx,xcolor}
\usepackage[fleqn]{amsmath}
\usepackage{newtxtext}
\usepackage[varg]{newtxmath}
\usepackage{url}
\input{papers/202610_letter/submission_metadata.tex}
\input{papers/202610_letter/inventory_tables.tex}
\input{papers/202610_letter/public_display_tables.tex}
\typeofletter{組版予行・未投稿}
\field{}
'''
    preamble += '\\jtitle{' + metadata['title_ja'] + '}\n\\etitle{' + metadata['title_en'] + '}\n'
    preamble += r'''\authorlist{\authorentry{著者未設定}{Author details pending}{}{}\MembershipNumber{}}
\jalcdoi{???????????}
\begin{document}
\maketitle
\begin{abstract}
\input{papers/202610_letter/cost_completion_abstract_ja.txt}
\end{abstract}
\begin{keyword}\LetterJapaneseKeywords\end{keyword}
\begin{eabstract}
\input{papers/202610_letter/cost_completion_abstract_en.txt}
\end{eabstract}
\begin{ekeyword}\LetterEnglishKeywords\end{ekeyword}
'''
    text = preamble + body + '\n' + r'\label{PreviewLastBodyPage}' + '\n' + r'\end{document}' + '\n'
    dependencies = {}
    def copy_inputs(content):
        for name in re.findall(r'\\input\{([^}]+)\}', content):
            if name in dependencies: continue
            path = (ROOT / name).resolve()
            if not path.is_relative_to(PAPER) or path.suffix not in ('.tex', '.txt'):
                raise ValueError('unexpected_preview_input:' + name)
            value = path.read_bytes(); dependencies[name] = sha(path)
            target = output / name; target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(value)
            copy_inputs(value.decode())
    copy_inputs(text); (output / 'preview.tex').write_text(text)
    environment = dict(os.environ, SOURCE_DATE_EPOCH='1792677600', FORCE_SOURCE_DATE='1',
                       openin_any='p', openout_any='p')
    manifest = {'mirror_check_sha256': sha(ROOT / CHECK), 'class_sha256': sha(mirror / 'ieicej.cls'),
        'class_version': check['actual_class_provides'], 'mirror_commit': check['source_commit'],
        'source_pdf_sha256': source_map['pdf_sha256'], 'source_map_sha256': sha(PAPER / 'cost_completion_source_map.json'),
        'source_tex_sha256': sha(PAPER / 'candidate_cost_completion.tex'), 'input_sha256': dependencies,
        'preview_tex_sha256': sha(output / 'preview.tex'), 'builder_sha256': sha(Path(__file__)),
        'current_official_template_verified': False, 'submission_ready': False,
        'authors_are_placeholders': True, 'main_source_or_results_modified': False,
        'shell_escape': False, 'file_input_output_policy': 'p', 'visual_reviewed_pages': [],
        'tex_engine_sha256': sha(tex_bin / 'uplatex'), 'dvi_converter_sha256': sha(tex_bin / 'dvipdfmx')}
    save(output / 'manifest.json', manifest)
    for number in (1, 2):
        result = subprocess.run([str(tex_bin / 'uplatex'), '-no-shell-escape', '-interaction=nonstopmode',
            '-halt-on-error', '-recorder', '-output-directory=build', 'preview.tex'], cwd=output, env=environment,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=120)
        (output / f'pass_{number}.log').write_text(result.stdout)
        if result.returncode:
            manifest['status'] = 'typesetting_failed'; save(output / 'manifest.json', manifest)
            raise RuntimeError('preview_typesetting_failed:' + str(output / f'pass_{number}.log'))
    result = subprocess.run([str(tex_bin / 'dvipdfmx'), '-o', 'build/preview.pdf', 'build/preview.dvi'],
        cwd=output, env=environment, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=120)
    (output / 'pdf.log').write_text(result.stdout); result.check_returncode()
    log = (output / 'build/preview.log').read_text(); aux = (output / 'build/preview.aux').read_text()
    tex_root = tex_bin.parent.parent.resolve(); tex_inputs = {}
    for line in (output / 'build/preview.fls').read_text().splitlines():
        if not line.startswith('INPUT '): continue
        path = Path(line[6:])
        if not path.is_absolute(): path = output / path
        path = path.resolve()
        if path.is_file() and path.is_relative_to(tex_root):
            tex_inputs[str(path.relative_to(tex_root))] = sha(path)
    manifest['tex_distribution_input_sha256'] = tex_inputs
    match = re.search(r'\\newlabel\{PreviewLastBodyPage\}\{\{[^}]*\}\{(\d+)\}', aux)
    if not match: raise ValueError('missing_body_boundary')
    manifest.update(status='rendered_unreviewed', main_pages=int(match[1]),
        pdf_sha256=sha(output / 'build/preview.pdf'), outside_page=[],
        overfull_boxes=log.count('Overfull \\hbox') + log.count('Overfull \\vbox'),
        underfull_boxes=log.count('Underfull \\hbox') + log.count('Underfull \\vbox'),
        undefined_citations=len(re.findall(r'Citation .*? undefined', log)),
        undefined_references=len(re.findall(r'Reference .*? undefined', log)))
    with pymupdf.open(output / 'build/preview.pdf') as pdf:
        manifest['pages'] = len(pdf)
        manifest['english_endmatter_pages'] = len(pdf) - manifest['main_pages']
        for number, page in enumerate(pdf, 1):
            for block in page.get_text('blocks'):
                box = pymupdf.Rect(block[:4])
                if box.x0 < -0.5 or box.y0 < -0.5 or box.x1 > page.rect.width + 0.5 or box.y1 > page.rect.height + 0.5:
                    manifest['outside_page'].append({'page': number, 'bbox': list(box)})
            page.get_pixmap(matrix=pymupdf.Matrix(1.4, 1.4)).save(output / f'page_{number}.png')
    save(output / 'manifest.json', manifest)
    print({key: manifest[key] for key in ('status', 'main_pages', 'pages', 'overfull_boxes', 'undefined_citations', 'pdf_sha256')})


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--mirror', type=Path, required=True); p.add_argument('--tex-bin', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True); a = p.parse_args()
    build(a.mirror.resolve(), a.tex_bin.resolve(), a.output.resolve())
