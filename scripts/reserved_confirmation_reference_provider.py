"""Finite, explicitly invoked provider for the twelve private initial references.

No CLI or import-time actions. Future use requires caller-authenticated full12
inputs, scientific authorization and a frozen protocol/source manifest BEFORE
task initialization. The authorization digests below bind that caller assertion;
they do not authenticate it or grant eligibility. Freshness checks are namespace
absence and fresh owned bridge instances, not a proof about underlying databases.

All output is PRIVATE: bridge replies include task/account data. No model,
native counting, task API, evaluator or generated program is called here. World
initialization/close are real actions only when collect_references is invoked.
Python/OS process creation, filesystem operations and scheduling are not hard
real-time; request and process waits are bounded, overruns fail closed. A process
still alive after a kill deadline is recorded unknown and requires owner action.
"""
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
import time

from preflight_public_api_live import RecordedBridge
from public_api_result_transport import TypedBridgeProcess
from reserved_confirmation_initial_state import (
    initialization_requests, bind_reference_initial_states, digest, _public,
)


def _require(ok, label):
    if not ok:
        raise ValueError(label)


def _write(path, value):
    # Exclusive artifacts; never overwrite another attempt or its failed receipt.
    with path.open('x') as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write('\n')
        handle.flush()


def authorization_inputs(schedule, *, namespace, world_seed, setup_seconds,
                         cleanup_seconds, total_lease_seconds):
    """Pure digest input for the external caller's explicit authorization."""
    return dict(schedule_sha256=digest(schedule), namespace=namespace, world_seed=world_seed,
                setup_seconds=setup_seconds, cleanup_seconds=cleanup_seconds,
                total_lease_seconds=total_lease_seconds)


def _close_owned(raw, recorded, deadline, clock):
    """Only the owned process handle; every request/wait receives time remaining."""
    started = clock(); operations = []; graceful = False; resource_close_failed = False
    process = getattr(raw, 'process', None)
    def alive():
        return process is not None and process.poll() is None
    def remaining():
        return max(0.0, deadline-clock())
    def wait(fraction):
        limit = remaining()*fraction
        if limit > 0 and alive():
            try:
                process.wait(timeout=limit)
            except subprocess.TimeoutExpired:
                operations.append('wait_timeout')
    try:
        if alive() and not getattr(raw, 'failed', True) and recorded is not None and remaining()>0:
            try:
                # Leave two thirds of cleanup time for exit/termination/escalation.
                raw.timeout_seconds = min(90.0, remaining()/3)
                recorded.deadline = clock()+raw.timeout_seconds
                response = recorded.request({'op':'close'})
                wait(1/3)
                graceful = response == {'ok':True,'result':{'closed':True}} and process.poll() == 0
                operations.append('graceful_close_confirmed' if graceful else 'close_not_confirmed')
            except BaseException as error:
                operations.append('close_error:'+type(error).__name__)
            if not graceful:
                raw.failed = True
        if alive():
            try:
                process.terminate(); operations.append('terminate_owned_process'); wait(1/2)
            except BaseException as error:
                operations.append('terminate_error:'+type(error).__name__)
        if alive():
            try:
                process.kill(); operations.append('kill_owned_process'); wait(1)
            except BaseException as error:
                operations.append('kill_error:'+type(error).__name__)
    finally:
        # Also handles partial TypedBridgeProcess construction after Popen.
        for stream in [getattr(raw,'selector',None),
                       getattr(process,'stdin',None),getattr(process,'stdout',None),
                       getattr(raw,'errors',None)]:
            if stream is not None:
                try:stream.close()
                except BaseException as error:
                    resource_close_failed = True
                    operations.append('resource_close_error:'+type(error).__name__)
        graceful = graceful and not resource_close_failed
        status = dict(process_stopped=not alive(), graceful=graceful,
                      transport_failed=bool(getattr(raw,'failed',True) or not graceful))
        raw.closed = True; raw.close_status = status
    return status, dict(operations=operations,wall_seconds=clock()-started,
        within_deadline=clock()<=deadline,owned_pid=getattr(process,'pid',None),
        exit_code=process.poll() if process is not None else None)


