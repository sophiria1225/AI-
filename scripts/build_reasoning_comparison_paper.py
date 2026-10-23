"""Include the entire closed P76 comparison in the checked empirical manuscript."""
import argparse
from pathlib import Path

import build_history_scope_paper as previous
from build_public_completion_paper import save
from build_reasoning_comparison_report import validated, paper_component, STEM
from run_handoff_factors import ROOT, read, sha

PAPER = previous.PAPER
COMPONENT = 'papers/202610_letter/reasoning_comparison_component.tex'


def build(tex_bin, output):
    report, preflight, session, sources = validated()
    material_path = ROOT / 'materials/20261023_p76/build_manifest.json'
    material = read(material_path)
    if (not material['visual_reviewed'] or material['visual_reviewed_pages'] != list(range(1, 6))
            or material['source_sha256'] != sources
            or material['pdf_sha256'] != sha(material_path.parent / (STEM + '.pdf'))
            or material['csv_sha256'] != sha(material_path.parent / 'all_reasoning_conditions.csv')
            or material['component_sha256'] != sha(ROOT / COMPONENT)
            or material['builder_sha256'] != sha(ROOT / 'scripts/build_reasoning_comparison_report.py')
            or (ROOT / COMPONENT).read_text() != paper_component(report, preflight, session)):
        raise ValueError('reviewed_all_condition_P76_material_and_component_required')
    if sha(ROOT / 'scripts/build_history_scope_paper.py') != '6584b7e9cc3e7648165adf261a90be9366b8a4818429a66c722eed43f065fa81':
        raise ValueError('previous_closed_evidence_checker_changed')
    tex = (PAPER / 'candidate_cost_completion.tex').read_text()
    if tex.count('\\input{' + COMPONENT + '}') != 1:
        raise ValueError('include_all_eight_P76_conditions_exactly_once')
    for name in ('docs/P76_findings.md', 'docs/P76_manuscript_integration.md'):
        if not (ROOT / name).is_file(): raise ValueError('document_P76_scope_before_typesetting')
    reference = read(ROOT / 'reports/letter_reasoning_reference_20261023.json')
    bibliography = read(ROOT / 'reports/letter_bibliography_ieice_style_20261023.json')
    entries = [e for e in bibliography['entries'] if e['key'] == reference['key']]
    if (len(entries) != 1 or reference['arxiv_id'] != '2609.29875v1'
            or not reference['primary_metadata_checked']
            or any(entries[0][k] != reference[k] for k in (
                'all_printed_authors', 'author_count', 'printed_entry', 'primary_sources', 'primary_metadata_checked'))
            or reference['printed_entry'] not in (PAPER / 'bibliography_ieice.tex').read_text()):
        raise ValueError('reasoning_reference_must_match_checked_primary_metadata')
    previous.build(tex_bin, output)
    path = PAPER / 'cost_completion_source_map.json'; manifest = read(path)
    manifest['sources'].update(sources)
    manifest['rendering_sources'].update({p: sha(ROOT / p) for p in (
        COMPONENT, 'docs/P76_findings.md', 'docs/P76_manuscript_integration.md',
        'reports/letter_reasoning_reference_20261023.json',
        'docs/reasoning_retention_overlap_20261023.md',
        'materials/20261023_p76/build_manifest.json', 'scripts/build_reasoning_comparison_report.py')})
    manifest['previous_history_scope_checker_sha256'] = manifest['builder_sha256']
    manifest['builder_sha256'] = sha(Path(__file__))
    manifest['data_checks']['reasoning_history_comparison'] = {
        key: report[key] for key in (
            'batch_status', 'all_planned_cells_accounted', 'all_eight_complete_with_known_usage',
            'paired_results', 'paired_success_losses', 'paired_success_gains', 'paired_successful_tasks',
            'candidate_minus_control_work_tokens', 'development_gate_met',
            'novel_method_claim', 'general_quality_preservation_claim')}
    manifest['data_checks']['reasoning_history_comparison']['totals'] = report['totals']
    manifest['data_checks']['reasoning_history_scope']['P76_results_included'] = True
    manifest['separate_reasoning_history_conditions'] = 8
    manifest['P76_is_concurrent_control_for_previous_display_conditions'] = False
    save(path, manifest)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--tex-bin', type=Path, required=True)
    p.add_argument('--output-dir', type=Path, default=ROOT / '.runtime/reasoning-comparison-paper')
    args = p.parse_args(); build(args.tex_bin.resolve(), args.output_dir.resolve())
