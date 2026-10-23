"""Build the P55/P71 letter with both complete terminal diagnostics, retaining older builders.

The body and references must occupy four pages in this provisional class. The
English abstract and keywords are separate end matter, not a fifth body page.
No model, task environment, evaluator, or network is called.
"""
import argparse
import os
from pathlib import Path
import re
import subprocess

import pymupdf

from build_cost_completion_paper import (
    NAME, PAPER, ROOT, evidence_checks, read, save, sha, write_control_component,
)
from build_public_display_paper_tables import validated
from build_public_completion_report import validated as completion_validated


def current_claims(report, session):
    arms = ('full_keep', 'details_omitted_keep', 'details_and_listings_omitted_keep')
    totals = [report['totals'][a] for a in arms]
    return {
        'planned_cells': len(report['rows']),
        'record_status_counts': report['record_status_counts'],
        'successes': [t['successes'] for t in totals],
        'whole_work_known_tokens': [t['logical_task_known_total_tokens'] for t in totals],
        'unknown_usage_calls': [t['unknown_usage_calls'] for t in totals],
        'continuation_model_calls': [t['model_calls'] for t in totals],
        'continuation_api_requests': [t['api_requests'] for t in totals],
        'restore_api_requests': [t['setup_api_requests'] for t in totals],
        'development_gate_met': report['development_gate_met'],
        'inventory_advantage_supported': report['inventory_advantage_supported'],
        'contrasts': report['contrasts'],
        'server_wall_seconds_rounded': round(session['wall_seconds'], 3),
    }


def check_sources():
    locked, earlier = evidence_checks()
    _, current = validated(ROOT)
    table_sources = read(PAPER / 'public_display_table_sources.json')
    for path, digest in table_sources['sources'].items():
        if sha(ROOT / path) != digest:
            raise ValueError('table source changed: ' + path)
    if (sha(PAPER / 'public_display_tables.tex') != table_sources['table_sha256']
            or sha(ROOT / 'scripts/build_public_display_paper_tables.py') != table_sources['builder_sha256']):
        raise ValueError('regenerate the tables after a source or builder change')
    locked.update(table_sources['sources'])
    session = read(ROOT / 'reports/P71_server_session.json')
    outcomes = read(ROOT / 'reports/P71_outcome_scope.json')
    audit_sha = sha(ROOT / 'reports/P71_comparison.json')
    if (session['status'] != 'stopped' or not session['owned_processes_absent']
            or session['audit_source_sha256'] != audit_sha
            or outcomes['source_audit_sha256'] != audit_sha or len(outcomes['rows']) != 12):
        raise ValueError('closed session and all twelve saved-state pairs required')
    claims = read(PAPER / 'public_display_manuscript_claims.json')
    actual = current_claims(current, session)
    if claims['audit_sha256'] != audit_sha or claims['claims'] != actual:
        raise ValueError('P71 manuscript claims differ from the reviewed evidence')
    for path in ('reports/P71_server_session.json', 'reports/P71_outcome_scope.json',
                 'papers/202610_letter/public_display_manuscript_claims.json'):
        locked[path] = sha(ROOT / path)
    _, _, completion, completion_sources = completion_validated()
    material = read(ROOT / 'materials/20261023_p72/build_manifest.json')
    if (material['claims'] != completion
            or material['builder_sha256'] != sha(ROOT / 'scripts/build_public_completion_report.py')
            or material['joint_component_sha256'] != sha(PAPER / 'completion_scope_joint.tex')):
        raise ValueError('P72 component and material must match the audited claims')
    locked.update(completion_sources)
    return locked, {'earlier_comparisons': earlier, 'public_display': actual,
                    'public_completion_diagnostic': completion}


def metadata_fragments():
    metadata = read(PAPER / 'submission_metadata.json')
    ja = (PAPER / metadata['japanese_abstract_path']).read_text().strip()
    en = (PAPER / metadata['english_abstract_path']).read_text().strip()
    if (len(ja) > 120 or len(en.split()) > 50
            or len(metadata['keywords_ja']) not in (4, 5)
            or len(metadata['keywords_ja']) != len(metadata['keywords_en'])):
        raise ValueError('abstract or corresponding keyword limits exceeded')
    def escape(value):
        return ''.join({'&': r'\&', '%': r'\%', '$': r'\$', '#': r'\#',
                        '_': r'\_', '{': r'\{', '}': r'\}'}.get(c, c) for c in value)
    lines = [r'% Generated from submission_metadata.json; no author names are inferred.']
    for macro, value in (
        ('LetterEnglishTitle', metadata['title_en']),
        ('LetterJapaneseKeywords', '，'.join(metadata['keywords_ja'])),
        ('LetterEnglishKeywords', ', '.join(metadata['keywords_en'])),
    ):
        lines.append('\\newcommand{\\' + macro + '}{' + escape(value) + '}')
    (PAPER / 'submission_metadata.tex').write_text('\n'.join(lines) + '\n')
    (PAPER / 'english_endmatter.tex').write_text(
        '% English abstract and keywords, outside the standard body page count.\n'
        r'\label{LastBodyPage}\clearpage\onecolumn' + '\n'
        r'\section*{English abstract and keywords}' + '\n'
        r'{\large\bfseries \LetterEnglishTitle\par}\bigskip' + '\n'
        r'\noindent\textbf{Abstract}\quad ' + '\n'
        r'\input{papers/202610_letter/cost_completion_abstract_en.txt}' + '\n\n'
        r'\noindent\textbf{Keywords}\quad\LetterEnglishKeywords' + '\n')
    return metadata, ja, en


