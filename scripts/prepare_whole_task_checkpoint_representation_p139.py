"""Freeze sixteen P139 development slots without model, task or evaluator calls."""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

from receipt_reasoning_history import require
from run_context_comparison import write_json
from run_handoff_factors import ROOT, read, sha
from run_whole_task_checkpoint_representation_p139 import predecessor_closed
from run_whole_task_tool_choice import sources as original_sources
from whole_task_checkpoint_representation_p139 import PLAN, fixed_fields, validate_plan


def prepare(storage, root):
    require(root.resolve() == ROOT.resolve() and not (root/PLAN).exists(),
            'matching_source_and_unused_P139_namespace_required')
    previous, original, _, _ = original_sources(storage, root)
    prior = read(root/'configs/P138_whole_task_prefix_exposure_v01.json')
    require(all(sha(root/name) == expected for name, expected in prior['source_sha256'].items()),
            'fixed_P138_sources_changed')
    plan = fixed_fields()
    plan['known_tasks'] = deepcopy(previous['known_tasks'])
    require(plan['source_runs'] == previous['source_runs']
            and [original['api_budget_by_task'][t['task_id']] for t in plan['known_tasks']] == [160, 80, 80, 80],
            'same_four_P123_tasks_and_API_caps_required')
    diagnosis_path = root/'reports/P138_task4_API_progress_metadata_20261027.json'
    diagnosis = read(diagnosis_path)
    require(diagnosis.get('status') == 'complete'
            and diagnosis.get('additional_model_API_evaluator_tokenizer_calls') == 0
            and diagnosis.get('original_results_modified') is False,
            'closed_generation_free_diagnosis_required')
    paths = {root/name for name in prior['source_sha256']}
    paths |= set((root/'scripts').rglob('*.py')) | set((root/'tests').rglob('*.py'))
    paths |= {root/name for name in (
        'configs/P123_whole_task_rolling_checkpoint_v01.json',
        'configs/P138_whole_task_prefix_exposure_v01.json',
        'reports/P138_comparison.json', 'reports/P138_server_session.json',
        'reports/P138_results_provenance_20261027.json',
        'reports/P138_task4_API_progress_metadata_20261027.json',
        'docs/experiments/P139_checkpoint_representation_draft_20261027.md')}
    publication = read(root/'reports/P138_results_provenance_20261027.json')
    require(publication['fixed_plan_sha256'] == sha(root/'configs/P138_whole_task_prefix_exposure_v01.json')
            == read(root/'reports/P138_comparison.json')['plan_sha256']
            and publication['fixed_execution_head'] ==
                read(storage/'records/context_pilot/P138_pipeline_v01/status.json')['git_commit'],
            'closed_P138_fixed_plan_or_head_changed')
    require(all(sha(root/name)==expected for name,expected in publication['source_sha256'].items()),
            'closed_P138_publication_changed')
    paths |= {root/name for name in publication['source_sha256']}
    plan.update(source_sha256={str(p.relative_to(root)):sha(p) for p in sorted(paths)},
        predecessor_closure=predecessor_closed(storage, root),
        created_at=datetime.now(timezone.utc).isoformat(), execution_ready=True,
        required_CI_events=['push', 'pull_request'], required_CI_job='accounting-and-syntax',
        user_authorization='Continue finite experiments until explicit stop; ordinary messages do not stop work.',
        primary_cost='All actual logical input and output from task start, all roles and failures; cached input is not deducted; unknown is not imputed.',
        primary_quality='Official independent final task success, never shown to the actor.',
        primary_gate='exposure_delta versus threshold_recursive: all four pairs evaluated and known, no success loss, lower all-task and nonempty common-success costs, actual intervention.',
        mechanism_gate='Also pass against exposure_recursive and threshold_delta; representation-only comparisons require actual known delta exposure and matched observed pre-treatment prefixes.',
        selection_scope='Four known development tasks, seed57 selected for known second-checkpoint activation; new max2 factorial, not an independent replication; all controls rerun once, no prior results pooled or heldout read.',
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
    print({'phase':'P139','source_files':len(result['source_sha256']),
           'planned_conditions':result['max_cells'],'model_generations':0})
