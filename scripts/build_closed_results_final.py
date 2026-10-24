"""Preserve intermediate drafts and add the closed cross-cohort evidence."""
from datetime import datetime, timezone
import json

from build_observed_control_draft import FOLDER as PARENT, replace_once
from run_handoff_factors import ROOT, read, sha

FOLDER = 'papers/202610_letter/closed_results_final'
BRIDGE = 'materials/20261024_closed_reference_cohorts/comparison.json'
LEDGER = 'reports/closed_reference_cohorts_provenance_20261024.json'


def bridge_paragraph(report):
    # This supplement describes one frozen, observed cohort comparison. Refuse
    # incompatible data instead of stretching this fixed prose to another run.
    tasks = report['task_summary']
    matches = report['P83_to_P82_call14_matches']
    if (report['old_runs'] != 12 or report['new_runs'] != 8 or len(report['rows']) != 20
            or report['dependent_cross_cohort_pairs'] != 24 or len(report['pairs']) != 24
            or len(tasks) != 4 or any(t['pairs'] != 6 for t in tasks)
            or any(t['old_successes'] != 3 or t['new_successes'] != 2
                   or t['all_requests_equal_pairs'] != 6 or t['all_public_outputs_equal_pairs'] != 6
                   for t in tasks[:3])
            or tasks[3]['old_successes'] != 0 or tasks[3]['new_successes'] != 0
            or tasks[3]['equal_request_prefix_lengths'] != [13] * 6
            or tasks[3]['first_request_differences'] != [14] * 6
            or tasks[3]['first_public_output_differences'] != [14] * 6
            or len(matches) != 12
            or any(m['full_saved_request_equal'] != (m['case'] in ('P83_P80_NORMALIZED', 'P83_R2_NORMALIZED'))
                   for m in matches)
            or report['randomized_or_concurrent_ablation'] is not False
            or report['P84_response_records_read'] is not False):
        raise ValueError('fixed_closed_reference_bridge_required')
    return ('補助的な事後照合として，旧Hの３反復と本群Hの２反復を全４課題で比べた24対を残した．'
            '成功３課題は全要求・公開出力列が一致し，書出しの全６対は最初の13生成が一致して14生成目で差があった．'
            '本群Hの書出し両反復の14生成目は保存統一入力C/Dと要求JSONが一致したが，課題は両方未達だった．'
            'これは時期の異なる群の記録照合であり，正規化の有無を同時に割り付けた因果比較ではない．'
            '次出力診断ではcacheを無効化しており，本群のwarm状態の再現でもない．\n')


def build():
    target = ROOT / FOLDER
    if target.exists():
        raise FileExistsError('preserve_first_final_results_draft')
    parent = ROOT / PARENT
    old = read(parent / 'build_manifest.json')
    if (old['unknown_usage_imputed'] is not False or old['resource_intervals_included'] is not False
            or old['observed_resource_accounting_included'] is not True or old.get('synthetic_only', False)):
        raise ValueError('closed_observed_resource_parent_required')
    sources = dict(old['source_sha256'])
    for name, expected in old['generated_sha256'].items():
        if sha(parent / name) != expected:
            raise ValueError('generated_parent_changed:' + name)
        sources[PARENT + '/' + name] = expected
    for name, expected in sources.items():
        if sha(ROOT / name) != expected:
            raise ValueError('bound_parent_source_changed:' + name)
    ledger = read(ROOT / LEDGER)
    for name, expected in ledger['source_sha256'].items():
        if sha(ROOT / name) != expected:
            raise ValueError('closed_bridge_source_changed:' + name)
        if name in sources and sources[name] != expected:
            raise ValueError('inconsistent_source_binding:' + name)
        sources[name] = expected
    paragraph = bridge_paragraph(read(ROOT / BRIDGE))
    generated = {name: (parent / name).read_text() for name in old['generated_sha256']}
    source = generated['draft.tex'].replace(PARENT + '/', FOLDER + '/')
    marker = '\\input{' + FOLDER + '/observed_resources.tex}'
    source = replace_once(source, marker, marker + '\n\\input{' + FOLDER + '/cross_cohort.tex}')
    generated.update({'draft.tex': source, 'cross_cohort.tex': paragraph})
    for name in (LEDGER, PARENT + '/build_manifest.json', 'scripts/build_closed_results_final.py'):
        sources[name] = sha(ROOT / name)
    target.mkdir(parents=True, exist_ok=False)
    for name, content in generated.items():
        with (target / name).open('x') as f: f.write(content)
    manifest = {**old, 'generated_at': datetime.now(timezone.utc).isoformat(),
        'source_sha256': sources, 'generated_sha256': {n: sha(target / n) for n in generated},
        'parent_draft': PARENT, 'cross_cohort_evidence_added': True,
        'cross_cohort_randomized_ablation': False, 'cross_cohort_runs': 20,
        'cross_cohort_dependent_pairs': 24, 'visual_reviewed': False, 'submission_ready': False}
    for key in ('pdf_sha256', 'renderer_sha256', 'pages', 'body_pages'):
        manifest.pop(key, None)
    with (target / 'build_manifest.json').open('x') as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2); f.write('\n')
    print({'folder': FOLDER, 'cross_cohort_runs': 20, 'cross_cohort_dependent_pairs': 24})
    return manifest


if __name__ == '__main__':
    build()