def build(tex_bin, output):
    locked, actual = check_sources()
    bib_path = ROOT / 'reports/letter_bibliography_ieice_style_20261023.json'
    bibliography = read(bib_path)
    bib = PAPER / 'bibliography_ieice.tex'
    if (sha(bib) != bibliography['bibliography_file_sha256']
            or re.findall(r'\\bibitem\{([^}]+)\}', bib.read_text()) != [e['key'] for e in bibliography['entries']]
            or not bibliography['all_printed_entries_checked'] or not bibliography['all_author_rule_applied']):
        raise ValueError('bibliography differs from verified primary metadata')
    tex = (PAPER / f'{NAME}.tex').read_text()
    required = ('public_display_tables.tex', 'public_display_methods_component.tex',
                'submission_metadata.tex', 'bibliography_ieice.tex', 'english_endmatter.tex',
                'completion_scope_joint.tex')
    if any(tex.count('\\input{papers/202610_letter/' + p + '}') != 1 for p in required):
        raise ValueError('manuscript must include each verified component once')
    if 'P71_' in tex or 'PENDING' in tex or r'\begin{thebibliography}' in tex:
        raise ValueError('resolve draft placeholders and use the verified bibliography')
    write_control_component()
    metadata, ja, en = metadata_fragments()
    title = re.search(r'\\title\{([^}]+)\}', tex, re.S)
    if (not title or ''.join(title[1].replace(r'\newline', '').split()) != metadata['title_ja']
            or tex.count(r'\LetterJapaneseKeywords') != 1):
        raise ValueError('printed Japanese title or keyword component differs from metadata')
    output.mkdir(parents=True, exist_ok=True)
    environment = dict(os.environ, SOURCE_DATE_EPOCH='1792677600', FORCE_SOURCE_DATE='1')
    for number in (1, 2):
        result = subprocess.run([
            str(tex_bin / 'uplatex'), '-no-shell-escape', '-interaction=nonstopmode',
            '-halt-on-error', '-output-directory=' + str(output),
            f'papers/202610_letter/{NAME}.tex',
        ], cwd=ROOT, env=environment, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        (output / f'pass_{number}.log').write_text(result.stdout)
        result.check_returncode()
    result = subprocess.run([
        str(tex_bin / 'dvipdfmx'), '-o', str(output / f'{NAME}.pdf'), str(output / f'{NAME}.dvi'),
    ], cwd=ROOT, env=environment, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    (output / 'pdf.log').write_text(result.stdout)
    result.check_returncode()
    log = (output / f'{NAME}.log').read_text()
    aux = (output / f'{NAME}.aux').read_text()
    match = re.search(r'\\newlabel\{LastBodyPage\}\{\{[^}]*\}\{(\d+)\}', aux)
    if not match:
        raise ValueError('body/end-matter boundary was not typeset')
    layout = {
        'pages': 0, 'main_pages': int(match[1]), 'english_endmatter_pages': 0,
        'outside_page': [], 'visual_reviewed_pages': [],
        'overfull_boxes': log.count('Overfull \\hbox') + log.count('Overfull \\vbox'),
        'underfull_boxes': log.count('Underfull \\hbox') + log.count('Underfull \\vbox'),
        'undefined_citations': len(re.findall(r'Citation .*? undefined', log)),
        'undefined_references': len(re.findall(r'Reference .*? undefined', log)),
        'pdf_sha256': sha(output / f'{NAME}.pdf'),
        'toolchain': 'TinyTeX v2026.10 / uplatex / dvipdfmx / shell escape disabled',
        'forced_body_section_or_column_breaks': False,
        'separate_english_endmatter': True,
    }
    with pymupdf.open(output / f'{NAME}.pdf') as pdf:
        layout['pages'] = len(pdf)
        for number, page in enumerate(pdf, 1):
            if 'English abstract and keywords' in page.get_text():
                if number != layout['main_pages'] + 1:
                    raise ValueError('English attachment overlaps or precedes the body boundary')
                layout['english_endmatter_pages'] += 1
            for block in page.get_text('blocks'):
                box = pymupdf.Rect(block[:4])
                if box.x0 < -0.5 or box.y0 < -0.5 or box.x1 > page.rect.width + 0.5 or box.y1 > page.rect.height + 0.5:
                    layout['outside_page'].append({'page': number, 'bbox': list(box)})
            page.get_pixmap(matrix=pymupdf.Matrix(1.4, 1.4)).save(output / f'page_{number}.png')
    save(output / 'layout.json', layout)
    if (layout['main_pages'] != metadata['target_main_pages'] or layout['english_endmatter_pages'] != 1
            or layout['pages'] != layout['main_pages'] + 1
            or any(layout[k] for k in ('outside_page', 'overfull_boxes', 'undefined_citations', 'undefined_references'))):
        raise ValueError(f'layout requires review: {layout}')
    old_layout = PAPER / 'cost_completion_layout.json'
    if old_layout.exists() and read(old_layout).get('pdf_sha256') == layout['pdf_sha256']:
        layout['visual_reviewed_pages'] = read(old_layout).get('visual_reviewed_pages', [])
    table_sources = read(PAPER / 'public_display_table_sources.json')
    table_sources['rendering_up_to_date'] = True
    save(PAPER / 'public_display_table_sources.json', table_sources)
    rendering = [f'papers/202610_letter/{NAME}.tex', *[
        'papers/202610_letter/' + p for p in (*required,
            'inventory_tables.tex', 'ordinary_completion_component.tex',
            'cost_completion_abstract_ja.txt', 'cost_completion_abstract_en.txt',
            'submission_metadata.json', 'public_display_table_sources.json')],
        'reports/letter_bibliography_ieice_style_20261023.json',
        'docs/P71_findings.md', 'docs/P71_manuscript_integration.md',
        'docs/P72_findings.md', 'docs/P72_manuscript_integration.md',
        'materials/20261023_p72/build_manifest.json', 'scripts/build_public_completion_report.py',
        'docs/letter_cost_metric_scope_20261023.md', 'docs/measurement_scope_review_20261023.md',
        'docs/letter_submission_format_20261023.md',
        'docs/P62_findings.md', 'docs/P63_findings.md', 'docs/P66_findings.md', 'docs/P68_findings.md',
        'docs/evidence_delivery_overlap_20261023.md', 'docs/termination_control_overlap_20261023.md',
        'docs/ordinary_completion_literature_20261023.md',
    ]
    manifest = {
        'sources': locked, 'rendering_sources': {p: sha(ROOT / p) for p in rendering},
        'builder_sha256': sha(Path(__file__)),
        'earlier_evidence_checker_sha256': sha(ROOT / 'scripts/build_cost_completion_paper.py'),
        'pdf_sha256': layout['pdf_sha256'], 'source_date_epoch': environment['SOURCE_DATE_EPOCH'],
        'data_checks': actual, 'pages': layout['pages'], 'main_pages': layout['main_pages'],
        'english_endmatter_pages': layout['english_endmatter_pages'],
        'visual_reviewed_pages': layout['visual_reviewed_pages'],
        'japanese_abstract_characters': len(ja), 'english_abstract_words': len(en.split()),
        'all_scheduled_agent_cells': 24, 'posthoc_replay_cases': 18,
        'posthoc_replay_cases_by_batch': {'P56': 4, 'P72': 14}, 'distinct_known_diagnostic_tasks': 3, 'distinct_known_agent_tasks': 4,
        'cohorts_are_independent': False, 'historical_access_difference_is_causal': False,
        'separate_ordinary_completion_conditions': 2, 'separate_ordinary_reference_conditions': 2,
        'separate_export_completion_conditions': 2,
        'official_class_used': False, 'submission_ready': False, 'central_contribution_confirmed': False,
        'forced_body_section_or_column_breaks': False, 'rendering_up_to_date': True,
        'new_model_calls_for_rendering': 0, 'new_api_requests_for_rendering': 0,
        'bibliography_verification': 'reports/letter_bibliography_ieice_style_20261023.json',
    }
    (PAPER / f'{NAME}.pdf').write_bytes((output / f'{NAME}.pdf').read_bytes())
    save(old_layout, layout)
    save(PAPER / 'cost_completion_source_map.json', manifest)
    print({k: manifest[k] for k in ('pages', 'main_pages', 'english_endmatter_pages',
                                   'japanese_abstract_characters', 'english_abstract_words', 'pdf_sha256')})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tex-bin', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, default=ROOT / '.runtime/public-display-paper')
    args = parser.parse_args()
    build(args.tex_bin.resolve(), args.output_dir.resolve())
