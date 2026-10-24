"""Reconstruct controlled input views from closed, handwritten observations.

This never evaluates the saved source. The ordinary interface is called with a
callback that returns a recorded result and records the saved API receipts. The
content-only representation is an attribution ablation, not an agent policy.
"""
import copy
from collections import Counter
import hashlib
import json
from pathlib import Path

from code_agent_interface import execute_response
from native_data_compute import selected_receipts
from protocol_stable_history import StableReferenceConversation
from public_display import capability_prompt
from stateful_code_prompts import stateful_system_prompt

POLICIES = ('eager', 'deferred')
REPRESENTATIONS = ('harness', 'content_attribution')
EXPECTED_API = {'eager': [6, 1, 0, 1, 1, 2], 'deferred': [6, 0, 1, 0, 0, 3]}
RESULT_FIELDS = ('status', 'stdout', 'stdout_truncated', 'api_requests',
                 'declared_complete', 'unknown_effects')
CONTENT_FIELDS = ('status', 'stdout', 'stdout_truncated', 'declared_complete',
                  'unknown_effects', 'error')
VIEW_GUIDE = '''
read_view(app, api, **arguments) explicitly requests a read-only Mapping view.
It is not a dict. A supported view can use fields already supplied by a verified
public response. Unknown fields and whole-value operations materialize the
original API result. Pending reads reserve the shared API budget. Before a
possibly state-changing API, outstanding reads are materialized against the
earlier state. Releasing the last reference can cancel an unmaterialized read.
Keep required values in Python and print the facts needed for the next decision.
'''


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                         separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def system_prompt(original):
    return capability_prompt(stateful_system_prompt(original)) + VIEW_GUIDE


class ForbiddenRuntime:
    """Fail loudly if reconstruction tries to discover or execute anything."""
    def __getattr__(self, name):
        raise AssertionError('no_live_runtime_in_input_reconstruction:' + name)


def validate_inventory(policy, programs, evidences, api_rows, public_condition):
    if policy not in POLICIES or len(programs) != 6 or len(evidences) != 6:
        raise ValueError('all_six_handwritten_programs_required')
    if (public_condition['policy'] != policy or public_condition['status'] != 'complete'
            or len(public_condition['programs']) != 6
            or len(api_rows) != sum(EXPECTED_API[policy])
            or public_condition['api_rows_recorded'] != len(api_rows)):
        raise ValueError('closed_full_policy_inventory_required')
    if any(type(p) is not str or not 0 < len(p) <= 20000 for p in programs):
        raise ValueError('fixed_program_source_required')
    for number, (evidence, public, expected) in enumerate(zip(
            evidences, public_condition['programs'], EXPECTED_API[policy], strict=True), 1):
        result = evidence['result']
        if (evidence.get('original_generated_source_unchanged') is not True
                or public['number'] != number or result['status'] != 'ok'
                or type(result['api_requests']) is not int or result['api_requests'] != expected
                or type(result['stdout']) is not str
                or any(result.get(k) is not False for k in
                       ('unknown_effects', 'declared_complete', 'stdout_truncated'))):
            raise ValueError('original_program_result_changed')
        for key in ('status', 'api_requests', 'unknown_effects', 'declared_complete',
                    'stdout_truncated', 'wall_seconds'):
            if result[key] != public[key]:
                raise ValueError('old_public_program_metadata_changed:' + key)
        if hashlib.sha256(result['stdout'].encode()).hexdigest() != public['stdout_sha256']:
            raise ValueError('old_public_stdout_hash_changed')
        for key in ('control_requests', 'control_request_bytes', 'control_reply_bytes'):
            if evidence[key] != public[key]:
                raise ValueError('old_control_accounting_changed')
    if dict(Counter(r['action']['name'] for r in api_rows)) != public_condition['api_names']:
        raise ValueError('old_API_inventory_changed')
    if any(r.get('api_request_sent') is not True or r.get('effects_unknown', False)
           for r in api_rows):
        raise ValueError('confirmed_original_API_receipts_required')


