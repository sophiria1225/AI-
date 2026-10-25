from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from public_display import CODE_TOOLS
from required_inline_checkpoint_history import RequiredInlineCheckpoint
from rolling_checkpoint_history import BOUNDARY, RollingCheckpoint
from single_checkpoint_history import SingleCheckpoint, candidate
from test_inline_checkpoint_protocol import VALID, fixture, response, split


def add_turn(conversation, number, checkpoint=None):
    message = response(checkpoint, content=f'synthetic action {number}')
    message['tool_calls'][0]['id'] = f'next-{number}'
    conversation.append(message, [{'id': f's{number}',
        'action': message['tool_calls'][0]['function'],
        'observation': {'status': 'ok', 'stdout': f'literal observation {number}'}}])
    return conversation.for_model()[0], message


def text_summary(value):
    return {'role': 'assistant', 'content': json.dumps(value)}


class RollingCheckpointTests(unittest.TestCase):
    def install_first_inline(self):
        before, after, msg, conv = fixture()
        control = RollingCheckpoint('inline')
        control.begin(before, 20000, CODE_TOOLS)
        control.close_inline(after, split(msg), usage_known=True)
        control.decide(18000, 9000)
        return control, after, conv

    def test_first_inline_offer_and_projection_match_the_existing_control_exactly(self):
        before, after, msg, _ = fixture()
        tools = deepcopy(CODE_TOOLS)
        for maximum in (1, 3):
            old = RequiredInlineCheckpoint()
            original = old.begin(before, CODE_TOOLS, 20000)
            new = RollingCheckpoint('inline', max_opportunities=maximum)
            offered = new.begin(before, 20000, CODE_TOOLS)
            self.assertEqual(offered['messages'], original['messages'])
            self.assertEqual(offered['tools'], original['tools'])
            old_views = old.close(after, split(msg))
            new_views = new.close_inline(after, split(msg), usage_known=True)
            self.assertEqual(new_views['ordinary'], old_views['ordinary'])
            self.assertEqual(new_views['compacted'], old_views['compacted'])
            old.decide(18000, 9000); new.decide(18000, 9000)
            self.assertEqual(new.view(after), old.view(after))
        self.assertEqual(CODE_TOOLS, tools)

    def test_first_separate_packet_and_projection_match_existing_control(self):
        before, _, _, _ = fixture()
        old = SingleCheckpoint(); proposal = old.begin(before, 20000)
        new = RollingCheckpoint('separate')
        offered = new.begin(before, 20000)
        self.assertEqual(offered['summary_messages'], proposal['summary_messages'])
        views = new.close_separate(before, text_summary(VALID), 'stop', usage_known=True)
        new.decide(18000, 9000)
        self.assertEqual(views['ordinary'], before)
        self.assertEqual(new.view(before), old.install(before, proposal, VALID))

    def test_second_inline_summary_uses_prior_memory_and_new_suffix_and_keeps_current_turn(self):
        control, after, conv = self.install_first_inline()
        first_cutoff = control.cutoff
        for n in range(6, 9):
            before, _ = add_turn(conv, n)
        saved = deepcopy(conv.messages())
        offered = control.begin(before, 20000, CODE_TOOLS)
        view = offered['messages']
        self.assertEqual(json.loads(view[2]['content'])['summary'], VALID)
        boundary = next(i for i, m in enumerate(view) if m.get('content') == BOUNDARY)
        cutoff = candidate(before)['cutoff']
        self.assertEqual(view[boundary+1:-1], before[cutoff:])
        self.assertNotIn('old-0', json.dumps(view))
        self.assertGreater(cutoff, first_cutoff)
        updated = {**VALID, 'remaining': ['new unresolved condition']}
        later, msg = add_turn(conv, 9, updated)
        raw = deepcopy(later)
        views = control.close_inline(later, split(msg), usage_known=True)
        control.decide(20000, 10000)
        selected = control.view(later)
        self.assertEqual(selected, views['compacted'])
        self.assertEqual(selected[:2], before[:2])
        self.assertEqual(selected[3:-2], before[cutoff:])
        self.assertEqual(selected[-1], later[-1])
        self.assertEqual(json.loads(selected[2]['content'])['summary'], updated)
        self.assertEqual(conv.messages()[:len(saved)], saved)
        self.assertEqual(later, raw)
        self.assertEqual(control.revision, 2)
        self.assertNotIn('checkpoint', json.loads(selected[-2]['tool_calls'][0]['function']['arguments']))

    def test_second_separate_packet_never_replays_old_omitted_raw_history(self):
        before, after, _, conv = fixture()
        control = RollingCheckpoint('separate')
        control.begin(before, 20000)
        control.close_separate(before, text_summary(VALID), 'stop', usage_known=True)
        control.decide(20000, 9000)
        cutoff = control.cutoff
        for n in range(6, 8):
            later, _ = add_turn(conv, n)
        offered = control.begin(later, 20000)
        packet = json.loads(offered['summary_messages'][1]['content'])
        self.assertEqual(packet['previous_checkpoint'], VALID)
        self.assertFalse(packet['previous_checkpoint_semantics_verified'])
        self.assertEqual(packet['older_history'], later[cutoff:offered['cutoff']])
        self.assertEqual(packet['recent_context'], later[offered['cutoff']:])
        self.assertNotIn('old-0', json.dumps(packet))
        control.close_separate(later, text_summary(VALID), 'stop', usage_known=True)
        control.decide(20000, 12000)
        self.assertEqual(control.revision, 2)

    def test_fresh_turn_spacing_and_native_threshold_apply_after_rejection(self):
        before, after, msg, conv = fixture(response({'completed': []}))
        control = RollingCheckpoint('inline')
        self.assertIsNone(control.begin(before, 16383, CODE_TOOLS))
        control.begin(before, 16384, CODE_TOOLS)
        views = control.close_inline(after, split(msg), usage_known=True)
        self.assertEqual(control.view(after), views['ordinary'])
        self.assertFalse(control.events[-1]['accepted'])
        self.assertIsNone(control.begin(after, 50000, CODE_TOOLS))
        for n in (6, 7):
            later, _ = add_turn(conv, n)
            self.assertIsNone(control.begin(later, 50000, CODE_TOOLS))
        later, _ = add_turn(conv, 8)
        self.assertIsNone(control.begin(later, 16383, CODE_TOOLS))
        self.assertIsNotNone(control.begin(later, 16384, CODE_TOOLS))

    def test_nonshrinking_update_retains_previous_memory_and_action_metadata_is_not_replayed(self):
        control, after, conv = self.install_first_inline()
        for n in range(6, 9):
            before, _ = add_turn(conv, n)
        old_cutoff = control.cutoff
        control.begin(before, 20000, CODE_TOOLS)
        updated = {**VALID, 'remaining': ['rejected new memory']}
        after, msg = add_turn(conv, 9, updated)
        views = control.close_inline(after, split(msg), usage_known=True)
        decision = control.decide(10000, 10000)
        self.assertFalse(decision['accepted'])
        selected = control.view(after)
        self.assertEqual(selected, views['ordinary'])
        self.assertEqual(control.cutoff, old_cutoff)
        self.assertEqual(json.loads(selected[2]['content'])['summary'], VALID)
        for m in selected:
            for call in m.get('tool_calls') or []:
                self.assertNotIn('checkpoint', json.loads(call['function']['arguments']))

    def test_three_opportunities_are_a_hard_bound_even_when_every_summary_is_invalid(self):
        before, after, msg, conv = fixture(response({'completed': []}))
        control = RollingCheckpoint('inline')
        next_id = 6
        for attempt in range(3):
            if attempt:
                for _ in range(3):
                    before, _ = add_turn(conv, next_id); next_id += 1
                after, msg = add_turn(conv, next_id, {'completed': []}); next_id += 1
            self.assertIsNotNone(control.begin(before, 20000, CODE_TOOLS))
            control.close_inline(after, split(msg), usage_known=True)
        for _ in range(4):
            later, _ = add_turn(conv, next_id); next_id += 1
        self.assertIsNone(control.begin(later, 50000, CODE_TOOLS))
        self.assertEqual(control.opportunities, 3)
        self.assertEqual(control.revision, 0)

    def test_unknown_usage_blocks_all_future_projection_and_offers(self):
        for mode in ('separate', 'inline'):
            before, after, msg, _ = fixture()
            control = RollingCheckpoint(mode)
            control.begin(before, 20000, CODE_TOOLS)
            with self.assertRaisesRegex(ValueError, 'unknown_usage'):
                if mode == 'inline':
                    control.close_inline(after, split(msg), usage_known=False)
                else:
                    control.close_separate(before, text_summary(VALID), 'stop', usage_known=False)
            with self.assertRaisesRegex(ValueError, 'unknown_usage'): control.view(after)
            with self.assertRaisesRegex(ValueError, 'unknown_usage'): control.begin(after, 20000, CODE_TOOLS)

    def test_one_opportunity_control_does_not_reopen_after_three_fresh_turns(self):
        before, after, msg, conv = fixture()
        control = RollingCheckpoint('inline', max_opportunities=1)
        control.begin(before, 20000, CODE_TOOLS)
        control.close_inline(after, split(msg), usage_known=True)
        control.decide(20000, 10000)
        for n in range(6, 10):
            later, _ = add_turn(conv, n)
        self.assertIsNone(control.begin(later, 50000, CODE_TOOLS))
        self.assertEqual(control.opportunities, 1)

    def test_valid_shape_and_shorter_input_do_not_certify_information_preservation(self):
        before, _, _, _ = fixture()
        control = RollingCheckpoint('separate')
        control.begin(before, 20000)
        # Empty lists satisfy the shared syntax contract while omitting facts.
        # Acceptance must remain explicitly structural, never a quality proof.
        empty = {field: [] for field in VALID}
        control.close_separate(before, text_summary(empty), 'stop', usage_known=True)
        decision = control.decide(20000, 8000)
        self.assertTrue(decision['accepted'])
        self.assertFalse(decision['semantics_verified'])
        self.assertFalse(json.loads(control.view(before)[2]['content'])['semantics_verified'])

    def test_pending_work_cannot_be_reentered_or_summary_attached_to_different_action(self):
        before, after, msg, _ = fixture()
        control = RollingCheckpoint('inline')
        control.begin(before, 20000, CODE_TOOLS)
        with self.assertRaisesRegex(ValueError, 'pending'): control.begin(before, 20000, CODE_TOOLS)
        with self.assertRaisesRegex(ValueError, 'close_and_resolve'): control.view(before)
        forged = split(msg)
        forged['execution_message']['tool_calls'][0]['function']['arguments'] = '{"code":"different","span_ids":[]}'
        with self.assertRaisesRegex(ValueError, 'binding_changed'):
            control.close_inline(after, forged, usage_known=True)
        control.close_inline(after, split(msg), usage_known=True)
        with self.assertRaisesRegex(ValueError, 'close_and_resolve'): control.view(after)
        control.decide(20000, 10000)
        changed = deepcopy(after); changed[0]['content'] = 'different task system'
        with self.assertRaisesRegex(ValueError, 'archive_changed'): control.view(changed)
        with self.assertRaisesRegex(ValueError, 'archive_changed'): control.view(before)

    def test_returned_objects_cannot_mutate_controller_and_summary_is_never_semantic_proof(self):
        before, after, msg, _ = fixture()
        control = RollingCheckpoint('inline', max_opportunities=1)
        offered = control.begin(before, 20000, CODE_TOOLS)
        offered['messages'][0]['content'] = 'changed outside'
        views = control.close_inline(after, split(msg), usage_known=True)
        views['compacted'][0]['content'] = 'changed outside'
        decision = control.decide(20000, 10000)
        decision['accepted'] = False
        self.assertEqual(control.view(after)[:2], before[:2])
        self.assertTrue(control.events[-1]['accepted'])
        self.assertFalse(control.events[-1]['semantics_verified'])
        self.assertIsNone(control.begin(after, 50000, CODE_TOOLS))

    def test_invalid_modes_caps_counts_and_incomplete_turns_are_rejected(self):
        for mode in ('automatic', '', None):
            with self.assertRaises(ValueError): RollingCheckpoint(mode)
        for maximum in (0, 2, 4, True):
            with self.assertRaises(ValueError): RollingCheckpoint('inline', max_opportunities=maximum)
        before, _, _, _ = fixture()
        for tokens in (0, -1, None, True, 1.5):
            with self.assertRaises(ValueError): RollingCheckpoint('inline').begin(before, tokens, CODE_TOOLS)
        with self.assertRaises(ValueError): RollingCheckpoint('inline').begin(before[:-1], 20000, CODE_TOOLS)
        self.assertIsNone(RollingCheckpoint('inline').begin(before[:6], 20000, CODE_TOOLS))


if __name__ == '__main__':
    unittest.main()
