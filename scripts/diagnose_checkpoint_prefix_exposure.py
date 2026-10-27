"""Bounded P123 fixed-history native prefix-exposure diagnosis; no generation.

The removed raw history is NOT certified redundant. Native input differences on
already realized requests are not attainable savings or a new policy evaluation.
Only first-accepted-checkpoint -> next offered checkpoint actor requests qualify.
"""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time

from budget_observation import NO_TIME_NOTICE
from measure_receipt_history import render
from model_provenance import verified_model
from receipt_reasoning_history import digest, require
from single_checkpoint_history import closed_turns, FIELDS

AUDIT = 'reports/P123_comparison.json'
PLAN = 'configs/P123_whole_task_rolling_checkpoint_v01.json'
BUILD = 'reports/P110_renderer_build.json'
RENDERER_PLAN = 'configs/P110_receipt_history_inputs_v01.json'
RUNTIME = 'records/context_pilot/P123_pipeline_v01/server_runtime.json'
FIXED = {
    AUDIT: '73d55305300ae6cb332213f08f8a813a40ab17f82a9a167e3fbbf1bb17fb6147',
    PLAN: 'b4bb3fabb6d1b97dc67f3f17f1a3a97bafccfd13f2ce02c70da73d54d6962b0e',
    BUILD: 'be1aebecf2fee02602eca09830df0d3715031652966ec58acc6705cce12c5ee3',
    RUNTIME: '2e72c3bbc12bce84d01f7b1798af98dcf1fc0182b76aa2399f4ace955c7faef4',
}
RUNS = tuple(f'BOC_P123_{n:02}_ROLLING_SEPARATE' for n in range(1, 5))
DEPENDENCIES = (
    'scripts/measure_receipt_history.py', 'scripts/render_receipt_history.cpp',
    'scripts/rolling_checkpoint_history.py', 'scripts/rolling_checkpoint_inference.py',
    'scripts/single_checkpoint_history.py', 'scripts/receipt_reasoning_history.py',
    'scripts/budget_observation.py', 'scripts/model_provenance.py',
    'configs/P29_stateful_code_v01.json',
    RENDERER_PLAN,
)
LIMITS = dict(max_renderings=640, max_wall_seconds=600, max_renderer_seconds=90,
              max_renderer_rss_bytes=2147483648, max_file_bytes=16777216,
              max_total_private_input_bytes=536870912,
              stop_marker='.runtime/checkpoint_prefix_exposure.stop')
LIMITATION = ('Fixed realized histories only. Removing eligible raw history is a diagnostic '
    'counterfactual, not information preservation, achievable token savings, summary fidelity, '
    'quality preservation, or a live trigger evaluation. No summary is generated. Cumulative '
    'marginals count repeated presentations, not distinct information. Native grammar changes '
    'or original usage disagreement are errors. RSS is sampled, not a hard OS memory limit.')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    p = Path(path)
    require(p.is_file() and not p.is_symlink() and p.stat().st_size <= LIMITS['max_file_bytes'],
            'bounded_regular_input_required')
    return json.loads(p.read_text())


def write_new(path, value):
    with Path(path).open('x') as f:
        json.dump(value, f, ensure_ascii=False, indent=2, allow_nan=False)
        f.write('\n')


def bound_read(path, expected, bindings):
    require(sha(path) == expected, 'source_hash_mismatch')
    value = read(path)
    bindings[str(Path(path).resolve())] = expected
    return value


def first_window(controls, checks):
    """Actual actor requests only; exclude the actor displaced by next focus."""
    decisions = [x for x in controls if x.get('status') == 'checkpoint_decided'
                 and x.get('accepted') is True]
    if not decisions:
        return None, []
    first = decisions[0]
    require(first['revision'] == 1 and type(first['cutoff']) is int and first['cutoff'] > 2,
            'first_accepted_cutoff_required')
    offers = [x for x in controls if x.get('status') == 'checkpoint_offered'
              and x['after_model_calls'] >= first['after_model_calls']]
    next_offer = min((x['after_model_calls'] for x in offers), default=None)
    selected = [x for x in checks if x['role'] == 'agent'
                and int(x['call_id'].split('_')[1]) > first['after_model_calls']
                and (next_offer is None or int(x['call_id'].split('_')[1]) <= next_offer)]
    return dict(first_accepted_after_model_calls=first['after_model_calls'],
                accepted_archive_cutoff=first['cutoff'], next_offer_after_model_calls=next_offer,
                endpoint='before_next_offer' if next_offer is not None else 'recorded_task_end'), selected


