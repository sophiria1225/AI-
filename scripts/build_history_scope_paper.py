"""Clarify the closed display comparison's reasoning policy without new results."""
import argparse
from pathlib import Path

import build_prompt_identity_paper as previous
from build_public_completion_paper import save
from build_reasoning_history_report import audit, RAW, RAW_SHA
from run_handoff_factors import ROOT, read, sha

PAPER = previous.PAPER
COMPONENT = 'papers/202610_letter/reasoning_history_scope_component.tex'


def build(tex_bin, output):
    raw, checked = audit()
    material_path = ROOT / 'materials/20261023_p75/build_manifest.json'
    material = read(material_path)
    if (material['claims'] != checked['totals'] or not material['visual_reviewed']
            or material['visual_reviewed_pages'] != [1, 2, 3, 4]
            or material['pdf_sha256'] != sha(material_path.parent / 'AI_harness_reasoning_history_20261023.pdf')
            or material['builder_sha256'] != sha(ROOT / 'scripts/build_reasoning_history_report.py')
            or material['source_sha256'][RAW] != RAW_SHA
            or read(ROOT / 'reports/P75_reasoning_history_audit.json') != checked
            or material['source_sha256']['reports/P75_reasoning_history_audit.json'] !=
               sha(ROOT / 'reports/P75_reasoning_history_audit.json')):
        raise ValueError('reviewed_P75_metadata_material_required')
    tex = (PAPER / 'candidate_cost_completion.tex').read_text()
    if tex.count('\\input{' + COMPONENT + '}') != 1:
        raise ValueError('include_reasoning_policy_scope_exactly_once')
    previous.build(tex_bin, output)
    path = PAPER / 'cost_completion_source_map.json'; manifest = read(path)
    manifest['sources'].update({RAW: RAW_SHA,
        'reports/P75_reasoning_history_audit.json': sha(ROOT / 'reports/P75_reasoning_history_audit.json'),
        'configs/P75_reasoning_history_v01.json': raw['plan_sha256']})
    manifest['rendering_sources'].update({p: sha(ROOT / p) for p in (
        COMPONENT, 'docs/P75_findings.md', 'docs/P75_manuscript_scope.md',
        'materials/20261023_p75/build_manifest.json', 'scripts/build_reasoning_history_report.py')})
    manifest['previous_prompt_checker_sha256'] = manifest['builder_sha256']
    manifest['builder_sha256'] = sha(Path(__file__))
    manifest['data_checks']['reasoning_history_scope'] = {
        'historical_display_conditions_replay_reasoning': False,
        'saved_attempts_inspected': 105, 'known_responses_with_nonempty_reasoning': 103,
        'requests_containing_reasoning': 0, 'unknown_usage_attempts_preserved': 2,
        'quality_effect_established_by_P75': False, 'P76_results_included': False}
    save(path, manifest)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--tex-bin', type=Path, required=True)
    p.add_argument('--output-dir', type=Path, default=ROOT / '.runtime/history-scope-paper')
    args = p.parse_args(); build(args.tex_bin.resolve(), args.output_dir.resolve())