def collect_references(schedule, reservation, *, baseline, candidate, seed, budgets,
                       namespace, world_seed, authorization, python, appworld_root,
                       output_dir, setup_seconds, cleanup_seconds, total_lease_seconds,
                       stop=lambda:False, clock=time.monotonic):
    """Initialize/close all12 in order; stop on the first failure, never retry.

    The supplied Python/installed AppWorld and fresh output namespaces must be
    authenticated by the external frozen protocol. The caller owns publication,
    later 24-cell preflight/worker integration and cleanup escalation if unknown.
    Returns a PRIVATE terminal record. A bundle file may survive finalization
    failure: use it only with terminal status complete AND bundle_accepted true,
    within_total_lease true, and all_owned_processes_stopped true. Existence of
    the candidate file alone never authorizes it.
    """
    kwargs=dict(baseline=baseline,candidate=candidate,seed=seed,budgets=budgets,
                namespace=namespace,world_seed=world_seed)
    commands=initialization_requests(schedule,reservation,**kwargs)
    for value in (setup_seconds,cleanup_seconds,total_lease_seconds):
        _require(type(value) in (int,float) and math.isfinite(value) and value>0,'finite_provider_limits_required')
    _require(setup_seconds<=budgets['max_setup_seconds'] and cleanup_seconds<=budgets['max_cleanup_seconds'],
             'provider_limits_exceed_explicit_cell_limits')
    _require(total_lease_seconds>=12*(setup_seconds+cleanup_seconds),'full12_provider_lease_required')
    expected=authorization_inputs(schedule,namespace=namespace,world_seed=world_seed,
        setup_seconds=setup_seconds,cleanup_seconds=cleanup_seconds,total_lease_seconds=total_lease_seconds)
    _require(type(authorization) is dict and set(authorization)==
        {'authorized','frozen_protocol_sha256','frozen_source_manifest_sha256','inputs_sha256'} and
        authorization['authorized'] is True and authorization['inputs_sha256']==digest(expected) and
        all(type(authorization[k]) is str and re.fullmatch('[a-f0-9]{64}',authorization[k])
            for k in ('frozen_protocol_sha256','frozen_source_manifest_sha256')),
        'caller_authorized_frozen_protocol_and_exact_inputs_required')
    out=Path(output_dir); appworld=Path(appworld_root)
    _require(not out.exists() and not out.is_symlink(),'preserve_existing_provider_attempt')
    # Check even the later cell namespaces before acquiring the first task body.
    worlds=appworld/'experiments/outputs'
    _require(appworld.is_dir() and worlds.is_dir(),'existing_authenticated_world_root_required')
    _require(all(not (worlds/c['experiment']).exists() and not (worlds/c['experiment']).is_symlink()
                 for group in commands.values() for c in group),'all_reference_and_cell_namespaces_must_be_new')
    out.mkdir(parents=False,exist_ok=False)
    started=clock(); deadline=started+total_lease_seconds
    record=dict(scope='private_full12_initial_reference_provider',status='running',
        authorization=deepcopy(authorization),authorization_inputs=expected,automatic_init_retries=0,
        rows=[dict(ordinal=n,task_id=c['task_id'],experiment=c['experiment'],status='not_run',
                   initialization_status=None,owned_pid=None,cleanup=None)
              for n,c in enumerate(commands['reference'],1)],bundle_canonical_sha256=None,bundle_accepted=False,
        model_API_native_evaluator_calls=0,task_bodies_are_private=True)
    _write(out/'provider_start_private.json',record)
    receipts=[]
    try:
        for row,command in zip(record['rows'],commands['reference']):
            if stop():raise InterruptedError('explicit_provider_stop')
            if deadline-clock()<setup_seconds+cleanup_seconds:
                raise TimeoutError('insufficient_remaining_lease_for_full_setup_and_cleanup')
            folder=out/f'reference_{row["ordinal"]:02d}';folder.mkdir(exist_ok=False)
            raw=recorded=None; failed=None; entry_started=clock(); init=None
            row['status']='started'
            try:
                # Hold the object before __init__: late constructor failures may own a child.
                raw=TypedBridgeProcess.__new__(TypedBridgeProcess)
                TypedBridgeProcess.__init__(raw,python,appworld,folder,timeout_seconds=min(90,setup_seconds))
                row['owned_pid']=getattr(raw.process,'pid',None)
                recorded=RecordedBridge(raw,folder,entry_started+setup_seconds,clock=clock,stop=stop)
                recorded.request(command)
                init=deepcopy(recorded.attempts[0])
                _public(init,command,setup_seconds)
                if clock()>entry_started+setup_seconds:raise TimeoutError('setup_elapsed_limit')
            except BaseException as error:
                failed=type(error).__name__
            finally:
                attempts=recorded.attempts if recorded is not None else []
                first=attempts[0] if attempts else {}
                row['initialization_status']=('response_recorded' if 'response' in first else
                    'request_started_terminal_unknown' if first.get('raw_request_started') is True else 'not_dispatched')
                row['setup_wall_seconds']=clock()-entry_started
                if raw is not None:
                    row['cleanup'],row['cleanup_detail']=_close_owned(raw,recorded,
                        min(deadline,clock()+cleanup_seconds),clock)
                    row['owned_pid']=row['cleanup_detail']['owned_pid']
                else:
                    row['cleanup']={'process_stopped':True,'graceful':False,'transport_failed':True}
                if (row['cleanup']!={'process_stopped':True,'graceful':True,'transport_failed':False}
                        or not row.get('cleanup_detail',{}).get('within_deadline',False)):
                    failed=failed or 'CleanupNotConfirmed'
                row['status']='failed_no_retry' if failed else 'complete'
                row['error_type']=failed
                _write(folder/'reference_end_private.json',row)
            if failed:raise RuntimeError('reference_failed_no_retry')
            receipts.append(dict(initialization=init,cleanup=deepcopy(row['cleanup'])))
        if stop():raise InterruptedError('explicit_provider_stop')
        if clock()>deadline:raise TimeoutError('provider_total_lease_expired')
        bundle=bind_reference_initial_states(schedule,reservation,receipts,**kwargs)
        _write(out/'initial_states_private.json',bundle)
        record['bundle_canonical_sha256']=digest(bundle)
        record['bundle_file_sha256']=hashlib.sha256((out/'initial_states_private.json').read_bytes()).hexdigest()
        if stop():raise InterruptedError('explicit_provider_stop_during_finalization')
        if clock()>deadline:raise TimeoutError('provider_lease_expired_during_finalization')
        record['bundle_accepted']=True
        record['status']='complete'
    except BaseException as error:
        record['status']='failed_no_retry';record['error_type']=type(error).__name__
    record['wall_seconds']=clock()-started
    record['within_total_lease']=clock()<=deadline
    record['all_owned_processes_stopped']=all(
        (r['status']=='not_run' and r['cleanup'] is None) or
        (type(r['cleanup']) is dict and r['cleanup'].get('process_stopped') is True)
        for r in record['rows'])
    if record['status']=='complete' and not record['within_total_lease']:
        record.update(status='failed_no_retry',error_type='ProviderLeaseExpired',bundle_accepted=False)
    _write(out/'provider_end_private.json',record)
    return record