def reconstruct(policy, representation, programs, evidences, api_rows, public_condition,
                *, prompt, public_task, page_limit):
    validate_inventory(policy, programs, evidences, api_rows, public_condition)
    if representation not in REPRESENTATIONS:
        raise ValueError('fixed_representation_required')
    conversation = StableReferenceConversation(prompt, public_task)
    spans = {}
    boundaries = []
    consumed = 0
    for number, (source, evidence) in enumerate(zip(programs, evidences, strict=True), 1):
        fn = {'name': 'run_python', 'arguments': json.dumps(
            {'code': source, 'span_ids': []}, ensure_ascii=False, separators=(',', ':'))}
        message = {'role': 'assistant', 'content': '', 'tool_calls': [
            {'id': f'manual_program_{number}', 'type': 'function', 'function': fn}]}
        visible = []
        receipt_count = EXPECTED_API[policy][number - 1]
        selected = api_rows[consumed:consumed + receipt_count]
        consumed += receipt_count
        callback_calls = 0

        def record(row, display=True):
            sid = f's{len(spans) + 1}'
            span = {'id': sid, 'assistant': '', 'action': copy.deepcopy(row['action']),
                    'observation': copy.deepcopy(row['observation'])}
            spans[sid] = span
            if display:
                visible.append(span)
            return sid

        def recorded_program(received_source, observations, channel, *, on_record, **kwargs):
            nonlocal callback_calls
            callback_calls += 1
            if received_source != source or observations or channel.rows:
                raise AssertionError('recorded_callback_inputs_changed')
            for saved in selected:
                on_record(copy.deepcopy(saved))
            return copy.deepcopy(evidence['result'])

        rows = execute_response(message, ForbiddenRuntime(), ForbiddenRuntime(),
            selected_receipts(list(spans), spans), record,
            out=Path('/unused_P104_record'), storage=Path('/unused_P104_storage'),
            call_id=f'manual_{number}', remaining_api=lambda: 100,
            may_continue=lambda: True, remaining_wall=lambda: 90,
            read_archive=lambda *_: (_ for _ in ()).throw(AssertionError('no_read_span')),
            program=recorded_program)
        if (callback_calls != 1 or len(rows) != receipt_count + 1 or len(visible) != 1
                or visible[0]['observation'].get('status') != 'ok'
                or len(visible[0]['observation']['api_receipts']) != receipt_count):
            raise ValueError('ordinary_interface_reconstruction_failed')
        if representation == 'content_attribution':
            visible = copy.deepcopy(visible)
            visible[0]['id'] = f'program_{number}'
            visible[0]['observation'] = {k: visible[0]['observation'][k] for k in CONTENT_FIELDS}
        conversation.append(message, visible)
        messages, formatting = conversation.for_model(page_limit)
        boundaries.append(dict(number=number, after_program=number,
            includes_terminal_boundary=number == 6, messages=messages,
            messages_sha256=digest(messages), formatting=formatting,
            program_sha256=hashlib.sha256(source.encode()).hexdigest(),
            stdout_sha256=hashlib.sha256(evidence['result']['stdout'].encode()).hexdigest(),
            original_program_API_requests=receipt_count,
            original_cumulative_API_requests=consumed,
            outer_observation_sha256=digest(visible[0]['observation'])))
    if consumed != len(api_rows):
        raise ValueError('every_original_API_receipt_must_be_accounted')
    return boundaries


def compare_boundaries(rows):
    """No sums pretending these hypothetical next inputs are observed usage."""
    keys = [(r['policy'], r['representation'], r['after_program']) for r in rows]
    expected = {(p, v, n) for p in POLICIES for v in REPRESENTATIONS for n in range(1, 7)}
    if len(rows) != 24 or set(keys) != expected:
        raise ValueError('all_twenty_four_renderings_required')
    lookup = dict(zip(keys, rows, strict=True))
    result = []
    for view in REPRESENTATIONS:
        for number in range(1, 7):
            a, b = (lookup[p, view, number] for p in POLICIES)
            if any(type(r['input_tokens']) is not int or r['input_tokens'] <= 0 for r in (a, b)):
                raise ValueError('exact_positive_token_counts_required')
            same_content = a['stdout_sha256'] == b['stdout_sha256']
            if not same_content or a['program_sha256'] != b['program_sha256']:
                raise ValueError('common_handwritten_source_and_stdout_required')
            result.append(dict(representation=view, after_program=number,
                includes_terminal_boundary=number == 6,
                eager_input_tokens=a['input_tokens'], deferred_input_tokens=b['input_tokens'],
                deferred_minus_eager_input_tokens=b['input_tokens'] - a['input_tokens'],
                stdout_equal=same_content, messages_equal=a['messages_sha256'] == b['messages_sha256'],
                prompt_equal=a['prompt_sha256'] == b['prompt_sha256'],
                token_sequence_equal=a['tokens_sha256'] == b['tokens_sha256'],
                session_controls_equal=a['session_controls_sha256'] == b['session_controls_sha256'],
                non_message_parameters_equal=a['parsed_non_message_parameters_sha256'] == b['parsed_non_message_parameters_sha256']))
    return result
