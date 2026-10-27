from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from checkpoint_representation_p139 import (
    DELTA_SUMMARY_PROMPT, MODES, RepresentationCheckpoint, RepresentationExposureLedger,
    eligible_prefix_views, serialize_fragment_body, trigger_decision, validate_fragment_budget)
from checkpoint_representation_preflight_p139 import synthetic_transport_cases
from receipt_reasoning_history import digest
from rolling_checkpoint_history import RollingCheckpoint, SUMMARY_PROMPT
from single_checkpoint_history import FIELDS, candidate


def history(n):
    result = [{'role': 'system', 'content': 'synthetic instructions'},
              {'role': 'user', 'content': 'synthetic task'}]
    for i in range(n):
        result += [{'role': 'assistant', 'content': '', 'tool_calls': [
            {'id': f'call-{i}', 'type': 'function', 'function':
             {'name': 'run_python', 'arguments': '{"code":"pass","span_ids":[]}'}}]},
            {'role': 'tool', 'tool_call_id': f'call-{i}', 'content': f'synthetic observation {i}'}]
    return result


def value(text='first'):
    return {field: [text+' '+field] for field in FIELDS}


def message(v):
    return {'role': 'assistant', 'content': json.dumps(v, ensure_ascii=False)}


def install_first(mode='exposure_delta', first=None):
    c = RepresentationCheckpoint(mode)
    c.begin(history(6), 20000)
    c.close_separate(history(6), message(value() if first is None else first), 'stop', usage_known=True)
    c.decide(20000, 9000)  # Handwritten counts only.
    return c


def decision(mode, **updates):
    args = dict(mode=mode, opportunities=1, fresh_turns=3, eligible_raw=True,
                measured_input_tokens=14000, accumulated_exposure=20000, previous_focus_cost=20000)
    args.update(updates)
    return trigger_decision(**args)


