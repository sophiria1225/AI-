"""Reconcile all P68 records without models, APIs, or private evaluation details."""
import argparse
from collections import Counter
import json
import os
from pathlib import Path
import time

from appworld_native_tools import NativeCatalog
from audit_ordinary_continuation import stream_receipt
from local_llama import parse_response
from export_completion_comparison import interface
from native_conversation import NativeConversation
from inspect_completion_identity_differences import difference_paths, IDENTIFIER
from export_completion_comparison import PLAN, sources
from export_completion_control import check_prefix, prefix_digest
from run_context_comparison import write_json
from run_handoff_factors import ROOT, read, sha


def audit_native_history(trial, config, task, tools, usage, events, spans, check):
    """Reconstruct each public prompt and then-available schemas without dispatch."""
    catalog = NativeCatalog(tools); view = NativeConversation(interface(config), task)
    complete = False
    check(all(e['stage'] in ('model_tool', 'controller_api') for e in events), 'native event stages')
    for call in usage:
        cid = call['id']; request = read(trial / cid / 'request.json')
        response = read(trial / cid / 'response.json')
        expected, _ = view.for_model(config['observation_page_characters'])
        check(request['messages'] == expected, cid+': exact public history')
        check(request['tools'] == catalog.tools(), cid+': then-visible public schemas')
        current = [e for e in events if e['call'] == cid and e['stage'] == 'model_tool']
        supplied = set(catalog.visible)
        for event in current:
            span = spans[event['span_id']]; expected_new = []
            if event['api_request_sent']:
                check(not complete, cid+': API after completion')
                try:
                    action = catalog.decode(span['action'], visible=supplied)
                    valid = set(action) == {'app', 'api', 'args'}
                except (ValueError, KeyError, TypeError): valid = False
                check(valid, cid+': sent API not in supplied schema set')
                observation = span['observation']
                if valid and not event.get('effects_unknown') and 'api_error' not in observation:
                    expected_new = catalog.expose_requested_document(action)
                complete |= bool(observation.get('declared_complete'))
            check(event['new_tools'] == expected_new, cid+': unsupported schema exposure')
        if response['status'] == 'ok':
            try: view.append(response['message'], [spans[e['span_id']] for e in current])
            except (ValueError, KeyError, TypeError): check(False, cid+': model actions/receipts differ')
        else: check(not current, cid+': quarantined model output executed')
    if (trial / 'conversation_private.json').exists():
        check(read(trial / 'conversation_private.json') == view.messages(), 'saved native conversation differs')
    for event in events:
        if event['stage'] != 'controller_api': continue
        try: action = catalog.decode(spans[event['span_id']]['action']); valid = True
        except (ValueError, KeyError, TypeError): valid = False
        check(valid and action == {'app': 'supervisor', 'api': 'complete_task', 'args': {'status': 'success'}},
              'controller uses ordinary completion schema')


def compare_pair(storage, rows):
    """Retain strict mismatches and missing outcomes in the fresh matched pair."""
    if len(rows) != 2 or any(r['status'] != 'evaluated' for r in rows):
        return {'both_evaluated': False, 'local_gate_met': False}
    baseline, controlled = rows
    folders = [storage / 'records/context_pilot' / r['run_id'] for r in rows]
    pairs = []; differences = Counter()
    for n, call in enumerate(controlled['calls']):
        cid = call['call_id']
        if n >= len(baseline['calls']):
            pairs.append({'call_id': cid, 'reference_present': False}); continue
        row = {'call_id': cid, 'reference_present': True}
        for kind in ('request', 'response'):
            values = [read(f / cid / (kind+'.json')) for f in folders]
            paths = difference_paths(*(values if kind == 'request' else [v.get('message') for v in values]))
            ids = [p for p in paths if IDENTIFIER.fullmatch(p)]
            other = [p for p in paths if not IDENTIFIER.fullmatch(p)]
            row[kind] = {'strict_equal': not paths, 'identifier_difference_paths': ids, 'other_difference_paths': other}
            differences[kind+'_identifier_differences'] += len(ids)
            differences[kind+'_other_differences'] += len(other)
        pairs.append(row)
    call_ids = {c['call_id'] for c in controlled['calls']}
    prefix_events = [[e for e in read(f / 'events.json') if e['call'] in call_ids and e['stage'] != 'controller_api'] for f in folders]
    source_spans = [read(f / 'spans.json') for f in folders]
    prefix_spans = [{e['span_id']: spans[e['span_id']] for e in evs} for spans, evs in zip(source_spans, prefix_events)]
    dbs = [read(f / 'evaluation.json')['frozen_database_hashes'] for f in folders]
    changed = sorted(k for k in set(dbs[0]) | set(dbs[1]) if dbs[0].get(k) != dbs[1].get(k))
    known = all(r['unknown_usage_calls'] == 0 for r in rows)
    token_delta = controlled['known_total_tokens']-baseline['known_total_tokens']
    return {'both_evaluated': True, 'original_official_successes': [r['official_success'] for r in rows],
        'logical_token_difference_controlled_minus_native': token_delta,
        'difference_is_exact': known, 'request_message_comparisons': pairs, **dict(differences),
        'same_prefix_events': prefix_events[0] == prefix_events[1],
        'same_prefix_spans': prefix_spans[0] == prefix_spans[1],
        'same_entire_executed_model_prefix': bool(pairs) and all(p.get('reference_present')
            and p['request']['strict_equal'] and p['response']['strict_equal'] for p in pairs)
            and prefix_events[0] == prefix_events[1] and prefix_spans[0] == prefix_spans[1],
        'changed_final_database_files': changed, 'final_database_file_counts': [len(d) for d in dbs],
        'local_gate_met': known and all(r['official_success'] for r in rows)
            and not changed and all(len(d) == 13 for d in dbs) and token_delta < 0,
        'is_repeated_or_randomized_causal_estimate': False}


