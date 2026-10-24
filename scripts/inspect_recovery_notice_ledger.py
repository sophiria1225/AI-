"""Publish sanitized P97 detector rows once, after all execution has closed."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import subprocess
import time

from auth_origin_observations import MODES
from recovery_notice_comparison import cell_id, run_order, validate_plan
from run_context_comparison import write_json
from run_handoff_factors import ROOT, read, sha


def summarize_monitor(record):
    return dict(requests=len(record['requests']),model_boundaries=len(record['model_boundaries']),
        candidate_counts={m:sum(c[m]['fixed_two_boundary_candidate'] for c in record['model_boundaries']) for m in MODES},
        equal_value_counts={m:sum(q.get(m,{}).get('value_equal') is True for q in record['requests']) for m in MODES},
        eligible_read_requests=sum(q['kind']=='declared_read' for q in record['requests']),
        offers=record['offers'],active_incomplete_boundary=record['active_incomplete_boundary'],
        controller_wall_seconds=record['controller_wall_seconds'],bounds_rejected=record['bounds_rejected'],
        api_elision_count=record['api_elision_count'],observation_replacement_count=record['observation_replacement_count'])


def inspect(storage, root=ROOT):
    started=time.monotonic()
    target=root/'reports/P97_notice_ledger.json'
    if target.exists():raise FileExistsError('preserve_all_notice_ledger_attempts')
    plan=read(root/'configs/P97_recovery_notice_comparison_v01.json');validate_plan(plan)
    report=read(root/'reports/P97_comparison.json')
    pipeline=read(storage/'records/context_pilot/P97_pipeline_v01/status.json')
    server=read(storage/'records/context_pilot/P97_pipeline_v01/server_final.json')
    if (report['audit_errors'] or len(report['rows'])!=12 or not report['owned_processes_absent']
            or pipeline['status'] not in ('complete','stopped') or not pipeline['server_stopped']
            or server['status']!='stopped' or server['supervisor_pid']!=pipeline['server_supervisor_pid']
            or sha(storage/'records/context_pilot/P97_pipeline_v01/status.json')!=report['pipeline_status_sha256']):
        raise ValueError('closed_owned_and_audited_cohort_required')
    for key in ('pid','supervisor_pid'):
        process=subprocess.run(['ps','-p',str(server[key]),'-o','command='],capture_output=True,text=True,timeout=10)
        if process.returncode!=1 or process.stdout.strip():raise ValueError('owned_process_still_exists')
    result=dict(phase='P97_notice_ledger',status='running',started_at=datetime.now(timezone.utc).isoformat(),
        rows=[],audit_source_sha256=sha(root/'reports/P97_comparison.json'),inspector_sha256=sha(Path(__file__)),
        additional_model_calls=0,additional_api_calls=0,additional_evaluator_calls=0,reserved_scenarios_read=0,
        interpreted_task_progress=False,model_attempt_is_not_server_receipt=True,novel_method_claim=False)
    try:
        for number,policy in run_order():
            if time.monotonic()-started>120:raise TimeoutError('finite_notice_inspection_deadline')
            rid=cell_id(number,policy);audit=next(r for r in report['rows'] if r['run_id']==rid)
            row=dict(run_id=rid,task_id=audit['task_id'],notice_policy=policy,
                record_status=audit['record_status'],record_present=False)
            result['rows'].append(row)
            path=storage/'records/context_pilot'/rid/'recovery_observations.json'
            if not path.exists():
                if audit['record_status']=='evaluated':raise ValueError('evaluated_monitor_missing')
                continue
            if path.stat().st_size>16777216:raise ValueError('fixed_monitor_file_bound')
            if sha(path)!=audit.get('recovery_observations_sha256'):
                raise ValueError('audited_monitor_hash_changed')
            record=read(path)
            if len(record['requests'])>160 or len(record['model_boundaries'])>80:
                raise ValueError('fixed_condition_bounds_exceeded')
            row.update(record_present=True,source_sha256=sha(path),**summarize_monitor(record),
                       all_requests=record['requests'],all_model_boundaries=record['model_boundaries'])
        result['status']='complete'
    except Exception as error:
        result.update(status='stopped',error_type=type(error).__name__)
        raise
    finally:
        result['wall_seconds']=time.monotonic()-started
        write_json(target,result)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--storage-root',type=Path,required=True)
    parser.add_argument('--repo-root',type=Path,default=ROOT);args=parser.parse_args()
    result=inspect(args.storage_root,args.repo_root)
    print(dict(status=result['status'],conditions=len(result['rows']),wall_seconds=result['wall_seconds']))
