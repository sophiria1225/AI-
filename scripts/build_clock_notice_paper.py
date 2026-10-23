"""Include the closed P79 calibration without treating it as a task result."""
import argparse
from pathlib import Path

import build_api_error_paper as previous
from build_clock_notice_report import validated, STEM
from build_public_completion_paper import save
from run_handoff_factors import ROOT, read, sha

PAPER = previous.PAPER
COMPONENT = 'papers/202610_letter/clock_notice_component.tex'


def build(tex_bin, output):
    plan, pre, report, sources = validated()
    provenance = read(ROOT / 'reports/P79_results_provenance_20261023.json')
    for name, expected in provenance['source_sha256'].items():
        if sha(ROOT / name) != expected:
            raise ValueError('published_P79_source_changed:' + name)
    material = read(ROOT / 'materials/20261023_p79/build_manifest.json')
    if (not report['all_twelve_audited'] or report['model_calls_attempted'] != 12
            or report['unknown_usage_calls'] or report['audit_errors']
            or not material['visual_reviewed'] or material['visual_reviewed_pages'] != list(range(1, 7))
            or material['pdf_sha256'] != sha(ROOT / 'materials/20261023_p79' / (STEM + '.pdf'))
            or material['builder_sha256'] != sha(ROOT / 'scripts/build_clock_notice_report.py')
            or not all(all(v['all_three_public_outputs_equal'] for v in item['within'].values())
                       and item['cross']['equal_public_pairs'] == 0
                       and item['cross']['compared_pairs'] == 9 for item in report['equality_summary'])):
        raise ValueError('reviewed_all_twelve_P79_calibration_required')
    if sha(ROOT / 'scripts/build_api_error_paper.py') != 'e3dea7e7aef1a9cae0ebb1c32c2c59523119950e2112b9a01551641ab8b155ea':
        raise ValueError('previous_P78_checker_changed')
    if (PAPER / 'candidate_cost_completion.tex').read_text().count('\\input{' + COMPONENT + '}') != 1:
        raise ValueError('include_P79_once')
    integration = ROOT / 'docs/P79_manuscript_integration.md'
    if not integration.is_file(): raise ValueError('document_calibration_scope')
    (ROOT / COMPONENT).write_text(
        '% Closed P79: saved-input calibration, not an independent task comparison.\n'
        '保存した上記２入力の残時間を元値／＋１秒とし各３回，計12生成した．'
        '全回cache０で同じ通知の公開出力は一致，通知間は両課題で異なった'
        f'（{report["known_total_tokens"]:,} token，推論器{report["server"]["wall_seconds"]:,.3f}秒，API・評価０）．'
        '元の再利用状態は未再現で，成否・費用の効果は未特定である．\n')
    previous.build(tex_bin, output)
    path = PAPER / 'cost_completion_source_map.json'; manifest = read(path)
    manifest['sources'].update(provenance['source_sha256'])
    manifest['sources']['reports/P79_results_provenance_20261023.json'] = sha(ROOT / 'reports/P79_results_provenance_20261023.json')
    manifest['rendering_sources'].update({p: sha(ROOT / p) for p in (
        COMPONENT, 'docs/P79_manuscript_integration.md', 'scripts/build_clock_notice_report.py')})
    manifest['previous_api_error_checker_sha256'] = manifest['builder_sha256']
    manifest['builder_sha256'] = sha(Path(__file__))
    manifest['data_checks']['clock_notice_calibration'] = {k: report[k] for k in (
        'all_twelve_audited', 'model_calls_attempted', 'known_total_tokens', 'unknown_usage_calls',
        'equality_summary', 'audit_errors', 'owned_processes_absent', 'environment_api_requests',
        'evaluations', 'reserved_scenarios_read', 'novel_method_claim', 'task_quality_or_savings_measured',
        'P78_causal_effect_identified', 'historical_warm_state_recreated')}
    manifest['P79_results_included'] = True
    manifest['P79_is_task_quality_comparison'] = False
    manifest['P79_adds_independent_agent_tasks'] = False
    save(path, manifest)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--tex-bin', type=Path, required=True)
    p.add_argument('--output-dir', type=Path, default=ROOT / '.runtime/clock-notice-paper')
    a = p.parse_args(); build(a.tex_bin.resolve(), a.output_dir.resolve())