def audit_controller(task, spans, events, usage, checks, summary, check):
    """Replay each bounded decision against exactly its then-visible prefix."""
    model_events = [e for e in events if e['stage'] != 'controller_api']
    controller_events = [e for e in events if e['stage'] == 'controller_api']
    if summary['arm'] == 'native':
        check(not checks and not controller_events and summary['controller_checks'] == 0
              and summary['controller_wall_seconds'] == 0 and summary['controller_completion_attempts'] == 0
              and not summary['controller_declared_complete'], 'baseline must not run controller')
        return {'checks': 0, 'wall_seconds': 0, 'completion_attempts': 0,
                'declared_complete': False, 'supported_boundaries': [], 'decisions': []}
    check(len(checks) == summary['controller_checks'] <= 80, 'controller check count')
    check(abs(sum(c['wall_seconds'] for c in checks)-summary['controller_wall_seconds']) < 1e-8,
          'controller measured time')
    check(all(c['wall_seconds'] >= 0 for c in checks), 'negative controller duration')
    expected_calls = []
    already_complete = False
    for call in usage:
        current = [e for e in model_events if e['call'] == call['id']]
        already_complete |= any(spans[e['span_id']]['observation'].get('declared_complete') for e in current)
        execution_failed = any(e.get('effects_unknown') or
            spans[e['span_id']]['observation'].get('status') == 'harness_error' for e in current)
        if current and not already_complete and not execution_failed and call.get('status', 'ok') == 'ok':
            expected_calls.append(call['id'])
    check([c['after_call'] for c in checks] == expected_calls, 'missing or extra model-boundary checks')
    supported = []
    for n, c in enumerate(checks, 1):
        number = c['model_calls']; prefix_usage = usage[:number]
        check(number == n and c['after_call'] == prefix_usage[-1]['id'], 'controller boundary identity')
        expected_events = [e for e in model_events if e['call'] in {u['id'] for u in prefix_usage}]
        check(c['event_count'] == len(expected_events), 'controller future/missing event count')
        prefix_spans = {e['span_id']: spans[e['span_id']] for e in expected_events}
        check(prefix_digest(task, prefix_spans, expected_events, prefix_usage) == c['prefix_sha256'], 'controller public prefix digest')
        decision = check_prefix(task, prefix_spans, expected_events, prefix_usage)
        check(decision == c['decision'], 'controller decision cannot be reproduced')
        if decision['trace_support'] == 'supported': supported.append(c['after_call'])
    check(len(controller_events) == summary['controller_completion_attempts'] <= 1, 'controller attempt count')
    if controller_events:
        e = controller_events[0]; span = spans[e['span_id']]
        check(bool(checks) and checks[-1]['decision']['trace_support'] == 'supported', 'completion without supported prefix')
        check(len(supported) == 1, 'continued past a supported boundary')
        check(e is events[-1] and e['call'] == 'controller_001', 'controller event order/identity')
        check(checks[-1]['model_calls'] == len(usage), 'model generation after controller action')
        check(span['assistant'] == '', 'controller fabricated model content')
        check(span['action']['name'] == 'supervisor__complete_task'
              and json.loads(span['action']['arguments']) == {'status': 'success'}, 'controller action changed')
    if summary['controller_declared_complete']:
        check(len(controller_events) == 1 and spans[controller_events[0]['span_id']]['observation'].get('declared_complete'),
              'unconfirmed controller completion')
        check(summary['stop_reason'] == 'controller_declared_complete', 'controller stop reason')
    return {'checks': len(checks), 'wall_seconds': summary['controller_wall_seconds'],
        'completion_attempts': summary['controller_completion_attempts'],
        'declared_complete': summary['controller_declared_complete'], 'supported_boundaries': supported,
        'decisions': [{'after_call': c['after_call'], 'trace_support': c['decision']['trace_support'],
            'reasons': c['decision']['reasons'], 'prefix_sha256': c['prefix_sha256'], 'wall_seconds': c['wall_seconds']} for c in checks]}



