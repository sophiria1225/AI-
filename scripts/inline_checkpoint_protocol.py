"""Pure prototype of an ordinary checkpoint carried with a Python tool call.

No model, Python program, API, evaluator, or budget controller runs here. The
caller must meter the entire original response and execute the extracted action
once. A complete old prefix and one closed new turn are required for projection.
No execution receipt or successful return proves semantic summary fidelity.
"""
from copy import deepcopy
import json

from context_preservation import compact
from receipt_reasoning_history import digest, require
from single_checkpoint_history import FIELDS, candidate, closed_turns, parse_checkpoint, project


def inline_tools(base_tools):
    """Offer the extra field for one requested turn; leave source schemas intact."""
    tools = deepcopy(base_tools)
    choices = [t['function'] for t in tools if t.get('function', {}).get('name') == 'run_python']
    require(len(choices) == 1, 'one_python_tool_required')
    params = choices[0]['parameters']
    require(set(params['properties']) == {'code', 'span_ids'} and
            set(params['required']) == {'code', 'span_ids'} and
            params['additionalProperties'] is False, 'original_python_arguments_required')
    params['properties']['checkpoint'] = {
        'type': 'object', 'description': 'Fallible summary of the requested older history only; '
            'not the results of this not-yet-executed program.',
        'properties': {name: {'type': 'array', 'maxItems': 32,
            'items': {'type': 'string', 'minLength': 1, 'maxLength': 2048}} for name in FIELDS},
        'required': list(FIELDS), 'additionalProperties': False}
    return tools


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'duplicate_inline_argument_key')
        result[key] = value
    return result


def _invalid_constant(value):
    raise ValueError('nonfinite_inline_argument')


def _payload(message):
    """Archival payload, allowing only protocol-reference renaming and null text."""
    content = message.get('content')
    calls = message.get('tool_calls')
    require(content is None or type(content) is str, 'text_assistant_content_required')
    require(calls is None or (type(calls) is list and all(type(call) is dict for call in calls)),
            'tool_call_objects_required')
    value = {'role': message.get('role'), 'content': '' if content is None else content,
             'tool_calls': [{k: deepcopy(v) for k, v in call.items() if k != 'id'}
                            for call in calls or []]}
    if 'reasoning_content' in message:
        value['reasoning_content'] = message['reasoning_content']
    return value


def split_inline_response(message, *, offered, finish_reason, usage_known):
    """Separate metadata without changing code or span IDs; never execute it.

    Unsupported shapes stay unchanged for the ordinary execution path. A valid
    action with invalid summary metadata remains a valid extracted action. A
    missing usage record blocks all extraction for execution.
    """
    require(usage_known is True, 'unknown_usage_blocks_inline_execution')
    require(type(message) is dict and message.get('role') == 'assistant', 'assistant_required')
    result = {'execution_message': deepcopy(message), 'checkpoint': None, 'binding': None,
              'original_payload_sha256': digest(_payload(message)),
              'status': 'not_offered_keep_original', 'semantics_verified': False}
    if not offered:
        return result
    result['status'] = 'unsupported_response_keep_original'
    calls = message.get('tool_calls') or []
    if len(calls) != 1 or calls[0].get('type') != 'function':
        return result
    fn = calls[0].get('function', {})
    if type(fn) is not dict or fn.get('name') != 'run_python':
        return result
    try:
        args = json.loads(fn['arguments'], object_pairs_hook=_unique_pairs,
                          parse_constant=_invalid_constant)
        require(type(args) is dict and set(args) <= {'code', 'span_ids', 'checkpoint'} and
                {'code', 'span_ids'} <= set(args), 'exact_inline_argument_fields_required')
        require(type(args['code']) is str and 0 < len(args['code']) <= 20000 and
                type(args['span_ids']) is list and len(args['span_ids']) <= 160 and
                all(type(s) is str for s in args['span_ids']) and
                len(set(args['span_ids'])) == len(args['span_ids']), 'valid_base_python_arguments_required')
    except (ValueError, TypeError, KeyError, RecursionError):
        result['status'] = 'invalid_envelope_keep_original'
        return result
    if 'checkpoint' not in args:
        result['status'] = 'checkpoint_absent_keep_original'
        return result
    executable = {key: deepcopy(args[key]) for key in ('code', 'span_ids')}
    action = deepcopy(fn)
    action['arguments'] = json.dumps(executable, ensure_ascii=False, separators=(',', ':'), allow_nan=False)
    result['execution_message']['tool_calls'][0]['function'] = action
    result['binding'] = {'original_function_sha256': digest(fn),
                         'executable_function_sha256': digest(action),
                         'code_sha256': digest(args['code']), 'span_ids_sha256': digest(args['span_ids']),
                         'metadata_sha256': digest(args['checkpoint'])}
    try:
        require(finish_reason == 'tool_calls', 'complete_tool_response_required')
        # Outer framing is a complete tool response; only the shared structural
        # summary validator is reused with a synthetic text envelope.
        text = json.dumps(args['checkpoint'], ensure_ascii=False, separators=(',', ':'), allow_nan=False)
        result['checkpoint'] = parse_checkpoint({'role': 'assistant', 'content': text}, 'stop')
        result['status'] = 'checkpoint_structurally_valid'
    except (ValueError, TypeError, RecursionError):
        result['status'] = 'invalid_checkpoint_keep_old_history'
    return result


