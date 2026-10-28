"""Freeze P147 before outcomes; require P145 closure and the new probe gate."""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path

from run_handoff_factors import ROOT, read, sha
from indexed_update_config_p147 import fixed_fields, validate_plan, run_order, cell_id

PLAN = 'configs/P147_indexed_update_v01.json'


def prepare(storage, root):
    target = root / PLAN
    if target.exists():
        raise FileExistsError('preserve_P147_predeclared_protocol')
    old = read(root / 'configs/P144_state_update_v01.json')
    plan = deepcopy(old)
    for name in ('deadline_jst','reporting_deadline_jst','predecessor_closure',
        'deadline_budget_changes_common_to_all_three_arms','native_preflight_focus_requests',
        'native_preflight_post_checkpoint_actor_requests','user_authorization','selection_scope'):
        plan.pop(name, None)
    plan.update(fixed_fields())
    plan.update(created_at=datetime.now(timezone.utc).isoformat(),
        required_P145_plan_sha256=sha(root / 'configs/P145_update_transport_v01.json'),
        source_plan='configs/P29_stateful_code_v01.json',
        source_runs=[f'P29_{n:02d}_CODE' for n in range(1,5)],
        native_preflight_initial_requests=8, parser_and_fragment_limits_unchanged=True,
        prior_cohort_work_budget_changed=False, second_opportunity_only_representation_change=False,
        second_update_focus_only_transport_change=True,
        probe_task_slots=[1,2,4],probe_output_cap=4096,probe_reasoning_budget=2048,
        whole_task_stage_conditional_on_all_three_probes=True,
        unknown_usage_stops_later_model_dispatch=True,
        development_probe_cost_reported_separately=True,
        P145_duplicate_index_failures_seen_before_design=True,
        representation_prompt_change_predeclared=True,
        raw_converted_and_materialized_character_limits=8192,
        seed_choice='fixed_P144_seed257_reused_without_search',
        schedule=[dict(task_slot=n,mode=m,run_id=cell_id(n,m)) for n,m in run_order()],
        selection_scope='Three saved-input probes of indexed actions, then only if the fixed probe gate passes all four previously known tasks paired against TR. Post-P145 development; no pooling, retries, seed search or unseen tasks.',
        user_authorization='Explicit renewed instruction to run background experiments while preparing the manuscript; the prior user deadline has passed and is not reinterpreted.',
        model_generations_started=False, manuscript_changed=False)
    prior = read(root / 'configs/P146_schema_update_v01.json')
    paths = set(prior['source_sha256']) | {'configs/P146_schema_update_v01.json'}
    for area in ('scripts','tests'):
        paths.update(str(p.relative_to(root)) for p in (root/area).glob('*p147.py'))
    paths.add('docs/experiments/P147_indexed_update_20261029.md')
    registry = read(storage / '.runtime/research_ledger_names.json')
    if len(registry) != len(set(registry)):
        raise ValueError('unique_registered_ledgers_required')
    count=0
    for name in registry:
        rel='reports/'+name+'.json'
        ledger=read(root/rel)
        paths.add(rel)
        for source,h in ledger['source_sha256'].items():
            if sha(root/source)!=h:
                raise ValueError('old_bound_evidence_changed:'+source)
            paths.add(source)
        count+=len(ledger['source_sha256'])
    plan.update(prior_ledger_count=len(registry), prior_binding_count=count,
        prior_registry_sha256=sha(storage/'.runtime/research_ledger_names.json'),
        source_sha256={p:sha(root/p) for p in sorted(paths)},
        private_source_sha256={p:sha(storage/p) for p in (
            '.runtime/P145_user_authorization_20261029.json',
            'records/context_pilot/P145_pipeline_v01/status.json',
            'records/context_pilot/P145_pipeline_v01/server_final.json',
            'records/context_pilot/P145_replay_v01/status.json',
            '.runtime/P145_closed_independent_20261029.json')})
    validate_plan(plan)
    with target.open('x') as f:
        json.dump(plan,f,indent=2,ensure_ascii=False,allow_nan=False)
        f.write('\n')
    return plan


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--storage-root',type=Path,required=True)
    args=parser.parse_args()
    p=prepare(args.storage_root.resolve(),ROOT)
    print({k:p[k] for k in ('experiment','max_cells','prior_ledger_count','prior_binding_count')})
