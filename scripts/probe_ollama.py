"""Bounded local connectivity checks; not a research benchmark."""
import datetime
import json
import pathlib
import signal
import time
import urllib.request
import uuid

ROOT = pathlib.Path(__file__).resolve().parents[1]
MODEL = 'qwen3.8-flash-next:125b-mlx'
RUN = ROOT / 'records' / 'model_probes' / (datetime.datetime.now().strftime('%Y%m%d_%H%M%S') + '_' + uuid.uuid4().hex[:8])
RUN.mkdir(parents=True)
summary = {'run_id': RUN.name, 'scope': 'synthetic_connection_check_not_E0', 'model': MODEL, 'calls': []}

def timeout_handler(signum, frame):
    raise TimeoutError('120 second wall-clock call limit reached')

signal.signal(signal.SIGALRM, timeout_handler)

def call(label, messages, tools=None):
    if len(summary['calls']) >= 3:
        raise RuntimeError('call budget exhausted')
    if sum((c.get('input_tokens') or 0) + (c.get('output_tokens') or 0) for c in summary['calls']) >= 12000:
        raise RuntimeError('token budget exhausted')
    payload = {'model': MODEL, 'messages': messages, 'stream': True, 'think': False,
               'keep_alive': '2m', 'options': {'num_ctx': 8192, 'num_predict': 256, 'temperature': 0, 'seed': 7}}
    if tools:
        payload['tools'] = tools
    (RUN / (label + '_request.json')).write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    record = {'label': label, 'started_at': datetime.datetime.now(datetime.timezone.utc).isoformat()}
    start = time.monotonic()
    final = None
    message = {'role': 'assistant', 'content': ''}
    signal.alarm(120)
    try:
        request = urllib.request.Request('http://127.0.0.1:11434/api/chat', data=json.dumps(payload).encode(),
                                         headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(request, timeout=120) as response, (RUN / (label + '_events.jsonl')).open('w') as out:
            for line in response:
                event = json.loads(line)
                out.write(json.dumps(event, ensure_ascii=False) + '\n')
                out.flush()
                if 'error' in event:
                    raise RuntimeError(event['error'])
                msg = event.get('message', {})
                message['content'] += msg.get('content', '')
                if msg.get('tool_calls'):
                    message.setdefault('tool_calls', []).extend(msg['tool_calls'])
                if msg.get('thinking'):
                    message['thinking'] = message.get('thinking', '') + msg['thinking']
                if event.get('done'):
                    final = event
                    break
        if final is None:
            raise RuntimeError('stream ended without terminal metrics')
        for key in ['prompt_eval_count', 'eval_count']:
            if not isinstance(final.get(key), int):
                raise RuntimeError('missing usage counter: ' + key)
        record.update(status='ok', input_tokens=final['prompt_eval_count'], output_tokens=final['eval_count'],
                      cached_input_tokens=final.get('prompt_eval_cached_count'), done_reason=final.get('done_reason'),
                      load_seconds=final.get('load_duration', 0) / 1e9,
                      decode_seconds=final.get('eval_duration', 0) / 1e9, message=message)
        if record['decode_seconds']:
            record['decode_tokens_per_second'] = record['output_tokens'] / record['decode_seconds']
    except Exception as error:
        record.update(status='error', error=repr(error), input_tokens=None, output_tokens=None)
        raise
    finally:
        signal.alarm(0)
        record['wall_seconds'] = time.monotonic() - start
        summary['calls'].append(record)
        (RUN / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n')
        print(json.dumps(record, ensure_ascii=False), flush=True)
    return message

try:
    first = call('json', [{'role': 'user', 'content': 'Return only JSON with keys status and sum. status must be "ok". sum must equal 17 + 25.'}])
    parsed = json.loads(first['content'])
    if parsed != {'status': 'ok', 'sum': 42}:
        raise RuntimeError('unexpected JSON probe result')
    tool_schema = [{'type': 'function', 'function': {'name': 'lookup_constraint', 'description': 'Read the authoritative fixture constraint for an item.',
                    'parameters': {'type': 'object', 'properties': {'item': {'type': 'string', 'enum': ['record_key']}}, 'required': ['item']}}}]
    messages = [{'role': 'user', 'content': 'Use lookup_constraint for record_key. Do not guess. After reading the tool result, respond with JSON containing max_length and evidence_id.'}]
    second = call('tool_request', messages, tool_schema)
    requests = second.get('tool_calls', [])
    if len(requests) != 1 or requests[0]['function']['name'] != 'lookup_constraint' or requests[0]['function']['arguments'] != {'item': 'record_key'}:
        raise RuntimeError('unexpected tool request; no tool executed')
    messages.extend([second, {'role': 'tool', 'tool_name': 'lookup_constraint', 'content': json.dumps({'max_length': 47, 'evidence_id': 'fixture-P0-7'})}])
    third = call('tool_result', messages, tool_schema)
    if json.loads(third['content']) != {'max_length': 47, 'evidence_id': 'fixture-P0-7'}:
        raise RuntimeError('tool result not used correctly')
    summary['passed'] = True
except Exception as error:
    summary.update(passed=False, failure=repr(error))
finally:
    summary['total_recorded_tokens'] = sum((c.get('input_tokens') or 0) + (c.get('output_tokens') or 0) for c in summary['calls'])
    summary['usage_complete'] = all(c.get('input_tokens') is not None and c.get('output_tokens') is not None for c in summary['calls'])
    (RUN / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'path': str(RUN), 'passed': summary['passed'], 'usage_complete': summary['usage_complete']}, ensure_ascii=False))
