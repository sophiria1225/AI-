from copy import deepcopy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from inline_checkpoint_history import BOUNDARY, OFFER, InlineCheckpoint
from inline_checkpoint_protocol import split_inline_response
from public_display import CODE_TOOLS
from single_checkpoint_history import candidate
from test_inline_checkpoint_protocol import VALID, fixture, response, split


class InlineCheckpointHistoryTests(unittest.TestCase):
    def test_one_opportunity_after_threshold_and_three_closed_turns(self):
        before, _, _, _ = fixture()
        control = InlineCheckpoint()
        self.assertIsNone(control.begin(before, CODE_TOOLS, 16383))
        self.assertIsNone(control.begin(before[:6], CODE_TOOLS, 20000))
        offered = control.begin(before, CODE_TOOLS, 16384)
        self.assertTrue(control.opportunity_used)
        self.assertIsNone(control.begin(before, CODE_TOOLS, 20000))
        cutoff = candidate(before)['cutoff']
        self.assertEqual(offered['messages'][:cutoff], before[:cutoff])
        self.assertEqual(offered['messages'][cutoff]['content'], BOUNDARY)
        self.assertEqual(offered['messages'][cutoff+1:-1], before[cutoff:])
        self.assertEqual(offered['messages'][-1]['content'], OFFER)

    def test_offer_and_candidate_do_not_mutate_archival_history_or_schema(self):
        before, after, message, _ = fixture()
        saved, tools = deepcopy(before), deepcopy(CODE_TOOLS)
        control = InlineCheckpoint()
        offered = control.begin(before, CODE_TOOLS, 20000)
        offered['messages'][0]['content'] = 'outside mutation'
        views = control.close(after, split(message))
        views['ordinary'][0]['content'] = 'outside mutation'
        self.assertEqual(before, saved)
        self.assertEqual(CODE_TOOLS, tools)
        control.decide(100, 99)
        self.assertEqual(control.view(after)[0], saved[0])

    def test_current_and_all_future_turns_remain_literal_after_acceptance(self):
        before, after, message, conv = fixture()
        control = InlineCheckpoint()
        control.begin(before, CODE_TOOLS, 20000)
        views = control.close(after, split(message))
        control.decide(100, 99)
        selected = control.view(after)
        self.assertEqual(selected, views['compacted'])
        future = response(); future['tool_calls'][0]['id'] = 'future-id'
        conv.append(future, [{'id': 's6', 'action': future['tool_calls'][0]['function'],
                              'observation': {'status': 'error', 'stdout': 'future literal'}}])
        later, _ = conv.for_model()
        self.assertEqual(control.view(later), selected + later[len(after):])
        self.assertEqual(later[:len(after)], after)

    def test_nonshrinking_and_invalid_checkpoint_never_retry(self):
        for message, ordinary, compacted in ((response(VALID), 100, 100),
                                             (response({'completed': []}), None, None)):
            before, after, raw, _ = fixture(message)
            control = InlineCheckpoint()
            control.begin(before, CODE_TOOLS, 20000)
            views = control.close(after, split(raw))
            if ordinary is not None:
                control.decide(ordinary, compacted)
            self.assertFalse(control.decision['accepted'])
            self.assertEqual(control.view(after), views['ordinary'])
            self.assertIsNone(control.begin(after, CODE_TOOLS, 50000))

    def test_cannot_continue_before_close_and_native_comparison_or_change_closed_source(self):
        before, after, message, _ = fixture()
        control = InlineCheckpoint()
        control.begin(before, CODE_TOOLS, 20000)
        with self.assertRaisesRegex(ValueError, 'close_and_resolve'):
            control.view(before)
        control.close(after, split(message))
        with self.assertRaisesRegex(ValueError, 'close_and_resolve'):
            control.view(after)
        control.decide(100, 99)
        changed = deepcopy(after); changed[-1]['content'] += ' altered'
        with self.assertRaisesRegex(ValueError, 'archive_changed'):
            control.view(changed)
        with self.assertRaisesRegex(ValueError, 'unresolved_closed'):
            control.decide(100, 98)
        with self.assertRaisesRegex(ValueError, 'one_offered'):
            control.close(after, split(message))

    def test_missing_metadata_or_malformed_action_is_a_spent_opportunity(self):
        for msg in (response(), response(arguments='not JSON')):
            before, after, message, _ = fixture(msg)
            control = InlineCheckpoint()
            control.begin(before, CODE_TOOLS, 20000)
            control.close(after, split(message))
            self.assertEqual(control.view(after), after)
            self.assertFalse(control.decision['accepted'])
            self.assertIsNone(control.begin(after, CODE_TOOLS, 50000))


if __name__ == '__main__':
    unittest.main()
