"""Bind a bibliography/scope revision to unchanged closed numeric evidence."""
from datetime import datetime, timezone
import re
from pathlib import Path

from run_context_comparison import write_json
from run_handoff_factors import ROOT, read, sha

FOLDER = 'papers/202610_letter/resource_prior_review'
PREVIOUS = 'papers/202610_letter/resource_measurement'


def build():
    folder = ROOT / FOLDER
    if (folder / 'build_manifest.json').exists():
        raise FileExistsError('preserve_prior_review_draft_attempt')
    original = read(ROOT / PREVIOUS / 'build_manifest.json')
    sources = dict(original['source_sha256'])
    for name, expected in read(ROOT / 'reports/resource_manuscript_provenance_20261024.json')['source_sha256'].items():
        sources[name] = expected
    for name, expected in sources.items():
        if sha(ROOT / name) != expected: raise ValueError('closed_resource_source_changed:' + name)
    old_text = (ROOT / PREVIOUS / 'draft.tex').read_text()
    text = (folder / 'draft.tex').read_text()
    inputs = re.findall(r'\\input\{([^}]+)\}', old_text)
    if re.findall(r'\\input\{([^}]+)\}', text) != inputs or len(inputs) != 4:
        raise ValueError('preserve_all_four_numeric_tables')
    for separator in ('\\title{', '\\textbf{あらまし案}\\quad\n', '\\textbf{Summary draft}\\quad ',
                      '\\textbf{Title}\\quad ', '\\textbf{Keywords}\\quad ', '\\textbf{キーワード}\\quad '):
        if old_text.split(separator, 1)[1].split('\n', 1)[0] != text.split(separator, 1)[1].split('\n', 1)[0]:
            raise ValueError('preserve_title_abstract_and_keywords')
    for name in [*inputs, FOLDER + '/draft.tex', 'scripts/build_resource_prior_draft.py',
                 'scripts/render_resource_prior_draft.py', 'reports/cost_proxy_prior_sources_20261024.json',
                 'docs/cost_proxy_prior_review_20261024.md']:
        sources[name] = sha(ROOT / name)
    result = {**original, 'generated_at': datetime.now(timezone.utc).isoformat(),
        'source_sha256': sources, 'generated_sha256': {}, 'builder_sha256': sha(Path(__file__)),
        'previous_draft_pdf_sha256': sha(ROOT / PREVIOUS / 'draft.pdf'),
        'pdf_sha256': None, 'visual_reviewed': False, 'bibliography_items': len(re.findall(r'\\bibitem', text)),
        'all_four_numeric_tables_unchanged': True, 'professor_brief_changed': False,
        'token_cost_direction_difference_is_novelty_claim': False}
    for key in ('renderer_sha256', 'pages', 'body_pages'):
        result.pop(key, None)
    write_json(folder / 'build_manifest.json', result)
    print({'sources': len(sources), 'references': result['bibliography_items'], 'numeric_tables_unchanged': True})


if __name__ == '__main__': build()
