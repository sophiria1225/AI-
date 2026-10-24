"""Improve table readability and reference style in a fresh mirror preview.

Uses the already rendered, hash-bound P94 preview. Experimental results and the
reviewed source manuscript remain unchanged. The mirror is still unofficial.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess

import pymupdf

from build_observed_control_draft import replace_once
from build_resource_mirror_preview import sha, save


TITLE_STYLE = {
    'On the Clock: Towards Punctual and Productive Time-Budgeted AI Agents':
        'On the Clock: towards punctual and productive time-budgeted AI agents',
    'Timely Machine: Awareness of Time Makes Test-Time Scaling Agentic':
        'Timely Machine: awareness of time makes test-time scaling agentic',
    'Understanding and Mitigating Numerical Sources of Nondeterminism in LLM Inference':
        'Understanding and mitigating numerical sources of nondeterminism in LLM inference',
    'ReproEvalCard: A Reporting Standard for Reproducible Evaluation of LLM Pipelines':
        'ReproEvalCard: a reporting standard for reproducible evaluation of LLM pipelines',
    'How Consistent Are LLM Agents? Measuring Behavioral Reproducibility in Multi-Step Tool-Calling Pipelines':
        'How consistent are LLM agents? Measuring behavioral reproducibility in multi-step tool-calling pipelines',
    'Beyond Prompts: Measuring and Optimizing LLM Tool-Agent Harnesses':
        'Beyond prompts: measuring and optimizing LLM tool-agent harnesses',
    'Measuring Local SLM Agents as Systems: Protocol Effects on Quality and Resource Use':
        'Measuring local SLM agents as systems: protocol effects on quality and resource use',
    'Same Simulation, Different Evidence: Where Retrieved Tool Output Costs LLM Agents Accuracy':
        'Same simulation, different evidence: where retrieved tool output costs LLM agents accuracy',
    'Formal Verification of Agentic Systems over Operational Data':
        'Formal verification of agentic systems over operational data',
    'Token Reduction Is Not Cost Reduction': 'Token reduction is not cost reduction',
    'Cache-Aware Prompt Compression: A Two-Tier Cost Model for LLM API Caching':
        'Cache-aware prompt compression: a two-tier cost model for LLM API caching',
    "Don't Break the Cache: An Evaluation of Prompt Caching for Long-Horizon Agentic Tasks":
        "Don't break the cache: an evaluation of prompt caching for long-horizon agentic tasks",
}


def format_preview(source, tex_bin, output):
    old = json.loads((source / 'manifest.json').read_text())
    if (old.get('selected_source_folder') != 'closed_results_action_execution'
            or old['current_official_template_verified'] or old['submission_ready']
            or old['source_pdf_sha256'] != 'd330b952ea9411901e70c68117c26aa6f8cbe3a39d33feedb1035c98b5d4e245'):
        raise ValueError('fixed_unofficial_P94_preview_required')
    if output.exists():
        raise FileExistsError('preserve_previous_renderings')
    for name, expected in {'preview.tex': old['preview_tex_sha256'],
                           'ieicej.cls': old['class_sha256'],
                           **old['input_sha256']}.items():
        if sha(source / name) != expected:
            raise ValueError('preview_input_changed:' + name)
    if sha(tex_bin / 'uplatex') != old['tex_engine_sha256'] or sha(tex_bin / 'dvipdfmx') != old['dvi_converter_sha256']:
        raise ValueError('fixed_renderer_tools_required')
    output.mkdir(parents=True); (output / 'build').mkdir()
    (output / 'ieicej.cls').write_bytes((source / 'ieicej.cls').read_bytes())
    changes = {}
    table_names = {'whole_task.tex', 'observed_resources.tex', 'local_replay.tex'}
    for name, expected in old['input_sha256'].items():
        relative = Path(name)
        if relative.is_absolute() or '..' in relative.parts or relative.suffix != '.tex':
            raise ValueError('unexpected_preview_input')
        text = (source / name).read_text()
        if relative.name in table_names:
            text = replace_once(text, r'\footnotesize', r'\fontsize{8pt}{10pt}\selectfont')
            if relative.name == 'whole_task.tex':
                for number in (1, 2):
                    text = replace_once(text, f'写真移動{number}', f'写真{number}')
                    text = replace_once(text, f'曲情報の書出し{number}', f'書出し{number}')
            changes[name] = {'source_sha256': expected,
                'edit': '8pt table text; whole-task row labels shortened without changing cell values.'}
        target = output / name; target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)
    text = (source / 'preview.tex').read_text()
    for original, replacement in TITLE_STYLE.items():
        text = replace_once(text, original, replacement)
    start, end = text.index(r'\begin{thebibliography}'), text.index(r'\end{thebibliography}')
    before = text[start:end]
    after = re.sub(r'(?<=[A-Z]\.) +(?=[A-Z]\.)', '', before)
    if before == after:
        raise ValueError('expected_author_initial_spacing_changes')
    text = text[:start] + after + text[end:]
    # Keep reference keys, order and all numeric identifiers unchanged.
    original = (source / 'preview.tex').read_text()
    if (re.findall(r'\\bibitem\{([^}]+)\}', original) != re.findall(r'\\bibitem\{([^}]+)\}', text)
            or re.findall(r'\d+', original) != re.findall(r'\d+', text)):
        raise ValueError('reference_identity_or_numeric_content_changed')
    (output / 'preview.tex').write_text(text)
    manifest = dict(old)
    for key in ('status', 'main_pages', 'pages', 'english_endmatter_pages', 'pdf_sha256',
                'outside_page', 'overfull_boxes', 'underfull_boxes', 'undefined_citations',
                'undefined_references', 'tex_distribution_input_sha256'):
        manifest.pop(key, None)
    manifest.update(created_at=datetime.now(timezone.utc).isoformat(),
        parent_preview_manifest_sha256=sha(source / 'manifest.json'),
        parent_preview_pdf_sha256=sha(source / 'build/preview.pdf'),
        source_input_sha256=old['input_sha256'],
        input_sha256={n: sha(output / n) for n in old['input_sha256']},
        preview_tex_sha256=sha(output / 'preview.tex'),
        formatter_sha256=sha(Path(__file__)), table_format_changes=changes,
        reference_title_style_changes=TITLE_STYLE, reference_keys_order_numbers_preserved=True,
        reference_author_initial_spacing_normalized=True, visual_reviewed_pages=[])
    save(output / 'manifest.json', manifest)
    environment = dict(os.environ, SOURCE_DATE_EPOCH='1792677600', FORCE_SOURCE_DATE='1',
                       openin_any='p', openout_any='p')
    for number in (1, 2):
        result = subprocess.run([str(tex_bin / 'uplatex'), '-no-shell-escape', '-interaction=nonstopmode',
            '-halt-on-error', '-recorder', '-output-directory=build', 'preview.tex'], cwd=output,
            env=environment, capture_output=True, text=True, timeout=60)
        (output / f'pass_{number}.log').write_text(result.stdout + result.stderr)
        if result.returncode:
            manifest['status'] = 'typesetting_failed'; save(output / 'manifest.json', manifest)
            result.check_returncode()
    result = subprocess.run([str(tex_bin / 'dvipdfmx'), '-o', 'build/preview.pdf', 'build/preview.dvi'],
        cwd=output, env=environment, capture_output=True, text=True, timeout=60)
    (output / 'pdf.log').write_text(result.stdout + result.stderr); result.check_returncode()
    log = (output / 'build/preview.log').read_text(); aux = (output / 'build/preview.aux').read_text()
    match = re.search(r'\\newlabel\{PreviewLastBodyPage\}\{\{[^}]*\}\{(\d+)\}', aux)
    if not match: raise ValueError('missing_body_boundary')
    tex_root = tex_bin.parent.parent.resolve(); inputs = {}
    for line in (output / 'build/preview.fls').read_text().splitlines():
        if not line.startswith('INPUT '): continue
        path = Path(line[6:])
        if not path.is_absolute(): path = output / path
        path = path.resolve()
        if path.is_file() and path.is_relative_to(tex_root): inputs[str(path.relative_to(tex_root))] = sha(path)
    manifest.update(status='rendered_unreviewed', main_pages=int(match[1]),
        tex_distribution_input_sha256=inputs, pdf_sha256=sha(output / 'build/preview.pdf'),
        outside_page=[], overfull_boxes=log.count('Overfull \\hbox') + log.count('Overfull \\vbox'),
        underfull_boxes=log.count('Underfull \\hbox') + log.count('Underfull \\vbox'),
        undefined_citations=len(re.findall(r'Citation .*? undefined', log)),
        undefined_references=len(re.findall(r'Reference .*? undefined', log)), table_font_samples=[])
    with pymupdf.open(output / 'build/preview.pdf') as pdf:
        manifest.update(pages=len(pdf), english_endmatter_pages=len(pdf)-manifest['main_pages'])
        for number, page in enumerate(pdf, 1):
            for block in page.get_text('blocks'):
                box = pymupdf.Rect(block[:4])
                if box.x0 < -.5 or box.y0 < -.5 or box.x1 > page.rect.width+.5 or box.y1 > page.rect.height+.5:
                    manifest['outside_page'].append({'page': number, 'bbox': list(box)})
            for block in page.get_text('dict')['blocks']:
                if block['type'] != 0: continue
                for line in block['lines']:
                    for span in line['spans']:
                        if any(s in span['text'] for s in ('128,796','除外入力','入力対')):
                            manifest['table_font_samples'].append({'page': number, 'text': span['text'], 'size': span['size']})
            page.get_pixmap(matrix=pymupdf.Matrix(1.4,1.4)).save(output / f'page_{number}.png')
    save(output / 'manifest.json', manifest)
    if (manifest['main_pages'] > 4 or any(manifest[k] for k in
            ('overfull_boxes','outside_page','undefined_citations','undefined_references'))
            or len(manifest['table_font_samples']) < 3
            or min(s['size'] for s in manifest['table_font_samples']) < 7):
        manifest['status'] = 'layout_needs_correction'
        save(output / 'manifest.json', manifest)
        raise ValueError('formatted_preview_needs_correction')
    print({k:manifest[k] for k in ('main_pages','pages','overfull_boxes','underfull_boxes','pdf_sha256','table_font_samples')})
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('source-preview','tex-bin','output'):
        parser.add_argument('--'+name, type=Path, required=True)
    args = parser.parse_args()
    format_preview(args.source_preview.resolve(), args.tex_bin.resolve(), args.output.resolve())
