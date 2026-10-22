"""Bounded SSE reconstruction with separate usage and message authority.

Intermediate llama.cpp predicted_n is a lower bound, never terminal usage.
prompt_n is processed prompt tokens, not the full logical input count.
No generated tool call can be returned before a complete validated stream.
"""
import json

from local_llama import parse_response


class StreamProtocolError(ValueError):
    pass


def integer(value):
    return type(value) is int and value >= 0


def strict_json(text):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('duplicate JSON key')
            result[key] = value
        return result
    def constant(_):
        raise ValueError('nonfinite JSON number')
    return json.loads(text, object_pairs_hook=pairs, parse_constant=constant)


class SSEDecoder:
    def __init__(self, max_wire_bytes=8 * 1024 * 1024, max_event_bytes=1024 * 1024):
        if not integer(max_wire_bytes) or not integer(max_event_bytes) or not 0 < max_event_bytes <= max_wire_bytes:
            raise ValueError('invalid stream bounds')
        self.max_wire_bytes = max_wire_bytes
        self.max_event_bytes = max_event_bytes
        self.total = 0
        self.pending = b''
        self.data = []
        self.event_bytes = 0
        self.failed = False

    def feed(self, chunk):
        if self.failed:
            raise StreamProtocolError('decoder_failed')
        try:
            if type(chunk) is not bytes:
                raise StreamProtocolError('wire_bytes_required')
            self.total += len(chunk)
            if self.total > self.max_wire_bytes:
                raise StreamProtocolError('wire_limit')
            self.pending += chunk
            result = []
            while b'\n' in self.pending:
                line, self.pending = self.pending.split(b'\n', 1)
                if line.endswith(b'\r'):
                    line = line[:-1]
                self.event_bytes += len(line) + 1
                if self.event_bytes > self.max_event_bytes:
                    raise StreamProtocolError('event_limit')
                if not line:
                    if self.data:
                        result.append(b'\n'.join(self.data).decode('utf-8', errors='strict'))
                    self.data, self.event_bytes = [], 0
                elif line.startswith(b'data:'):
                    value = line[5:]
                    self.data.append(value[1:] if value.startswith(b' ') else value)
                elif line.startswith(b':'):
                    pass
                else:
                    raise StreamProtocolError('unsupported_sse_field')
            if self.event_bytes + len(self.pending) > self.max_event_bytes:
                raise StreamProtocolError('event_limit')
            return result
        except (ValueError, UnicodeError):
            self.failed = True
            raise StreamProtocolError('invalid_or_oversized_sse') from None

    def finish(self):
        if self.failed or self.pending or self.data:
            raise StreamProtocolError('truncated_sse_event')


