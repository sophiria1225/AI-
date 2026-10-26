from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from compact_api_receipts import encode_receipts
from context_preservation import compact, page_span
from native_conversation import recover_turn
from native_data_compute import selected_receipts
from protocol_stable_history import StableReferenceConversation
from receipt_disclosure_history import FORMAT, ReceiptDisclosureConversation, SHARED_GUIDE
from rolling_checkpoint_history import RollingCheckpoint
from single_checkpoint_history import FIELDS


def fixture(number=1, count=4):
    """Handwritten host records; the illustrative source string is never executed."""
    fn = {'name': 'run_python', 'arguments': compact({'code': 'synthetic_source_only', 'span_ids': []})}
    response = {'role': 'assistant', 'content': 'literal assistant text',
        'reasoning_content': 'literal synthetic reasoning', 'tool_calls': [
            {'id': f'native-{number}', 'type': 'function', 'function': fn}]}
    events, archive, receipts = [], {}, []
    for i in range(count):
        sid = f'inner-{number}-{i}'
        api = 'synthetic_service__read'
        archive[sid] = {'id': sid, 'assistant': '',
            'action': {'name': api, 'arguments': '{}'},
            'observation': {'observation': {'synthetic_result': i}}}
        events.append({'span_id': sid, 'call': f'call-{number}', 'stage': 'python_api',
            'api_request_sent': True, 'effects_unknown': False,
            'api_execution': {'status': 'returned', 'bridge_request_sent': True, 'automatic_retries': 0}})
        receipts.append({'span_id': sid, 'api': api, 'api_request_sent': True})
    sid = f'outer-{number}'
    outer = {'id': sid, 'assistant': '', 'action': deepcopy(fn), 'observation': {
        'status': 'ok', 'stdout': 'literal stdout with 日本語', 'stdout_truncated': False,
        'api_requests': count, 'declared_complete': False, 'unknown_effects': False,
        'api_receipts': encode_receipts(receipts), 'error': None}}
    archive[sid] = outer
    events.append({'span_id': sid, 'call': f'call-{number}', 'stage': 'model_tool',
                   'api_request_sent': False, 'effects_unknown': False})
    return response, [outer], events, archive


def append(conversation, data, **kwargs):
    response, spans, events, archive = data
    conversation.append_recorded(response, spans, events=events, archive_spans=archive, **kwargs)


def ordinary(data, limit=24000):
    conv = StableReferenceConversation('instructions' + SHARED_GUIDE, {'synthetic': True})
    conv.append(data[0], data[1])
    return conv.for_model(limit)[0]


