"""Audit saved P106 receipts once and summarize both handwritten cases.

No model, AppWorld, saved program, or evaluator is executed. Reply-byte metrics
are checked against saved adapter receipts, not independently captured replies.
"""
import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import time

from audit_choice_action_execution import typed_status
from ordinary_cache_live_plan import (POLICIES, PROGRAMS, EXPECTED_API, EXPECTED_PENDING,
    EXPECTED_ORDINARY_COMPLETE_REUSES, validate_plan)


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, data):
    with path.open('x') as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')


def require(value, reason):
    if not value:
        raise ValueError(reason)


def build(storage, root):
    target = root/'reports/P106_saved_record_audit.json'
    require(not target.exists(), 'preserve_every_record_audit')
    began = time.monotonic()
    public_hashes, private_hashes = {}, {}
    checked = 0
    audit = dict(phase='P106_saved_record_audit', status='running',
        started_at=datetime.now(timezone.utc).isoformat(), audit_errors=[],
        model_generations=0, environment_API_requests=0, programs_executed=0, evaluations=0,
        original_full_state_verified=False, reply_bytes_independently_captured=False)

    def read(path, *, private=False, lines=False):
        require(time.monotonic()-began < 180, 'bounded_record_audit_deadline')
        base = storage if private else root
        require(not path.is_symlink() and path.resolve().is_relative_to(base.resolve())
                and path.stat().st_size <= 16777216, 'bounded_regular_record_required')
        (private_hashes if private else public_hashes)[str(path.relative_to(base))] = sha(path)
        return ([json.loads(line) for line in path.read_text().splitlines()] if lines
                else json.loads(path.read_text()))

    try:
        report = read(root/'reports/P106_ordinary_complete_read_cache.json')
        plan = read(root/'configs/P106_ordinary_complete_read_cache_v01.json')
        validate_plan(plan)
        require(report['status'] == 'complete' and report['all_seven_observations_equal'] is True
                and report['all_outputs_match_P105'] is True
                and report['plan_sha256'] == sha(root/'configs/P106_ordinary_complete_read_cache_v01.json'),
                'complete_fixed_P106_required')
        for rel, digest in plan['source_sha256'].items():
            require(sha(root/rel) == digest, 'frozen_source_changed:'+rel)
        base = storage/plan['private_output']
        require(read(base/'status.json', private=True) == report, 'terminal_record_copy_differs')
        require([c['policy'] for c in report['conditions']] == list(POLICIES), 'fixed_policy_order')
        require(len(report['all_program_slots']) == 14 and all(x['status'] == 'ok' for x in report['all_program_slots']),
                'all_14_successful_handwritten_slots_required')
        for condition in report['conditions']:
            policy = condition['policy']
            folder = base/policy
            require(condition['ordinary_complete_reuses'] == EXPECTED_ORDINARY_COMPLETE_REUSES[policy]
                    == len(condition['ordinary_cache_events']), 'ordinary_cache_event_count_differs')
            require(condition['status'] == 'complete' and len(condition['programs']) == 7,
                    'all_seven_program_records_required')
            require(read(folder/'progress.json', private=True) == condition, 'condition_copy_differs')
            previous_spent = 0
            for n, row in enumerate(condition['programs'], 1):
                path = folder/f'program_{n:02d}'
                evidence = read(path/'view_program_private.json', private=True)
                payload = read(path/'input_private.json', private=True)
                ordinary = read(path/'result_private.json', private=True)
                wire = read(path/'wire_private.jsonl', private=True, lines=True)
                result = evidence['result']
                require(payload['code'] == PROGRAMS[n-1] and payload['observations'] == {}
                        and payload['program_index'] == n+1, 'fixed_handwritten_input_changed')
                require(row['program_sha256'] == hashlib.sha256(PROGRAMS[n-1].encode()).hexdigest()
                        and row['private_program_receipt_sha256'] == sha(path/'view_program_private.json'),
                        'source_or_corrected_receipt_binding_differs')
                for key in ('status', 'api_requests', 'unknown_effects', 'declared_complete',
                            'stdout_truncated', 'wall_seconds'):
                    require(row[key] == result[key], 'corrected_program_metric_differs:'+key)
                for key in ('status', 'stdout', 'stdout_truncated', 'error', 'declared_complete', 'unknown_effects'):
                    require(result[key] == ordinary[key], 'underlying_program_result_differs:'+key)
                require(row['stdout_sha256'] == hashlib.sha256(result['stdout'].encode()).hexdigest(),
                        'stdout_hash_differs')
                require(row['budget'] == evidence['budget_after'] and evidence['budget_before']['spent'] == previous_spent,
                        'shared_budget_continuity_differs')
                require(evidence['budget_after']['spent']-previous_spent == row['api_requests'] == EXPECTED_API[policy][n-1]
                        and row['budget']['pending'] == EXPECTED_PENDING[policy][n-1], 'API_or_pending_count_differs')
                previous_spent = row['budget']['spent']
                controls = [x for x in wire if x.get('kind') == 'api']
                require(all(x['app'] == '__harness_views__' and x['api'] == 'control' for x in controls),
                        'unexpected_control_boundary')
                require(len(controls) == evidence['control_requests'],
                        'control_request_count_differs')
                require(sum(len(json.dumps(x['arguments']['packet'], allow_nan=False).encode()) for x in controls)
                        == evidence['control_request_bytes'], 'control_request_bytes_differs')
                for key in ('control_requests', 'control_request_bytes', 'control_reply_bytes'):
                    require(row[key] == evidence[key], 'control_receipt_metric_differs:'+key)
                require(row['client_setup_included'] == (n == 1) == (evidence['setup'] is not None),
                        'one_bootstrap_per_world_required')
                checked += 1
            records = [read(p, private=True) for p in sorted(folder.glob('record_*_private.json'))]
            require(all(x['api_request_sent'] and not x.get('effects_unknown', False) for x in records),
                    'only_confirmed_API_records_required')
            require(len(records) == condition['budget']['spent'] == condition['api_rows_recorded']
                    == condition['typed_requests_started'] == sum(EXPECTED_API[policy]), 'API_totals_disagree')
            require(dict(Counter(x['action']['name'] for x in records)) == condition['api_names'], 'API_inventory_differs')
            require(dict(Counter(x['api_execution']['status'] for x in records)) == condition['typed_status_counts'],
                    'typed_record_statuses_differ')
            bridge = [read(p, private=True) for p in sorted(folder.glob('bridge_*_private.json'))]
            typed = [x for x in bridge if x['command']['op'] == 'call_typed']
            require(len(bridge) == condition['bridge_attempts'] and sum(x['raw_request_started'] for x in typed)
                    == condition['typed_requests_started'], 'bridge_dispatch_counts_differ')
            require(dict(Counter(typed_status(x) for x in typed)) == condition['typed_status_counts'],
                    'raw_typed_statuses_differ')
            session = read(folder/'python_session/session_private.json', private=True)
            require(session == condition['python_cleanup'] and session['container_removed'] is True
                    and session['status'] == 'closed' and len(session['programs']) == 8,
                    'closed_session_and_eight_executions_required')
            require(not condition['cleanup_errors'] and condition['bridge_cleanup']['graceful']
                    and len(condition['container_controls']) == 14 and all(condition['container_controls'].values()),
                    'cleanup_and_isolation_receipts_required')
            absent = subprocess.run(['ps', '-p', str(condition['owned_bridge_pid']), '-o', 'pid='],
                                    capture_output=True, text=True, timeout=10)
            require(absent.returncode == 1 and not absent.stdout.strip(), 'owned_bridge_PID_present')
        require(report['environment_API_requests'] == sum(c['budget']['spent'] for c in report['conditions']) == 24,
                'total_API_disagrees')
        observations = [[x['stdout_sha256'] for x in c['programs']] for c in report['conditions']]
        require(all(x == observations[0] for x in observations), 'all_seven_stdout_hashes_must_match')
        previous = read(root/'reports/P105_coalesced_read_live.json')
        previous_stdout = [x['stdout_sha256'] for x in previous['conditions'][0]['programs']]
        require(all(x == previous_stdout for x in observations), 'P105_stdout_hashes_must_match')
        audit['status'] = 'complete'
    except Exception as error:
        audit.update(status='stopped', audit_errors=[dict(type=type(error).__name__, reason=str(error))])
    finally:
        audit.update(checked_programs=checked, source_sha256=public_hashes, private_record_sha256=private_hashes,
            auditor_sha256=sha(Path(__file__)), wall_seconds=time.monotonic()-began)
        write(target, audit)
    require(audit['status'] == 'complete', 'record_audit_stopped_no_retry')
    output = root/'materials/20261025_p106_results'
    output.mkdir(parents=True, exist_ok=False)
    rows = [dict(policy=c['policy'], **row) for c in report['conditions'] for row in c['programs']]
    summary = []
    for c in report['conditions']:
        summary.append(dict(policy=c['policy'], environment_API_requests=c['budget']['spent'],
            ordinary_complete_reuses=c['ordinary_complete_reuses'],
            pending=c['budget']['pending'], exact_reuses=c['exact_reuses'], coalesced_reuses=c['coalesced_reuses'],
            materialization_cache_reuses=c['materialization_cache_reuses'],
            control_requests=sum(x['control_requests'] for x in c['programs']),
            control_request_bytes=sum(x['control_request_bytes'] for x in c['programs']),
            control_reply_bytes=sum(x['control_reply_bytes'] for x in c['programs']),
            full_wall_seconds=c['full_wall_seconds'], cleanup_wall_seconds=c['cleanup_wall_seconds']))
    for filename, values in [('all_14_programs.csv', rows), ('all_2_conditions.csv', summary)]:
        with (output/filename).open('x', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(values[0]))
            writer.writeheader()
            for row in values:
                writer.writerow({k:json.dumps(v, sort_keys=True) if isinstance(v, dict) else v for k,v in row.items()})
    write(output/'summary.json', dict(conditions=summary, all_seven_observations_equal=True,
        environment_API_requests=24, handwritten_programs=14, bootstrap_programs=2,
        model_generations=0, evaluations=0, task_quality_measured=False, novel_method_claim=False,
        complete_response_cache_covers_ordinary_target_call_in_both_policies=True,
        equal_API_count_in_this_handwritten_sequence=True))
    write(output/'build_manifest.json', dict(created_at=datetime.now(timezone.utc).isoformat(),
        builder_sha256=sha(Path(__file__)), source_report_sha256=sha(root/'reports/P106_ordinary_complete_read_cache.json'),
        audit_sha256=sha(target), public_artifact_sha256={p.name:sha(p) for p in output.iterdir() if p.is_file()},
        program_or_API_reexecution=False, manuscript_changed=False))
    print(json.dumps(dict(audit_status=audit['status'], checked_programs=checked,
                         private_records=len(private_hashes), conditions=summary)))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo-root', type=Path, required=True)
    parser.add_argument('--storage-root', type=Path, required=True)
    args = parser.parse_args()
    build(args.storage_root.resolve(), args.repo_root.resolve())
