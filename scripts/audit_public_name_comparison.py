"""Reconcile all P64 records without models, APIs, or private evaluation details."""
import argparse
from collections import Counter
import json
import os
from pathlib import Path
import time

from appworld_native_tools import NativeCatalog
from audit_ordinary_continuation import stream_receipt
from local_llama import parse_response
from public_name_catalog import PublicNameCatalog
from public_name_comparison import PLAN, interface, sources
from run_context_comparison import write_json
from run_handoff_factors import ROOT, read, sha


def clock_observed(observation):
    try: value = json.loads(observation.get('observation', ''))
    except (ValueError, TypeError): return False
    return (isinstance(value, dict) and isinstance(value.get('date'), str)
            and isinstance(value.get('time'), str))


def audit(storage, frozen):
    began = time.monotonic(); errors = []; checks = 0
    def check(condition, label):
        nonlocal checks
        checks += 1
        if not condition: errors.append(label)
    plan, original, tasks, tools = sources(storage)
    report_path = frozen / 'reports/P64_public_name_comparison.json'; report = read(report_path)
    directory = storage / 'records/context_pilot/P64_pipeline_v01'
    pipeline = read(directory / 'status.json'); server = read(directory / 'server_final.json')
    check(report['status'] in ('complete', 'stopped') and pipeline['status'] in ('complete', 'stopped'), 'processes not closed')
    check(report['git_commit'] == pipeline['git_commit'], 'fixed commit differs')
    check(report['plan_sha256'] == sha(ROOT / PLAN), 'fixed plan differs')
    for name, digest in report['code_sha256'].items():
        check(sha(frozen / name) == digest, 'frozen code differs: ' + name)
    check([[r['task_id'], r['arm'], r['run_id']] for r in report['rows']] == plan['run_order'], 'planned order differs')
    check(server['status'] == 'stopped' and pipeline.get('server_stopped'), 'owned server not stopped')
    live = []
    for pid in (server.get('pid'), server.get('supervisor_pid')):
        if pid is None: continue
        try: os.kill(pid, 0); live.append(pid)
        except ProcessLookupError: pass
    check(not live, 'owned server processes remain')
    totals = Counter(); rows = []
    for reported in report['rows']:
        rid, tid, arm = (reported[k] for k in ('run_id', 'task_id', 'arm'))
        trial = storage / 'records/context_pilot' / rid
        row = {k: reported[k] for k in ('run_id', 'task_id', 'arm', 'status')}
        if reported['status'] == 'not_run':
            check(not trial.exists(), rid + ': unreported attempt'); rows.append(row); continue
        summary, usage, events, spans = [read(trial / (name + '.json')) for name in ('summary', 'usage', 'events', 'spans')]
        admissions = read(trial / 'admissions.json') if (trial / 'admissions.json').exists() else []
        check(read(trial / 'comparison_plan.json') == plan, rid + ': comparison plan differs')
        check(summary['model_calls'] == len(usage) <= plan['max_calls'], rid + ': generation budget/count')
        check(sum(a.get('model_request_started', False) for a in admissions) == len(usage), rid + ': missing model attempt')
        check(set(spans) == {e['span_id'] for e in events} and len(events) == len(spans), rid + ': unaccounted/repeated events')
        check(summary['api_requests'] == sum(e['api_request_sent'] for e in events) <= plan['api_budget_by_task'][tid], rid + ': API budget/count')
        check(summary['unknown_effect_requests'] == sum(e['api_request_sent'] and bool(e['effects_unknown']) for e in events), rid + ': unknown effects')
        if usage:
            check(summary['setup']['status'] == 'matched_public_task_start', rid + ': generation before verified start')
        if summary['setup']['status'] == 'matched_public_task_start':
            check(read(trial / 'public_task.json') == tasks[tid]['public_task'], rid + ': public task differs')
            check(summary['setup']['initial_database_hashes'] == tasks[tid]['initial_database_hashes'], rid + ': initial databases differ')
        config = {**original, 'max_api_requests': plan['api_budget_by_task'][tid]}
        prompt, definitions = interface(arm, config)
        catalog = NativeCatalog(tools) if arm == 'documented' else PublicNameCatalog(tools)
        api_counts = Counter(); clock_ids = []; rejected_clock = 0; programs = []; after_completion = False
        for event in events:
            span = spans[event['span_id']]; action = span.get('action') or {}; name = action.get('name')
            if event['api_request_sent']:
                check(not after_completion, rid + ': API sent after completion')
                try: catalog.decode(action); valid = True
                except (ValueError, KeyError, TypeError): valid = False
                check(valid, rid + ': sent API violates admission')
                api_counts[name] += 1
                if name == 'phone__get_current_date_and_time' and clock_observed(span['observation']):
                    clock_ids.append({'call_id': event['call'], 'span_id': event['span_id']})
                after_completion |= bool(span['observation'].get('declared_complete'))
            elif event['stage'] == 'python_api' and name == 'phone__get_current_date_and_time':
                rejected_clock += 1
            check(all(n in catalog.catalog for n in event['new_tools']), rid + ': unknown schema exposed')
            catalog.visible.update(event['new_tools'])
            if name == 'run_python':
                programs.append({'call_id': event['call'], 'status': span['observation'].get('status'),
                    'error_present': bool(span['observation'].get('error'))})
        measured = []; amounts = Counter()
        for n, call in enumerate(usage):
            cid = call['id']; folder = trial / cid
            response, request = read(folder / 'response.json'), read(folder / 'request.json')
            if (folder / 'wire_private.sse').exists():
                receipt, failure = stream_receipt(folder / 'wire_private.sse'); decoded = receipt.summary()
                is_known = decoded['terminal_usage_received'] and failure is None
            else:
                receipt = None; decoded = {'input_tokens': None, 'output_tokens': None, 'message_ready': False}
                is_known = False
            check(is_known == call['usage_known'], rid + '/' + cid + ': usage classification')
            check(call['status'] == response['status'], rid + '/' + cid + ': status differs')
            check(request['seed'] == plan['seed']+n and request['cache_prompt'] == (n != 0), rid + '/' + cid + ': seed/cache policy')
            check(request['max_tokens'] == plan['max_output_tokens'], rid + '/' + cid + ': output cap')
            check(request['messages'][0] == {'role': 'system', 'content': prompt} and request['tools'] == definitions, rid + '/' + cid + ': capability guidance/tools')
            if n == 0:
                check(len(request['messages']) == 2 and json.loads(request['messages'][1]['content']) == {'task': tasks[tid]['public_task']}, rid + ': not a fresh public input')
            if is_known:
                for key in ('input_tokens', 'output_tokens'):
                    check(call[key] == response[key] == decoded[key], rid + '/' + cid + ': ' + key)
                    amounts[key] += decoded[key]
                check(decoded['input_tokens'] == call['predicted_input_tokens'], rid + '/' + cid + ': input reservation')
                check(decoded['output_tokens'] <= plan['max_output_tokens'], rid + '/' + cid + ': output reservation')
            else: amounts['unknown_usage_calls'] += 1
            if response['status'] == 'ok':
                check(is_known and decoded['message_ready'], rid + '/' + cid + ': incomplete stream executed')
                parsed = parse_response(receipt.final_response())
                check(parsed['message'] == response['message'], rid + '/' + cid + ': message differs')
                check(parsed['cached_input_tokens'] == call['cached_input_tokens'], rid + '/' + cid + ': cache count')
                amounts['cached_input_tokens'] += parsed['cached_input_tokens']
                if n == 0: check(parsed['cached_input_tokens'] == 0, rid + ': first request not cold')
            else:
                check(not any(e['call'] == cid and e['api_request_sent'] for e in events), rid + ': unusable response executed')
            measured.append({'call_id': cid, 'status': call['status'], 'usage_known': is_known,
                'input_tokens': decoded['input_tokens'], 'output_tokens': decoded['output_tokens'],
                'cached_input_tokens': call.get('cached_input_tokens'),
                'request_sha256': sha(folder / 'request.json'), 'response_sha256': sha(folder / 'response.json'),
                'wire_sha256': sha(folder / 'wire_private.sse') if receipt else None})
        known_tokens = amounts['input_tokens']+amounts['output_tokens']
        check(summary['known_total_tokens'] == known_tokens <= plan['max_total_tokens'], rid + ': whole-task token sum/budget')
        check(summary['unknown_usage_calls'] == amounts['unknown_usage_calls'], rid + ': unknown usage sum')
        if summary['python_session']: check(summary['python_session']['container_removed'], rid + ': interpreter remains')
        evaluation = read(trial / 'evaluation.json') if (trial / 'evaluation.json').exists() else None
        if reported.get('evaluation_attempted'): totals['evaluator_calls'] += 1
        if evaluation:
            check(evaluation['appworld_version'] == original['appworld_version'], rid + ': evaluator version differs')
            check(evaluation['execution_summary_sha256'] == sha(trial / 'summary.json'), rid + ': frozen evaluated execution differs')
            check(not evaluation['evaluation_returned_to_model'], rid + ': evaluator feedback used')
            check(reported['evaluation']['official_success'] == evaluation['official_success'], rid + ': official result differs')
        row.update(model_calls=len(usage), known_total_tokens=known_tokens,
            **{k: amounts[k] for k in ('input_tokens', 'output_tokens', 'cached_input_tokens', 'unknown_usage_calls')},
            api_requests=summary['api_requests'], sent_api_counts=dict(api_counts),
            clock_receipts_with_date_and_time=clock_ids, undispatched_clock_requests=rejected_clock,
            python_programs=programs, stop_reason=summary['stop_reason'],
            official_success=evaluation['official_success'] if evaluation else None,
            wall_seconds=summary['wall_seconds'], full_wall_seconds=summary['full_wall_seconds'],
            setup_wall_seconds=summary['setup']['wall_seconds'], calls=measured,
            source_sha256={name: sha(trial / (name+'.json')) for name in ('summary', 'events', 'spans', 'usage')})
        rows.append(row)
        totals.update(model_calls=len(usage), known_total_tokens=known_tokens,
            unknown_usage_calls=amounts['unknown_usage_calls'], api_requests=summary['api_requests'])
    for key in ('model_calls', 'known_total_tokens', 'unknown_usage_calls', 'api_requests', 'evaluator_calls'):
        check(report[key] == totals[key], 'batch accounting: ' + key)
    return {'phase': 'P64', 'source_report_sha256': sha(report_path), 'plan_sha256': sha(ROOT / PLAN),
        'fixed_commit': report['git_commit'], 'checks': checks, 'audit_errors': errors, 'rows': rows,
        **dict(totals), 'planned_conditions': 4, 'known_tasks': 2,
        'server_stopped': pipeline.get('server_stopped'), 'owned_server_processes_present': live,
        'server': {k: server.get(k) for k in ('wall_seconds', 'load_wall_seconds', 'sampled_peak_rss_bytes',
            'peak_system_swap_bytes', 'stop_reason', 'exit_code')},
        'pipeline_sha256': sha(directory / 'status.json'), 'server_final_sha256': sha(directory / 'server_final.json'),
        'audit_model_calls': 0, 'audit_environment_api_requests': 0, 'audit_evaluator_calls': 0,
        'reserved_scenarios_read': 0, 'audit_wall_seconds': time.monotonic()-began,
        'novel_method_claim': False, 'general_quality_preservation_established': False}


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--storage-root', type=Path, required=True)
    p.add_argument('--frozen-root', type=Path, required=True); a = p.parse_args()
    target = ROOT / 'reports/P64_public_name_audit.json'
    if target.exists(): raise FileExistsError('preserve original audit')
    result = audit(a.storage_root, a.frozen_root); write_json(target, result)
    print({k: result[k] for k in ('checks', 'audit_errors', 'model_calls', 'known_total_tokens', 'unknown_usage_calls')})