class ReceiptDisclosureTests(unittest.TestCase):
    def conversation(self, **kwargs):
        return ReceiptDisclosureConversation('instructions', {'synthetic': True},
                                             execution_scope='synthetic-test-run', **kwargs)

    def test_shared_guide_and_initial_messages_identical(self):
        full, disclose = self.conversation(mode='full'), self.conversation()
        self.assertEqual(full.for_model()[0], disclose.for_model()[0])
        self.assertIn(SHARED_GUIDE, full.messages()[0]['content'])
        self.assertEqual(disclose.sidecar(), [])

    def test_first_display_is_reference_and_all_other_values_remain_literal(self):
        data = fixture(); before = deepcopy(data)
        full, conv = self.conversation(mode='full'), self.conversation()
        append(full, data); append(conv, data)
        actual, stats = conv.for_model()
        expected = full.for_model()[0]
        payload = json.loads(expected[-1]['content'])
        payload['observation']['api_receipts'] = {
            'format': FORMAT, 'span_id': 'outer-1', 'receipt_rows': 4}
        expected[-1]['content'] = compact(payload)
        self.assertEqual(actual, expected)
        self.assertEqual(full.for_model()[0], ordinary(data))
        self.assertEqual(conv.messages(), full.messages())
        self.assertEqual(conv.archive(), data[3])
        self.assertEqual(data, before)
        self.assertGreater(stats['receipt_disclosure']['removed_receipt_UTF8_bytes'], 0)
        self.assertFalse(stats['receipt_disclosure']['task_quality_established'])

    def test_native_pairing_and_reference_resolution_after_canonicalization(self):
        conv = self.conversation(); append(conv, fixture())
        messages = conv.for_model()[0]
        self.assertEqual(messages[-2]['tool_calls'][0]['id'], 'transport_reference_1')
        self.assertEqual(messages[-1]['tool_call_id'], 'transport_reference_1')
        ref = recover_turn(messages[-2:])[0]['observation']['api_receipts']
        raw = json.loads(page_span(conv.archive(), ref['span_id'])['text'])
        self.assertEqual(len(raw['observation']['api_receipts']['rows']), ref['receipt_rows'])
        inner_id = raw['observation']['api_receipts']['rows'][0][0]
        self.assertEqual(page_span(conv.archive(), inner_id)['span_id'], inner_id)
        self.assertEqual(selected_receipts([ref['span_id']], conv.archive())[0]['observation'],
                         raw['observation'])

    def test_raw_read_span_offsets_and_archive_unchanged_after_all_views(self):
        data = fixture(); conv = self.conversation(); append(conv, data)
        expected = [page_span(data[3], 'outer-1', offset, 31) for offset in (0, 7, 37, 1000)]
        for _ in range(3): conv.for_model(); conv.sidecar()
        actual = [page_span(conv.archive(), 'outer-1', offset, 31) for offset in (0, 7, 37, 1000)]
        self.assertEqual(actual, expected)
        self.assertEqual(conv.archive(), data[3])

    def test_expansion_is_new_literal_turn_and_prior_prefix_stays_fixed(self):
        conv = self.conversation(); append(conv, fixture())
        prior = conv.for_model()[0]
        page = page_span(conv.archive(), 'outer-1', 3, 83)
        fn = {'name': 'read_span', 'arguments': compact({'span_id': 'outer-1', 'offset': 3})}
        message = {'role': 'assistant', 'content': '', 'tool_calls': [
            {'id': 'expansion', 'type': 'function', 'function': fn}]}
        span = {'id': 'expansion-result', 'assistant': '', 'action': fn, 'observation': page}
        event = {'span_id': span['id'], 'call': 'expansion-call', 'stage': 'model_tool',
                 'api_request_sent': False}
        conv.append_recorded(message, [span], events=[event], archive_spans={span['id']: span})
        after = conv.for_model()[0]
        self.assertEqual(after[:len(prior)], prior)
        self.assertEqual(json.loads(after[-1]['content'])['observation'], page)
        self.assertEqual(conv.sidecar()[-1]['reasons'], ['single_native_python_turn_required'])

    def test_failure_unknown_unsent_raised_and_truncation_stay_full(self):
        cases = ['outer_error', 'error_despite_ok', 'inner_raised', 'inner_unknown', 'unsent', 'effects_unknown',
                 'unknown_effects', 'truncated', 'missing_status', 'missing_execution',
                 'retry', 'unknown_outer_field', 'non_boolean_flag']
        for case in cases:
            with self.subTest(case=case):
                data = fixture(); obs = data[1][0]['observation']; inner = data[2][0]
                if case == 'outer_error': obs.update(status='execution_error', error='synthetic failure')
                elif case == 'error_despite_ok': obs['error'] = 'synthetic error despite ok'
                elif case == 'inner_raised': inner['api_execution']['status'] = 'raised'
                elif case == 'inner_unknown': inner['api_execution']['status'] = 'unknown'
                elif case == 'unsent':
                    inner['api_request_sent'] = False
                    inner['api_execution']['bridge_request_sent'] = False
                    obs['api_receipts']['rows'][0][2] = False; obs['api_requests'] -= 1
                elif case == 'effects_unknown': inner['effects_unknown'] = True
                elif case == 'unknown_effects': obs['unknown_effects'] = True
                elif case == 'truncated': obs['stdout_truncated'] = True
                elif case == 'missing_status': del obs['status']
                elif case == 'missing_execution': del inner['api_execution']
                elif case == 'retry': inner['api_execution']['automatic_retries'] = 1
                elif case == 'unknown_outer_field': obs['future_error_information'] = 'unknown'
                elif case == 'non_boolean_flag': obs['stdout_truncated'] = 0
                conv = self.conversation(); append(conv, data)
                self.assertEqual(conv.for_model()[0], ordinary(data))
                self.assertFalse(conv.sidecar()[0]['eligible'])

    def test_missing_evidence_pending_local_empty_and_unknown_table_keep_full(self):
        for case in ('missing', 'pending', 'local', 'unknown_table'):
            with self.subTest(case=case):
                data = fixture(count=0 if case == 'local' else 4)
                conv = self.conversation()
                if case == 'unknown_table': data[1][0]['observation']['api_receipts'] = {'other': []}
                if case == 'missing': conv.append(data[0], data[1])
                else: append(conv, data, pending_reads=int(case == 'pending'))
                self.assertEqual(conv.for_model()[0], ordinary(data))
                self.assertFalse(conv.sidecar()[0]['eligible'])

    def test_paged_archive_or_reconstructed_turn_uses_original_paging(self):
        for long_field in ('stdout', 'assistant'):
            with self.subTest(long_field=long_field):
                data = fixture()
                if long_field == 'stdout': data[1][0]['observation']['stdout'] = 'x' * 3000
                else: data[0]['content'] = 'x' * 3000
                conv = self.conversation(page_limit=1200); append(conv, data)
                self.assertEqual(conv.for_model()[0], ordinary(data, 1200))
                self.assertIn('raw_outer_requires_paging', conv.sidecar()[0]['reasons'])

    def test_mixed_batch_invalid_arguments_no_tool_and_unknown_action_fallback(self):
        for kind in ('mixed', 'invalid', 'no_tool', 'unknown'):
            with self.subTest(kind=kind):
                data = fixture()
                if kind == 'invalid':
                    data[0]['tool_calls'][0]['function']['arguments'] = '{bad'
                    data[1][0]['action']['arguments'] = '{bad'
                elif kind == 'no_tool':
                    data[0].pop('tool_calls'); data[1][0]['action'] = None
                elif kind == 'unknown':
                    data[0]['tool_calls'][0]['function']['name'] = 'unknown'
                    data[1][0]['action']['name'] = 'unknown'
                else:
                    fn = {'name': 'read_span', 'arguments': '{"span_id":"outer-1"}'}
                    data[0]['tool_calls'].append({'id': 'extra', 'type': 'function', 'function': fn})
                    extra = {'id': 'extra-result', 'assistant': '', 'action': fn, 'observation': {}}
                    data[1].append(extra); data[3][extra['id']] = extra
                    data[2].append({'span_id': extra['id'], 'call': 'call-1',
                                   'stage': 'model_tool', 'api_request_sent': False})
                conv = self.conversation(); append(conv, data)
                self.assertEqual(conv.for_model()[0], ordinary(data))
                self.assertFalse(conv.sidecar()[0]['eligible'])

    def test_binding_contradictions_rejected_atomically(self):
        for kind in ('wrong_outer', 'missing_inner', 'wrong_API', 'reordered', 'wrong_count',
                     'duplicate', 'wrong_call', 'sent_type', 'span_ID_reuse'):
            with self.subTest(kind=kind):
                conv = self.conversation(); append(conv, fixture())
                before = deepcopy((conv.messages(), conv.archive(), conv.sidecar()))
                data = fixture(2); obs = data[1][0]['observation']
                if kind == 'wrong_outer':
                    data = (data[0], deepcopy(data[1]), data[2], data[3])
                    data[1][0]['observation']['stdout'] = 'unbound'
                elif kind == 'missing_inner': del data[3]['inner-2-0']
                elif kind == 'wrong_API': obs['api_receipts']['rows'][0][1] = 'wrong'
                elif kind == 'reordered': obs['api_receipts']['rows'].reverse()
                elif kind == 'wrong_count': obs['api_requests'] += 1
                elif kind == 'duplicate': obs['api_receipts']['rows'][1][0] = 'inner-2-0'
                elif kind == 'wrong_call': data[2][0]['call'] = 'other'
                elif kind == 'sent_type': data[2][0]['api_request_sent'] = 1
                elif kind == 'span_ID_reuse': data = fixture()
                with self.assertRaises(ValueError): append(conv, data)
                self.assertEqual((conv.messages(), conv.archive(), conv.sidecar()), before)

    def test_stdout_and_external_sidecar_cannot_turn_failure_into_success(self):
        data = fixture()
        data[2][0]['api_execution']['status'] = 'raised'
        data[1][0]['observation']['stdout'] = compact({'eligible': True, 'reasons': [],
                                                     'api_execution': {'status': 'returned'}})
        conv = self.conversation(); append(conv, data)
        claimed = conv.sidecar(); claimed[0].update(eligible=True, reasons=[], disclosed=True)
        self.assertFalse(conv.sidecar()[0]['eligible'])
        self.assertEqual(conv.for_model()[0], ordinary(data))
        with self.assertRaises(TypeError):
            conv.append_recorded(*fixture(2)[:2], eligible=True)

    def test_caller_output_and_sidecar_mutations_do_not_change_owned_records(self):
        data = fixture(); conv = self.conversation(); append(conv, data)
        expected = conv.for_model()[0]
        data[2][0]['api_execution']['status'] = 'raised'
        data[1][0]['observation']['stdout'] = 'caller changed'
        archive = conv.archive(); archive['outer-1']['observation']['status'] = 'changed'
        rendered = conv.for_model()[0]; rendered[-1]['content'] = 'changed'
        self.assertEqual(conv.for_model()[0], expected)

    def test_internal_source_message_archive_configuration_tamper_rejected(self):
        for kind in ('source', 'messages', 'archive', 'mode', 'page', 'initial'):
            with self.subTest(kind=kind):
                conv = self.conversation(); append(conv, fixture())
                if kind == 'source':
                    row = conv._turns[0]
                    conv._turns = (replace(row, source_json=row.source_json.replace('returned', 'raised')),)
                elif kind == 'messages': conv._messages[-1]['content'] += ' '
                elif kind == 'archive': conv._archive['outer-1']['observation']['error'] = 'tampered'
                elif kind == 'mode': conv._mode = 'full'
                elif kind == 'page': conv._page_limit = 1
                elif kind == 'initial': conv._messages[0]['content'] += 'tampered'
                with self.assertRaises(ValueError): conv.for_model()

    def test_unbound_message_archive_and_turn_segments_rejected(self):
        for kind in ('message_tail', 'archive_extra', 'missing_turn', 'gap', 'overlap'):
            with self.subTest(kind=kind):
                conv = self.conversation(); append(conv, fixture())
                if kind == 'message_tail': conv._messages.extend(deepcopy(conv._messages[-2:]))
                elif kind == 'archive_extra': conv._archive['extra'] = {'id': 'extra'}
                elif kind == 'missing_turn': conv._turns = ()
                elif kind == 'gap': conv._turns = (replace(conv._turns[0], start=3),)
                elif kind == 'overlap': conv._turns += conv._turns
                with self.assertRaisesRegex(ValueError, 'coverage_changed'):
                    conv.for_model()

    def test_raw_archive_member_order_is_bound_for_source_and_returned_offsets(self):
        for kind in ('outer', 'inner'):
            with self.subTest(kind=kind):
                data = fixture(); conv = self.conversation(); append(conv, data)
                sid = 'outer-1' if kind == 'outer' else 'inner-1-0'
                original = compact(data[3][sid])
                loaded = json.loads(conv._turns[0].source_json)
                self.assertEqual(compact(loaded['archive'][sid]), original)
                self.assertEqual(compact(conv.archive()[sid]), original)
                self.assertEqual(page_span(conv.archive(), sid, 20, 80),
                                 page_span(data[3], sid, 20, 80))
                row = conv._archive[sid]
                if kind == 'outer':
                    row['observation'] = dict(reversed(list(row['observation'].items())))
                else:
                    row['action'] = dict(reversed(list(row['action'].items())))
                self.assertEqual(row, data[3][sid])  # Semantic equality is insufficient.
                self.assertNotEqual(compact(row), original)
                with self.assertRaisesRegex(ValueError, 'raw_archival_text_changed'):
                    conv.for_model()
                with self.assertRaisesRegex(ValueError, 'raw_archival_text_changed'):
                    conv.archive()

    def test_byte_shorter_reference_that_exceeds_character_page_limit_stays_full(self):
        data = fixture(count=1)
        api = '猫' * 100
        data[3]['inner-1-0']['action']['name'] = api
        data[1][0]['observation']['api_receipts']['rows'][0][1] = api
        span = data[3].pop('outer-1'); span['id'] = 'outer-' + 'x' * 220
        data[3][span['id']] = span; data[2][-1]['span_id'] = span['id']
        raw_turn = ordinary(data)[-2:]
        limit = max(len(compact(span)), len(compact(recover_turn(raw_turn)[0])))
        conv = self.conversation(page_limit=limit); append(conv, data)
        evidence = conv.sidecar()[0]
        self.assertGreater(evidence['table_bytes'], evidence['reference_bytes'])
        self.assertNotIn('raw_outer_requires_paging', evidence['reasons'])
        self.assertIn('reference_outer_requires_paging', evidence['reasons'])
        self.assertEqual(conv.for_model()[0], ordinary(data, limit))

    def test_page_limit_cannot_change_between_renderings(self):
        conv = self.conversation(); append(conv, fixture())
        before = conv.for_model()[0]
        for value in (1000, True, 24000.0):
            with self.assertRaises(ValueError): conv.for_model(value)
        self.assertEqual(conv.for_model(24000)[0], before)

    def test_nonshrinking_reference_retains_full_table(self):
        data = fixture(count=1)
        span = data[3].pop('outer-1')
        span['id'] = 'outer-' + 'x' * 600
        data[3][span['id']] = span
        data[2][-1]['span_id'] = span['id']
        conv = self.conversation(); append(conv, data)
        self.assertEqual(conv.for_model()[0], ordinary(data))
        self.assertIn('reference_not_strictly_shorter_in_UTF8_bytes', conv.sidecar()[0]['reasons'])

    def test_sidecar_cannot_be_reused_for_another_host_execution_scope(self):
        first = self.conversation(); append(first, fixture())
        second = ReceiptDisclosureConversation('instructions', {'synthetic': True},
                                                execution_scope='different-synthetic-run')
        append(second, fixture())
        self.assertEqual(first.for_model()[0], second.for_model()[0])
        second._turns = first._turns
        with self.assertRaisesRegex(ValueError, 'trusted_sidecar_scope_changed'):
            second.for_model()

    def test_rolling_separate_prefix_binding_and_installed_summary_keep_new_suffix(self):
        conv = self.conversation()
        for number in range(1, 5): append(conv, fixture(number))
        before = conv.for_model()[0]
        checkpoint = RollingCheckpoint('separate')
        self.assertIsNone(checkpoint.begin(before, 100))  # Synthetic count, no tokenizer.
        append(conv, fixture(5)); current = conv.for_model()[0]
        self.assertEqual(current[:len(before)], before)
        self.assertEqual(checkpoint.view(current), current)
        offer = checkpoint.begin(current, 20000)
        self.assertIsNotNone(offer)
        summary = {field: ['handwritten synthetic summary'] for field in FIELDS}
        checkpoint.close_separate(current, {'role': 'assistant', 'content': compact(summary)},
                                  'stop', usage_known=True)
        checkpoint.decide(20000, 10000)
        saved = checkpoint.view(current)
        append(conv, fixture(6)); after = conv.for_model()[0]
        self.assertEqual(after[:len(current)], current)
        self.assertEqual(checkpoint.view(after)[:len(saved)], saved)
        self.assertEqual(checkpoint.view(after)[-2:], after[-2:])
        self.assertEqual(len(conv.archive()), 30)


if __name__ == '__main__':
    unittest.main()
