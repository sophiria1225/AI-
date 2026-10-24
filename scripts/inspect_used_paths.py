"""P109: all closed P107 paths, without code, model, API or evaluator replay."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import signal
import time

from inspect_appworld_api_schemas import load_public_tools
from inspect_recorded_action_agreement import verify_ci
from replay_read_view_controls import read, sha
from used_path_diagnosis import acquisition_history, message_components, program_syntax, require

PLAN = 'configs/P109_used_paths_v01.json'
RUN_IDS = ['BOC_P107_01_EAGER_CACHED', 'BOC_P107_01_COALESCED_CACHED']


def fixed_parameters():
    return dict(phase='P109', run_ids=RUN_IDS, max_wall_seconds=180,
        max_files_per_cell=1024, max_bytes_per_cell=268435456, max_model_calls_per_cell=80,
        max_programs_per_cell=256, model_generations=0, environment_API_requests=0,
        evaluations=0, saved_generated_program_executions=0, task_databases_read=0,
        reserved_scenarios_read=0, tokenizer_calls=0, automatic_retries=0,
        prior_P107_results_known=True, private_reasoning_interpreted_semantically=False,
        current_saved_code_read_syntactically=True, novel_method_claim=False)


def write_new(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')


def bound_inventory(original, replay, folder, plan):
    manifest = replay['private_record_sha256'][original['run_id']]
    selected = {n: manifest[n] for n in ('events.json', 'spans.json', 'summary.json')}
    selected['usage.json'] = original['usage_sha256']
    selected.update({n: h for n, h in manifest.items() if n.startswith('programs/')
                     and n.endswith('/input_private.json') and '_view_setup/' not in n})
    for call in original['request_checks']:
        for kind in ('request', 'response'):
            require(call[kind + '_sha256'] is not None, 'known_source_packets_required')
            selected[call['call_id'] + '/' + kind + '.json'] = call[kind + '_sha256']
    require(len(selected) <= plan['max_files_per_cell'], 'file_count_bound')
    size = 0
    for name, expected in selected.items():
        path = folder / name
        require(path.is_file() and not path.is_symlink() and path.stat().st_size <= 16777216,
                'bounded_regular_private_input_required')
        path.resolve().relative_to(folder.resolve())
        require(sha(path) == expected, 'saved_private_input_changed')
        size += path.stat().st_size
    require(size <= plan['max_bytes_per_cell'], 'private_bytes_bound')
    return selected


def analyze_cell(folder, original, inventory, public_names, plan):
    usage = read(folder / 'usage.json'); events = read(folder / 'events.json')
    spans = read(folder / 'spans.json')
    require(len(usage) == original['model_calls'] <= plan['max_model_calls_per_cell'],
            'all_original_calls_required')
    history = acquisition_history(events, spans, usage, public_names)
    require(history['counts']['sent_API_requests'] == original['api_requests'], 'actual_API_count_changed')
    rows = []; previous_reasoning = []
    for use, expected in zip(usage, original['request_checks'], strict=True):
        cid = use['id']
        require(cid == expected['call_id'] and use['status'] == expected['status'] == 'ok',
                'all_known_calls_required')
        request = read(folder / cid / 'request.json'); response = read(folder / cid / 'response.json')
        for key in ('input_tokens', 'output_tokens', 'cached_input_tokens'):
            require(use[key] == expected[key] == response[key], 'original_measured_usage_changed')
        messages = request['messages']
        incoming_reasoning = [m.get('reasoning_content') for m in messages if m['role'] == 'assistant']
        require(incoming_reasoning == previous_reasoning, 'original_reasoning_prefix_changed')
        components = message_components(messages)
        output_components = message_components([response['message']])
        previous_reasoning.append(response['message'].get('reasoning_content'))
        rows.append(dict(call_id=cid, input_tokens=use['input_tokens'], output_tokens=use['output_tokens'],
            cached_input_tokens=use['cached_input_tokens'], actual_API_requests=expected['API_requests'],
            Python_execution_errors=expected['Python_execution_errors'],
            input=components, output=output_components,
            tool_schema_compact_JSON_characters=len(json.dumps(request.get('tools', []),
                ensure_ascii=False, separators=(',', ':'))),
            reasoning_is_exactly_recorded_prior_responses=True))
    program_names = sorted(n for n in inventory if n.startswith('programs/'))
    require(len(program_names) <= plan['max_programs_per_cell'], 'program_count_bound')
    outer_sources = []
    for event in events:
        if event['stage'] == 'model_tool':
            span = spans[event['span_id']]
            if span.get('action', {}).get('name') == 'run_python':
                args = span['action']['arguments']
                if type(args) is str:
                    args = json.loads(args)
                outer_sources.append(args['code'])
    require(len(outer_sources) == len(program_names), 'all_submitted_programs_required')
    programs = []
    for name, source in zip(program_names, outer_sources, strict=True):
        payload = read(folder / name)
        require(payload['code'] == source, 'submitted_source_and_executed_input_differ')
        programs.append(dict(record_name=name.split('/')[1],
            input_sha256=inventory[name], **program_syntax(source, public_names)))
    return dict(run_id=original['run_id'], policy=original['read_view_policy'], status='checked',
        original_success=original['success'], original_stop_reason=original['stop_reason'],
        original_known_total_tokens=original['known_total_tokens'], original_unknown_usage_calls=0,
        original_API_requests=original['api_requests'], calls=rows, programs=programs,
        acquisition_history=history, syntax_programs=len(programs),
        input_character_exposures={k: sum(r['input'][k] for r in rows)
            for k in rows[0]['input'] if k.endswith('_characters')},
        output_character_totals={k: sum(r['output'][k] for r in rows)
            for k in rows[0]['output'] if k.endswith('_characters')},
        whole_task_savings_established=False, future_field_demand_inferred=False)


def inspect(storage, root):
    plan = read(root / PLAN)
    for key, value in fixed_parameters().items():
        require(type(plan.get(key)) is type(value) and plan[key] == value, 'fixed_plan_changed:' + key)
    for name, expected in plan['source_sha256'].items():
        require(sha(root / name) == expected, 'analysis_source_changed:' + name)
    head, ci = verify_ci(root)
    audit = read(root / 'reports/P107_comparison.json')
    replay = read(root / 'reports/P108_read_view_lifetimes.json')
    session = read(root / 'reports/P107_server_session.json')
    require(not audit['audit_errors'] and audit['owned_processes_absent'] and
            audit['batch_status'] == 'complete' and session['status'] == 'stopped' and
            [r['run_id'] for r in audit['rows']] == RUN_IDS and
            all(r['record_status'] == 'evaluated' and not r['unknown_usage_calls'] for r in audit['rows']),
            'entire_original_batch_closed_required')
    require(replay['status'] == 'complete' and not replay['errors'] and
            replay['source_audit_sha256'] == sha(root / 'reports/P107_comparison.json'),
            'closed_factual_replay_required')
    public_tools, schema_hashes, _ = load_public_tools(storage / '.runtime/appworld/r18_probe_01/data')
    require(schema_hashes == plan['public_schema_sha256'], 'fixed_public_schema_changed')
    public_names = {t['function']['name'] for t in public_tools}
    directory = storage / 'records/context_pilot/P109_used_paths_v01'
    output = root / 'reports/P109_used_paths.json'
    require(not directory.exists() and not output.exists(), 'preserve_every_attempt')
    directory.mkdir(parents=True)
    result = dict(**fixed_parameters(), source_commit=head, ci=ci,
        started_at=datetime.now(timezone.utc).isoformat(), plan_sha256=sha(root / PLAN),
        rows=[], errors=[], private_record_sha256={}, status='incomplete',
        measured_savings=None, online_substitutions_enabled=0,
        limitation='Lexical same-spelling uses are not runtime alias or liveness proofs. '
            'Prior observed names are not permission to substitute full responses. '
            'Disjoint character fields are not token attribution or measured savings. '
            'No generated Python, API, model or evaluator is rerun.')
    started = time.monotonic()
    def expired(*_):
        raise TimeoutError('P109_analysis_deadline')
    previous = signal.signal(signal.SIGALRM, expired)
    signal.alarm(plan['max_wall_seconds'])
    try:
        for original in audit['rows']:
            rid = original['run_id']; folder = storage / 'records/context_pilot' / rid
            try:
                inventory = bound_inventory(original, replay, folder, plan)
                result['private_record_sha256'][rid] = inventory
                write_new(directory / (rid + '_input_manifest.json'), inventory)
                row = analyze_cell(folder, original, inventory, public_names, plan)
                require(bound_inventory(original, replay, folder, plan) == inventory, 'inputs_changed_during_analysis')
                result['rows'].append(row)
            except Exception as error:
                result['errors'].append(dict(run_id=rid, type=type(error).__name__,
                    reason=str(error) if type(error) in (ValueError, TimeoutError) else 'local_analysis_exception'))
                result['rows'].append(dict(run_id=rid, status='analysis_error'))
                if isinstance(error, TimeoutError):
                    break
        result['status'] = 'complete' if not result['errors'] and len(result['rows']) == 2 else 'incomplete'
    finally:
        signal.alarm(0); signal.signal(signal.SIGALRM, previous)
        for rid in RUN_IDS:
            if not any(r['run_id'] == rid for r in result['rows']):
                result['rows'].append(dict(run_id=rid, status='not_analyzed'))
        result.update(ended_at=datetime.now(timezone.utc).isoformat(), wall_seconds=time.monotonic() - started)
        write_new(output, result)
        write_new(directory / 'end.json', dict(status=result['status'], report_sha256=sha(output)))
    print(json.dumps({k: result[k] for k in ('status', 'wall_seconds', 'errors')}))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--storage-root', type=Path, required=True)
    parser.add_argument('--repo-root', type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args(); inspect(args.storage_root.resolve(), args.repo_root.resolve())
