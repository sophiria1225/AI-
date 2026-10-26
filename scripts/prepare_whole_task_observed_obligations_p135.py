"""Freeze six P135 slots; this preparer makes no model or task calls."""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

from run_handoff_factors import ROOT, read, sha
from run_context_comparison import write_json
from run_whole_task_observed_obligations_p135 import predecessor_closed
from run_whole_task_tool_choice import sources as original_sources
from whole_task_observed_obligations_p135 import PLAN, fixed_fields, validate_plan


def prepare(storage, root):
    if root.resolve() != ROOT.resolve() or (root / PLAN).exists():
        raise ValueError('matching_repository_and_new_P135_plan_required')
    prior = read(root / 'configs/P123_whole_task_rolling_checkpoint_v01.json')
    previous, original, _, _ = original_sources(storage, root)
    plan = fixed_fields()
    plan['known_tasks'] = deepcopy([t for t in previous['known_tasks'] if t['source_run'] == 'P29_04_CODE'])
    if original['api_budget_by_task'][plan['known_tasks'][0]['task_id']] != 80:
        raise ValueError('same_P123_CSV_API80_required')
    paths = {root / name for name in prior['source_sha256']}
    paths |= set((root / 'scripts').rglob('*.py')) | set((root / 'tests').rglob('*.py'))
    paths.update(root / name for name in ('configs/P123_whole_task_rolling_checkpoint_v01.json',
        'configs/P134_whole_task_observed_obligations_v01.json',
        'reports/P123_comparison.json', 'reports/P123_server_session.json',
        'reports/P132_comparison.json', 'reports/P132_server_session.json',
        'docs/experiments/P135_whole_task_observed_obligations.md',
        'reports/P133_continuation_authorization_20261027.json'))
    plan.update(source_sha256={str(p.relative_to(root)): sha(p) for p in sorted(paths)},
        predecessor_closure=predecessor_closed(storage, root),
        launch_predecessor_closure_at_preparation=None,
        P133_reporting_recovery_required_at_launch=True, P134_original_unstarted_failure_required_at_launch=True,
        created_at=datetime.now(timezone.utc).isoformat(), execution_ready=True,
        required_CI_events=['push', 'pull_request'], required_CI_job='accounting-and-syntax',
        primary_cost='All logical input and output tokens from task start, including summaries, failures and control. Unknown stays unknown.',
        primary_quality='Official independent task success; evaluation never reaches the model.',
        primary_gate='All six evaluated with known usage, no success lost to either control, fewer all/common-success tokens than counts and fewer all tokens than raw anchor, paid entity-row exposure on primary common success, intact accounting.',
        selection_scope='One known CSV task, original seeds57/157; development design after earlier results were seen. No heldout or fresh-seed claim.',
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
    print({'phase': 'P135', 'source_files': len(result['source_sha256']),
           'maximum_cells': result['max_cells'], 'model_calls_started': 0})