def audit(storage, frozen):
    began = time.monotonic(); errors = []; checks = 0
    def check(condition, label):
        nonlocal checks
        checks += 1
        if not condition: errors.append(label)
    plan, original, tasks, tools = sources(storage)
    report_path = frozen / 'reports/P68_export_completion.json'; report = read(report_path)
    directory = storage / 'records/context_pilot/P68_pipeline_v01'
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
        prompt = interface(config)
        api_counts = Counter(spans[e['span_id']]['action']['name'] for e in events if e['api_request_sent'])
        audit_native_history(trial, config, tasks[tid]['public_task'], tools, usage, events, spans,
                             lambda ok, label: check(ok, rid+': '+label))
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
            check(request['messages'][0] == {'role': 'system', 'content': prompt}, rid + '/' + cid + ': capability guidance/tools')
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
        check(summary['python_session'] is None, rid + ': unplanned Python interface')
        evaluation = read(trial / 'evaluation.json') if (trial / 'evaluation.json').exists() else None
        if reported.get('evaluation_attempted'): totals['evaluator_calls'] += 1
        if evaluation:
            check(evaluation['appworld_version'] == original['appworld_version'], rid + ': evaluator version differs')
            check(evaluation['execution_summary_sha256'] == sha(trial / 'summary.json'), rid + ': frozen evaluated execution differs')
            check(not evaluation['evaluation_returned_to_model'], rid + ': evaluator feedback used')
            check(reported['evaluation']['official_success'] == evaluation['official_success'], rid + ': official result differs')
        controller = audit_controller(tasks[tid]['public_task'], spans, events, usage,
            read(trial / 'controller_checks.json'), summary, lambda ok, label: check(ok, rid+': '+label))
        row.update(controller=controller,
            model_calls=len(usage), known_total_tokens=known_tokens,
            **{k: amounts[k] for k in ('input_tokens', 'output_tokens', 'cached_input_tokens', 'unknown_usage_calls')},
            api_requests=summary['api_requests'], sent_api_counts=dict(api_counts),
            stop_reason=summary['stop_reason'],
            official_success=evaluation['official_success'] if evaluation else None,
            wall_seconds=summary['wall_seconds'], full_wall_seconds=summary['full_wall_seconds'],
            setup_wall_seconds=summary['setup']['wall_seconds'], calls=measured,
            source_sha256={name: sha(trial / (name+'.json')) for name in ('summary', 'events', 'spans', 'usage', 'controller_checks')})
        rows.append(row)
        totals.update(model_calls=len(usage), known_total_tokens=known_tokens,
            unknown_usage_calls=amounts['unknown_usage_calls'], api_requests=summary['api_requests'])
    for key in ('model_calls', 'known_total_tokens', 'unknown_usage_calls', 'api_requests', 'evaluator_calls'):
        check(report[key] == totals[key], 'batch accounting: ' + key)
    comparison = compare_pair(storage, rows)
    return {'phase': 'P68', 'source_report_sha256': sha(report_path), 'plan_sha256': sha(ROOT / PLAN),
        'fixed_commit': report['git_commit'], 'checks': checks, 'audit_errors': errors, 'rows': rows,
        'comparison': comparison, 'local_adoption_gate_met': not errors and comparison.get('local_gate_met', False),
        **dict(totals), 'planned_conditions': 2, 'known_tasks': 1,
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
    target = ROOT / 'reports/P68_completion_audit.json'
    if target.exists(): raise FileExistsError('preserve original audit')
    result = audit(a.storage_root, a.frozen_root); write_json(target, result)
    print({k: result[k] for k in ('checks', 'audit_errors', 'model_calls', 'known_total_tokens', 'unknown_usage_calls')})