def remove_eligible(request):
    """Return a data-only request copy and numeric coordinates, without text output."""
    require(type(request) is dict and type(request.get('messages')) is list,
            'plain_chat_request_required')
    messages = request['messages']
    require(4 <= len(messages) <= 2050 and messages[0].get('role') == 'system'
            and messages[1].get('role') == 'user', 'original_initial_pair_required')
    require(all(type(m) is dict and (m.get('content') is None or type(m.get('content')) is str)
                for m in messages), 'plain_text_messages_required')
    note = messages[2]
    require(set(note) == {'role', 'content'} and note['role'] == 'user', 'summary_note_required')
    value = json.loads(note['content'])
    require(type(value) is dict and set(value) == {'checkpoint_kind', 'semantics_verified', 'summary'}
            and value['checkpoint_kind'] == 'ordinary_fallible_summary'
            and value['semantics_verified'] is False and type(value['summary']) is dict
            and set(value['summary']) == set(FIELDS)
            and all(type(v) is list and all(type(s) is str for s in v)
                    for v in value['summary'].values()), 'fixed_summary_note_shape_required')
    notice = messages[-1]
    require(set(notice) == {'role', 'content'} and notice['role'] == 'user'
            and notice['content'].startswith(NO_TIME_NOTICE)
            and notice['content'].endswith('\n</whole_task_budget_v1>'), 'exact_budget_notice_required')
    state = json.loads(notice['content'][len(NO_TIME_NOTICE):-len('\n</whole_task_budget_v1>')])
    require(type(state) is dict and 'wall_seconds_at_snapshot' not in state.get('remaining', {}),
            'unchanged_no_time_notice_required')
    # The virtual archive removes only the synthetic previous-summary message.
    turns = closed_turns(messages[:2] + messages[3:-1])
    require(len(turns) >= 2, 'two_retained_closed_turns_required')
    end = turns[-2][0] + 1  # Convert virtual-archive offset back to request offset.
    payload = deepcopy(request)
    payload['messages'] = deepcopy(messages[:3] + messages[end:])
    require(payload['messages'][:3] == messages[:3] and payload['messages'][-1] == notice,
            'protected_messages_changed')
    other = deepcopy(payload)
    other['messages'] = messages
    require(other == request, 'nonmessage_parameters_changed')
    return payload, dict(request_message_start=3, request_message_end_exclusive=end,
                         eligible_closed_turns=len(turns)-2, retained_closed_turns=2,
                         removed_message_count=end-3,
                         removed_UTF8_bytes=len(json.dumps(messages[3:end], ensure_ascii=False,
                                                           separators=(',', ':')).encode()) - 2)


def validate_counts(original, reduced, expected_input):
    for value in (original, reduced):
        require(type(value['input_tokens']) is int and value['input_tokens'] == len(value['tokens'])
                and value['media_files'] == 0, 'native_count_shape_mismatch')
    require(original['input_tokens'] == expected_input, 'original_usage_input_count_mismatch')
    require(original['session_controls'] == reduced['session_controls']
            and original['parsed_non_message_parameters'] == reduced['parsed_non_message_parameters'],
            'counterfactual_grammar_or_parameters_changed')
    return original['input_tokens'] - reduced['input_tokens']


def exposure_totals(deltas):
    """Keep signed template effects separate from a proposed positive-part meter."""
    return dict(signed=sum(deltas), positive_part=sum(max(0, value) for value in deltas))


def effective_render_plan(historical_plan):
    # P110 binds the parser's effective template, which differs from the raw
    # GGUF template by its trailing newline. Never substitute the latter hash.
    value = historical_plan['effective_template_sha256']
    require(type(value) is str and len(value) == 64
            and all(c in '0123456789abcdef' for c in value), 'effective_template_hash_required')
    return dict(LIMITS, effective_template_sha256=value)


