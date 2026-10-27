"""Build aggregate P138 artifacts once from closed audited records; no inference."""
import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from receipt_reasoning_history import require
from whole_task_prefix_exposure_p138 import MODES, PLAN, run_order, cell_id, summarize, validate_plan

ROOT = Path(__file__).resolve().parents[1]
DESTINATION = 'materials/20261027_p138_results'


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
    audit_path=root/'reports/P138_comparison.json'
    session_path=root/'reports/P138_server_session.json'
    plan=read(root/PLAN)
    validate_plan(plan)
    require(all(sha(root/name)==expected for name,expected in plan['source_sha256'].items()),
            'fixed_P138_reporting_sources_changed')
    audit, session=read(audit_path),read(session_path)
    expected=[cell_id(n,m) for n,m in run_order()]
    require(audit['phase']==session['phase']=='P138' and audit['batch_status'] in ('complete','stopped')
        and audit['owned_processes_absent'] is True and not audit['audit_errors']
        and session['status']=='stopped' and session['owned_processes_absent'] is True
        and session['audit_source_sha256']==sha(audit_path)
        and audit['plan_sha256']==sha(root/PLAN)
        and [r['run_id'] for r in audit['rows']]==expected,'closed_fixed_P138_records_required')
    summary=summarize(audit['rows'],audit['audit_errors'])
    require(all(audit[k]==v for k,v in summary.items()),'closed_gate_recalculation_mismatch')
    target=root/DESTINATION
    target.mkdir(parents=True,exist_ok=False)
    fields=['run_id','task_id','prefix_exposure_mode','record_status','success','stop_reason',
        'model_calls','known_total_tokens','unknown_usage_calls','input_tokens','output_tokens',
        'cached_input_tokens','api_requests','checkpoint_installations',
        'decision_differences_from_rolling_separate','decision_differences_from_fixed_interval',
        'actual_decision_differences_from_rolling_separate','actual_decision_differences_from_fixed_interval',
        'prefix_exposure_contract_failed','prefix_exposure_accounting_complete','wall_seconds','full_wall_seconds']
    rows=[{k:r.get(k) for k in fields} for r in audit['rows']]
    csv_new(target/'conditions.csv',rows,fields)
    calls=[]
    for r in audit['rows']:
        for c in r.get('request_checks',[]):
            calls.append(dict(run_id=r['run_id'],task_id=r['task_id'],
                prefix_exposure_mode=r['prefix_exposure_mode'],**c))
    csv_new(target/'model_calls.csv',calls,['run_id','task_id','prefix_exposure_mode','call_id',
        'role','status','input_tokens','output_tokens','cached_input_tokens','finish_reason',
        'request_sha256','response_sha256'])
    pairs=[p for c in summary['comparisons'] for p in c['pairs']]
    csv_new(target/'pairs.csv',pairs,['task_id','baseline','baseline_success','candidate_success',
        'both_evaluated','both_usage_known','success_lost','both_successful',
        'candidate_minus_baseline_tokens','decision_differences'])
    summary.update(phase='P138',created_at=datetime.now(timezone.utc).isoformat(),
        conditions=rows, all_model_roles_included=True, cached_input_deducted=False,
        added_model_calls=0,added_environment_API_requests=0,added_evaluations=0,
        manuscript_written=False, source_sha256={str(p.relative_to(root)):sha(p)
            for p in (audit_path,session_path,root/PLAN,Path(__file__))})
    json_new(target/'summary.json',summary)
    (target/'README.md').write_text(
        '# P138: three checkpoint schedules\n\n'
        'All twelve planned cells are retained in [conditions.csv](conditions.csv). '
        'The [summary](summary.json) recalculates the fixed primary utility and '
        'both-control development gates from the closed audit. '
        '[Pairs](pairs.csv) separate both comparisons; [model calls](model_calls.csv) '
        'include every audited actor and focus attempt.\n\n'
        'Logical tokens include cached input, summaries and failures. Missing usage '
        'remains unknown. Prefix exposure is a counting-only representation metric; '
        'it is not achievable savings or a competitive guarantee. Shadow decisions '
        'are evaluated on each run\'s realized history and are not counterfactual '
        'trajectories. Fixed interval is an unmeasured timing control, while the '
        '16,384-token control has prior development evidence. One seed on four '
        'known tasks establishes neither novelty nor statistical noninferiority.\n\n'
        'The original P123/P133/P137 results remain separate. No manuscript was written.\n')
    files=sorted(p for p in target.iterdir() if p.is_file())
    json_new(target/'build_manifest.json',dict(phase='P138',status='complete',
        source_sha256=summary['source_sha256'],
        artifact_sha256={p.name:sha(p) for p in files},
        additional_model_calls=0,additional_API_requests=0,additional_evaluations=0))
    return summary


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo-root',type=Path,default=ROOT)
    args=parser.parse_args()
    result=build(args.repo_root.resolve())
    print({k:result[k] for k in ('planned_rows','primary_utility_gate_met','development_gate_met')})
