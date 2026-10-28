"""P147 update-only transport; P147 fixed indexed representation is the fixed candidate.

The P144 saved user packet, sampling and 4096 output cap are retained.
Only the UPDATE system prompt, response_format and reasoning_budget_tokens differ. No task action is
executed here. Count and generation bind the exact same request digest.
"""
import json
from pathlib import Path
import signal
import time

from checkpoint_indexed_update_p147 import payload_for as indexed_payload_for
from fixed_budget_local_llama import payload_for as native_payload_for
from local_llama import parse_response, post
from receipt_reasoning_history import digest, require

TRANSPORT = 'schema_indexed_bounded'
REASONING_BUDGET = 2048


def payload_for(config, messages, tools, old_state):
    require(tools == [], 'P147_update_focus_has_no_tools')
    native = native_payload_for(config, messages, tools)
    return indexed_payload_for(native, old_state)


def count_input(config, messages, tools, old_state, timeout=60):
    started = time.monotonic()
    payload = payload_for(config, messages, tools, old_state)
    result = post(config, '/v1/chat/completions/input_tokens', payload, timeout)
    count = result.get('input_tokens')
    require(type(count) is int and count > 0, 'positive_native_input_count_required')
    return dict(input_tokens=count, wall_seconds=time.monotonic()-started,
        method='llama.cpp /v1/chat/completions/input_tokens',
        request_sha256=digest(payload), update_transport=TRANSPORT,
        reasoning_budget_tokens=REASONING_BUDGET)


def model_call(config, messages, out, remaining_wall, tools, old_state, *, expected_request_sha256):
    out = Path(out)
    payload = payload_for(config, messages, tools, old_state)
    require(digest(payload) == expected_request_sha256, 'P147_count_generation_payload_mismatch')
    (out/'request.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2)+'\n')
    record = dict(status='error', input_tokens=None, output_tokens=None,
        message={'role':'assistant','content':''}, backend='llama.cpp',
        request_sha256=digest(payload), update_transport=TRANSPORT,
        reasoning_budget_tokens=REASONING_BUDGET)
    started = time.monotonic()
    timeout = max(1, min(config['call_timeout_seconds'], int(remaining_wall)))
    record.update(timeout_seconds=timeout,
        timeout_scope='run_wall' if remaining_wall <= config['call_timeout_seconds'] else 'call',
        error_kind=None)
    signal.alarm(timeout)
    try:
        raw = post(config, '/v1/chat/completions', payload, timeout)
        (out/'raw_response.json').write_text(json.dumps(raw, ensure_ascii=False, indent=2)+'\n')
        record.update(parse_response(raw))
    except Exception as error:
        record['error'] = repr(error)
        record['error_kind'] = ('timeout' if isinstance(error, TimeoutError)
            or isinstance(getattr(error, 'reason', None), TimeoutError) else 'request_or_response')
    finally:
        signal.alarm(0)
        record['wall_seconds'] = time.monotonic()-started
        (out/'response.json').write_text(json.dumps(record, ensure_ascii=False, indent=2)+'\n')
    return record