def prepare(root, storage, bindings):
    audit = bound_read(root/AUDIT, FIXED[AUDIT], bindings)
    plan = bound_read(root/PLAN, FIXED[PLAN], bindings)
    build = bound_read(root/BUILD, FIXED[BUILD], bindings)
    runtime = bound_read(storage/RUNTIME, FIXED[RUNTIME], bindings)
    require(audit['phase'] == 'P123' and audit['batch_status'] == 'complete'
            and audit['owned_processes_absent'] is True and not audit['audit_errors']
            and audit['all_twelve_complete_with_known_usage'] is True
            and audit['plan_sha256'] == FIXED[PLAN], 'original_complete_closed_cohort_required')
    for rel in DEPENDENCIES:
        require(sha(root/rel) == plan['source_sha256'][rel], 'fixed_dependency_changed')
        bindings[str(root/rel)] = plan['source_sha256'][rel]
    require(build['exit_code'] == 0 and sha(storage/build['renderer_relative']) == build['renderer_sha256']
            and sha(root/'scripts/render_receipt_history.cpp') == build['source_cpp_sha256'],
            'fixed_vocabulary_renderer_required')
    bindings[str(storage/build['renderer_relative'])] = build['renderer_sha256']
    for rel, h in build['library_sha256'].items():
        require(sha(storage/rel) == h, 'renderer_library_changed')
        bindings[str(storage/rel)] = h
    for rel, h in build['header_sha256'].items():
        p = storage/build['source_tree_relative']/rel
        require(sha(p) == h, 'renderer_header_changed')
        bindings[str(p)] = h
    base = read(root/'configs/P29_stateful_code_v01.json')
    selection, _, model = verified_model(base['model_selection'], root=storage)
    require(runtime['runtime']['commit'] == build['runtime_commit']
            and runtime['model_revision'] == selection['revision'] == build['metadata_inspection']['model_revision']
            and runtime['command'].count('--model') == 1
            and Path(runtime['command'][runtime['command'].index('--model')+1]).resolve() == model.resolve(),
            'original_runtime_model_required')
    cells, requests = [], []
    for rid in RUNS:
        matches = [r for r in audit['rows'] if r['run_id'] == rid]
        require(len(matches) == 1, 'all_four_original_identities_required')
        row = matches[0]
        require(row['success'] is True and row['unknown_usage_calls'] == 0
                and row['checkpoint_policy'] == 'rolling_separate', 'fixed_original_row_required')
        folder = storage/'records/context_pilot'/rid
        usage = bound_read(folder/'usage.json', row['usage_sha256'], bindings)
        controls = read(folder/'rolling_controls.json')
        require(controls == row['checkpoint_controls'], 'controls_differ_from_closed_audit')
        bindings[str(folder/'rolling_controls.json')] = sha(folder/'rolling_controls.json')
        checks = row['request_checks']
        require(len(usage) == len(checks) == row['model_calls'] and len(usage) <= 80,
                'usage_call_count_mismatch')
        for u, c in zip(usage, checks, strict=True):
            require(u['id'] == c['call_id'] and u['role'] == c['role'] and u['status'] == c['status'] == 'ok'
                    and all(u[k] == c[k] for k in ('input_tokens', 'output_tokens', 'cached_input_tokens')),
                    'closed_usage_request_check_mismatch')
        window, selected = first_window(controls, checks)
        cells.append(dict(run_id=rid, task_slot=RUNS.index(rid)+1, original_success=row['success'],
            original_known_total_tokens=row['known_total_tokens'],
            status='pending' if window else 'no_accepted_checkpoint', window=window,
            planned_actor_requests=len(selected), native_renderings=2*len(selected)))
        previous_suffix, protected = None, None
        for c in selected:
            path = folder/c['call_id']/'request.json'
            req = bound_read(path, c['request_sha256'], bindings)
            reduced, coordinates = remove_eligible(req)
            require(protected is None or req['messages'][:3] == protected,
                    'initial_pair_or_accepted_summary_changed')
            protected = deepcopy(req['messages'][:3])
            suffix = req['messages'][3:-1]
            require(previous_suffix is None or suffix[:len(previous_suffix)] == previous_suffix,
                    'raw_suffix_rewritten_or_rewound')
            previous_suffix = deepcopy(suffix)
            coordinates.update(archive_message_start=window['accepted_archive_cutoff'],
                archive_message_end_exclusive=window['accepted_archive_cutoff']+coordinates['removed_message_count'])
            requests.append(dict(run_id=rid, call_id=c['call_id'], expected_input_tokens=c['input_tokens'],
                request_sha256=c['request_sha256'], coordinates=coordinates, original=req, reduced=reduced))
    require(2*len(requests) <= LIMITS['max_renderings'], 'rendering_cap_exceeded')
    require(sum(Path(p).stat().st_size for p in bindings if '/records/context_pilot/' in p)
            <= LIMITS['max_total_private_input_bytes'], 'private_input_byte_cap_exceeded')
    return cells, requests, build, runtime, model, effective_render_plan(read(root/RENDERER_PLAN))