def _matches_received(rendered, split):
    if digest(_payload(rendered)) == split['original_payload_sha256']:
        return True
    # The ordinary renderer retains malformed/non-object calls as text. Bind
    # that exact fallback to the received payload instead of treating arbitrary
    # model-written JSON as a tool envelope. Such a response cannot compact.
    if split['binding'] is not None or rendered.get('tool_calls'):
        return False
    try:
        value = json.loads(rendered['content'], object_pairs_hook=_unique_pairs)
        require(type(value) is dict and set(value) == {'assistant_text', 'tool_call_records'},
                'exact_renderer_fallback_required')
        require(compact(value) == rendered['content'], 'exact_renderer_serialization_required')
        original = {**rendered, 'content': value['assistant_text'],
                    'tool_calls': value['tool_call_records']}
        calls = original['tool_calls']
        require(type(calls) is list and len(calls) > 0, 'fallback_calls_required')
        malformed = False
        for call in calls:
            try:
                malformed |= type(json.loads(call['function']['arguments'])) is not dict
            except (ValueError, TypeError):
                malformed = True
        return malformed and digest(_payload(original)) == split['original_payload_sha256']
    except (ValueError, TypeError, KeyError, RecursionError):
        return False


def projection_after_turn(before, after, split):
    """Return both display candidates only after the offered turn closes.

    Accepted sidecar transport is stripped from the action's displayed arguments
    in BOTH candidates, avoiding duplicate summary replay. The original archive
    is unchanged. This metadata omission is an explicit part of the prototype,
    including when the summary is invalid or is later rejected for length.
    """
    require(type(split) is dict, 'bound_inline_split_required')
    old_turns, new_turns = closed_turns(before), closed_turns(after)
    require(after[:len(before)] == before and len(new_turns) == len(old_turns) + 1,
            'exact_source_prefix_and_one_closed_new_turn_required')
    assistant_position = len(before)
    require(_matches_received(after[assistant_position], split),
            'closed_turn_differs_from_received_response')
    ordinary = deepcopy(after)
    binding = split['binding']
    if binding is not None:
        original_fn = ordinary[assistant_position]['tool_calls'][0]['function']
        action = split['execution_message']['tool_calls'][0]['function']
        require(digest(original_fn) == binding['original_function_sha256'] and
                digest(action) == binding['executable_function_sha256'], 'inline_action_binding_changed')
        original_args = json.loads(original_fn['arguments'], object_pairs_hook=_unique_pairs)
        executed_args = json.loads(action['arguments'], object_pairs_hook=_unique_pairs)
        require(set(executed_args) == {'code', 'span_ids'} and
                executed_args == {k: original_args[k] for k in ('code', 'span_ids')} and
                digest(original_args['checkpoint']) == binding['metadata_sha256'] and
                digest(executed_args['code']) == binding['code_sha256'] and
                digest(executed_args['span_ids']) == binding['span_ids_sha256'],
                'metadata_removal_must_not_change_action')
        ordinary[assistant_position]['tool_calls'][0]['function'] = deepcopy(action)
    proposal = candidate(before)
    compacted = None
    if split['checkpoint'] is not None:
        require(binding is not None and proposal is not None, 'eligible_old_prefix_required')
        require(digest(split['checkpoint']) == binding['metadata_sha256'], 'checkpoint_value_changed')
        compacted = project(ordinary, proposal, split['checkpoint'])
    return {'ordinary': ordinary, 'compacted': compacted,
            'before_sha256': digest(before), 'after_sha256': digest(after),
            'ordinary_sha256': digest(ordinary),
            'compacted_sha256': digest(compacted) if compacted is not None else None,
            'transport_metadata_hidden': binding is not None, 'archive_deleted': False,
            'same_call_observations_summarized': False, 'semantics_verified': False}


def choose_counted_projection(views, ordinary_input_tokens, compacted_input_tokens):
    """Choose between already metered views; this function is not a tokenizer."""
    require(digest(views['ordinary']) == views['ordinary_sha256'], 'counted_ordinary_view_changed')
    require(type(ordinary_input_tokens) is int and ordinary_input_tokens > 0, 'native_ordinary_count_required')
    if views['compacted'] is None:
        require(compacted_input_tokens is None, 'no_count_for_absent_checkpoint')
        return deepcopy(views['ordinary']), False
    require(digest(views['compacted']) == views['compacted_sha256'], 'counted_compacted_view_changed')
    require(type(compacted_input_tokens) is int and compacted_input_tokens > 0, 'native_compacted_count_required')
    accepted = compacted_input_tokens < ordinary_input_tokens
    return deepcopy(views['compacted'] if accepted else views['ordinary']), accepted
