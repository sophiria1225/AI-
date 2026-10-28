"""Native output-shape constraints for the fixed P144 update contract.

The grammar constrains object shape, bounded arrays, index ranges and strings.
It does not enforce the cross-operation partition of old indices or total
materialized size. The unchanged P144 parser remains authoritative for those
checks. No old state text is embedded in the schema or inferred as true.
"""
from copy import deepcopy
import json

from checkpoint_state_update_p144 import (
    UPDATE_SUMMARY_PROMPT, apply_update_patch, parse_update_patch,
    validate_fragment_budget,
)
from single_checkpoint_history import FIELDS

SCHEMA_NAME = 'checkpoint_update_p145'
REASONING_BUDGETS = (-1, 2048)


def _require(condition, reason):
    if not condition:
        raise ValueError(reason)


def schema_for(old_state):
    """Return the supported bounded schema; semantic checks remain on the host."""
    validate_fragment_budget([old_state])
    properties = {}
    for field in FIELDS:
        count = len(old_state[field])
        index = {'type': 'integer', 'minimum': 0, 'maximum': max(0, count - 1)}
        text = {'type': 'string', 'minLength': 1, 'maxLength': 2048}
        update = {'type': 'object', 'properties': {
            'index': deepcopy(index), 'text': deepcopy(text)},
            'required': ['index', 'text'], 'additionalProperties': False}
        operations = {
            'keep': {'type': 'array', 'items': deepcopy(index), 'minItems': 0, 'maxItems': count},
            'update': {'type': 'array', 'items': update, 'minItems': 0, 'maxItems': count},
            'delete': {'type': 'array', 'items': deepcopy(index), 'minItems': 0, 'maxItems': count},
            'add': {'type': 'array', 'items': deepcopy(text), 'minItems': 0, 'maxItems': 32},
        }
        properties[field] = {'type': 'object', 'properties': operations,
            'required': ['keep', 'update', 'delete', 'add'], 'additionalProperties': False}
    return {'type': 'object', 'properties': properties, 'required': list(FIELDS),
            'additionalProperties': False}


def structured_payload(saved_request, old_state, reasoning_budget):
    """Copy a saved update request, changing only schema and reasoning budget.

Counting and generation must both use the returned payload unchanged. Native
control construction and fresh-server ownership are the caller's responsibility.
"""
    _require(type(saved_request) is dict, 'saved_focus_request_object_required')
    _require(type(reasoning_budget) is int and reasoning_budget in REASONING_BUDGETS,
             'fixed_P145_reasoning_budget_required')
    _require(type(saved_request.get('max_tokens')) is int and
             saved_request['max_tokens'] == 4096, 'unchanged_4096_output_cap_required')
    _require(saved_request.get('stream') is False, 'nonstreaming_saved_focus_required')
    _require(not any(key in saved_request for key in (
        'tools', 'tool_choice', 'parallel_tool_calls', 'grammar', 'json_schema',
        'response_format', 'reasoning_effort', 'thinking_budget_tokens')),
        'conflicting_saved_focus_transport')
    _require(saved_request.get('reasoning_format') == 'deepseek' and
             saved_request.get('chat_template_kwargs') == {'thinking_mode': 'enabled'},
             'unchanged_saved_thinking_transport_required')
    _require(type(saved_request.get('reasoning_budget_tokens')) is int and
             saved_request['reasoning_budget_tokens'] == -1,
             'original_unlimited_saved_focus_required')
    messages = saved_request.get('messages')
    _require(type(messages) is list and len(messages) == 2 and
             messages[0] == {'role': 'system', 'content': UPDATE_SUMMARY_PROMPT} and
             type(messages[1]) is dict and messages[1].get('role') == 'user' and
             type(messages[1].get('content')) is str, 'frozen_update_messages_required')
    supplied = json.loads(messages[1]['content'])
    _require(type(supplied) is dict and supplied.get('previous_checkpoint') == old_state,
             'schema_must_match_supplied_old_state')
    result = deepcopy(saved_request)
    result['reasoning_budget_tokens'] = reasoning_budget
    result['response_format'] = {'type': 'json_schema', 'json_schema': {
        'name': SCHEMA_NAME, 'strict': True, 'schema': schema_for(old_state)}}
    return result


def parse_and_apply(message, finish_reason, old_state):
    """Validate with the frozen host contract, without repairing any response."""
    patch = parse_update_patch(message, finish_reason, old_state)
    state, counts = apply_update_patch(old_state, patch)
    return state, counts
