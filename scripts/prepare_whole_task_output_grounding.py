"""Bind P129 once after its predecessors close; no model or environment work."""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
from pathlib import Path

from compact_api_receipts import RECEIPT_GUIDE
from region_projection_runtime import EXPLICIT_FIELD_GUIDE
from run_handoff_factors import ROOT, read, sha
from run_context_comparison import write_json
from run_whole_task_output_grounding import predecessor_closed
from run_whole_task_tool_choice import sources as previous_sources
from whole_task_output_grounding import PLAN, API_BUDGETS, fixed_fields, validate_plan


def prepare(storage, root):
    if root.resolve() != ROOT.resolve() or (root / PLAN).exists():
        raise ValueError('matching_repository_and_new_P129_plan_required')
    predecessor = predecessor_closed(storage, root)
    previous, original, _, _ = previous_sources(storage, root)
    plan = fixed_fields()
    plan['known_tasks'] = deepcopy([t for t in previous['known_tasks'] if t['source_run'] == 'P29_04_CODE'])
    if any(plan[key] != previous[key] for key in ('source_plan', 'world_seed')):
        raise ValueError('same_known_development_tasks_required')
    if ([original['api_budget_by_task'][item['task_id']] for item in plan['known_tasks']] != [80]
            or sum(API_BUDGETS) * 6 != 720):
        raise ValueError('prespecified_known_task_API_budgets_required')
    paths = set((root / 'scripts').rglob('*.py')) | set((root / 'tests').rglob('*.py'))
    paths.update(root / name for name in (plan['source_plan'], 'configs/python_export_image_v01.json',
        'reports/P123_comparison.json', 'reports/P123_server_session.json',
        'reports/P127_comparison.json', 'reports/P127_server_session.json',
        'reports/P129_closed_source_diagnosis_20261026.json',
        'docs/experiments/P129_whole_task_output_grounding.md'))
    plan.update(source_sha256={str(path.relative_to(root)): sha(path) for path in sorted(paths)},
        predecessor_closure=predecessor, created_at=datetime.now(timezone.utc).isoformat(),
        receipt_guide_sha256=hashlib.sha256(RECEIPT_GUIDE.encode()).hexdigest(),
        explicit_field_guide_sha256=hashlib.sha256(EXPLICIT_FIELD_GUIDE.encode()).hexdigest(),
        execution_ready=True, required_CI_events=['push', 'pull_request'],
        required_CI_job='accounting-and-syntax', no_previous_replacement_or_retry=True,
        primary_cost='All actual logical input plus output tokens from task start, including focus, failures, recovery and notices; unknown stays unknown.',
        primary_quality='Independent official task success; no evaluation result reaches the model.',
        secondary_cost='Actual API requests, source checks, blocked writes, sent/returned repairs, cache use, wire bytes, complete task/setup/cleanup/evaluation/server time separately.',
        selection_scope='One known CSV task with off/feedback/repair; fixed seeds57,157. No heldout or seed-search claim. Prior P127 and all earlier results stay separate.',
        API_budget_change='CSV120 in every new mode and seed; other tasks are outside this cohort.',
        preparation_does_not_require_P128_outcomes=True,
        primary_gate='All six evaluated with known usage; no repair success lost to feedback or off; lower aggregate and common-success tokens versus feedback; real successful repair on a common success; intact contracts.',
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
    print({'phase': 'P129', 'source_files': len(result['source_sha256']),
           'maximum_cells': result['max_cells'], 'model_calls_started': 0})
