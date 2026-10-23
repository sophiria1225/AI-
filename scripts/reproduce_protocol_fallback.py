"""Public, synthetic, model-free example of normalization/rendering order.

Run with Python 3.12 from a complete checkout. No model, tokenizer, vendor
checkout, task records, API, or generated code is loaded or executed.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path

from budget_visibility_comparison import canonical_messages
from protocol_stable_history import StableReferenceConversation
from reasoning_history import ReasoningConversation


LITERAL = 'example-a-1 is ordinary text here; keep it unchanged.'


def synthetic_history(conversation_type, prefix):
    conversation = conversation_type(
        'Synthetic formatting example; do not execute these calls.',
        {'instruction': LITERAL},
    )
    for index, arguments in enumerate(('{', json.dumps({'code': 'pass # ' + LITERAL})), 1):
        call = {'id': f'{prefix}-{index}', 'type': 'function',
                'function': {'name': 'run_python', 'arguments': arguments}}
        response = {'role': 'assistant', 'content': LITERAL, 'tool_calls': [call]}
        # These are invented receipts, not observations from any execution.
        observation = ({'format_error': 'synthetic malformed arguments; no execution',
                        'literal': LITERAL} if index == 1 else
                       {'synthetic_receipt': 'not executed', 'literal': LITERAL})
        conversation.append(response, [{'id': f'span_{index}', 'assistant': LITERAL,
                                         'action': call['function'], 'observation': observation}])
    return conversation


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()


def digest(value):
    return hashlib.sha256(encoded(value)).hexdigest()


def without_protocol_fields(messages):
    """Projection of the source structure only; never parse ordinary text."""
    result = copy.deepcopy(messages)
    for message in result:
        message.pop('tool_call_id', None)
        for call in message.get('tool_calls', []):
            call.pop('id')
    return result


def reproduce():
    cases = {}
    for label, prefix in (('A', 'example-a'), ('B', 'example-b')):
        old = synthetic_history(ReasoningConversation, prefix)
        new = synthetic_history(StableReferenceConversation, prefix)
        raw = new.messages()
        old_rendered, old_stats = old.for_model()
        old_order = canonical_messages(old_rendered)
        new_order, new_stats = new.for_model()
        if raw != old.messages() or raw != new.messages():
            raise RuntimeError('archival_source_changed')
        old_fallback = json.loads(old_order[2]['content'])
        new_fallback = json.loads(new_order[2]['content'])
        preservation = {
            'archive_unchanged': raw == new.messages(),
            'source_non_protocol_fields_unchanged': (
                without_protocol_fields(raw) == without_protocol_fields(canonical_messages(raw))),
            'initial_messages_unchanged': old_order[:2] == new_order[:2],
            'assistant_text_unchanged': old_fallback['assistant_text'] == new_fallback['assistant_text'] == LITERAL,
            'malformed_arguments_unchanged': (
                old_fallback['tool_call_records'][0]['function'] ==
                new_fallback['tool_call_records'][0]['function'] ==
                {'name': 'run_python', 'arguments': '{'}),
            'fallback_receipt_unchanged': old_order[3] == new_order[3],
            'normal_turn_unchanged_except_reference': (
                without_protocol_fields(old_order[4:]) == without_protocol_fields(new_order[4:])),
            'normal_call_and_result_remain_paired': (
                new_order[4]['tool_calls'][0]['id'] == new_order[5]['tool_call_id'] == 'transport_reference_2'),
            'same_rendering_statistics': old_stats == new_stats == {
                'text_fallback_turns': 1, 'paged_spans': 0},
        }
        if not all(preservation.values()):
            raise RuntimeError('synthetic_preservation_check_failed')
        cases[label] = {
            'raw_archival_messages': raw,
            'old_order_normalize_after_rendering': old_order,
            'new_order_normalize_before_rendering': new_order,
            'preservation_checks': preservation,
            'old_order_sha256': digest(old_order), 'new_order_sha256': digest(new_order),
        }
    a, b = cases.values()
    checks = {
        'sources_differ_only_in_protocol_fields': (
            a['raw_archival_messages'] != b['raw_archival_messages'] and
            without_protocol_fields(a['raw_archival_messages']) ==
            without_protocol_fields(b['raw_archival_messages'])),
        'old_order_differs': (a['old_order_normalize_after_rendering'] !=
                              b['old_order_normalize_after_rendering']),
        'new_order_matches': (a['new_order_normalize_before_rendering'] ==
                              b['new_order_normalize_before_rendering']),
        'all_preservation_checks_pass': all(
            all(case['preservation_checks'].values()) for case in cases.values()),
    }
    if not all(checks.values()):
        raise RuntimeError('synthetic_reproduction_failed')
    return {
        'schema_version': 1, 'synthetic_only': True,
        'comparison_level': 'outgoing_conversation_JSON_values_not_model_token_sequences',
        'model_generations': 0, 'tokenizer_calls': 0, 'api_requests': 0,
        'evaluations': 0, 'generated_code_executions': 0,
        'raw_experiment_histories_read': False, 'private_reasoning_read': False,
        'model_output_effect_measured': False, 'quality_or_cost_improvement_claim': False,
        'novel_algorithm_claim': False, 'checks': checks, 'cases': cases,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, help='Create a new JSON file; existing files are never overwritten.')
    args = parser.parse_args()
    text = json.dumps(reproduce(), ensure_ascii=False, indent=2) + '\n'
    if args.output:
        with args.output.open('x', encoding='utf-8') as stream:
            stream.write(text)
    else:
        print(text, end='')


if __name__ == '__main__':
    main()
