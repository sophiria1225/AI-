"""Build the bounded P55/P56 manuscript from the closed, hash-locked evidence.

Use the reporting Python environment and pass the installed TeX binary directory.
This command performs no task execution, model generation, or network request.
Visual review is a separate step and is retained only for identical PDF bytes.
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
NAME = 'candidate_cost_completion'


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')


def evidence_checks():
    locked = read(PAPER / 'terminal_draft_source_map.json')['sources']
    for relative, digest in locked.items():
        if sha(ROOT / relative) != digest:
            raise ValueError(f'closed source changed: {relative}')
    report = read(ROOT / 'reports/P55_comparison.json')
    totals = list(report['totals'][key] for key in (
        'full_keep', 'details_omitted_keep', 'details_and_listings_omitted_keep'))
    diagnostic = read(ROOT / 'reports/P56_completion_audit.json')
    session = read(ROOT / 'reports/P55_server_session.json')
    actual = {
        'planned_and_evaluated_cells': len(report['rows']),
        'all_planned_cells_accounted': report['all_planned_cells_accounted'],
        'audit_errors': report['audit_errors'],
        'successes': [r['successes'] for r in totals],
        'whole_work_known_tokens': [r['logical_task_known_total_tokens'] for r in totals],
        'unknown_usage_calls': [r['unknown_usage_calls'] for r in totals],
        'continuation_model_calls': [r['model_calls'] for r in totals],
        'detail_minus_full_known_tokens': totals[1]['logical_task_known_total_tokens'] - totals[0]['logical_task_known_total_tokens'],
        'development_gate_met': report['development_gate_met'],
        'completion_diagnostic_all_evaluated': diagnostic['all_four_evaluated'],
        'completion_diagnostic_audit_errors': diagnostic['audit_errors'],
        'completion_diagnostic_outcomes': [r['outcomes'] for r in diagnostic['comparisons']],
        'completion_diagnostic_non_supervisor_unchanged': all(r['non_supervisor_files_unchanged'] for r in diagnostic['rows']),
        'completion_diagnostic_api_requests': diagnostic['total_api_requests'],
        'display_server_wall_seconds_rounded': round(session['wall_seconds'], 3),
    }
    expected = {
        'planned_and_evaluated_cells': 12,
        'all_planned_cells_accounted': True, 'audit_errors': [],
        'successes': [1, 2, 1],
        'whole_work_known_tokens': [512565, 555648, 563774],
        'unknown_usage_calls': [0, 1, 0], 'continuation_model_calls': [22, 26, 29],
        'detail_minus_full_known_tokens': 43083, 'development_gate_met': False,
        'completion_diagnostic_all_evaluated': True, 'completion_diagnostic_audit_errors': [],
        'completion_diagnostic_outcomes': [[False, True], [False, False]],
        'completion_diagnostic_non_supervisor_unchanged': True,
        'completion_diagnostic_api_requests': 346,
        'display_server_wall_seconds_rounded': 4112.859,
    }
    if actual != expected:
        raise ValueError(f'manuscript claim/source mismatch: {actual}')
    return locked, actual


def build(tex_bin, output):
    locked, actual = evidence_checks()
    ja = (PAPER / 'cost_completion_abstract_ja.txt').read_text().strip()
    en = (PAPER / 'cost_completion_abstract_en.txt').read_text().strip()
    if len(ja) > 120 or len(en.split()) > 50:
        raise ValueError('abstract exceeds the current 120-character/50-word target')
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
    layout = {
        'pages': 0, 'outside_page': [], 'visual_reviewed_pages': [],
        'overfull_boxes': log.count('Overfull \\hbox') + log.count('Overfull \\vbox'),
        'underfull_boxes': log.count('Underfull \\hbox') + log.count('Underfull \\vbox'),
        'undefined_citations': len(re.findall(r'Citation .*? undefined', log)),
        'undefined_references': len(re.findall(r'Reference .*? undefined', log)),
        'pdf_sha256': sha(output / f'{NAME}.pdf'),
        'toolchain': 'TinyTeX v2026.10 / uplatex / dvipdfmx / shell escape disabled',
        'forced_section_or_column_breaks': False,
    }
    with pymupdf.open(output / f'{NAME}.pdf') as pdf:
        layout['pages'] = len(pdf)
        for number, page in enumerate(pdf, 1):
            for block in page.get_text('blocks'):
                box = pymupdf.Rect(block[:4])
                if box.x0 < -0.5 or box.y0 < -0.5 or box.x1 > page.rect.width + 0.5 or box.y1 > page.rect.height + 0.5:
                    layout['outside_page'].append({'page': number, 'bbox': list(box)})
            page.get_pixmap(matrix=pymupdf.Matrix(1.4, 1.4)).save(output / f'page_{number}.png')
    if layout['pages'] != 4 or any(layout[k] for k in ('outside_page', 'overfull_boxes', 'undefined_citations', 'undefined_references')):
        raise ValueError(f'layout requires review: {layout}')
    old_layout = PAPER / 'cost_completion_layout.json'
    if old_layout.exists() and read(old_layout).get('pdf_sha256') == layout['pdf_sha256']:
        layout['visual_reviewed_pages'] = read(old_layout).get('visual_reviewed_pages', [])
    rendering = [
        f'papers/202610_letter/{NAME}.tex', 'papers/202610_letter/p55_methods_component.tex',
        'papers/202610_letter/inventory_tables.tex', 'papers/202610_letter/completion_diagnostic.tex',
        'papers/202610_letter/cost_completion_abstract_ja.txt', 'papers/202610_letter/cost_completion_abstract_en.txt',
        'materials/20261023_p55/work_tokens.pdf', 'docs/evidence_delivery_overlap_20261023.md',
    ]
    manifest = {
        'sources': locked, 'rendering_sources': {p: sha(ROOT / p) for p in rendering},
        'source_lock_manifest_sha256': sha(PAPER / 'terminal_draft_source_map.json'),
        'builder_sha256': sha(Path(__file__)), 'pdf_sha256': layout['pdf_sha256'],
        'source_date_epoch': environment['SOURCE_DATE_EPOCH'], 'data_checks': actual,
        'pages': layout['pages'], 'visual_reviewed_pages': layout['visual_reviewed_pages'],
        'japanese_abstract_characters': len(ja), 'english_abstract_words': len(en.split()),
        'all_scheduled_agent_cells': 12, 'posthoc_replay_cases': 4, 'independent_agent_tasks': 4,
        'official_class_used': False, 'submission_ready': False, 'central_contribution_confirmed': False,
        'forced_section_or_column_breaks': False, 'rendering_up_to_date': True,
        'new_model_calls_for_rendering': 0, 'new_api_requests_for_rendering': 0,
        'nearest_new_reference': {
            'url': 'https://arxiv.org/html/2610.26836v1',
            'read_scope': 'Abstract, introduction, and Appendix D boundary selection and paired continuation. Not an implementation reproduction or acceptance-status check.',
            'record': 'docs/evidence_delivery_overlap_20261023.md',
        },
    }
    (PAPER / f'{NAME}.pdf').write_bytes((output / f'{NAME}.pdf').read_bytes())
    save(old_layout, layout)
    save(PAPER / 'cost_completion_source_map.json', manifest)
    print(json.dumps({'pages': layout['pages'], 'ja_chars': len(ja), 'en_words': len(en.split()),
        'pdf_sha256': layout['pdf_sha256'], 'overfull_boxes': layout['overfull_boxes'],
        'underfull_boxes': layout['underfull_boxes'], 'visual_reviewed_pages': layout['visual_reviewed_pages']}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tex-bin', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, default=ROOT / '.runtime/cost-completion-draft')
    args = parser.parse_args()
    build(args.tex_bin.resolve(), args.output_dir.resolve())
