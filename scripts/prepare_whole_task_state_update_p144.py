"""Freeze the twelve known-task/common-8k P144 slots after final source approval.

No reservation requirements, world, native counter, model or evaluator are
opened here. The historical known-four source provider is called only by the
explicit prepare entrypoint. Untracked reserved-confirmation drafts are not
part of this experiment's frozen source graph.
"""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import subprocess

from receipt_reasoning_history import require
from run_context_comparison import write_json
from run_handoff_factors import ROOT, read, sha
from run_whole_task_tool_choice import sources as original_sources

PRIOR_PLAN = 'configs/P143_threshold_object_v01.json'
PRIOR_PUBLICATION = 'reports/P143_results_provenance_20261028.json'
PRIOR_AUDIT = 'reports/P143_comparison.json'


def _path(root, relative):
    name = Path(relative)
    require(type(relative) is str and not name.is_absolute() and '..' not in name.parts,
            'source_path_must_be_repository_relative')
    path = root / name
    require(path.is_file() and not path.is_symlink() and path.resolve().is_relative_to(root.resolve()),
            'source_must_be_regular_file_inside_repository')
    return path


def source_paths(root, prior, publication, required_sources):
    """Explicit bound history + tracked Python + listed new P144 sources only."""
    names = set(prior['source_sha256']) | set(publication['source_sha256'])
    names |= {PRIOR_PLAN, PRIOR_PUBLICATION, PRIOR_AUDIT, *required_sources}
    tracked = subprocess.check_output(['git', 'ls-files', '-z', '--', 'scripts', 'tests'], cwd=root)
    names |= {name for name in tracked.decode().split('\0') if name.endswith('.py')}
    untracked = subprocess.check_output(['git', 'ls-files', '--others', '--exclude-standard',
                                       '-z', '--', 'scripts', 'tests'], cwd=root)
    new_phase = {name for name in untracked.decode().split('\0')
                 if name.endswith('.py') and 'p144' in Path(name).stem.lower()}
    require(new_phase <= set(required_sources), 'unlisted_new_P144_source_requires_review')
    require(not any('reserved_confirmation_' in Path(name).name
                    for name in names & set(untracked.decode().split('\0'))),
            'untracked_reserved_confirmation_drafts_are_out_of_scope')
    return {_path(root, name) for name in names}


def verify_predecessor_sources(storage, root):
    prior = read(root / PRIOR_PLAN)
    require(all(sha(_path(root, name)) == expected
                for name, expected in prior['source_sha256'].items()), 'fixed_P143_sources_changed')
    publication = read(root / PRIOR_PUBLICATION)
    require(publication['fixed_plan_sha256'] == sha(root / PRIOR_PLAN)
            == read(root / PRIOR_AUDIT)['plan_sha256']
            and publication['fixed_execution_head'] ==
                read(storage / 'records/context_pilot/P143_pipeline_v01/status.json')['git_commit'],
            'closed_P143_plan_or_head_changed')
    require(all(sha(_path(root, name)) == expected
                for name, expected in publication['source_sha256'].items()),
            'closed_P143_publication_changed')
    return prior, publication


def prepare(storage, root):
    from whole_task_state_update_p144 import PLAN, REQUIRED_SOURCES, fixed_fields, validate_plan
    from run_whole_task_state_update_p144 import predecessor_closed
    require(root.resolve() == ROOT.resolve() and not (root / PLAN).exists(),
            'matching_source_and_unused_P144_namespace_required')
    previous, original, _, prepared = original_sources(storage, root)
    plan = fixed_fields()
    known = previous['known_tasks']
    require(len(known) == len(prepared) == 4 and plan['source_runs'] == previous['source_runs']
            and len(set(previous['source_runs'])) == 4
            and [item['task_id'] for item in prepared] == [item['task_id'] for item in known]
            and [item['source_run'] for item in prepared] == previous['source_runs']
            and [original['api_budget_by_task'][item['task_id']] for item in known] == [160,80,80,80],
            'all_four_original_known_tasks_and_API_caps_required')
    prior, publication = verify_predecessor_sources(storage, root)
    plan['known_tasks'] = deepcopy(known)
    paths = source_paths(root, prior, publication, REQUIRED_SOURCES)
    plan.update(source_sha256={str(path.relative_to(root)): sha(path) for path in sorted(paths)},
        predecessor_closure=predecessor_closed(storage, root),
        created_at=datetime.now(timezone.utc).isoformat(), execution_ready=True,
        required_CI_events=['push','pull_request'], required_CI_job='accounting-and-syntax',
        user_authorization='User reopened experiments through 2026-10-28 end of day while rewriting a positive-evidence-centered letter; this known-four three-arm seed257 protocol is fixed before launch.',
        primary_cost='All actual logical input and output across actor/focus, including failures; cached input retained and unknown never imputed.',
        primary_quality='Official independent final task success, never returned to the actor.',
        selection_scope='Post-P143 three-arm development comparison on all four known tasks, fixed seed257, common8192/work1800. No seed search, pooling, or unseen task reads; existing edit-memory overlap disclosed.',
        model_generations_started=False, manuscript_changed=False)
    validate_plan(plan)
    write_json(root / PLAN, plan)
    return plan


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--storage-root', type=Path, required=True)
    parser.add_argument('--repo-root', type=Path, default=ROOT)
    args = parser.parse_args()
    plan = prepare(args.storage_root.resolve(), args.repo_root.resolve())
    print({'phase':'P144','source_files':len(plan['source_sha256']),
           'planned_conditions':12,'model_generations':0})
