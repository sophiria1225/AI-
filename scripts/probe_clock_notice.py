"""Replay twelve fixed model inputs without executing any generated action."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import signal
import time

from api_error_comparison import ARMS
from clock_notice_replay import LEVELS, digest, equality_summary, output_fingerprints, requests_for, reserve_tokens, schedule
from inference_cache_control import cache_measurement
from inspect_api_error_content_divergence import canonical_transport_references
from inspect_api_error_divergence import without_wall_snapshot
from inspect_input_exposure import check_resume, frozen_sources
from local_llama import parse_response, post
from probe_inference_cache import live_identity
from run_context_comparison import write_json
from run_handoff_factors import ROOT, read, sha
from run_reasoning_history_comparison import wait_idle

PLAN = 'configs/P79_clock_notice_replay_v01.json'
PREFLIGHT = 'reports/P79_initial_checks.json'


def sources(storage, root):
    plan = read(root / PLAN)
    fixed = {'phase': 'P79', 'batch_id': 'P79_clock_notice_v01', 'max_calls': 12,
        'max_total_tokens': 150000, 'max_output_tokens': 4096, 'seed': 56,
        'call_timeout_seconds': 480, 'max_wall_seconds': 7200,
        'max_preflight_seconds': 300, 'max_idle_seconds': 60,
        'server_max_lifetime_seconds': 9000, 'cache_prompt': False,
        'automatic_retries': 0, 'environment_api_requests': 0, 'evaluations': 0,
        'reserved_scenarios_read': 0, 'novel_method_claim': False}
    if any(plan.get(k) != v for k, v in fixed.items()) or plan['schedule'] != schedule():
        raise ValueError('fixed_P79_scope_or_budget_changed')
    for name, expected in plan['source_sha256'].items():
        if sha(root / name) != expected: raise ValueError('fixed_source_changed:' + name)
    closed = read(root / 'reports/P78_results_provenance_20261023.json')
    for name, expected in closed['source_sha256'].items():
        if sha(root / name) != expected: raise ValueError('closed_P78_source_changed:' + name)
    comparison = read(root / 'reports/P78_comparison.json')
    divergence = read(root / 'reports/P78_input_content_divergence.json')
    if (comparison['audit_errors'] or not comparison['all_eight_complete_with_known_usage']
            or divergence['comparison_sha256'] != sha(root / 'reports/P78_comparison.json')):
        raise ValueError('closed_all_eight_P78_conditions_required')
    eligible = [p for p in divergence['pairs'] if p.get('divergence_before_any_API_exception') is True
                and p.get('requests_equal_after_transport_ids_and_wall_snapshot_normalization') is True
                and p.get('requests_equal_after_transport_id_renaming') is False]
    if len(eligible) != 2 or [p['task_id'] for p in eligible] != [c['task_id'] for c in plan['cases']]:
        raise ValueError('use_all_and_only_fixed_preexception_clock_pairs')
    raw = read(root / 'reports/P78_input_divergence.json')
    requests = []
    for case, pair in zip(plan['cases'], eligible, strict=True):
        if pair['first_unmatched_call'] != 6 or case['source_call'] != 'call_006':
            raise ValueError('fixed_first_content_difference_changed')
        records = []
        for arm in ARMS:
            row = next(r for r in comparison['rows'] if r['task_id'] == case['task_id'] and r['arm'] == arm)
            if row['run_id'] != case['source_run' if arm == ARMS[0] else 'other_run']:
                raise ValueError('fixed_source_run_correspondence_changed')
            folder = storage / 'records/context_pilot' / row['run_id']
            for name in ('request', 'response'):
                path = folder / 'call_006' / (name + '.json')
                expected = next(c for c in row['request_checks'] if c['call_id'] == 'call_006')[name + '_sha256']
                if sha(path) != expected or plan['source_record_sha256'][str(path.relative_to(storage))] != expected:
                    raise ValueError('audited_saved_record_changed')
            signals = folder / 'budget_signals.json'
            if sha(signals) != raw['budget_signal_sha256'][row['run_id']]:
                raise ValueError('audited_budget_signals_changed')
            if sha(signals) != plan['source_record_sha256'][str(signals.relative_to(storage))]:
                raise ValueError('fixed_budget_signals_changed')
            signal_row = next(s for s in read(signals) if s['next_call_id'] == 'call_006' and s['model_attempted'])
            request, response = read(folder / 'call_006/request.json'), read(folder / 'call_006/response.json')
            state = signal_row['state']
            without_wall_snapshot(request, state)
            if response['input_tokens'] != case['expected_input_tokens']:
                raise ValueError('source_input_count_changed')
            records.append((request, state))
        a, b = records
        if (canonical_transport_references(without_wall_snapshot(*a)) !=
                canonical_transport_references(without_wall_snapshot(*b))
                or b[1]['remaining']['wall_seconds_at_snapshot'] != a[1]['remaining']['wall_seconds_at_snapshot'] + 1
                or a[1]['remaining']['wall_seconds_at_snapshot'] != case['original_wall_seconds']):
            raise ValueError('only_corresponding_transport_ids_and_one_second_may_differ')
        prepared = requests_for(*a)
        if {k: digest(v) for k, v in prepared.items()} != case['condition_payload_sha256']:
            raise ValueError('fixed_derived_payload_changed')
        requests.append(prepared)
    return plan, read(root / 'configs/P29_stateful_code_v01.json'), requests


def frozen_hashes(root, plan):
    paths = list((root / 'scripts').glob('*.py')) + list((root / 'tests').glob('test_*.py'))
    paths += [root / p for p in (PLAN, 'docs/experiments/P79_clock_notice_replay.md', *plan['source_sha256'])]
    return {str(p.relative_to(root)): sha(p) for p in sorted(set(paths))}


def check_stop(storage):
    check_resume(storage)
    if (storage / '.runtime/P79.stop').exists(): raise InterruptedError('P79_user_stop')


def preflight(storage, root):
    plan, original, requests = sources(storage, root)
    target = root / PREFLIGHT
    out = storage / 'records/context_pilot/P79_preflight_v01'
    if out.exists() or target.exists(): raise FileExistsError('preserve_P79_preflight_attempts')
    hashes = frozen_hashes(root, plan)
    commit = frozen_sources(root, tuple(hashes))
    check_stop(storage)
    identity, end = live_identity(storage, original, 360)
    out.mkdir(parents=True)
    began = time.monotonic()
    result = {'phase': 'P79_preflight', 'status': 'running', 'rows': [], 'git_commit': commit,
        'source_sha256': hashes, 'model_identity': identity, 'server_lease_end': end,
        'research_resume': check_resume(storage), 'input_count_requests': 0,
        'model_generations': 0, 'environment_api_requests': 0, 'evaluations': 0,
        'reserved_scenarios_read': 0}
    def save():
        result['wall_seconds'] = time.monotonic() - began
        write_json(out / 'status.json', result)
    try:
        save()
        for index, prepared in enumerate(requests):
            for level in LEVELS:
                check_stop(storage)
                remaining = plan['max_preflight_seconds'] - (time.monotonic() - began)
                if remaining <= 0: raise TimeoutError('P79_preflight_budget')
                row = {'case_index': index, 'level': level, 'payload_sha256': digest(prepared[level]), 'status': 'count_requested'}
                result['rows'].append(row); result['input_count_requests'] += 1; save()
                count_started = time.monotonic()
                counted = post({'base_url': 'http://127.0.0.1:8011'}, '/v1/chat/completions/input_tokens',
                               prepared[level], min(30, remaining))
                row.update(input_tokens=counted.get('input_tokens'), count_wall_seconds=time.monotonic() - count_started)
                if row['input_tokens'] != plan['cases'][index]['expected_input_tokens']:
                    raise ValueError('P79_actual_input_count_differs_from_fixed_source')
                row['status'] = 'counted'; save()
        result['reserved_total_tokens'] = reserve_tokens([r['input_tokens'] for r in result['rows']])
        result['status'] = 'complete'
    except Exception as error:
        result.update(status='stopped', error_type=type(error).__name__)
        (out / 'error_private.txt').write_text(str(error))
    finally:
        save(); write_json(target, result)
    print({k: result.get(k) for k in ('status', 'input_count_requests', 'reserved_total_tokens', 'wall_seconds')})
    return 0 if result['status'] == 'complete' else 1


def run(storage, root):
    plan, original, requests = sources(storage, root)
    activation = read(root / PREFLIGHT)
    if activation['status'] != 'complete' or activation['source_sha256'] != frozen_hashes(root, plan):
        raise ValueError('successful_unchanged_P79_preflight_required')
    identity, end = live_identity(storage, original, plan['max_wall_seconds'] + 90)
    if identity != activation['model_identity']: raise ValueError('same_owned_runtime_required')
    out = storage / 'records/context_pilot' / plan['batch_id']
    if out.exists(): raise FileExistsError('preserve_P79_generation_attempts')
    out.mkdir(parents=True)
    write_json(out / 'plan.json', plan); write_json(out / 'preflight.json', activation)
    started = time.monotonic()
    rows = []
    state = {'phase': 'P79', 'status': 'running', 'active': None, 'rows': rows,
        'git_commit': activation['git_commit'], 'source_sha256': activation['source_sha256'],
        'source_record_sha256': plan['source_record_sha256'], 'model_identity': identity,
        'server_lease_end': end, 'started_at': datetime.now(timezone.utc).isoformat(),
        'environment_api_requests': 0, 'generated_programs_executed': 0, 'evaluations': 0,
        'reserved_scenarios_read': 0, 'automatic_retries': 0, 'known_total_tokens': 0,
        'unknown_usage_calls': 0}
    def save():
        state['wall_seconds'] = time.monotonic() - started
        state['model_calls_attempted'] = len(rows)
        write_json(out / 'status.json', state)
    try:
        save()
        for item in schedule():
            check_stop(storage)
            remaining = plan['max_wall_seconds'] - (time.monotonic() - started)
            if remaining < plan['call_timeout_seconds'] + 75: raise TimeoutError('insufficient_full_call_and_idle_budget')
            current, _ = live_identity(storage, original, plan['call_timeout_seconds'] + 75)
            if current != identity: raise ValueError('runtime_identity_changed')
            count = plan['cases'][item['case_index']]['expected_input_tokens']
            if state['known_total_tokens'] + count + plan['max_output_tokens'] > plan['max_total_tokens']:
                raise ValueError('P79_token_budget')
            payload = requests[item['case_index']][item['level']]
            if digest(payload) != plan['cases'][item['case_index']]['condition_payload_sha256'][item['level']]:
                raise ValueError('payload_changed_after_preflight')
            folder = out / item['id']; folder.mkdir()
            write_json(folder / 'request.json', payload)
            state['active'] = item['id']
            row = {**item, 'status': 'attempting', 'input_tokens': None, 'output_tokens': None,
                   'request_sha256': sha(folder / 'request.json'), 'payload_sha256': digest(payload),
                   **output_fingerprints({'status': 'error'})}
            rows.append(row); save()
            record = {'status': 'error', 'input_tokens': None, 'output_tokens': None}
            began = time.monotonic()
            signal.alarm(plan['call_timeout_seconds'])
            try:
                raw = post({'base_url': 'http://127.0.0.1:8011'}, '/v1/chat/completions', payload, plan['call_timeout_seconds'])
                write_json(folder / 'raw_response.json', raw)
                record.update(parse_response(raw))
            except Exception as error:
                record['error_type'] = type(error).__name__
                (folder / 'error_private.txt').write_text(str(error))
            finally:
                signal.alarm(0)
                record['wall_seconds'] = time.monotonic() - began
                write_json(folder / 'response.json', record)
            row.update({k: record.get(k) for k in ('status', 'input_tokens', 'output_tokens', 'done_reason', 'wall_seconds')})
            row['response_sha256'] = sha(folder / 'response.json')
            if record['status'] != 'ok':
                state['unknown_usage_calls'] += 1; save()
                raise ValueError('unknown_terminal_usage_no_replacement')
            state['known_total_tokens'] += record['input_tokens'] + record['output_tokens']
            save()
            if record['output_tokens'] > plan['max_output_tokens'] or state['known_total_tokens'] > plan['max_total_tokens']:
                raise ValueError('observed_generation_exceeded_reserved_budget')
            row.update(output_fingerprints(record))
            row['cache'] = cache_measurement('cold_1', record, count)
            if not row['cache']['state_confirmed']: raise ValueError('input_reuse_detected')
            row['idle'] = wait_idle(storage, original, identity, plan['max_idle_seconds'])
            save()
            if not row['idle']['one_slot_idle']: raise ValueError('idle_not_confirmed')
            print({k: row[k] for k in ('id', 'case_index', 'level', 'status', 'input_tokens', 'output_tokens', 'done_reason')}, flush=True)
        state['status'] = 'complete'
    except Exception as error:
        state.update(status='stopped', error_type=type(error).__name__)
        (out / 'error_private.txt').write_text(str(error))
    finally:
        signal.alarm(0)
        state['active'] = None
        state['equality_summary'] = equality_summary(rows)
        state['finished_at'] = datetime.now(timezone.utc).isoformat()
        save()
    return 0 if state['status'] == 'complete' else 1


def interrupt(*_):
    raise InterruptedError('bounded_P79_generation_interrupted')


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--storage-root', type=Path, required=True)
    p.add_argument('--repo-root', type=Path, default=ROOT)
    p.add_argument('--preflight', action='store_true')
    a = p.parse_args()
    for sig in (signal.SIGALRM, signal.SIGTERM, signal.SIGINT): signal.signal(sig, interrupt)
    raise SystemExit((preflight if a.preflight else run)(a.storage_root.resolve(), a.repo_root.resolve()))
