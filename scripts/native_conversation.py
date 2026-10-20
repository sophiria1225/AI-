"""Standard append-only assistant/tool history, a baseline representation only.

No tool dispatch, truth judgement, compaction, or reasoning trace replay occurs
here. The caller supplies already recorded observations for every proposed call,
including rejected and skipped calls. They never become successful by formatting.
"""
import copy
import json

from context_preservation import compact, page_span


class NativeConversation:
    def __init__(self, system_prompt, task):
        self._messages = [{'role': 'system', 'content': system_prompt},
                          {'role': 'user', 'content': compact({'task': task})}]
        self._call_ids = set()
        self._span_ids = set()

    def messages(self):
        return copy.deepcopy(self._messages)

    def for_model(self, page_limit=24000):
        """Page long receipts; preserve invalid calls as text, never repair them.

        The pinned template rejects malformed/non-object function arguments. If
        any call in a turn is not representable, retain the whole proposed batch
        as assistant text and its actual recorded outcomes as a user receipt.
        This does not label a partially executed batch as wholly unexecuted.
        """
        result = copy.deepcopy(self._messages[:2])
        stats = {'text_fallback_turns': 0, 'paged_spans': 0}
        offset = 2
        while offset < len(self._messages):
            assistant = self._messages[offset]
            calls = assistant.get('tool_calls') or []
            size = 1 + (len(calls) or 1)
            original = self._messages[offset:offset + size]
            spans = recover_turn(original)
            visible = []
            for span in spans:
                if len(compact(span)) > page_limit:
                    visible.append({'id': span['id'], 'first_page': page_span(
                        {span['id']: span}, span['id'], 0, page_limit)})
                    stats['paged_spans'] += 1
                else:
                    visible.append(span)
            native = True
            for call in calls:
                try:
                    native &= isinstance(json.loads(call['function']['arguments']), dict)
                except (TypeError, ValueError):
                    native = False
            if not native:
                stats['text_fallback_turns'] += 1
                result.extend([
                    {'role': 'assistant', 'content': compact({
                        'assistant_text': assistant['content'], 'tool_call_records': calls})},
                    {'role': 'user', 'content': compact({'recorded_results': visible})},
                ])
            else:
                rendered = copy.deepcopy(original)
                for index, span in enumerate(visible):
                    if 'first_page' in span:
                        rendered[index + 1]['content'] = compact({
                            'span_id': span['id'], 'first_page': span['first_page']})
                result.extend(rendered)
            offset += size
        return result, stats

    def append(self, response, spans):
        """Validate a whole saved turn before adding it; no partial history commit."""
        if response.get('role') != 'assistant':
            raise ValueError('expected an assistant response')
        content = response.get('content') or ''
        if not isinstance(content, str):
            raise ValueError('non-text assistant content is not supported')
        calls = response.get('tool_calls') or []
        if not isinstance(calls, list) or len(spans) != (len(calls) or 1):
            raise ValueError('each proposed tool call needs one recorded observation')
        ids = [s['id'] for s in spans]
        if (any(not isinstance(s, str) or not s for s in ids)
                or len(set(ids)) != len(ids) or set(ids) & self._span_ids):
            raise ValueError('invalid or reused span ID')
        pending, call_ids = [], set()
        if calls:
            for call, span in zip(calls, spans):
                cid = call.get('id')
                if (not isinstance(cid, str) or not cid or cid in call_ids
                        or cid in self._call_ids or call.get('type') != 'function'):
                    raise ValueError('invalid or reused function-call identity')
                fn = call.get('function')
                if (not isinstance(fn, dict) or not isinstance(fn.get('name'), str)
                        or not isinstance(fn.get('arguments'), str)
                        or fn != span.get('action')):
                    raise ValueError('ordered action and recorded operation disagree')
                # Malformed JSON is intentionally preserved, with its actual error
                # observation; template support must be checked before deployment.
                call_ids.add(cid)
                pending.append({'role': 'tool', 'tool_call_id': cid, 'name': fn['name'],
                                'content': compact({'span_id': span['id'],
                                                    'observation': span['observation']})})
            assistant = {'role': 'assistant', 'content': content, 'tool_calls': copy.deepcopy(calls)}
        else:
            if spans[0].get('action') is not None:
                raise ValueError('no-tool response cannot create an action')
            assistant = {'role': 'assistant', 'content': content}
            pending.append({'role': 'user', 'content': compact({
                'span_id': spans[0]['id'], 'observation': spans[0]['observation']})})
        self._messages += [assistant] + pending
        self._call_ids.update(call_ids)
        self._span_ids.update(ids)


def recover_turn(messages):
    """For conformance checks: decode the public action and observation values."""
    first = messages[0]
    calls = first.get('tool_calls') or []
    if len(messages) != 1 + (len(calls) or 1):
        raise ValueError('incomplete turn')
    rows = []
    for index, message in enumerate(messages[1:]):
        data = json.loads(message['content'])
        if calls and message.get('tool_call_id') != calls[index]['id']:
            raise ValueError('tool result identity disagrees')
        rows.append({'id': data['span_id'],
                     'assistant': first['content'] if index == 0 else '',
                     'action': calls[index]['function'] if calls else None,
                     'observation': data['observation']})
    return rows
