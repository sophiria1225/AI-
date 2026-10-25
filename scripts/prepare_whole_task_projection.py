"""Bind P125 once after its predecessors close; no model or environment work."""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
from pathlib import Path

from compact_api_receipts import RECEIPT_GUIDE
from run_handoff_factors import ROOT, read, sha
from run_context_comparison import write_json
from run_whole_task_projection import predecessor_closed
from run_whole_task_tool_choice import sources as previous_sources
from whole_task_projection import PLAN, fixed_fields, validate_plan


def prepare(storage, root):
    if root.resolve() != ROOT.resolve() or (root / PLAN).exists():
        raise ValueError('matching_repository_and_new_P125_plan_required')
    predecessor = predecessor_closed(storage, root)
    manifest_path = storage / '.runtime/P124_replay_input_manifest_v01.json'
    manifest = read(manifest_path)
    replay = read(root / 'reports/P124_projection_replay.json')
    if (sha(manifest_path) != replay['input_manifest_sha256']
            or any(sha(root / name) != expected for name, expected in manifest['implementation_files'].items())):
        raise ValueError('preserve_all_sources_of_successful_P124_replay')
    previous, original, _, _ = previous_sources(storage, root)
    plan = fixed_fields()
    plan['known_tasks'] = deepcopy(previous['known_tasks'])
    if any(plan[key] != previous[key] for key in ('source_plan', 'source_runs', 'world_seed')):
        raise ValueError('same_known_development_tasks_required')
    if sum(original['api_budget_by_task'][item['task_id']] for item in plan['known_tasks']) * 2 != 800:
        raise ValueError('same_known_API_budgets_required')
    paths = set((root / 'scripts').rglob('*.py')) | set((root / 'tests').rglob('*.py'))
    paths.update(root / name for name in (plan['source_plan'], 'configs/python_export_image_v01.json',
        'reports/P123_comparison.json', 'reports/P123_server_session.json',
        'reports/P124_projection_replay.json', 'reports/P124_projection_replay_independent_audit.json',
        'docs/experiments/P125_whole_task_projection.md',
        'reports/P125_prior_static_coverage_20261026.json',
        'docs/P125_prior_static_coverage_20261026.md',
        'reports/P125_prior_applicability_gap_20261026.json',
        'docs/P125_prior_applicability_gap_20261026.md',
        'docs/automatic_projection_direct_prior_20261026.md'))
    plan.update(source_sha256={str(path.relative_to(root)): sha(path) for path in sorted(paths)},
        predecessor_closure=predecessor, created_at=datetime.now(timezone.utc).isoformat(),
        receipt_guide_sha256=hashlib.sha256(RECEIPT_GUIDE.encode()).hexdigest(),
        execution_ready=True, required_CI_events=['push', 'pull_request'],
        required_CI_job='accounting-and-syntax', no_previous_replacement_or_retry=True,
        primary_cost='All actual logical input plus output tokens from task start, including focus, failures, recovery and notices; unknown stays unknown.',
        primary_quality='Independent official task success; no evaluation result reaches the model.',
        secondary_cost='Actual API requests, projection/cache use, wire bytes, complete task/setup/cleanup/evaluation/server time separately.',
        selection_scope='Known four-task development screen. Seed157 selected from closed activation evidence, not heldout or a seed-search success.',
        model_generations_started=False, manuscript_changed=False)
    validate_plan(plan)
    write_json(root / PLAN, plan)
    return plan


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--storage-root', type=Path, required=True)
    parser.add_argument('--repo-root', type=Path, default=ROOT)
    args = parser.parse_args()
    result = prepare(args.storage_root, args.repo_root)
    print({'phase': 'P125', 'source_files': len(result['source_sha256']),
           'maximum_cells': result['max_cells'], 'model_calls_started': 0})