class CompletionReceipt:
    def __init__(self):
        self.response_id = None
        self.identity = None
        self.content = ''
        self.reasoning = ''
        self.tool_calls = {}
        self.finish_reason = None
        self.usage = None
        self.timings = None
        self.done = False
        self.valid = True
        self.events = 0
        self.output_lower_bound = 0
        self.prompt_progress = None

    def consume(self, text):
        if not self.valid:
            raise StreamProtocolError('receipt_failed')
        try:
            self._consume(text)
        except (ValueError, TypeError, KeyError, IndexError, RecursionError):
            self.valid = False
            raise StreamProtocolError('invalid_completion_stream') from None

    def _consume(self, text):
        if self.done:
            raise ValueError('after done')
        if text == '[DONE]':
            if self.usage is None or self.finish_reason is None:
                raise ValueError('missing terminal receipt')
            self.done = True
            return
        obj = strict_json(text)
        if type(obj) is not dict or obj.get('object') != 'chat.completion.chunk':
            raise ValueError('wrong object')
        identity = tuple(obj.get(k) for k in ('id', 'model', 'system_fingerprint'))
        if any(type(x) is not str or not x for x in identity):
            raise ValueError('missing response identity')
        if self.identity is not None and self.identity != identity:
            raise ValueError('response identity changed')
        self.identity = identity
        self.response_id = identity[0]
        choices = obj.get('choices')
        if type(choices) is not list or len(choices) > 1:
            raise ValueError('expected one choice')
        for choice in choices:
            if type(choice) is not dict or type(choice.get('index')) is not int or choice['index'] != 0:
                raise ValueError('choice index')
            if self.finish_reason is not None:
                raise ValueError('choice after finish')
            self._delta(choice.get('delta'))
            reason = choice.get('finish_reason')
            if reason is not None:
                if reason not in ('stop', 'length', 'tool_calls'):
                    raise ValueError('unsupported finish')
                self.finish_reason = reason
        if obj.get('usage') is not None:
            if choices or self.usage is not None or self.finish_reason is None:
                raise ValueError('unexpected usage')
            # Reuse the pinned non-stream validator for exact terminal counts.
            raw = {'usage': obj['usage'], 'choices': [{'finish_reason': self.finish_reason,
                'message': {'role': 'assistant', 'content': ''}}]}
            checked = parse_response(raw)
            if checked['output_tokens'] < self.output_lower_bound:
                raise ValueError('terminal count below observed generation')
            self.usage = checked['usage_details']
        if 'timings' in obj:
            timing = obj['timings']
            if type(timing) is not dict or not integer(timing.get('predicted_n')):
                raise ValueError('invalid generation telemetry')
            count = timing['predicted_n']
            if count < self.output_lower_bound:
                raise ValueError('generation count decreased')
            if self.usage is not None and count > self.usage['completion_tokens']:
                raise ValueError('telemetry exceeds terminal usage')
            self.output_lower_bound = count
            self.timings = timing
        if 'prompt_progress' in obj:
            progress = obj['prompt_progress']
            if type(progress) is not dict or any(not integer(progress.get(k)) for k in ('total', 'cache', 'processed')):
                raise ValueError('invalid prompt progress')
            if not 0 <= progress['cache'] <= progress['processed'] <= progress['total']:
                raise ValueError('inconsistent prompt progress')
            self.prompt_progress = progress
        self.events += 1

    def _delta(self, delta):
        if type(delta) is not dict:
            raise ValueError('delta object required')
        if delta.get('role') not in (None, 'assistant'):
            raise ValueError('wrong role')
        for field, destination in [('content', 'content'), ('reasoning_content', 'reasoning')]:
            value = delta.get(field)
            if value is not None:
                if type(value) is not str:
                    raise ValueError('text fragment required')
                setattr(self, destination, getattr(self, destination) + value)
        calls = delta.get('tool_calls', [])
        if type(calls) is not list:
            raise ValueError('tool deltas required')
        for fragment in calls:
            if type(fragment) is not dict:
                raise ValueError('tool fragment object required')
            index = fragment.get('index')
            if not integer(index) or index >= 128:
                raise ValueError('tool index bound')
            if fragment.get('type') not in (None, 'function'):
                raise ValueError('wrong tool kind')
            call = self.tool_calls.setdefault(index, {'type':'function', 'id':None,
                'function':{'name':'', 'arguments':''}})
            if 'id' in fragment:
                value = fragment['id']
                if type(value) is not str or not value or call['id'] not in (None, value):
                    raise ValueError('tool identity changed')
                call['id'] = value
            function = fragment.get('function', {})
            if type(function) is not dict or set(function) - {'name', 'arguments'}:
                raise ValueError('function fragment shape')
            for key, value in function.items():
                if type(value) is not str:
                    raise ValueError('function text fragment required')
                call['function'][key] += value
        size = len(self.content) + len(self.reasoning) + sum(
            len(c['function']['name']) + len(c['function']['arguments']) for c in self.tool_calls.values())
        if size > 4 * 1024 * 1024:
            raise ValueError('assembled response bound')

    def summary(self):
        exact = self.valid and self.usage is not None and self.finish_reason is not None
        calls = list(self.tool_calls.values())
        complete_tools = (sorted(self.tool_calls) == list(range(len(calls)))
            and all(c['id'] and c['function']['name'] for c in calls)
            and len({c['id'] for c in calls}) == len(calls)
            and (self.finish_reason != 'tool_calls' or bool(calls)))
        return {'stream_events': self.events, 'protocol_valid': self.valid,
            'terminal_usage_received': exact, 'stream_done': self.done,
            'message_ready': bool(exact and self.done and complete_tools),
            'input_tokens': self.usage['prompt_tokens'] if exact else None,
            'output_tokens': self.usage['completion_tokens'] if exact else None,
            'observed_output_tokens_lower_bound': self.output_lower_bound,
            'observed_input_tokens_lower_bound': 0,
            'last_prompt_progress': self.prompt_progress,
            'last_server_timings': self.timings,
            'input_lower_bound_is_not_exact_usage': True,
            'partial_message_may_execute': False}

    def final_response(self):
        if not self.summary()['message_ready']:
            raise StreamProtocolError('complete_stream_required_for_message')
        if self.tool_calls and sorted(self.tool_calls) != list(range(len(self.tool_calls))):
            raise StreamProtocolError('noncontiguous_tool_indices')
        calls = [self.tool_calls[i] for i in sorted(self.tool_calls)]
        if any(not c['id'] or not c['function']['name'] for c in calls):
            raise StreamProtocolError('incomplete_tool_call')
        if len({c['id'] for c in calls}) != len(calls):
            raise StreamProtocolError('duplicate_tool_call_id')
        message = {'role':'assistant', 'content':self.content}
        if self.reasoning:
            message['reasoning_content'] = self.reasoning
        if calls:
            message['tool_calls'] = calls
        raw = {'id':self.response_id, 'model':self.identity[1], 'system_fingerprint':self.identity[2],
            'choices':[{'index':0, 'finish_reason':self.finish_reason, 'message':message}],
            'usage':self.usage, 'timings':self.timings}
        parse_response(raw)
        return raw
