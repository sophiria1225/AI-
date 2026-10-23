"""Ordinary protocol-reference formatting, including invalid-call fallback.

Only validated protocol fields in the source conversation are renamed. Generated
text, arguments, observations and returned reasoning remain byte-for-byte values.
This does not repair invalid calls, execute them, or assert task success.
"""
import copy

from budget_visibility_comparison import canonical_messages
from context_preservation import compact
from reasoning_history import ReasoningConversation


class StableReferenceConversation(ReasoningConversation):
    def for_model(self, page_limit=24000):
        # Normalize the validated source structure BEFORE its invalid-call
        # fallback becomes text. The append-only archival history stays raw.
        view = copy.copy(self)
        view._messages = canonical_messages(self._messages)
        return ReasoningConversation.for_model(view, page_limit)


def fallback_inspection_view(conversation, page_limit=24000):
    """Post-hoc comparison view; never supplied to an experimental executor.

    Bind each fallback to the source assistant and exact renderer output. This
    avoids treating arbitrary generated JSON as a trusted protocol envelope.
    Return metadata paths only, never the private strings or original IDs.
    """
    if type(conversation) is not ReasoningConversation:
        raise ValueError('original_reasoning_conversation_required')
    rendered, stats = conversation.for_model(page_limit)
    result = canonical_messages(rendered)
    originals = [m for m in conversation.messages() if m['role'] == 'assistant']
    positions = [i for i,m in enumerate(rendered) if m['role'] == 'assistant']
    if len(originals) != len(positions):
        raise ValueError('renderer_source_turns_disagree')
    references = []
    for turn, (original, position) in enumerate(zip(originals, positions, strict=True), 1):
        calls = original.get('tool_calls') or []
        if not calls or rendered[position].get('tool_calls'):
            continue
        expected = {'assistant_text': original['content'], 'tool_call_records': calls}
        if rendered[position]['content'] != compact(expected):
            raise ValueError('fallback_not_bound_to_original_renderer')
        changed = copy.deepcopy(expected)
        for index, call in enumerate(changed['tool_call_records']):
            call['id'] = f'fallback_reference_{turn}_{index+1}'
            references.append({'message_index':position, 'source_assistant_turn':turn,
                'call_index':index, 'path':f'/messages/{position}/content[JSON]/tool_call_records/{index}/id'})
        result[position]['content'] = compact(changed)
    if len({r['source_assistant_turn'] for r in references}) != stats['text_fallback_turns']:
        raise ValueError('all_fallback_turns_must_be_bound')
    return result, references
