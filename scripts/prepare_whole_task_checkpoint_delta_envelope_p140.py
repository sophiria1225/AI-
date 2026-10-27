"""Freeze twelve P140 slots only after explicit final source approval; no generation."""
import argparse
from copy import deepcopy
from datetime import datetime,timezone
from pathlib import Path
from receipt_reasoning_history import require
from run_context_comparison import write_json
from run_handoff_factors import ROOT,read,sha
from run_whole_task_checkpoint_delta_envelope_p140 import predecessor_closed
from run_whole_task_tool_choice import sources as original_sources
from whole_task_checkpoint_delta_envelope_p140 import PLAN,REQUIRED_SOURCES,fixed_fields,validate_plan

PREPARATION_APPROVED = True
DIAGNOSES = ('reports/P139_delta_envelope_scalar_diagnosis_20261027.json',
    'reports/P139_delta_envelope_structure_diagnosis_20261027.json',
    'reports/P139_transport_id_prefix_diagnosis_20261027.json')


def prepare(storage,root):
    require(PREPARATION_APPROVED is True,'P140_draft_not_approved_for_plan_preparation')
    require(root.resolve()==ROOT.resolve() and not (root/PLAN).exists(),'matching_source_and_unused_P140_namespace_required')
    previous,original,_,_=original_sources(storage,root)
    prior_path=root/'configs/P139_whole_task_checkpoint_representation_v01.json';prior=read(prior_path)
    require(all(sha(root/name)==expected for name,expected in prior['source_sha256'].items()),'fixed_P139_sources_changed')
    plan=fixed_fields();plan['known_tasks']=deepcopy(previous['known_tasks'])
    require(plan['source_runs']==previous['source_runs'] and [original['api_budget_by_task'][t['task_id']] for t in plan['known_tasks']]==[160,80,80,80],
            'same_four_P123_tasks_and_API_caps_required')
    for name in DIAGNOSES:require(read(root/name).get('status')=='complete','closed_public_diagnostic_required')
    publication=read(root/'reports/P139_results_provenance_20261027.json')
    require(publication['fixed_plan_sha256']==sha(prior_path)==read(root/'reports/P139_comparison.json')['plan_sha256']
        and publication['fixed_execution_head']==read(storage/'records/context_pilot/P139_pipeline_v01/status.json')['git_commit'],
        'closed_P139_fixed_plan_or_head_changed')
    require(all(sha(root/name)==expected for name,expected in publication['source_sha256'].items()),'closed_P139_publication_changed')
    paths={root/name for name in prior['source_sha256']}|{root/name for name in publication['source_sha256']}
    paths|=set((root/'scripts').rglob('*.py'))|set((root/'tests').rglob('*.py'))
    paths|={root/name for name in (*REQUIRED_SOURCES,*DIAGNOSES)}
    plan.update(source_sha256={str(p.relative_to(root)):sha(p) for p in sorted(paths)},
        predecessor_closure=predecessor_closed(storage,root),created_at=datetime.now(timezone.utc).isoformat(),execution_ready=True,
        required_CI_events=['push','pull_request'],required_CI_job='accounting-and-syntax',
        user_authorization='Persistent user instruction to continue finite experiments until explicit stop; P140 design is agent-selected.',
        primary_cost='Whole-job logical input+output from all roles, paid invalid/failed summaries and failures; cache included, unknown not imputed.',
        primary_quality='Official independent final task success; never returned to actor.',
        primary_gate='Candidate versus threshold_recursive: all four pairs known, no success loss, lower all/common costs, paid object prompt and known delta actor exposure on common success.',
        mechanism_gate='Independently pass against unchanged exposure_delta with fixed validated transport-ID canonical prefix evidence, strict evidence reported separately.',
        selection_scope='Posthoc known four-task seed57 development study motivated by closed P139 output-envelope evidence; no old result changed or pooled, no heldout read.',
        model_generations_started=False,manuscript_changed=False)
    validate_plan(plan);write_json(root/PLAN,plan);return plan


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--storage-root',type=Path,required=True);p.add_argument('--repo-root',type=Path,default=ROOT);a=p.parse_args()
    value=prepare(a.storage_root.resolve(),a.repo_root.resolve());print({'phase':'P140','source_files':len(value['source_sha256']),'planned_conditions':12,'model_generations':0})
