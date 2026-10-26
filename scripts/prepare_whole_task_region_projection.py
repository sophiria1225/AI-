"""Bind P127 once after its predecessors close; no model or environment work."""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
from pathlib import Path

from compact_api_receipts import RECEIPT_GUIDE
from region_projection_runtime import EXPLICIT_FIELD_GUIDE
from run_handoff_factors import ROOT, read, sha
from run_context_comparison import write_json
from run_whole_task_region_projection import predecessor_closed
from run_whole_task_tool_choice import sources as previous_sources
from whole_task_region_projection import PLAN, API_BUDGETS, REPLAY_REPORT, fixed_fields, validate_plan


def prepare(storage, root):
    if root.resolve() != ROOT.resolve() or (root / PLAN).exists():
        raise ValueError('matching_repository_and_new_P127_plan_required')
    predecessor = predecessor_closed(storage, root)
    previous, original, _, _ = previous_sources(storage, root)
    plan = fixed_fields()
    plan['known_tasks'] = deepcopy(previous['known_tasks'])
    if any(plan[key] != previous[key] for key in ('source_plan', 'source_runs', 'world_seed')):
        raise ValueError('same_known_development_tasks_required')
    if ([original['api_budget_by_task'][item['task_id']] for item in plan['known_tasks']] != [160, 80, 80, 80]
            or sum(API_BUDGETS) * 2 != 880):
        raise ValueError('prespecified_known_task_API_budgets_required')
    paths = set((root / 'scripts').rglob('*.py')) | set((root / 'tests').rglob('*.py'))
    paths.update(root / name for name in (plan['source_plan'], 'configs/python_export_image_v01.json',
        'reports/P123_comparison.json', 'reports/P123_server_session.json',
        'reports/P125_comparison.json', 'reports/P125_server_session.json', REPLAY_REPORT,
        'docs/experiments/P127_whole_task_region_projection.md'))
    plan.update(source_sha256={str(path.relative_to(root)): sha(path) for path in sorted(paths)},
        predecessor_closure=predecessor, created_at=datetime.now(timezone.utc).isoformat(),
        receipt_guide_sha256=hashlib.sha256(RECEIPT_GUIDE.encode()).hexdigest(),
        explicit_field_guide_sha256=hashlib.sha256(EXPLICIT_FIELD_GUIDE.encode()).hexdigest(),
        execution_ready=True, required_CI_events=['push', 'pull_request'],
        required_CI_job='accounting-and-syntax', no_previous_replacement_or_retry=True,
        primary_cost='All actual logical input plus output tokens from task start, including focus, failures, recovery and notices; unknown stays unknown.',
        primary_quality='Independent official task success; no evaluation result reaches the model.',
        secondary_cost='Actual API requests, projection/cache use, wire bytes, complete task/setup/cleanup/evaluation/server time separately.',
        selection_scope='Known four-task development screen; fixed seed157. No heldout or seed-search claim. Prior P125/P126 results stay separate.',
        API_budget_change='CSV is fixed at 120 in both new arms; other tasks retain 160/80/80. Closed P125 remains at its original limits.',
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
    print({'phase': 'P127', 'source_files': len(result['source_sha256']),
           'maximum_cells': result['max_cells'], 'model_calls_started': 0})
