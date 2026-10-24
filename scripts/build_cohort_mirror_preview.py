"""Typeset an explicitly unofficial preview with the already checked mirror class.

No archive download, class redistribution, author inference, or publication.
The closed resource manuscript and every earlier PDF are left intact.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

import pymupdf
from format_action_execution_preview import TITLE_STYLE

ROOT = Path(__file__).resolve().parents[1]
PAPER = ROOT / 'papers/202610_letter'
SOURCE = PAPER / 'execution_evidence_cohort'
CHECK = 'reports/ieice_mirror_check_20261023.json'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')


def build(mirror, tex_bin, output):
    check = json.loads((ROOT / CHECK).read_text())
    for name, expected in check['files'].items():
        if sha(mirror / name) != expected['sha256']: raise ValueError('mirror_file_changed:' + name)
    source_map = json.loads((SOURCE / 'build_manifest.json').read_text())
    if (not source_map['visual_reviewed'] or not source_map.get('closed_P98_evidence_added')
            or source_map['pdf_sha256'] != '9d4a7d1f76e952cb9bd78ff50bf1384f303e09d47d778d87cdef1b3742f38981'):
        raise ValueError('reviewed_closed_P98_cohort_manuscript_required')
    for name, digest in source_map['source_sha256'].items():
        if sha(ROOT / name) != digest: raise ValueError('manuscript_source_changed:' + name)
    for name, digest in source_map['generated_sha256'].items():
        if sha(SOURCE / name) != digest: raise ValueError('generated_table_changed:' + name)
    if sha(SOURCE / 'draft.pdf') != source_map['pdf_sha256']:
        raise ValueError('checked_resource_manuscript_required')
    if output.exists(): raise FileExistsError('use_a_new_preview_directory_to_preserve_prior_attempts')
    output.mkdir(parents=True); (output / 'build').mkdir()
    (output / 'ieicej.cls').write_bytes((mirror / 'ieicej.cls').read_bytes())
    source = (SOURCE / 'draft.tex').read_text()
    body = source[source.index(r'\section{問題設定と関連研究}'):source.index(r'\clearpage')]
    metadata = json.loads((PAPER / 'submission_metadata.json').read_text())
    title_ja = re.search(r'\\title\{(.*?)\}\s*\\author', source, re.S).group(1)
    title_en = source.split('\\textbf{Title}\\quad ', 1)[1].split('\n', 1)[0]
    if (title_ja.replace(r'\newline', '').replace(' ', '') != metadata['title_ja'].replace(' ', '')
            or title_en != metadata['title_en']):
        raise ValueError('preserve_agreed_source_titles')
    abstract_ja = source.split('\\textbf{あらまし案}\\quad\n', 1)[1].split('\n\n', 1)[0]
    abstract_en = source.split('\\textbf{Summary draft}\\quad ', 1)[1].split('\n', 1)[0]
    keywords_ja = source.split('\\textbf{キーワード}\\quad ', 1)[1].split('\n', 1)[0]
    keywords_en = source.split('\\textbf{Keywords}\\quad ', 1)[1].split('\n', 1)[0]
    preamble = r'''% Unofficial mirror-class typesetting preview; not a submission-ready manuscript.
\documentclass[letter]{ieicej}
\usepackage[dvipdfmx]{graphicx,xcolor}
\usepackage[fleqn]{amsmath}
\usepackage{newtxtext}
\usepackage[varg]{newtxmath}
\usepackage{url}
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
    preamble = preamble.replace(r'\input{papers/202610_letter/cost_completion_abstract_ja.txt}', abstract_ja)
    preamble = preamble.replace(r'\input{papers/202610_letter/cost_completion_abstract_en.txt}', abstract_en)
    preamble = preamble.replace(r'\LetterJapaneseKeywords', keywords_ja).replace(r'\LetterEnglishKeywords', keywords_en)
    text = preamble + body + '\n' + r'\label{PreviewLastBodyPage}' + '\n' + r'\end{document}' + '\n'
    before = text
    for original,replacement in TITLE_STYLE.items():
        if text.count(original) != 1: raise ValueError('expected_reference_title_once')
        text = text.replace(original,replacement)
    start,end = text.index(r'\begin{thebibliography}'),text.index(r'\end{thebibliography}')
    text = text[:start] + re.sub(r'(?<=[A-Z]\.) +(?=[A-Z]\.)', '', text[start:end]) + text[end:]
    if (re.findall(r'\\bibitem\{([^}]+)\}',before) != re.findall(r'\\bibitem\{([^}]+)\}',text)
            or re.findall(r'\d+',before) != re.findall(r'\d+',text)):
        raise ValueError('reference_keys_or_numbers_changed')
    dependencies = {}; source_dependencies = {}; table_changes = {}

    def copy_inputs(content):
        for name in re.findall(r'\\input\{([^}]+)\}', content):
            if name in dependencies: continue
            path = (ROOT / name).resolve()
            if not path.is_relative_to(PAPER) or path.suffix not in ('.tex', '.txt'):
                raise ValueError('unexpected_preview_input:' + name)
            value = path.read_text(); source_dependencies[name] = sha(path)
            if path.name in ('whole_task.tex','observed_resources.tex','local_replay.tex','cohort.tex'):
                if value.count(r'\footnotesize') != 1: raise ValueError('one_table_font_setting_required')
                formatted = value.replace(r'\footnotesize',r'\fontsize{8pt}{10pt}\selectfont')
                if path.name == 'whole_task.tex':
                    for n in (1,2):
                        formatted = formatted.replace(f'写真移動{n}',f'写真{n}').replace(f'曲情報の書出し{n}',f'書出し{n}')
                if re.findall(r'\d+',value) != re.findall(r'\d+',formatted.replace(r'\fontsize{8pt}{10pt}\selectfont',r'\footnotesize')):
                    raise ValueError('table_numeric_content_changed')
                table_changes[name] = '8pt/10pt table font; whole-task labels shortened; all numeric content retained.'
                value = formatted
            target = output / name; target.parent.mkdir(parents=True, exist_ok=True); target.write_text(value)
            dependencies[name] = sha(target)
            copy_inputs(value)
    copy_inputs(text); (output / 'preview.tex').write_text(text)
    environment = dict(os.environ, SOURCE_DATE_EPOCH='1792677600', FORCE_SOURCE_DATE='1',
                       openin_any='p', openout_any='p')
    manifest = {'mirror_check_sha256': sha(ROOT / CHECK), 'class_sha256': sha(mirror / 'ieicej.cls'),
        'ja_abstract_characters': len(abstract_ja), 'en_summary_words': len(abstract_en.split()),
        'class_version': check['actual_class_provides'], 'mirror_commit': check['source_commit'],
        'source_pdf_sha256': source_map['pdf_sha256'], 'source_manifest_sha256': sha(SOURCE / 'build_manifest.json'),
        'source_tex_sha256': sha(SOURCE / 'draft.tex'), 'input_sha256': dependencies,
        'source_input_sha256': source_dependencies, 'table_format_changes': table_changes,
        'reference_title_style_changes': TITLE_STYLE, 'reference_keys_order_numbers_preserved': True,
        'selected_source_folder': 'execution_evidence_cohort', 'new_model_generations': 0,
        'new_environment_API_requests': 0, 'new_evaluations': 0, 'reserved_scenarios_read': 0,
        'title_metadata_sha256': sha(PAPER / 'submission_metadata.json'),
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
        pdf_sha256=sha(output / 'build/preview.pdf'), outside_page=[], table_font_samples=[],
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
            for block in page.get_text('dict')['blocks']:
                if block['type'] != 0: continue
                for line in block['lines']:
                    for span in line['spans']:
                        if any(s in span['text'] for s in ('128,796','除外入力','入力対','前史一致')):
                            manifest['table_font_samples'].append(dict(page=number,text=span['text'],size=span['size']))
            page.get_pixmap(matrix=pymupdf.Matrix(1.4, 1.4)).save(output / f'page_{number}.png')
    save(output / 'manifest.json', manifest)
    if (manifest['main_pages'] > 4 or any(manifest[k] for k in
            ('overfull_boxes','outside_page','undefined_citations','undefined_references'))
            or len(manifest['table_font_samples']) < 4
            or min(x['size'] for x in manifest['table_font_samples']) < 7):
        manifest['status']='layout_needs_correction';save(output/'manifest.json',manifest)
        raise ValueError('preview_layout_requires_correction')
    print({key: manifest[key] for key in ('status','main_pages','pages','overfull_boxes','underfull_boxes','undefined_citations','pdf_sha256','table_font_samples')})


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--mirror', type=Path, required=True); p.add_argument('--tex-bin', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True); a = p.parse_args()
    build(a.mirror.resolve(), a.tex_bin.resolve(), a.output.resolve())
