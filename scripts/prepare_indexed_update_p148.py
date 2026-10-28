"""Freeze seed357 replication without generating models, probes or task outputs."""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path

from run_handoff_factors import ROOT, read, sha
from indexed_update_config_p148 import fixed_fields, validate_plan, run_order, cell_id

PLAN = 'configs/P148_indexed_update_v01.json'


def prepare(storage, root):
    target = root / PLAN
    if target.exists():
        raise FileExistsError('preserve_fixed_P148_protocol')
    old = read(root/'configs/P147_indexed_update_v01.json')
    plan = deepcopy(old)
    for key in ('required_P145_plan_sha256','required_P145_owned_server_stopped',
                'required_probe_preflight_pass','latest_launch_jst',
                'operational_latest_launch_is_not_a_user_deadline'):
        plan.pop(key, None)
    plan.update(fixed_fields())
    plan.update(created_at=datetime.now(timezone.utc).isoformat(),
        required_P147_plan_sha256=sha(root/'configs/P147_indexed_update_v01.json'),
        probe_task_slots=[], whole_task_stage_conditional_on_all_three_probes=False,
        new_probe_generations=0, inherited_P147_probe_evidence=True,
        development_probe_cost_reported_separately=True,
        seed_choice='fixed_next_increment_357_not_selected_from_new_outcomes',
        schedule=[dict(task_slot=n,mode=m,run_id=cell_id(n,m)) for n,m in run_order()],
        selection_scope='One fixed new seed, all four previously known tasks paired against TR; unchanged P147 candidate. No new probes, task selection, retries, outcome-dependent stopping or pooling with earlier seeds.',
        user_authorization='Existing instruction to continue background experiments while preparing the manuscript; fixed seed357 eight-cell replication approved by the root reviewer. The 11:00 JST model deadline is an operational cap, not a completion promise.',
        model_generations_started=False, manuscript_changed=False,
        scientific_method_changed_from_P147=False,
        source_registry_snapshot_is_not_latest_global_registry=True)
    snapshot_path=storage/'.runtime/P148_registry_snapshot_20261029.json'
    snapshot=read(snapshot_path)
    names=snapshot['names']
    if len(names)!=219 or len(names)!=len(set(names)):
        raise ValueError('fixed_unique_219_ledger_snapshot_required')
    paths=set(old['source_sha256'])|{'configs/P147_indexed_update_v01.json',
        'docs/experiments/P148_seed357_replication_20261029.md',
        'docs/experiments/P147_closed_results_20261029.md',
        'reports/P147_closed_results_20261029.json',
        'reports/P147_closed_publication_provenance_20261029.json'}
    for area in ('scripts','tests'):
        paths.update(str(p.relative_to(root)) for p in (root/area).glob('*p148.py'))
    count=0
    for name in names:
        rel='reports/'+name+'.json'
        paths.add(rel)
        for source,expected in read(root/rel)['source_sha256'].items():
            if sha(root/source)!=expected:
                raise ValueError('old_bound_evidence_changed:'+source)
            paths.add(source)
            count+=1
    if count!=3118:
        raise ValueError('fixed_3118_binding_snapshot_required')
    audit_path=storage/'.runtime/P147_closed_independent_20261029.json'
    audit=read(audit_path)
    if (sha(audit_path)!='011a40cc12ed126dfd9b90f7b299fe4e48dee6669321eeeae1d99e09d87a71c3'
            or audit['audit_status']!='pass_closed_records_consistent'):
        raise ValueError('fixed_closed_P147_independent_audit_required')
    private=dict(audit['evidence_sha256'])
    for rel in ('.runtime/P147_closed_independent_20261029.json',
                '.runtime/P148_registry_snapshot_20261029.json',
                '.runtime/P148_user_authorization_20261029.json'):
        private[rel]=sha(storage/rel)
    for rel,expected in private.items():
        if sha(storage/rel)!=expected:
            raise ValueError('closed_P147_private_evidence_changed')
    plan.update(prior_ledger_count=219,prior_binding_count=count,
        prior_registry_sha256=snapshot['registry_sha256'],
        source_registry_snapshot_sha256=sha(snapshot_path),
        source_sha256={rel:sha(root/rel) for rel in sorted(paths)},
        private_source_sha256=dict(sorted(private.items())))
    validate_plan(plan)
    with target.open('x') as f:
        json.dump(plan,f,ensure_ascii=False,indent=2,allow_nan=False)
        f.write('\n')
    return plan


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--storage-root',type=Path,required=True)
    args=parser.parse_args()
    result=prepare(args.storage_root.resolve(),ROOT)
    print({k:result[k] for k in ('experiment','model_seed','max_cells','prior_ledger_count','prior_binding_count')})
