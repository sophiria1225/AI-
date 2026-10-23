"""Add the separately labelled P73 posthoc input diagnosis to the checked letter."""
import argparse
from pathlib import Path

import build_public_completion_paper as previous
from build_prompt_identity_report import validated
from run_handoff_factors import ROOT, read, sha

PAPER = previous.PAPER


def build(tex_bin, output):
    _, _, claims, sources = validated()
    material_path = ROOT / 'materials/20261023_p73/build_manifest.json'
    material = read(material_path)
    component = PAPER / 'prompt_identity_component.tex'
    if (material['claims'] != claims or material['source_sha256'] != sources
            or material['component_sha256'] != sha(component)
            or material['builder_sha256'] != sha(ROOT / 'scripts/build_prompt_identity_report.py')
            or material['csv_sha256'] != sha(material_path.parent / 'all_input_pairs.csv')
            or not material['visual_reviewed'] or material['visual_reviewed_pages'] != list(range(1, 6))
            or material['pdf_sha256'] != sha(material_path.parent / 'AI_harness_prompt_identity_20261023.pdf')):
        raise ValueError('reviewed P73 component, all-pair table and material required')
    tex = (PAPER / 'candidate_cost_completion.tex').read_text()
    if tex.count(r'\input{papers/202610_letter/prompt_identity_component.tex}') != 1:
        raise ValueError('include the posthoc input component exactly once')
    if sha(ROOT / 'scripts/build_public_completion_paper.py') != 'd7ab01737a6b68316c515ad1956beb07cc4177a604e043e054cad7342862544d':
        raise ValueError('previous full evidence and layout checker changed')
    previous.build(tex_bin, output)
    path = PAPER / 'cost_completion_source_map.json'
    manifest = read(path)
    manifest['sources'].update(sources)
    manifest['rendering_sources'].update({p: sha(ROOT / p) for p in (
        'papers/202610_letter/prompt_identity_component.tex',
        'materials/20261023_p73/build_manifest.json',
        'scripts/build_prompt_identity_report.py', 'scripts/inspect_prompt_identity_stop.py',
        'docs/P73_findings.md', 'docs/P73_manuscript_integration.md',
    )})
    manifest['previous_full_checker_sha256'] = manifest['builder_sha256']
    manifest['builder_sha256'] = sha(Path(__file__))
    manifest['data_checks']['posthoc_prompt_identity'] = claims
    manifest['original_prompt_reconstruction_status'] = 'stopped'
    manifest['posthoc_input_pairs_inspected'] = 33
    manifest['prompt_input_diagnosis_changes_original_criteria'] = False
    manifest['historical_gpu_or_rng_state_restored'] = False
    previous.save(path, manifest)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--tex-bin', type=Path, required=True)
    p.add_argument('--output-dir', type=Path, default=ROOT / '.runtime/prompt-identity-paper')
    args = p.parse_args(); build(args.tex_bin.resolve(), args.output_dir.resolve())
