"""Ordinary auto/required tool choice with unchanged -1 reasoning budget.

Counting and generation receive the identical choice. Requiring a tool does not
guarantee completion within a finite output cap or Python correctness.
"""
import json
from pathlib import Path
import signal
import time

from local_llama import parse_response, payload_for as original_payload_for, post


def reasoning_budget(config):
    value = config.get('reasoning_budget_tokens')
    if type(value) is not int or value != -1:
        raise ValueError('unchanged_unlimited_reasoning_required')
    if (config.get('thinking_mode', 'enabled') != 'enabled'
            or any(k in config for k in ('reasoning_effort', 'thinking_budget_tokens',
                                        'reasoning_control', 'reasoning_budget_message'))):
        raise ValueError('conflicting_reasoning_control')
    return value


def tool_choice(config):
    value = config.get('tool_choice')
    if type(value) is not str or value not in ('auto', 'required'):
        raise ValueError('explicit_ordinary_tool_choice_required')
    if any(k in config for k in ('grammar', 'json_schema', 'response_format', 'tool_choice_override')):
        raise ValueError('conflicting_format_control')
    return value


def payload_for(config, messages, tools):
    value = reasoning_budget(config)
    choice = tool_choice(config)
    if not tools:
        raise ValueError('declared_tools_required_in_both_conditions')
    return {**original_payload_for(config, messages, tools),
            'reasoning_budget_tokens': value, 'tool_choice': choice}


def count_input(config, messages, tools, timeout=60):
    started = time.monotonic()
    payload = payload_for(config, messages, tools)
    result = post(config, '/v1/chat/completions/input_tokens', payload, timeout)
    count = result.get('input_tokens')
    if type(count) is not int or count < 1:
        raise ValueError('invalid input token count')
    return {'input_tokens': count, 'wall_seconds': time.monotonic() - started,
            'method': 'llama.cpp /v1/chat/completions/input_tokens'}


def model_call(config, messages, out, remaining_wall, tools):
    out = Path(out)
    payload = payload_for(config, messages, tools)
    (out / 'request.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n')
    record = {'status': 'error', 'input_tokens': None, 'output_tokens': None,
              'message': {'role': 'assistant', 'content': ''}, 'backend': 'llama.cpp'}
    started = time.monotonic()
    timeout = max(1, min(config['call_timeout_seconds'], int(remaining_wall)))
    record.update(timeout_seconds=timeout,
                  timeout_scope=('run_wall' if remaining_wall <= config['call_timeout_seconds']
                                 else 'call'),
                  error_kind=None)
    signal.alarm(timeout)
    try:
        raw = post(config, '/v1/chat/completions', payload, timeout)
        (out / 'raw_response.json').write_text(json.dumps(raw, ensure_ascii=False, indent=2) + '\n')
        record.update(parse_response(raw))
    except Exception as error:
        record['error'] = repr(error)
        record['error_kind'] = ('timeout' if isinstance(error, TimeoutError)
                                or isinstance(getattr(error, 'reason', None), TimeoutError)
                                else 'request_or_response')
    finally:
        signal.alarm(0)
        record['wall_seconds'] = time.monotonic() - started
        (out / 'response.json').write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n')
    return record
