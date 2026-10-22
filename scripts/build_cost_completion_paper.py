"""Build the bounded P55/P56/P66/P68 manuscript from closed, hash-locked evidence.

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
    locked.update({
        'reports/P62_public_move_scope.json': '8f99d38b6497c186d170b907ed01881a10d9b37a78fcf4f7c74b3b89084aa6c5',
        'reports/P63_public_name_scope.json': 'ce3efc942aebf8415b105ea9adf09f3483ed31a632774b7c9eb8c9fd9736d7e4',
        'reports/P64_public_name_audit.json': '8c5dac74fcb69c59b89df936270b5bed8ab00db0abef10feca15f07faebfd283',
        'configs/P66_ordinary_completion_v01.json': 'c0320ff4f5d0b594b5afe9e95654167693dfca4ca04a02d6796667051aa66dba',
        'reports/P66_ordinary_completion.json': '5e38fab2a658da64ea47d63cef936a2a027ef1f35d5fd93e9c5638ca6172eaaa',
        'reports/P66_completion_audit.json': 'f8864e42c0b627f6ffc5dc10636c78573050236beb2b1811115c1248030ca990',
        'reports/P66_identity_differences.json': '8ac7c2f1914924d98151f7bcc857fdc335ee91f79a7999104fa65654964b6d27',
        'reports/P68_export_completion.json': 'c42a14a72c298d530d054e790aec150f2f5e0d93dc9735715ce27421fce1aba4',
        'reports/P68_completion_audit.json': '36fc231b04efb84758c44c3969c61c0179912114ee1c3feef7c95bc74da4a980',
    })
    for relative, digest in locked.items():
        if sha(ROOT / relative) != digest:
            raise ValueError(f'closed source changed: {relative}')
    report = read(ROOT / 'reports/P55_comparison.json')
    totals = list(report['totals'][key] for key in (
        'full_keep', 'details_omitted_keep', 'details_and_listings_omitted_keep'))
    diagnostic = read(ROOT / 'reports/P56_completion_audit.json')
    session = read(ROOT / 'reports/P55_server_session.json')
    move_scope = read(ROOT / 'reports/P62_public_move_scope.json')
    control = read(ROOT / 'reports/P66_completion_audit.json')
    identities = read(ROOT / 'reports/P66_identity_differences.json')
    export = read(ROOT / 'reports/P68_completion_audit.json')
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
        'photo_public_clock_requests': [r['public_clock_requests_sent'] for r in move_scope['rows']],
        'photo_name_preserved_moves': [r['final']['filename_preserved_moves'] for r in move_scope['rows']],
        'photo_public_trace_support': [r['final']['trace_support'] for r in move_scope['rows']],
        'ordinary_control_conditions': control['planned_conditions'],
        'ordinary_control_audit_errors': control['audit_errors'],
        'ordinary_control_usage': [control[k] for k in ('model_calls', 'known_total_tokens', 'unknown_usage_calls', 'api_requests', 'evaluator_calls')],
        'ordinary_control_success': [r['official_success'] for r in control['rows']],
        'ordinary_control_reference_success': [r['baseline_comparison']['reference_official_success'] for r in control['rows']],
        'ordinary_control_tokens': [[r['baseline_comparison']['reference_known_tokens'], r['known_total_tokens']] for r in control['rows']],
        'ordinary_control_final_database_differences': [r['baseline_comparison']['changed_final_database_files'] for r in control['rows']],
        'ordinary_control_public_prefix_equal': [[r['baseline_comparison'][k] for k in ('same_prefix_events', 'same_prefix_spans')] for r in control['rows']],
        'ordinary_control_strict_prefix_equal': [r['baseline_comparison']['same_entire_executed_model_prefix'] for r in control['rows']],
        'ordinary_control_identity_other_differences': [[r['request_other_differences'], r['response_other_differences']] for r in identities['rows']],
        'ordinary_control_identity_criterion_changed': identities['criterion_changed'],
        'ordinary_control_server_stopped': control['server_stopped'],
        'export_audit_errors': export['audit_errors'],
        'export_all_evaluated': export['comparison']['both_evaluated'],
        'export_usage': [export[k] for k in ('model_calls', 'known_total_tokens', 'unknown_usage_calls', 'api_requests', 'evaluator_calls')],
        'export_success': [r['official_success'] for r in export['rows']],
        'export_tokens': [r['known_total_tokens'] for r in export['rows']],
        'export_stop_reason': [r['stop_reason'] for r in export['rows']],
        'export_write_delete_calls': [[r['sent_api_counts'].get(k, 0) for k in ('file_system__create_file','spotify__delete_account')] for r in export['rows']],
        'export_controller_checks_attempts': [[r['controller'][k] for k in ('checks','completion_attempts')] for r in export['rows']],
        'export_controller_seconds': round(export['rows'][1]['controller']['wall_seconds'], 6),
        'export_final_database_differences': export['comparison']['changed_final_database_files'],
        'export_strict_prefix_equal': export['comparison']['same_entire_executed_model_prefix'],
        'export_local_gate_met': export['local_adoption_gate_met'],
        'export_server_stopped': export['server_stopped'],
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
        'photo_public_clock_requests': [0, 0, 0],
        'photo_name_preserved_moves': [42, 42, 0],
        'photo_public_trace_support': ['unknown', 'unknown', 'unknown'],
        'ordinary_control_conditions': 2, 'ordinary_control_audit_errors': [],
        'ordinary_control_usage': [25, 203349, 0, 199, 2],
        'ordinary_control_success': [True, True],
        'ordinary_control_reference_success': [True, True],
        'ordinary_control_tokens': [[130439, 91116], [151664, 112233]],
        'ordinary_control_final_database_differences': [[], []],
        'ordinary_control_public_prefix_equal': [[True, True], [True, True]],
        'ordinary_control_strict_prefix_equal': [False, False],
        'ordinary_control_identity_other_differences': [[0, 0], [0, 0]],
        'ordinary_control_identity_criterion_changed': False,
        'ordinary_control_server_stopped': True,
        'export_audit_errors': [], 'export_all_evaluated': True,
        'export_usage': [16, 438252, 0, 160, 2],
        'export_success': [False, False], 'export_tokens': [219126, 219126],
        'export_stop_reason': ['api_request_limit', 'api_request_limit'],
        'export_write_delete_calls': [[0, 0], [0, 0]],
        'export_controller_checks_attempts': [[0, 0], [8, 0]],
        'export_controller_seconds': 0.004080,
        'export_final_database_differences': [], 'export_strict_prefix_equal': False,
        'export_local_gate_met': False, 'export_server_stopped': True,
    }
    if actual != expected:
        raise ValueError(f'manuscript claim/source mismatch: {actual}')
    return locked, actual


def write_control_component():
    control = read(ROOT / 'reports/P66_completion_audit.json')
    lines = [r'% Generated from the closed P66 audit by build_cost_completion_paper.py.',
             r'\begin{center}\begin{minipage}{\columnwidth}\centering',
             r'\small 表5\quad 別条件の写真課題：全体token\par\smallskip',
             r'\begin{tabular}{lrrr}\hline',
             r'接続 & 通常終了 & 終了制御 & 減少率\\\hline']
    labels = {'documented': '文書取得必須', 'named': '公開名'}
    for row in control['rows']:
        baseline = row['baseline_comparison']['reference_known_tokens']
        current = row['known_total_tokens']
        lines.append(f"{labels[row['arm']]} & {baseline:,} & {current:,} & {(baseline-current)/baseline*100:.1f}\\%" + r'\\')
    lines += [r'\hline\end{tabular}', r'\end{minipage}\end{center}']
    (PAPER / 'ordinary_completion_component.tex').write_text('\n'.join(lines) + '\n')


def build(tex_bin, output):
    locked, actual = evidence_checks()
    bibliography_report = read(ROOT / 'reports/letter_bibliography_check_20261023.json')
    tex = (PAPER / f'{NAME}.tex').read_text()
    bibliography = tex.split(r'\begin{thebibliography}', 1)[1].split(r'\end{thebibliography}', 1)[0]
    if (hashlib.sha256(bibliography.encode()).hexdigest() != bibliography_report['bibliography_sha256']
            or re.findall(r'\\bibitem\{([^}]+)\}', bibliography) != [r['key'] for r in bibliography_report['entries']]
            or not bibliography_report['all_printed_entries_checked']):
        raise ValueError('printed bibliography differs from the manually verified primary sources')
    write_control_component()
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
        'docs/evidence_delivery_overlap_20261023.md',
        'docs/P62_findings.md', 'docs/P63_findings.md',
        'docs/termination_control_overlap_20261023.md',
        'papers/202610_letter/ordinary_completion_component.tex', 'docs/P66_findings.md',
        'docs/ordinary_completion_literature_20261023.md',
        'reports/letter_bibliography_check_20261023.json',
        'docs/P68_findings.md',
    ]
    manifest = {
        'sources': locked, 'rendering_sources': {p: sha(ROOT / p) for p in rendering},
        'source_lock_manifest_sha256': sha(PAPER / 'terminal_draft_source_map.json'),
        'builder_sha256': sha(Path(__file__)), 'pdf_sha256': layout['pdf_sha256'],
        'source_date_epoch': environment['SOURCE_DATE_EPOCH'], 'data_checks': actual,
        'pages': layout['pages'], 'visual_reviewed_pages': layout['visual_reviewed_pages'],
        'japanese_abstract_characters': len(ja), 'english_abstract_words': len(en.split()),
        'all_scheduled_agent_cells': 12, 'posthoc_replay_cases': 4, 'independent_agent_tasks': 4,
        'separate_ordinary_completion_conditions': 2, 'separate_ordinary_reference_conditions': 2,
        'ordinary_completion_uses_same_known_photo_task': True,
        'separate_export_completion_conditions': 2,
        'export_completion_uses_same_known_export_task': True,
        'official_class_used': False, 'submission_ready': False, 'central_contribution_confirmed': False,
        'forced_section_or_column_breaks': False, 'rendering_up_to_date': True,
        'new_model_calls_for_rendering': 0, 'new_api_requests_for_rendering': 0,
        'nearest_new_reference': {
            'url': 'https://arxiv.org/html/2610.26836v1',
            'read_scope': 'Abstract, introduction, and Appendix D boundary selection and paired continuation. Not an implementation reproduction or acceptance-status check.',
            'record': 'docs/evidence_delivery_overlap_20261023.md',
        },
        'additional_related_reference': {
            'url': 'https://arxiv.org/html/2610.21394v1',
            'read_scope': 'Sections 3.1–4.3, 20.2–20.3 and 20.5; not all later sections or an implementation reproduction. Abstract page identifies the work as a non-peer-reviewed research preprint.',
            'record': 'docs/termination_control_overlap_20261023.md',
        },
        'ordinary_termination_reference': {
            'url': 'https://arxiv.org/html/2608.23623v1',
            'read_scope': 'Declared contract, evidence ledger, deterministic verification and trust boundary; no implementation reproduction.',
            'record': 'docs/termination_control_overlap_20261023.md',
        },
        'additional_termination_cost_review': 'docs/ordinary_completion_literature_20261023.md',
        'bibliography_verification': 'reports/letter_bibliography_check_20261023.json',
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
