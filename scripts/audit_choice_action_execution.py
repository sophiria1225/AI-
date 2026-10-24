"""Check closed P102 public accounting against saved execution receipts, without replay."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import subprocess
import time

from choice_action_execution import execution_comparisons, source_slots, validate_plan
from matched_live_prefix import digest
from public_api_result_transport import PROTOCOL, decode_reply
from run_choice_action_execution import PLAN, PREFIX
from run_saved_action_execution import sha, write
from run_handoff_factors import ROOT

SOURCE='reports/P101_choice_context.json'
REPORT='reports/P102_choice_action_execution.json'
AUDIT='reports/P102_execution_record_audit.json'
RESULT_KEYS=('status','stdout','stdout_truncated','error','declared_complete',
             'unknown_effects','api_requests','session_usable','program_index')


def require(ok, reason):
    if not ok:raise ValueError(reason)


def count(value):return type(value) is int and value>=0


def validate_closed(plan, source, report):
    validate_plan(plan);slots=source_slots(source);rows=report['conditions']
    require(report['phase']=='P102' and report['status'] in ('complete','stopped')
            and len(rows)==36,'closed_all_36_execution_slots_required')
    require(all(report.get(k)==0 for k in ('model_generations','evaluator_calls',
            'reserved_scenarios_read','automatic_retries'))
            and all(report.get(k) is False for k in ('original_full_state_restored',
            'task_quality_measured','new_method_claim')),'unchanged_P102_scope_required')
    ended=False
    for slot,row,original in zip(slots,rows,source['rows'],strict=True):
        require(all(row.get(k)==v for k,v in slot.items()),'all_source_slot_metadata_required')
        state=row['status']
        require(state in ('complete','stopped','cleanup_or_accounting_failed',
                         'source_unavailable','not_attempted'),'closed_slot_status_required')
        require(not ended or state=='not_attempted','no_execution_after_stop_or_unattempted')
        if state in ('stopped','cleanup_or_accounting_failed','not_attempted'):ended=True
        if state=='source_unavailable':
            require(not slot['should_execute'] and not row.get('owned_bridge_pid')
                    and not row.get('typed_requests_started',0)
                    and not row.get('saved_program_executions',0),'unavailable_source_cannot_execute')
        if state in ('complete','stopped','cleanup_or_accounting_failed'):
            require(slot['should_execute'],'only_known_sources_can_execute')
        for key in ('prefix_api_requests','suffix_api_requests','typed_requests_started',
                    'transport_attempts','bridge_attempts','saved_program_executions','suffix_saved_programs'):
            require(key not in row or count(row[key]),'nonnegative_integer_cost_required')
        for key in ('active_wall_seconds','cleanup_wall_seconds','full_wall_seconds'):
            require(key not in row or isinstance(row[key],(int,float))
                    and math.isfinite(row[key]) and row[key]>=0,'finite_recorded_time_required')
        if state=='complete':
            require(row['public_prefix_matched'] is True and row['prefix_api_requests']==28
                    and len(row['prefix_programs'])==12
                    and all(p['public_prefix_matches'] is True for p in row['prefix_programs']),
                    'all_twelve_prefix_programs_must_match')
            require(row['structured_submissions']==original['structure']['tool_calls']
                    and row['saved_program_executions']==12+row['suffix_saved_programs'],
                    'original_submission_and_all_program_counts_required')
            total=28+row['suffix_api_requests']
            require(total==row['transport_attempts']==row['typed_requests_started']<=80
                    and all(count(v) for v in row['typed_status_counts'].values())
                    and sum(row['typed_status_counts'].values())==total
                    and not any(row['typed_status_counts'].get(k,0) for k in ('unknown','not_dispatched')),
                    'complete_slot_API_accounting_must_reconcile')
            require(not row['cleanup_errors'] and row['owned_bridge_absent'] is True
                    and row['python_cleanup']['container_removed'] is True
                    and row['bridge_cleanup']['graceful'] is True
                    and len(row['container_controls'])==14 and all(row['container_controls'].values()),
                    'completed_slot_cleanup_and_controls_required')
    require(report['status']!='complete' or not ended,'complete_report_cannot_hide_unattempted_slots')
    for key,expected in {
        'available_saved_outputs':sum(s['should_execute'] for s in slots),
        'completed_conditions':sum(r['status']=='complete' for r in rows),
        'unavailable_source_slots':sum(r['status']=='source_unavailable' for r in rows),
        'unattempted_execution_slots':sum(r['status']=='not_attempted' for r in rows),
        'environment_api_requests':sum(r.get('typed_requests_started',0) for r in rows),
        'saved_program_executions':sum(r.get('saved_program_executions',0) for r in rows),
    }.items():require(report.get(key)==expected,'total_mismatch:'+key)
    require(report['execution_comparisons']==execution_comparisons(rows),
            'all_12_within_and_66_cross_comparisons_required')
    return slots


def typed_status(entry):
    try:
        response=entry['response'];result=response['result']
        require(set(response)=={'ok','result'} and response['ok'] is True
                and set(result)=={'protocol','observation','declared_complete'}
                and result['protocol']==PROTOCOL and type(result['declared_complete']) is bool,
                'typed_envelope_shape')
        return decode_reply(result['observation'],entry['command']['nonce']).status
    except (KeyError,TypeError,ValueError):return 'unknown'


def inspect_private_slot(storage, plan, row, read, deadline, check_pid=True):
    folder=storage/plan['private_output']/row['id']
    if row['status'] in ('not_attempted','source_unavailable'):
        require(not folder.exists(),'unattempted_slot_has_execution_records');return
    require(folder.is_dir(),'attempted_slot_missing_records')
    progress=read(folder/'progress.json')
    require(all(progress.get(k)==v for k,v in row.items() if k!='status')
            and progress['status'] in (row['status'],'complete'),'saved_progress_disagrees')
    entries=[read(p) for p in sorted(folder.glob('bridge_*_private.json'))]
    require(len(entries)==row['bridge_attempts'],'bridge_attempt_count_disagrees')
    typed=[e for e in entries if e['command']['op']=='call_typed']
    require(sum(e['raw_request_started'] for e in typed)==row['typed_requests_started'],
            'sent_API_count_disagrees_with_bridge_receipts')
    require(dict(Counter(typed_status(e) for e in typed))==row['typed_status_counts'],
            'typed_result_counts_disagree')
    session_path=folder/'python_session/session_private.json'
    if session_path.exists():
        session=read(session_path)
        require(len(session['programs'])==row['saved_program_executions'],
                'saved_program_count_disagrees')
        require(session['status']=='closed' and session['container_removed'] is True
                and all(session.get(k)==v for k,v in row['python_cleanup'].items()),
                'closed_python_session_required')
        require(session.get('controls',{})==row.get('container_controls',{}),
                'saved_container_controls_disagree')
        for item in session['programs']:
            require(time.monotonic()<deadline,'audit_deadline')
            parent='prefix' if item['program_index']<=12 else 'programs'
            program=folder/parent/item['record_name']
            result=read(program/'result_private.json')
            require(all(result.get(k)==v for k,v in item.items() if k!='record_name'),
                    'saved_program_receipt_disagrees')
            if item['program_index']<=len(row['prefix_programs']):
                source=storage/PREFIX/'programs'/item['record_name']
                require(read(program/'input_private.json')==read(source/'input_private.json'),
                        'prefix_program_source_changed')
                original=read(source/'result_private.json')
                check=row['prefix_programs'][item['program_index']-1]
                actual={k:result.get(k) for k in RESULT_KEYS};expected={k:original.get(k) for k in RESULT_KEYS}
                require(check['actual_result_sha256']==digest(actual)
                        and check['expected_result_sha256']==digest(expected)
                        and all(check['checks'][k]==(actual[k]==expected[k]) for k in RESULT_KEYS),
                        'prefix_result_comparison_disagrees')
    else:require(row.get('saved_program_executions',0)==0,'missing_python_session_with_spent_programs')
    prefix=folder/'prefix_rows_private.json'
    if prefix.exists():
        values=read(prefix)
        require(digest(values)==row['prefix_api_trace_sha256']
                and sum(r['api_request_sent'] for r in values)==row['prefix_api_requests'],
                'prefix_request_trace_disagrees')
    suffix=folder/'suffix_rows_private.json'
    if 'suffix_execution_evidence_sha256' in row:
        values=read(suffix) if suffix.exists() else []
        sent=[r for r in values if r['api_request_sent']]
        require(digest(values)==row['suffix_execution_evidence_sha256']
                and digest([r['action'] for r in sent])==row['suffix_request_sequence_sha256']
                and len(sent)==row['suffix_api_requests']
                and dict(Counter(r['action']['name'] for r in sent))==row['suffix_API_names'],
                'suffix_execution_trace_disagrees')
    if check_pid and row.get('owned_bridge_pid'):
        probe=subprocess.run(['ps','-p',str(row['owned_bridge_pid']),'-o','pid='],
                             capture_output=True,text=True,timeout=10)
        require(probe.returncode==1 and not probe.stdout.strip(),'owned_bridge_process_present')


def audit(storage,root=ROOT):
    target=root/AUDIT
    require(not target.exists(),'preserve_existing_P102_record_audit')
    started=time.monotonic();deadline=started+180;hashes={};private_hashes={};errors=[]
    def read(path):
        require(time.monotonic()<deadline,'audit_deadline')
        base=root if path.is_relative_to(root) else storage
        require(path.resolve().is_relative_to(base.resolve()) and not path.is_symlink()
                and path.stat().st_size<=16777216,'bounded_record_path_required')
        data=path.read_bytes();rel=str(path.relative_to(base))
        (hashes if base==root else private_hashes)[rel]=sha(path)
        return ([json.loads(line) for line in data.splitlines()] if path.suffix=='.jsonl'
                else json.loads(data))
    checked=0
    try:
        plan=read(root/PLAN);source=read(root/SOURCE);report=read(root/REPORT)
        require(plan.get('execution_ready') is True,'final_execution_plan_required')
        for rel,value in plan['source_sha256'].items():
            require(sha(root/rel)==value,'frozen_source_changed:'+rel)
        for rel,value in plan['private_file_sha256'].items():
            read(storage/rel);require(private_hashes[rel]==value,'frozen_private_source_changed')
        require(report['plan_sha256']==sha(root/PLAN) and report['source_audit_sha256']==sha(root/SOURCE),
                'plan_or_generation_source_binding_disagrees')
        require(read(storage/plan['private_output']/'status.json')==report,'terminal_status_copy_disagrees')
        validate_closed(plan,source,report)
        for row in report['conditions']:
            inspect_private_slot(storage,plan,row,read,deadline);checked+=1
    except Exception as error:
        errors.append(dict(type=type(error).__name__,reason=str(error)))
    value=dict(phase='P102_record_audit',status='complete' if not errors else 'stopped',
        generated_at=datetime.now(timezone.utc).isoformat(),all_planned_slots=36,checked_slots=checked,
        audit_errors=errors,source_sha256=hashes,private_record_sha256=private_hashes,
        auditor_sha256=sha(Path(__file__)),wall_seconds=time.monotonic()-started,
        model_generations=0,environment_API_requests=0,programs_executed=0,evaluator_calls=0,
        original_full_state_verified=False,task_quality_measured=False,novel_method_claim=False,
        scope='Recorded accounting, hashes, prefix results, suffix traces, cleanup records and bridge PID absence; no replay or task evaluation.')
    write(target,value);return value


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--storage-root',type=Path,required=True)
    args=parser.parse_args();result=audit(args.storage_root.resolve())
    print({k:result[k] for k in ('status','checked_slots','audit_errors','wall_seconds')})
    raise SystemExit(0 if result['status']=='complete' else 1)
