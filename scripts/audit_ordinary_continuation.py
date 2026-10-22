"""Reconcile every P61 condition, including missing usage, without new calls."""
import argparse
from collections import Counter
import json
import os
from pathlib import Path
import time

from local_llama import parse_response
from ordinary_continuation import PLAN, sources
from run_context_comparison import write_json
from run_handoff_factors import ROOT, read, sha
from streaming_usage_receipt import CompletionReceipt, SSEDecoder, StreamProtocolError


def stream_receipt(path):
    decoder, receipt = SSEDecoder(), CompletionReceipt()
    failure = None
    try:
        with path.open('rb') as f:
            for chunk in iter(lambda: f.read(4096), b''):
                for event in decoder.feed(chunk): receipt.consume(event)
        decoder.finish()
    except (StreamProtocolError, ValueError) as error:
        failure = type(error).__name__
    return receipt, failure


def audit(storage, frozen):
    began = time.monotonic(); errors = []; checks = 0
    def check(condition, label):
        nonlocal checks
        checks += 1
        if not condition: errors.append(label)
    plan, _, prefix, _ = sources(storage)
    report_path = frozen / 'reports/P61_ordinary_continuation.json'
    report = read(report_path)
    pipeline_dir = storage / 'records/context_pilot/P61_pipeline_v01'
    pipeline = read(pipeline_dir / 'status.json'); server = read(pipeline_dir / 'server_final.json')
    check(report['status'] in ('complete', 'stopped'), 'worker not closed')
    check(pipeline['status'] in ('complete', 'stopped'), 'pipeline not closed')
    check(report['git_commit'] == pipeline['git_commit'], 'fixed commit differs')
    check(report['plan_sha256'] == sha(ROOT / PLAN), 'fixed plan differs')
    for name, digest in report['code_sha256'].items():
        check(sha(frozen / name) == digest, 'frozen implementation changed: ' + name)
    check([r['arm'] for r in report['rows']] == plan['arms'], 'planned condition order differs')
    check([r['run_id'] for r in report['rows']] == plan['run_ids'], 'planned run IDs differ')
    check(server['status'] == 'stopped' and pipeline.get('server_stopped'), 'server not stopped')
    live = []
    for pid in (server.get('pid'), server.get('supervisor_pid')):
        if pid is None: continue
        try: os.kill(pid, 0); live.append(pid)
        except ProcessLookupError: pass
    check(not live, 'owned server process still present')
    rows = []; total_calls = total_tokens = unknown = apis = replayed = evaluated = 0
    for reported in report['rows']:
        rid = reported['run_id']; trial = storage / 'records/context_pilot' / rid
        row = {'arm': reported['arm'], 'run_id': rid, 'status': reported['status']}
        if reported['status'] == 'not_run':
            check(not (trial / 'usage.json').exists(), rid + ': hidden unreported attempt')
            rows.append(row); continue
        s, calls, events, spans = [read(trial / name) for name in
            ('summary.json', 'usage.json', 'events.json', 'spans.json')]
        admissions = read(trial / 'admissions.json') if (trial / 'admissions.json').exists() else []
        for name in ('usage', 'events', 'spans'):
            check(read(trial / ('prefix_' + name + '.json')) == prefix[name], rid + ': prefix ' + name + ' differs')
        check(read(trial / 'public_task.json') == prefix['public_task'], rid + ': task changed')
        setup = s['setup']['environment_replay']
        check(not calls or s['setup']['status'] == 'matched_observable_prefix', rid + ': generated before matching original boundary')
        if s['setup']['status'] == 'matched_observable_prefix':
            check(setup['api_requests'] == setup['observation_matches'] == 20 and setup['db_files_match']
                  and setup['db_files'] == 13, rid + ': incomplete reconstruction')
        check(s['model_calls'] == len(calls) <= plan['max_calls'], rid + ': generation count')
        check(sum(a.get('model_request_started', False) for a in admissions) == len(calls), rid + ': unaccounted model attempt')
        check(s['api_requests'] == sum(e['api_request_sent'] for e in events) <= 60, rid + ': API count/budget')
        check(s['unknown_effect_requests'] == sum(bool(e['effects_unknown']) for e in events), rid + ': unknown effects count')
        check(s['additional_contact_searches'] == sum(e['api_request_sent'] and
              spans[e['span_id']]['action']['name'] == 'phone__search_contacts' for e in events), rid + ': contact-search count')
        check(len(events) == len({e['span_id'] for e in events}), rid + ': repeated event receipt')
        check(set(prefix['spans']) | {e['span_id'] for e in events} == set(spans), rid + ': missing/unaccounted spans')
        api_counts = Counter(spans[e['span_id']]['action']['name'] for e in events if e['api_request_sent'])
        programs = []
        for event in events:
            span = spans[event['span_id']]; action = span.get('action') or {}
            if action.get('name') != 'run_python': continue
            try:
                arguments = json.loads(action['arguments'])
                ids = arguments.get('span_ids') if isinstance(arguments, dict) else None
            except (ValueError, TypeError): ids = None
            programs.append({'call_id': event['call'], 'status': span['observation'].get('status'),
                'prior_receipt_count': len(ids) if isinstance(ids, list) else None,
                'error_present': bool(span['observation'].get('error'))})
        measured = []; known_tokens = input_tokens = output_tokens = cached = 0; missing = 0
        for n, call in enumerate(calls):
            folder = trial / call['id']; response = read(folder / 'response.json'); request = read(folder / 'request.json')
            receipt, stream_error = stream_receipt(folder / 'wire_private.sse')
            decoded = receipt.summary(); is_known = decoded['terminal_usage_received'] and stream_error is None
            check(is_known == call['usage_known'], rid + '/' + call['id'] + ': exact usage classification')
            check(call['status'] == response['status'], rid + '/' + call['id'] + ': response status')
            check(request['seed'] == 54+n and request['cache_prompt'] == (n != 0), rid + '/' + call['id'] + ': seed/cache policy')
            check(request['max_tokens'] == 4096, rid + '/' + call['id'] + ': output cap')
            if is_known:
                for name in ('input_tokens', 'output_tokens'):
                    check(call[name] == response[name] == decoded[name], rid + '/' + call['id'] + ': ' + name)
                input_tokens += decoded['input_tokens']; output_tokens += decoded['output_tokens']
                known_tokens += decoded['input_tokens']+decoded['output_tokens']
            else:
                missing += 1
                check(not any(e['call'] == call['id'] and e['api_request_sent'] for e in events), rid + ': unknown response executed')
            if response['status'] == 'ok':
                check(decoded['message_ready'], rid + '/' + call['id'] + ': incomplete stream executed')
                parsed = parse_response(receipt.final_response())
                check(parsed['message'] == response['message'], rid + '/' + call['id'] + ': generated message differs')
                check(parsed['cached_input_tokens'] == call['cached_input_tokens'], rid + '/' + call['id'] + ': cached input')
                cached += parsed['cached_input_tokens']
                if n == 0: check(parsed['cached_input_tokens'] == 0, rid + ': first request not cold')
            else:
                check(not any(e['call'] == call['id'] and e['api_request_sent'] for e in events), rid + ': quarantined response executed')
            measured.append({'call_id': call['id'], 'status': call['status'], 'usage_known': is_known,
                'input_tokens': decoded['input_tokens'], 'output_tokens': decoded['output_tokens'],
                'cached_input_tokens': call.get('cached_input_tokens'), 'stream_done': decoded['stream_done'],
                'output_lower_bound': decoded['observed_output_tokens_lower_bound'],
                'wire_sha256': sha(folder / 'wire_private.sse'), 'request_sha256': sha(folder / 'request.json'),
                'response_sha256': sha(folder / 'response.json')})
        check(known_tokens == s['known_total_tokens'] <= plan['max_total_tokens'], rid + ': logical token sum/budget')
        check(missing == s['unknown_usage_calls'], rid + ': unknown usage count')
        check(s['whole_task_known_tokens'] == 252602+known_tokens, rid + ': whole-work token sum')
        if s['python_session'] is not None:
            check(s['python_session']['container_removed'], rid + ': interpreter not removed')
        evaluation = read(trial / 'evaluation.json') if (trial / 'evaluation.json').exists() else None
        if reported.get('evaluation_attempted'): evaluated += 1
        if evaluation:
            check(evaluation['execution_summary_sha256'] == sha(trial / 'summary.json'), rid + ': evaluated state not frozen')
            check(not evaluation['evaluation_returned_to_model'], rid + ': evaluator feedback used')
            check(reported['evaluation']['official_success'] == evaluation['official_success'], rid + ': official result differs')
        row.update(model_calls=len(calls), known_continuation_tokens=known_tokens, unknown_usage_calls=missing,
            input_tokens=input_tokens, output_tokens=output_tokens, cached_input_tokens=cached,
            whole_task_known_tokens=252602+known_tokens, continuation_api_requests=s['api_requests'],
            replay_api_requests=setup.get('api_requests', 0), additional_contact_searches=s['additional_contact_searches'],
            official_success=evaluation['official_success'] if evaluation else None,
            sent_api_counts=dict(api_counts), python_programs=programs,
            stop_reason=s['stop_reason'], setup_status=s['setup']['status'], wall_seconds=s['wall_seconds'], setup_wall_seconds=s['setup']['wall_seconds'],
            whole_task_wall_seconds=s['whole_task_wall_seconds'], full_wall_seconds=s['full_wall_seconds'], calls=measured,
            summary_sha256=sha(trial / 'summary.json'), events_sha256=sha(trial / 'events.json'),
            spans_sha256=sha(trial / 'spans.json'), usage_sha256=sha(trial / 'usage.json'))
        rows.append(row); total_calls += len(calls); total_tokens += known_tokens; unknown += missing
        apis += s['api_requests']; replayed += setup.get('api_requests', 0)
    for key, value in [('model_calls', total_calls), ('known_continuation_tokens', total_tokens),
                       ('unknown_usage_calls', unknown), ('continuation_api_requests', apis),
                       ('replay_api_requests', replayed), ('evaluator_calls', evaluated)]:
        check(report[key] == value, 'batch accounting: ' + key)
    return {'phase': 'P61', 'source_report_sha256': sha(report_path), 'plan_sha256': sha(ROOT / PLAN),
        'pipeline_sha256': sha(pipeline_dir / 'status.json'), 'server_final_sha256': sha(pipeline_dir / 'server_final.json'),
        'fixed_commit': report['git_commit'], 'checks': checks, 'audit_errors': errors, 'rows': rows,
        'model_calls': total_calls, 'known_continuation_tokens': total_tokens, 'unknown_usage_calls': unknown,
        'continuation_api_requests': apis, 'replay_api_requests': replayed, 'evaluator_calls': evaluated,
        'planned_conditions': 2, 'known_source_tasks': 1, 'all_planned_rows_present': len(rows) == 2,
        'server_stopped': pipeline.get('server_stopped'), 'owned_server_processes_present': live,
        'server': {k: server.get(k) for k in ('wall_seconds', 'load_wall_seconds', 'sampled_peak_rss_bytes',
                                             'peak_system_swap_bytes', 'stop_reason', 'exit_code')},
        'audit_model_calls': 0, 'audit_environment_api_requests': 0, 'audit_evaluator_calls': 0,
        'reserved_scenarios_read': 0, 'audit_wall_seconds': time.monotonic()-began,
        'is_novel_method_comparison': False, 'general_quality_preservation_established': False}


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--storage-root', type=Path, required=True)
    p.add_argument('--frozen-root', type=Path, required=True); a = p.parse_args()
    result = audit(a.storage_root, a.frozen_root)
    write_json(ROOT / 'reports/P61_ordinary_audit.json', result)
    print({k: result[k] for k in ('checks', 'audit_errors', 'model_calls', 'known_continuation_tokens', 'unknown_usage_calls')})
