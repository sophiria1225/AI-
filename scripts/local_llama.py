"""Adapter for the pinned local llama.cpp API; no hosted service or API key.

Input counting uses the server's own chat template/tokenizer. Usage remains
unknown on a failed request; it is never replaced with zero or a text estimate.
"""
import json
from pathlib import Path
import signal
import time
import urllib.parse
import urllib.request


def post(config, endpoint, payload, timeout):
    base = config.get('base_url', 'http://127.0.0.1:8011').rstrip('/')
    parsed = urllib.parse.urlsplit(base)
    if parsed.scheme != 'http' or parsed.hostname not in ('127.0.0.1', 'localhost', '::1'):
        raise ValueError('local research backend requires a loopback HTTP URL')
    request = urllib.request.Request(base + endpoint, data=json.dumps(payload).encode(),
                                     headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)


def payload_for(config, messages, tools):
    allowed = {'role', 'content', 'tool_calls', 'tool_call_id', 'name', 'reasoning_content'}
    clean = [{k: v for k, v in m.items() if k in allowed} for m in messages]
    payload = {'model': config['model'], 'messages': clean, 'stream': False,
               'temperature': config['temperature'], 'top_p': config.get('top_p', 0.95),
               'top_k': config.get('top_k', 0), 'min_p': config.get('min_p', 0.0),
               'repeat_penalty': config.get('repeat_penalty', 1.0),
               'seed': config['seed'], 'max_tokens': config['num_predict'],
               'cache_prompt': config.get('cache_prompt', True),
               'reasoning_format': 'deepseek',
               'chat_template_kwargs': {'thinking_mode': config.get('thinking_mode', 'enabled')}}
    if config.get('thinking_mode') == 'disabled':
        payload['reasoning_effort'] = 'none'
    if tools:
        payload.update(tools=tools, tool_choice='auto', parallel_tool_calls=True)
    return payload


def count_input(config, messages, tools, timeout=60):
    started = time.monotonic()
    payload = payload_for(config, messages, tools)
    result = post(config, '/v1/chat/completions/input_tokens', payload, timeout)
    count = result.get('input_tokens')
    if type(count) is not int or count < 1:
        raise ValueError('invalid input token count')
    return {'input_tokens': count, 'wall_seconds': time.monotonic() - started,
            'method': 'llama.cpp /v1/chat/completions/input_tokens'}


def parse_response(raw):
    usage = raw.get('usage', {})
    counts = [usage.get(k) for k in ('prompt_tokens', 'completion_tokens', 'total_tokens')]
    if any(type(n) is not int or n < 0 for n in counts):
        raise ValueError('missing or invalid terminal usage')
    if counts[0] + counts[1] != counts[2]:
        raise ValueError('inconsistent terminal usage')
    choices = raw.get('choices', [])
    if len(choices) != 1 or choices[0].get('finish_reason') not in ('stop', 'length', 'tool_calls'):
        raise ValueError('missing/unsupported terminal choice')
    message = choices[0]['message']
    if message.get('role') != 'assistant':
        raise ValueError('non-assistant completion')
    cache = usage.get('prompt_tokens_details', {}).get('cached_tokens')
    if cache is not None and (type(cache) is not int or not 0 <= cache <= counts[0]):
        raise ValueError('invalid cached input count')
    return {'status': 'ok', 'input_tokens': counts[0], 'output_tokens': counts[1],
            'cached_input_tokens': cache, 'done_reason': choices[0]['finish_reason'],
            'timings': raw.get('timings'), 'message': message,
            'usage_details': usage}


def model_call(config, messages, out, remaining_wall, tools):
    out = Path(out)
    payload = payload_for(config, messages, tools)
    (out / 'request.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n')
    record = {'status': 'error', 'input_tokens': None, 'output_tokens': None,
              'message': {'role': 'assistant', 'content': ''}, 'backend': 'llama.cpp'}
    started = time.monotonic()
    timeout = max(1, min(config['call_timeout_seconds'], int(remaining_wall)))
    signal.alarm(timeout)
    try:
        raw = post(config, '/v1/chat/completions', payload, timeout)
        (out / 'raw_response.json').write_text(json.dumps(raw, ensure_ascii=False, indent=2) + '\n')
        record.update(parse_response(raw))
    except Exception as error:
        record['error'] = repr(error)
    finally:
        signal.alarm(0)
        record['wall_seconds'] = time.monotonic() - started
        (out / 'response.json').write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n')
    return record
