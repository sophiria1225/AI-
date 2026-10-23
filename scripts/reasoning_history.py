"""Optional ordinary history with the local model's returned reasoning field.

The historical NativeConversation remains unchanged. This module neither
generates reasoning nor treats it as evidence that a tool operation succeeded.
Raw reasoning belongs only in local model messages, never in public reports.
"""
import copy

from native_conversation import NativeConversation


def reasoning_shape(message):
    """Return only presence/length metadata; never return the private text."""
    if not isinstance(message, dict) or message.get('role') != 'assistant':
        raise ValueError('expected_assistant_message')
    value = message.get('reasoning_content')
    if value is not None and not isinstance(value, str):
        raise ValueError('unsupported_reasoning_content_type')
    content = message.get('content') or ''
    if not isinstance(content, str):
        raise ValueError('unsupported_assistant_content_type')
    return {'field_present': 'reasoning_content' in message,
            'nonempty': bool(value), 'characters': len(value or ''),
            'inline_think_begin': '<mm:think>' in content,
            'inline_think_end': '</mm:think>' in content}


def public_assistant(message):
    reasoning_shape(message)
    result = {'role': 'assistant', 'content': message.get('content') or ''}
    if message.get('tool_calls'):
        result['tool_calls'] = copy.deepcopy(message['tool_calls'])
    return result


def with_recorded_reasoning(messages, saved_messages):
    """Attach only preceding, exactly matching assistant responses.

    The caller must supply the causal prefix, not future responses. Counts and
    public assistant values must match; observations and other roles are copied
    unchanged. This is for a separately declared baseline, not a history repair.
    """
    assistants = [m for m in messages if m.get('role') == 'assistant']
    if len(assistants) != len(saved_messages):
        raise ValueError('saved_response_count_disagrees')
    for historical, saved in zip(assistants, saved_messages, strict=True):
        if historical != public_assistant(saved):
            raise ValueError('public_assistant_history_disagrees')
    result = copy.deepcopy(messages)
    for historical, saved in zip((m for m in result if m.get('role') == 'assistant'),
                                 saved_messages, strict=True):
        if 'reasoning_content' in saved:
            historical['reasoning_content'] = saved['reasoning_content']
    return result


class ReasoningConversation(NativeConversation):
    """Explicit opt-in baseline; all returned reasoning is kept without selection."""
    def append(self, response, spans):
        reasoning_shape(response)  # Validate before NativeConversation can commit.
        offset = len(self._messages)
        super().append(response, spans)
        if 'reasoning_content' in response:
            self._messages[offset]['reasoning_content'] = response['reasoning_content']

    def for_model(self, page_limit=24000):
        rendered, stats = super().for_model(page_limit)
        old = [m for m in self._messages if m['role'] == 'assistant']
        new = [m for m in rendered if m['role'] == 'assistant']
        if len(old) != len(new):
            raise ValueError('assistant_turn_count_changed')
        # NativeConversation's invalid-argument text fallback intentionally drops
        # extra fields. Keep this optional field on the same fallback turn too.
        for original, visible in zip(old, new, strict=True):
            if 'reasoning_content' in original:
                visible['reasoning_content'] = original['reasoning_content']
        return rendered, stats
