"""Prepare only the fixed posthoc known-Task4 diagnostic; no generation.

The parent freezes sources after peer review and the closed P140 publication.
All earlier results and their ledger-bound files remain unchanged.
"""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from receipt_reasoning_history import require
from run_context_comparison import write_json
from run_handoff_factors import ROOT, read, sha
from run_whole_task_object_timing_p141 import predecessor_closed
from run_whole_task_tool_choice import sources as original_sources
from whole_task_object_timing_p141 import PLAN, REQUIRED_SOURCES, fixed_fields, validate_plan


def prepare(storage, root):
    require(root.resolve() == ROOT.resolve() and not (root / PLAN).exists(),
            'matching_source_and_unused_P141_namespace_required')
    previous, original, _, prepared = original_sources(storage, root)
    known = [item for item in previous['known_tasks'] if item['task_id'] == '6104387_1']
    selected = [item for item in prepared if item['task_id'] == '6104387_1' and item['source_run'] == 'P29_04_CODE']
    require(len(known) == len(selected) == 1 and original['api_budget_by_task']['6104387_1'] == 80,
            'one_predeclared_known_Task4_with_original_API_cap_required')
    prior_path = root / 'configs/P140_whole_task_checkpoint_delta_envelope_v01.json'
    prior = read(prior_path)
    require(all(sha(root / name) == expected for name, expected in prior['source_sha256'].items()),
            'fixed_P140_sources_changed')
    publication = read(root / 'reports/P140_results_provenance_20261028.json')
    require(publication['fixed_plan_sha256'] == sha(prior_path)
            == read(root / 'reports/P140_comparison.json')['plan_sha256']
            and publication['fixed_execution_head'] == read(storage / 'records/context_pilot/P140_pipeline_v01/status.json')['git_commit'],
            'closed_P140_plan_or_head_changed')
    require(all(sha(root / name) == expected for name, expected in publication['source_sha256'].items()),
            'closed_P140_publication_changed')
    plan = fixed_fields()
    plan['known_tasks'] = deepcopy(known)
    paths = {root / name for name in prior['source_sha256']} | {root / name for name in publication['source_sha256']}
    paths |= set((root / 'scripts').rglob('*.py')) | set((root / 'tests').rglob('*.py'))
    paths |= {root / name for name in REQUIRED_SOURCES}
    plan.update(source_sha256={str(p.relative_to(root)): sha(p) for p in sorted(paths)},
        predecessor_closure=predecessor_closed(storage, root),
        created_at=datetime.now(timezone.utc).isoformat(), execution_ready=True,
        required_CI_events=['push','pull_request'], required_CI_job='accounting-and-syntax',
        user_authorization='Persistent user authorization to continue finite research until explicit stop; this diagnostic is agent-selected.',
        primary_cost='Whole-job logical input+output across all roles; cached input retained; unknown is never imputed.',
        primary_quality='Official independent final task success, never returned to the actor.',
        selection_scope='Posthoc known Task4 failure-focused diagnostic, selected after P140. No old results pooled or replaced; no reserved tasks read.',
        scientific_adoption_evaluated=False, development_gate_met=False,
        model_generations_started=False, manuscript_changed=False)
    validate_plan(plan)
    write_json(root / PLAN, plan)
    return plan


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--storage-root', type=Path, required=True)
    p.add_argument('--repo-root', type=Path, default=ROOT)
    args = p.parse_args()
    value = prepare(args.storage_root.resolve(), args.repo_root.resolve())
    print({'phase':'P141', 'source_files':len(value['source_sha256']), 'planned_conditions':3, 'model_generations':0})
