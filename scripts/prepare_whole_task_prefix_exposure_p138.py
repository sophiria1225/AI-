"""Freeze twelve P138 development slots without model, task or evaluator calls."""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

from receipt_reasoning_history import require
from run_context_comparison import write_json
from run_handoff_factors import ROOT, read, sha
from run_whole_task_prefix_exposure_p138 import predecessor_closed
from run_whole_task_tool_choice import sources as original_sources
from whole_task_prefix_exposure_p138 import PLAN, fixed_fields, validate_plan


def prepare(storage, root):
    require(root.resolve() == ROOT.resolve() and not (root/PLAN).exists(),
            'matching_source_and_unused_P138_namespace_required')
    previous, original, _, _ = original_sources(storage, root)
    prior = read(root/'configs/P123_whole_task_rolling_checkpoint_v01.json')
    plan = fixed_fields()
    plan['known_tasks'] = deepcopy(previous['known_tasks'])
    require(plan['source_runs'] == previous['source_runs']
            and [original['api_budget_by_task'][t['task_id']] for t in plan['known_tasks']] == [160, 80, 80, 80],
            'same_four_P123_tasks_and_API_caps_required')
    feasibility_path = root/'reports/P138_prefix_exposure_feasibility_20261027.json'
    feasibility = read(feasibility_path)
    require(feasibility.get('status') == 'complete' and feasibility.get('model_generations') == 0,
            'completed_generation_free_feasibility_required')
    paths = {root/name for name in prior['source_sha256']}
    paths |= set((root/'scripts').rglob('*.py')) | set((root/'tests').rglob('*.py'))
    paths |= {root/name for name in ('configs/P123_whole_task_rolling_checkpoint_v01.json',
        'reports/P123_comparison.json', 'reports/P123_server_session.json',
        'reports/P137_comparison.json', 'reports/P137_server_session.json',
        'reports/P138_prefix_exposure_feasibility_20261027.json',
        'docs/checkpoint_prefix_exposure_candidate_20261027.md',
        'docs/experiments/P138_prefix_exposure_draft_20261027.md')}
    plan.update(source_sha256={str(p.relative_to(root)):sha(p) for p in sorted(paths)},
        predecessor_closure=predecessor_closed(storage, root),
        created_at=datetime.now(timezone.utc).isoformat(), execution_ready=True,
        required_CI_events=['push', 'pull_request'], required_CI_job='accounting-and-syntax',
        user_authorization='Continue finite experiments until explicit stop; ordinary messages do not stop work.',
        primary_cost='All actual logical input and output from task start, all roles and failures; cached input is not deducted; unknown is not imputed.',
        primary_quality='Official independent final task success, never shown to the actor.',
        primary_gate='All threshold/exposure pairs known and evaluated; no success loss; lower all-task and nonempty common-success costs; actual changed timing.',
        mechanism_gate='The same conditions must also hold against fixed_interval to support the cumulative-exposure rule over this timing control.',
        selection_scope='Four known development tasks, seed57 fixed before new outcomes; no old results pooled, no heldout read.',
        model_generations_started=False, manuscript_changed=False)
    validate_plan(plan)
    write_json(root/PLAN, plan)
    return plan


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--storage-root',type=Path,required=True)
    parser.add_argument('--repo-root',type=Path,default=ROOT)
    args=parser.parse_args()
    result=prepare(args.storage_root.resolve(),args.repo_root.resolve())
    print({'phase':'P138','source_files':len(result['source_sha256']),
           'planned_conditions':result['max_cells'],'model_generations':0})
