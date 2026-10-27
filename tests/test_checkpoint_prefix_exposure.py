from copy import deepcopy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from checkpoint_prefix_exposure import (MODES, PrefixExposureCheckpoint, PrefixExposureLedger,
                                       eligible_prefix_views, trigger_decision)
from rolling_checkpoint_history import RollingCheckpoint
from test_inline_checkpoint_protocol import VALID, fixture
from test_rolling_checkpoint_history import add_turn, text_summary


def decision(mode='prefix_exposure', **changes):
    values = dict(mode=mode, opportunities=1, fresh_turns=3, eligible_raw=True,
                  measured_input_tokens=14000, accumulated_exposure=20000, previous_focus_cost=20000)
    values.update(changes)
    return trigger_decision(**values)


def paid_focus(ledger, name='focus-1', cost=20000):
    return ledger.record_focus(call_id=name, model_attempted=True, usage_known=True,
                               input_tokens=cost-20, output_tokens=20)


class PrefixExposureTests(unittest.TestCase):
    def test_repeat_predicates_distinguish_three_fixed_policies(self):
        self.assertFalse(decision('rolling_separate')['offer'])
        self.assertTrue(decision('fixed_interval')['offer'])
        self.assertTrue(decision()['offer'])
        self.assertFalse(decision(accumulated_exposure=19999)['offer'])
        self.assertFalse(decision(accumulated_exposure=1000, measured_input_tokens=17000)['offer'])
        self.assertTrue(decision('rolling_separate', accumulated_exposure=1000,
                                 measured_input_tokens=17000)['offer'])

    def test_first_threshold_and_common_spacing_limits_never_change(self):
        for mode in MODES:
            self.assertFalse(decision(mode, opportunities=0, measured_input_tokens=16383)['offer'])
            self.assertTrue(decision(mode, opportunities=0, measured_input_tokens=16384)['offer'])
            for changes in ({'fresh_turns': 2}, {'opportunities': 3}, {'eligible_raw': False}):
                self.assertFalse(decision(mode, measured_input_tokens=50000, **changes)['offer'])
        self.assertFalse(decision(previous_focus_cost=None)['offer'])
        self.assertTrue(decision('fixed_interval', previous_focus_cost=None)['offer'])

    def test_false_integer_and_invalid_modes_are_rejected(self):
        for changes in ({'opportunities': True}, {'fresh_turns': False},
                        {'measured_input_tokens': 0}, {'accumulated_exposure': -1},
                        {'previous_focus_cost': True}, {'eligible_raw': 1}, {'mode': 'adaptive'}):
            with self.assertRaises(ValueError): decision(**changes)

    def test_only_known_paid_actor_contributes_and_negative_delta_is_preserved(self):
        ledger = PrefixExposureLedger('prefix_exposure')
        first = ledger.record_actor(call_id='actor-0', model_attempted=True, usage_known=True, input_tokens=3000)
        self.assertIsNone(first['raw_delta'])
        self.assertEqual(ledger.accumulated_exposure, 0)
        paid_focus(ledger)
        a = ledger.record_actor(call_id='actor-1', model_attempted=True, usage_known=True,
                                input_tokens=12000, without_raw_input_tokens=8000)
        self.assertEqual(a['added_exposure'], 4000)
        b = ledger.record_actor(call_id='actor-2', model_attempted=True, usage_known=True,
                                input_tokens=12000, without_raw_input_tokens=12007)
        self.assertEqual(b['raw_delta'], -7)
        self.assertEqual(b['positive_part'], 0)
        self.assertEqual(ledger.accumulated_exposure, 4000)
        self.assertEqual(ledger.summary()['negative_raw_deltas'], 1)
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            ledger.record_actor(call_id='actor-1', model_attempted=True, usage_known=True,
                                input_tokens=12000, without_raw_input_tokens=8000)

    def test_unsent_has_no_cost_or_reset_and_known_focus_always_resets(self):
        ledger = PrefixExposureLedger('rolling_separate')
        paid_focus(ledger)
        ledger.record_actor(call_id='actor-1', model_attempted=True, usage_known=True,
                            input_tokens=12000, without_raw_input_tokens=8000)
        ledger.record_actor(call_id='not-sent', model_attempted=False, usage_known=False)
        ledger.record_focus(call_id='not-sent', model_attempted=False, usage_known=False)
        self.assertEqual((ledger.previous_focus_cost, ledger.accumulated_exposure), (20000, 4000))
        # The ledger deliberately does not condition cost/reset on valid syntax
        # or installation. A rejected paid summary still bought a focus call.
        paid_focus(ledger, name='invalid-focus', cost=24000)
        self.assertEqual((ledger.previous_focus_cost, ledger.accumulated_exposure), (24000, 0))

    def test_unknown_sent_actor_or_focus_is_sticky_without_invented_exposure(self):
        for role in ('actor', 'focus'):
            ledger = PrefixExposureLedger('prefix_exposure')
            paid_focus(ledger)
            getattr(ledger, 'record_'+role)(call_id='unknown', model_attempted=True, usage_known=False)
            self.assertTrue(ledger.blocked)
            self.assertEqual(ledger.accumulated_exposure, 0)
            with self.assertRaisesRegex(ValueError, 'blocks_continuation'):
                paid_focus(ledger, name='later')

    def test_first_offer_and_selected_views_match_original_in_all_modes(self):
        before, _, _, _ = fixture()
        old = RollingCheckpoint('separate')
        original = old.begin(before, 20000)
        for mode in MODES:
            new = PrefixExposureCheckpoint(mode)
            self.assertEqual(new.begin(before, 20000), original)
            views = new.close_separate(before, text_summary(VALID), 'stop', usage_known=True)
            new.decide(20000, 9000)
            self.assertEqual(new.view(before), views['compacted'])

    def test_count_projection_preserves_previous_summary_and_exact_recent_tail(self):
        before, _, _, conversation = fixture()
        new = PrefixExposureCheckpoint('prefix_exposure')
        new.begin(before, 20000)
        new.close_separate(before, text_summary(VALID), 'stop', usage_known=True)
        new.decide(20000, 9000)
        for n in (6, 7, 8):
            archive, _ = add_turn(conversation, n)
        untouched = deepcopy(archive)
        result = eligible_prefix_views(new, archive)
        self.assertEqual(result['without_raw'][:3], result['working'][:3])
        self.assertEqual(result['without_raw'][3:], archive[result['raw_end']:])
        self.assertEqual(result['eligible_raw_messages'], result['raw_end']-new.cutoff)
        self.assertGreater(result['eligible_raw_messages'], 0)
        self.assertEqual(archive, untouched)
        self.assertEqual(new.view(archive), result['working'])

    def test_repeat_offer_below_native_threshold_keeps_actual_count_and_packet(self):
        before, _, _, conversation = fixture()
        new = PrefixExposureCheckpoint('prefix_exposure')
        new.begin(before, 20000)
        new.close_separate(before, text_summary(VALID), 'stop', usage_known=True)
        new.decide(20000, 9000)
        for n in (6, 7, 8): archive, _ = add_turn(conversation, n)
        self.assertIsNone(new.begin(archive, 50000, repeat_ready=False))
        offered = new.begin(archive, 14000, repeat_ready=True)
        self.assertEqual(offered['trigger_input_tokens'], 14000)
        self.assertEqual(offered['opportunity_index'], 2)
        self.assertEqual(new.pending['before'], archive)


if __name__ == '__main__': unittest.main()
