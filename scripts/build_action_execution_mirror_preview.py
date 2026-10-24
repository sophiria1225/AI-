"""Typeset the reviewed P94 paper with the pinned, explicitly unofficial class."""
import argparse
import json
from pathlib import Path

import build_resource_mirror_preview as renderer

FOLDER = 'closed_results_action_execution'


def build(mirror, tex_bin, output):
    source = renderer.PAPER / FOLDER
    manifest = json.loads((source / 'build_manifest.json').read_text())
    if (not manifest.get('visual_reviewed')
            or not manifest.get('P94_execution_comparison_included')
            or manifest.get('P94_conditions') != 18
            or manifest.get('P94_original_full_state_restored') is not False
            or manifest.get('P94_task_quality_measured') is not False
            or manifest.get('synthetic_only', False)
            or not (source / 'draft.pdf').is_file()):
        raise ValueError('reviewed_closed_P94_manuscript_required')
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
    result.update(selected_source_folder=FOLDER,
        source_selection_wrapper_sha256=renderer.sha(Path(__file__)),
        original_renderer_source_unchanged=True,
        model_generations=0, input_count_requests=0, environment_api_requests=0, evaluations=0)
    renderer.save(path, result)
    return result


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('mirror', 'tex-bin', 'output'):
        p.add_argument('--' + name, type=Path, required=True)
    a = p.parse_args()
    build(a.mirror.resolve(), a.tex_bin.resolve(), a.output.resolve())
