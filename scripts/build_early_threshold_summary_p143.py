"""Build aggregate P143 artifacts once from closed audited records; no inference."""
import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from receipt_reasoning_history import require
from whole_task_threshold_object_p143 import MODES, PLAN, run_order, cell_id, summarize, validate_plan

ROOT = Path(__file__).resolve().parents[1]
DESTINATION = 'materials/20261028_p143_results'


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def json_new(path, value):
    with path.open('x') as f:
        json.dump(value, f, ensure_ascii=False, indent=2, allow_nan=False)
        f.write('\n')


def csv_new(path, rows, fields):
    with path.open('x', newline='') as f:
        writer=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore')
        writer.writeheader(); writer.writerows(rows)


def build(root):
    audit_path=root/'reports/P143_comparison.json'
    session_path=root/'reports/P143_server_session.json'
    plan=read(root/PLAN)
    validate_plan(plan)
    require(all(sha(root/name)==expected for name,expected in plan['source_sha256'].items()),
            'fixed_P143_reporting_sources_changed')
    audit, session=read(audit_path),read(session_path)
    expected=[cell_id(n,m) for n,m in run_order()]
    require(audit['phase']==session['phase']=='P143' and audit['batch_status'] in ('complete','stopped')
        and audit['owned_processes_absent'] is True and type(audit['audit_errors']) is list
        and session['status']=='stopped' and session['owned_processes_absent'] is True
        and session['audit_source_sha256']==sha(audit_path)
        and audit['plan_sha256']==sha(root/PLAN)
        and [r['run_id'] for r in audit['rows']]==expected,'closed_fixed_P143_records_required')
    summary=summarize(audit['rows'],audit['audit_errors'])
    require(all(audit[k]==v for k,v in summary.items()),'closed_descriptive_recalculation_mismatch')
    target=root/DESTINATION
    target.mkdir(parents=True,exist_ok=False)
    fields=['run_id','task_id','model_seed','object_timing_mode','checkpoint_representation_mode','record_status','success','stop_reason',
        'model_calls','known_total_tokens','unknown_usage_calls','input_tokens','output_tokens',
        'cached_input_tokens','api_requests','checkpoint_installations',
        'object_prompt_offers','object_prompt_dispatched_focus_calls','object_prompt_known_focus_calls',
        'object_prompt_unknown_focus_calls','delta_envelope_contract_failed','delta_envelope_accounting_complete',
        'decision_differences_from_threshold','decision_differences_from_exposure',
        'actual_decision_differences_from_threshold','actual_decision_differences_from_exposure',
        'delta_installations','fragment_count','actual_delta_actor_calls',
        'actual_delta_known_actor_calls','actual_delta_unknown_actor_calls',
        'checkpoint_representation_contract_failed','checkpoint_representation_accounting_complete',
        'prefix_exposure_contract_failed','prefix_exposure_accounting_complete','wall_seconds','full_wall_seconds']
    rows=[{k:r.get(k) for k in fields} for r in audit['rows']]
    csv_new(target/'conditions.csv',rows,fields)
    calls=[]
    for r in audit['rows']:
        for c in r.get('request_checks',[]):
            calls.append(dict(run_id=r['run_id'],task_id=r['task_id'],model_seed=r['model_seed'],
                object_timing_mode=r['object_timing_mode'],
                checkpoint_representation_mode=r['checkpoint_representation_mode'],**c))
    csv_new(target/'model_calls.csv',calls,['run_id','task_id','model_seed','object_timing_mode','checkpoint_representation_mode','call_id',
        'role','status','input_tokens','output_tokens','cached_input_tokens','finish_reason',
        'request_sha256','response_sha256'])
    pairs=[p for c in summary['comparisons'] for p in c['pairs']]
    csv_new(target/'pairs.csv',pairs,['task_id','baseline','candidate','baseline_success','candidate_success',
        'both_evaluated','both_usage_known','success_lost','both_successful',
        'candidate_minus_baseline_tokens','candidate_object_prompt_known_focus_calls',
        'candidate_delta_known_actor_calls','strict_prefix_match','canonical_prefix_match',
        'actual_intervention'])
    summary.update(phase='P143',created_at=datetime.now(timezone.utc).isoformat(),
        conditions=rows, all_model_roles_included=True, cached_input_deducted=False,
        added_model_calls=0,added_environment_API_requests=0,added_evaluations=0,
        manuscript_written=False, source_sha256={str(p.relative_to(root)):sha(p)
            for p in (audit_path,session_path,root/PLAN,Path(__file__))})
    json_new(target/'summary.json',summary)
    (target/'README.md').write_text(
        '# P143: early-threshold coverage on four known tasks\n\n'
        'All eight planned cells remain in [conditions.csv](conditions.csv), including '
        'failures, unknown usage and cells not completed. [Pairs](pairs.csv) retains all '
        'four task-matched comparisons. [Model calls](model_calls.csv) includes all actor '
        'and focus attempts. [Summary](summary.json) preserves the fixed development '
        'eligibility criteria and separate success-loss and common-success comparisons.\n\n'
        'Both policies use the fixed 8192-token first/repeat threshold, maximum two checkpoint opportunities and '
        'the same per-task budgets. The candidate uses the explicit object-delta contract. '
        'This post-P142 coverage study reuses seed157 on all four known tasks with 1200 work seconds per cell; no older '
        'cohort is pooled or replaced. It does not use the reserved twelve tasks and '
        'is not a reserved-task confirmation or independent population sample. Selection followed the closed P142 non-activation finding. Because threshold and work budget both differ from P142, cross-phase differences cannot identify a threshold effect.\n\n'
        'Known logical input plus output includes cached input, paid rejected summaries '
        'and failed calls with known usage. Unknown or missing values remain null and '
        'are not zero. Exact whole-cohort differences require all four paired usages '
        'known; an empty common-success group has a null cost difference. Lower known '
        'subtotals in incomplete records are not a measured saving.\n\n'
        'Strict prefix identity and validated transport-ID canonical identity are '
        'reported separately. Actual known object-focus dispatch and subsequent '
        'delta-bearing actor input are required where intervention is claimed. '
        'Absent or invalid evidence cannot establish attribution. The paired '
        'comparison is of the representation-plus-prompt bundle, not an object-prompt '
        'effect in isolation; it establishes no semantic fidelity, general quality '
        'guarantee, novelty or statistical interaction. Audit errors remain visible.\n')
    files=sorted(p for p in target.iterdir() if p.is_file())
    json_new(target/'build_manifest.json',dict(phase='P143',status='complete',
        source_sha256=summary['source_sha256'],
        artifact_sha256={p.name:sha(p) for p in files},
        additional_model_calls=0,additional_API_requests=0,additional_evaluations=0))
    return summary


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo-root',type=Path,default=ROOT)
    args=parser.parse_args()
    result=build(args.repo_root.resolve())
    print({k:result[k] for k in ('planned_rows','development_gate_met')})