class RepresentationTests(unittest.TestCase):
    def test_first_focus_packet_and_projection_match_frozen_controller_in_four_modes(self):
        raw = history(6)
        old = RollingCheckpoint('separate')
        offered = old.begin(raw, 20000)
        old_views = old.close_separate(raw, message(value()), 'stop', usage_known=True)
        old.decide(20000, 9000)
        for mode in MODES:
            c = RepresentationCheckpoint(mode)
            new_offer = c.begin(raw, 20000)
            self.assertEqual(new_offer['summary_messages'], offered['summary_messages'])
            self.assertFalse(new_offer['delta_requested'])
            views = c.close_separate(raw, message(value()), 'stop', usage_known=True)
            self.assertEqual(views['ordinary'], old_views['ordinary'])
            self.assertEqual(views['compacted'], old_views['compacted'])
            c.decide(20000, 9000)
            self.assertEqual(c.view(raw), old.view(raw))
            self.assertEqual(c.max_opportunities, 2)

    def test_first_threshold_repeat_timing_and_shared_limits_are_explicit(self):
        for mode in MODES:
            self.assertFalse(decision(mode, opportunities=0, measured_input_tokens=16383)['offer'])
            self.assertTrue(decision(mode, opportunities=0, measured_input_tokens=16384)['offer'])
            for change in ({'opportunities': 2}, {'fresh_turns': 2}, {'eligible_raw': False}):
                self.assertFalse(decision(mode, measured_input_tokens=50000, **change)['offer'])
            self.assertEqual(decision(mode)['offer'], mode.startswith('exposure'))
            self.assertEqual(decision(mode, measured_input_tokens=17000,
                                      accumulated_exposure=100)['offer'], mode.startswith('threshold'))
        for change in ({'opportunities': True}, {'fresh_turns': False}, {'eligible_raw': 1},
                       {'previous_focus_cost': True}, {'accumulated_exposure': -1}):
            with self.assertRaises(ValueError): decision('exposure_delta', **change)

    def test_second_user_packet_is_same_reference_and_only_delta_system_contract_changes(self):
        recursive = install_first('exposure_recursive')
        delta = install_first()
        a = recursive.begin(history(9), 14000, repeat_ready=True)
        b = delta.begin(history(9), 14000, repeat_ready=True)
        self.assertEqual(a['summary_messages'][1], b['summary_messages'][1])
        self.assertEqual(a['summary_messages'][0]['content'], SUMMARY_PROMPT)
        self.assertEqual(b['summary_messages'][0]['content'], DELTA_SUMMARY_PROMPT)
        packet = json.loads(b['summary_messages'][1]['content'])
        self.assertEqual(packet['previous_checkpoint'], value())
        self.assertEqual(packet['older_history'], history(9)[10:16])
        self.assertEqual(packet['recent_context'], history(9)[16:])
        self.assertNotIn('synthetic observation 0', json.dumps(packet['older_history']))

    def test_recursive_second_packet_and_view_match_original_rolling(self):
        raw = history(6)
        old = RollingCheckpoint('separate')
        old.begin(raw, 20000); old.close_separate(raw, message(value()), 'stop', usage_known=True)
        old.decide(20000, 9000)
        old_offer = old.begin(history(9), 20000)
        for mode in ('threshold_recursive', 'exposure_recursive'):
            c = install_first(mode)
            offer = c.begin(history(9), 20000, repeat_ready=True)
            self.assertEqual(offer['summary_messages'], old_offer['summary_messages'])
            views = c.close_separate(history(9), message(value('second')), 'stop', usage_known=True)
            c.decide(20000, 10000)
            self.assertEqual(c.fragment_count, 1)
            self.assertEqual(c.view(history(9)), views['compacted'])
            self.assertEqual(json.loads(c.view(history(9))[2]['content'])['summary'], value('second'))

    def test_delta_keeps_old_note_bytes_and_two_recent_turns_and_archive(self):
        c = install_first()
        note = c.summary_notes[0]
        raw = history(9); saved = deepcopy(raw)
        c.begin(raw, 14000, repeat_ready=True)
        views = c.close_separate(raw, message(value('delta')), 'stop', usage_known=True)
        self.assertEqual(views['compacted'][2], note)
        self.assertEqual(views['compacted'][:2], raw[:2])
        self.assertEqual(views['compacted'][4:], raw[16:])
        event = c.decide(14000, 11000)
        self.assertTrue(event['delta_applied'])
        self.assertEqual(event['preserved_first_note_sha256'], digest(note))
        self.assertEqual(c.summary_notes[0]['content'].encode(), note['content'].encode())
        self.assertEqual(raw, saved)
        returned = c.summary_notes; returned[0]['content'] = 'tampered copy'
        self.assertEqual(c.summary_notes[0], note)

    def test_count_only_projection_after_delta_preserves_both_notes(self):
        c = install_first()
        c.begin(history(9), 14000, repeat_ready=True)
        c.close_separate(history(9), message(value('delta')), 'stop', usage_known=True)
        c.decide(14000, 11000)
        raw = history(12); saved = deepcopy(raw)
        views = eligible_prefix_views(c, raw)
        self.assertEqual(views['fragment_count'], 2)
        self.assertEqual(views['raw_start'], 16)
        self.assertEqual(views['raw_end'], 22)
        self.assertEqual(views['working'][:4], views['without_raw'][:4])
        self.assertEqual(views['without_raw'][4:], raw[22:])
        self.assertEqual(views['working'][4:], raw[16:])
        self.assertEqual(raw, saved)
        self.assertIsNone(c.begin(raw, 50000, repeat_ready=True))

    def test_prefix_count_handles_zero_and_one_note_without_erasing_recent_turns(self):
        for c in (RepresentationCheckpoint('threshold_delta'), install_first()):
            raw = history(6)
            views = eligible_prefix_views(c, raw)
            head = 2+c.fragment_count
            self.assertEqual(views['working'][:head], views['without_raw'][:head])
            self.assertEqual(views['without_raw'][head:], raw[views['raw_end']:])
        c = RepresentationCheckpoint('exposure_recursive')
        self.assertEqual(eligible_prefix_views(c, history(1))['eligible_raw_messages'], 0)

    def test_combined_size_boundary_counts_characters_and_not_each_fragment(self):
        first = {k: [] for k in FIELDS}; second = deepcopy(first)
        first['completed'] = ['x'*2048, 'x'*2048, 'x'*2000]
        second['remaining'] = ['y'*1000]
        n = 8192-len(serialize_fragment_body([first, second]))
        second['remaining'][0] += 'y'*n
        self.assertLessEqual(len(second['remaining'][0]), 2048)
        self.assertEqual(validate_fragment_budget([first, second])['body_characters'], 8192)
        second['remaining'][0] += 'y'
        with self.assertRaisesRegex(ValueError, 'body_too_long'): validate_fragment_budget([first, second])
        unicode_value = {k: [] for k in FIELDS}; unicode_value['usable_state'] = ['語'*2048]*3
        body = serialize_fragment_body([unicode_value])
        self.assertGreater(len(body.encode()), 8192)
        self.assertLess(validate_fragment_budget([unicode_value])['body_characters'], 8192)

    def test_combined_field_limit_is_total_not_per_fragment(self):
        first = {k: [] for k in FIELDS}; second = deepcopy(first)
        first['completed'] = ['old']*16; second['completed'] = ['new']*16
        self.assertEqual(validate_fragment_budget([first, second])['field_item_counts']['completed'], 32)
        second['completed'].append('extra')
        with self.assertRaisesRegex(ValueError, 'field_too_long'): validate_fragment_budget([first, second])

    def test_structurally_valid_delta_over_combined_budget_is_rejected_before_counts(self):
        first = {k: [] for k in FIELDS}; first['completed'] = ['x'*2048]*3
        c = install_first(first=first); old_note, cutoff = c.summary_notes, c.cutoff
        c.begin(history(9), 14000, repeat_ready=True)
        v = {k: [] for k in FIELDS}; v['remaining'] = ['y'*2048]
        views = c.close_separate(history(9), message(v), 'stop', usage_known=True)
        self.assertIsNone(views['compacted'])
        self.assertIsNone(c.pending)
        self.assertEqual(c.events[-1]['reason'], 'fragment_budget_exceeded')
        self.assertEqual((c.summary_notes, c.cutoff), (old_note, cutoff))

    def test_nonshrinking_delta_keeps_prior_checkpoint_and_consumes_opportunity(self):
        c = install_first(); old = c.summary_notes; cutoff = c.cutoff
        c.begin(history(9), 14000, repeat_ready=True)
        c.close_separate(history(9), message(value('delta')), 'stop', usage_known=True)
        self.assertFalse(c.decide(10000, 10000)['accepted'])
        self.assertEqual((c.summary_notes, c.cutoff, c.revision), (old, cutoff, 1))
        self.assertIsNone(c.begin(history(12), 50000, repeat_ready=True))

    def test_first_rejected_means_second_uses_ordinary_packet_not_delta(self):
        for mode in MODES:
            c = RepresentationCheckpoint(mode)
            c.begin(history(6), 20000)
            c.close_separate(history(6), message(value()), 'stop', usage_known=True)
            c.decide(20000, 20000)
            offer = c.begin(history(9), 20000, repeat_ready=True)
            self.assertFalse(offer['delta_requested'])
            self.assertEqual(offer['summary_messages'], candidate(history(9))['summary_messages'])

    def test_unknown_preserves_prior_summary_pending_and_blocks_all_continuation(self):
        c = install_first(); old, cutoff = c.summary_notes, c.cutoff
        c.begin(history(9), 14000, repeat_ready=True)
        with self.assertRaisesRegex(ValueError, 'unknown_usage'):
            c.close_separate(history(9), message(value('not trusted')), 'stop', usage_known=False)
        self.assertEqual((c.summary_notes, c.cutoff), (old, cutoff))
        self.assertIsNotNone(c.pending)
        with self.assertRaises(ValueError): c.view(history(9))
        with self.assertRaises(ValueError): c.begin(history(12), 50000, repeat_ready=True)

    def test_paid_invalid_resets_exposure_without_installation_and_unsent_does_not(self):
        for sent in (False, True):
            c = install_first(); ledger = RepresentationExposureLedger('exposure_delta')
            ledger.record_focus(call_id='focus1', model_attempted=True, usage_known=True,
                                input_tokens=1000, output_tokens=10)
            ledger.record_actor(call_id='actor1', model_attempted=True, usage_known=True,
                                input_tokens=400, without_raw_input_tokens=100)
            old = (c.summary_notes, c.cutoff)
            c.begin(history(9), 14000, repeat_ready=True)
            if sent:
                c.close_separate(history(9), message({'completed': []}), 'stop', usage_known=True)
                ledger.record_focus(call_id='focus2', model_attempted=True, usage_known=True,
                                    input_tokens=2000, output_tokens=20)
                self.assertEqual((ledger.previous_focus_cost, ledger.accumulated_exposure), (2020, 0))
            else:
                c.skip_unstarted_summary(history(9), 'insufficient_shared_token_budget')
                ledger.record_focus(call_id='focus2', model_attempted=False, usage_known=False)
                self.assertEqual((ledger.previous_focus_cost, ledger.accumulated_exposure), (1010, 300))
            self.assertEqual((c.summary_notes, c.cutoff), old)
            self.assertEqual(c.opportunities, 2)
            self.assertIsNone(c.begin(history(12), 50000, repeat_ready=True))

    def test_ledger_four_modes_reuse_paid_negative_delta_and_unknown_rules(self):
        for mode in MODES:
            ledger = RepresentationExposureLedger(mode)
            ledger.record_focus(call_id='focus1', model_attempted=True, usage_known=True,
                                input_tokens=1000, output_tokens=10)
            e = ledger.record_actor(call_id='actor1', model_attempted=True, usage_known=True,
                                    input_tokens=99, without_raw_input_tokens=100)
            self.assertEqual((e['raw_delta'], e['positive_part']), (-1, 0))
            ledger.record_focus(call_id='focus2', model_attempted=True, usage_known=False)
            self.assertTrue(ledger.blocked)
            with self.assertRaises(ValueError): ledger.record_actor(call_id='later', model_attempted=False, usage_known=False)
            self.assertEqual(ledger.summary()['mode'], mode)

    def test_invalid_two_opportunities_are_not_retried_and_fresh_spacing_is_preserved(self):
        for mode in MODES:
            c = RepresentationCheckpoint(mode)
            for n in (6, 9):
                self.assertIsNotNone(c.begin(history(n), 20000, repeat_ready=True))
                c.close_separate(history(n), message({}), 'stop', usage_known=True)
                self.assertIsNone(c.begin(history(n+2), 50000, repeat_ready=True))
            self.assertIsNone(c.begin(history(12), 50000, repeat_ready=True))
            self.assertEqual((c.opportunities, c.revision), (2, 0))

    def test_archive_changes_and_incomplete_tool_turns_are_rejected(self):
        c = install_first()
        changed = history(9); changed[3]['content'] = 'changed old result'
        with self.assertRaisesRegex(ValueError, 'changed_or_rewound'): c.begin(changed, 20000, repeat_ready=True)
        with self.assertRaises(ValueError): c.begin(history(9)[:-1], 20000, repeat_ready=True)
        c.begin(history(9), 14000, repeat_ready=True)
        with self.assertRaisesRegex(ValueError, 'archive_changed_during_summary'):
            c.close_separate(history(10), message(value('delta')), 'stop', usage_known=True)

    def test_preflight_six_cases_are_handwritten_and_cover_two_note_actor_transport(self):
        cases = synthetic_transport_cases()
        self.assertEqual([c['name'] for c in cases], ['recursive_focus1', 'recursive_focus2',
            'delta_focus1', 'delta_focus2', 'recursive_actor_after2', 'delta_actor_after2'])
        self.assertTrue(all(c['synthetic_only'] is True for c in cases))
        self.assertEqual(cases[0]['messages'], cases[2]['messages'])
        self.assertEqual(cases[1]['messages'][1], cases[3]['messages'][1])
        self.assertEqual(cases[4]['messages'][:2], cases[5]['messages'][:2])
        self.assertEqual(len(cases[5]['messages']), len(cases[4]['messages'])+1)
        self.assertEqual(cases[4]['tools'], cases[5]['tools'])
        cases[0]['messages'][0]['content'] = 'external mutation'
        self.assertNotEqual(cases[0], synthetic_transport_cases()[0])


if __name__ == '__main__':
    unittest.main()