def run(root, storage, output):
    output.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    deadline = started + LIMITS['max_wall_seconds']
    bindings = {str(Path(__file__).resolve()): sha(Path(__file__))}
    test = root/'tests/test_checkpoint_prefix_exposure_diagnosis.py'
    bindings[str(test)] = sha(test)
    result = dict(status='failed', scope='P123_all_four_rolling_separate_first_checkpoint_window',
        started_at=datetime.now(timezone.utc).isoformat(), limits=LIMITS, cells=[], rows=[], operations=[],
        errors=[], limitation=LIMITATION, model_generations=0, environment_API_requests=0,
        evaluations=0, saved_generated_program_executions=0, task_databases_read=0,
        reserved_scenarios_read=0, original_accounting_changed=False)
    try:
        cells, requests, build, runtime, model, count_plan = prepare(root, storage, bindings)
        result['cells'] = cells
        result['rows'] = [dict(run_id=x['run_id'], call_id=x['call_id'], status='not_counted',
                              **x['coordinates']) for x in requests]
        write_new(output/'source_bindings_private.json', bindings)
        for cell in cells:
            selected = [(i, x) for i, x in enumerate(requests) if x['run_id'] == cell['run_id']]
            if not selected:
                continue
            require(time.monotonic() < deadline, 'diagnosis_deadline')
            directory = output/cell['run_id']
            directory.mkdir()
            cases = []
            for _, req in selected:
                for kind in ('original', 'reduced'):
                    key = req['call_id']+'_'+kind
                    p = directory/(key+'_request_private.json')
                    write_new(p, req[kind])
                    cases.append(dict(id=key, request_path=str(p)))
            op = dict(run_id=cell['run_id'], status='not_started', renderings=0)
            result['operations'].append(op)
            render(storage, count_plan, build, runtime, model, directory, cases, deadline, op)
            deltas = []
            for i, req in selected:
                paths = [directory/(req['call_id']+'_'+k+'_rendered_private.json') for k in ('original', 'reduced')]
                original, reduced = map(read, paths)
                require(original['id'] == req['call_id']+'_original'
                        and reduced['id'] == req['call_id']+'_reduced', 'native_case_identity_mismatch')
                delta = validate_counts(original, reduced, req['expected_input_tokens'])
                deltas.append(delta)
                totals = exposure_totals(deltas)
                result['rows'][i].update(status='counted', original_input_tokens=original['input_tokens'],
                    removed_prefix_input_tokens=delta, remaining_input_tokens=reduced['input_tokens'],
                    positive_part_prefix_input_tokens=max(0, delta),
                    cumulative_prefix_input_exposure=totals['signed'],
                    cumulative_positive_part_prefix_input_exposure=totals['positive_part'],
                    original_request_sha256=req['request_sha256'],
                    original_rendered_sha256=sha(paths[0]), reduced_rendered_sha256=sha(paths[1]))
            cell.update(status='counted', cumulative_prefix_input_exposure=totals['signed'],
                        cumulative_positive_part_prefix_input_exposure=totals['positive_part'])
        for path, expected in bindings.items():
            require(sha(path) == expected, 'input_changed_during_diagnosis')
        require(time.monotonic() <= deadline, 'diagnosis_deadline')
        result['status'] = 'complete'
    except BaseException as error:
        # Never echo parser payloads, prompts, credentials, or private reasoning.
        result['errors'].append(dict(type=type(error).__name__, reason='see_private_source_and_failed_stage'))
        raise
    finally:
        if not result['cells']:
            result['cells'] = [dict(run_id=r, status='not_completed') for r in RUNS]
        result.update(wall_seconds=time.monotonic()-started,
            completed_renderings=2*sum(r['status']=='counted' for r in result['rows']),
            source_binding_count=len(bindings))
        write_new(output/'result.json', result)
        write_new(output/'end.json', dict(status=result['status'], result_sha256=sha(output/'result.json')))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--count-once', action='store_true', required=True)
    parser.add_argument('--repo-root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--storage-root', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    try:
        result = run(args.repo_root.resolve(), args.storage_root.resolve(), args.output_dir.resolve())
        print(json.dumps({k: result[k] for k in ('status', 'completed_renderings', 'wall_seconds')}))
    except BaseException as error:
        print(json.dumps({'status': 'failed', 'exception_type': type(error).__name__}))
        raise SystemExit(1)
