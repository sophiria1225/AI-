"""Reuse the frozen mirror renderer for a reviewed, source-bound later draft.

The selected source is configuration for the unchanged renderer, not a rewrite
of any previous manuscript, result, class file, or published provenance ledger.
"""
import argparse
import json
from pathlib import Path

import build_resource_mirror_preview as renderer


def build(folder, mirror, tex_bin, output):
    if folder not in ('resource_prior_review', 'closed_control_integration'):
        raise ValueError('reviewed_closed_manuscript_folder_required')
    source = renderer.PAPER / folder
    manifest = json.loads((source / 'build_manifest.json').read_text())
    if not manifest.get('visual_reviewed') or not (source / 'draft.pdf').is_file():
        raise ValueError('unreviewed_or_preparation_only_manuscript')
    text = (source / 'draft.tex').read_text()
    ja = text.split('\\textbf{あらまし案}\\quad\n', 1)[1].split('\n\n', 1)[0]
    en = text.split('\\textbf{Summary draft}\\quad ', 1)[1].split('\n', 1)[0]
    if not 0 < len(ja) <= 120 or not 0 < len(en.split()) <= 50 or '・' in ja or '。' in ja:
        raise ValueError('source_abstract_format_mismatch')
    if output.exists():
        raise FileExistsError('preserve_previous_renderings')
    old_source = renderer.SOURCE
    try:
        renderer.SOURCE = source
        renderer.build(mirror, tex_bin, output)
    finally:
        renderer.SOURCE = old_source
    path = output / 'manifest.json'
    result = json.loads(path.read_text())
    result.update(selected_source_folder=folder,
        source_selection_wrapper_sha256=renderer.sha(Path(__file__)),
        original_renderer_source_unchanged=True,
        model_generations=0, input_count_requests=0, environment_api_requests=0, evaluations=0)
    renderer.save(path, result)
    return result


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--folder', choices=('resource_prior_review', 'closed_control_integration'), required=True)
    for name in ('mirror', 'tex-bin', 'output'):
        p.add_argument('--' + name, type=Path, required=True)
    a = p.parse_args()
    build(a.folder, a.mirror.resolve(), a.tex_bin.resolve(), a.output.resolve())
