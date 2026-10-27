"""Build aggregate P141 artifacts once from closed audited records; no inference."""
import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from receipt_reasoning_history import require
from whole_task_object_timing_p141 import MODES, PLAN, run_order, cell_id, summarize, validate_plan

ROOT = Path(__file__).resolve().parents[1]
DESTINATION = 'materials/20261028_p141_results'


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
    audit_path=root/'reports/P141_comparison.json'
    session_path=root/'reports/P141_server_session.json'
    plan=read(root/PLAN)
    validate_plan(plan)
    require(all(sha(root/name)==expected for name,expected in plan['source_sha256'].items()),
            'fixed_P141_reporting_sources_changed')
    audit, session=read(audit_path),read(session_path)
    expected=[cell_id(n,m) for n,m in run_order()]
    require(audit['phase']==session['phase']=='P141' and audit['batch_status'] in ('complete','stopped')
        and audit['owned_processes_absent'] is True and type(audit['audit_errors']) is list
        and session['status']=='stopped' and session['owned_processes_absent'] is True
        and session['audit_source_sha256']==sha(audit_path)
        and audit['plan_sha256']==sha(root/PLAN)
        and [r['run_id'] for r in audit['rows']]==expected,'closed_fixed_P141_records_required')
    summary=summarize(audit['rows'],audit['audit_errors'])
    require(all(audit[k]==v for k,v in summary.items()),'closed_descriptive_recalculation_mismatch')
    target=root/DESTINATION
    target.mkdir(parents=True,exist_ok=False)
    fields=['run_id','task_id','object_timing_mode','checkpoint_representation_mode','record_status','success','stop_reason',
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
            calls.append(dict(run_id=r['run_id'],task_id=r['task_id'],
                object_timing_mode=r['object_timing_mode'],
                checkpoint_representation_mode=r['checkpoint_representation_mode'],**c))
    csv_new(target/'model_calls.csv',calls,['run_id','task_id','object_timing_mode','checkpoint_representation_mode','call_id',
        'role','status','input_tokens','output_tokens','cached_input_tokens','finish_reason',
        'request_sha256','response_sha256'])
    pairs=[p for c in summary['comparisons'] for p in c['pairs']]
    csv_new(target/'pairs.csv',pairs,['task_id','baseline','candidate','baseline_success','candidate_success',
        'both_evaluated','both_usage_known','success_lost','both_successful',
        'candidate_minus_baseline_tokens','candidate_object_prompt_known_focus_calls',
        'candidate_delta_known_actor_calls','strict_prefix_match','canonical_prefix_match',
        'actual_timing_dispatch_diverged','both_timing_dispatches_known'])
    summary.update(phase='P141',created_at=datetime.now(timezone.utc).isoformat(),
        conditions=rows, all_model_roles_included=True, cached_input_deducted=False,
        added_model_calls=0,added_environment_API_requests=0,added_evaluations=0,
        manuscript_written=False, source_sha256={str(p.relative_to(root)):sha(p)
            for p in (audit_path,session_path,root/PLAN,Path(__file__))})
    json_new(target/'summary.json',summary)
    (target/'README.md').write_text(
        '# P141: one known-task object-delta timing diagnostic\n\n'
        'All three planned cells remain in [conditions.csv](conditions.csv). '
        '[Pairs](pairs.csv) contains the timing comparison (threshold-object versus exposure-object), '
        'strong recursive control versus exposure-object, and recursive versus threshold-object '
        'representation-plus-prompt bundle. [Model calls](model_calls.csv) includes all actor/focus '
        'attempts. No comparison is a scientific adoption test; every adoption gate stays false.\n\n'
        'This is original known Task4, now diagnostic slot1, selected posthoc after P140. '
        'Seed57 and the original per-cell model/token/wall/API caps remain fixed. '
        'P140 results and failures are not pooled or replaced. Neither the original four-task '
        'scope nor the untouched reserved12 confirmation is replaced by this diagnostic.\n\n'
        'Known logical input plus output includes cached input, paid rejected summaries and '
        'failed calls. Unknown/missing values stay null; unevaluated cells remain planned rows. '
        'Each pair cost is descriptive and requires both usages known; an empty common-success '
        'set has null cost difference. Overall fixed totals require all three usages known.\n\n'
        'Timing attribution compares the prefix before the first observed timing-predicate difference '
        'and requires actual dispatch divergence at that same boundary. If the offered focus is '
        'not sent, actual divergence is false; no later favorable boundary is selected. '
        'It does not require later second-focus cutoffs to match. Strict and validated '
        'transport-ID canonical evidence are separate and neither proves semantic equivalence. '
        'Absent or invalid evidence does not support attribution. Audit errors, if present, '
        'remain diagnostic limitations and cannot produce adoption.\n')
    files=sorted(p for p in target.iterdir() if p.is_file())
    json_new(target/'build_manifest.json',dict(phase='P141',status='complete',
        source_sha256=summary['source_sha256'],
        artifact_sha256={p.name:sha(p) for p in files},
        additional_model_calls=0,additional_API_requests=0,additional_evaluations=0))
    return summary


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo-root',type=Path,default=ROOT)
    args=parser.parse_args()
    result=build(args.repo_root.resolve())
    print({k:result[k] for k in ('planned_rows','diagnostic_only','scientific_adoption_evaluated','development_gate_met')})
