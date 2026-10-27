"""P140 prompt boundary: handwritten histories, no model/native/API execution."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from checkpoint_delta_envelope_p140 import (MODES, DeltaEnvelopeCheckpoint,
    OBJECT_DELTA_SUMMARY_PROMPT, DELTA_SUMMARY_PROMPT, base_mode_for,
    serialize_fragment_body, validate_fragment_budget, trigger_decision)
from checkpoint_representation_p139 import RepresentationCheckpoint, trigger_decision as old_trigger
from single_checkpoint_history import FIELDS, parse_checkpoint
from test_checkpoint_representation_p139 import history, value, message


def installed(cls, mode, first=None):
    obj = cls(mode)
    obj.begin(history(6), 20000)
    obj.close_separate(history(6), message(value() if first is None else first),
                       'stop', usage_known=True)
    obj.decide(20000, 9000)
    return obj


class DeltaEnvelopeCoreTests(unittest.TestCase):
    def test_first_offer_and_accepted_view_are_frozen_bytes_all_three_modes(self):
        for mode in MODES:
            old = RepresentationCheckpoint(base_mode_for(mode)); new = DeltaEnvelopeCheckpoint(mode)
            self.assertEqual(new.begin(history(6), 20000), old.begin(history(6), 20000))
            self.assertEqual(new.close_separate(history(6), message(value()), 'stop', usage_known=True),
                             old.close_separate(history(6), message(value()), 'stop', usage_known=True))
            self.assertEqual(new.decide(20000, 9000), old.decide(20000, 9000))
            self.assertEqual(new.view(history(6)), old.view(history(6)))

    def test_second_offer_changes_only_candidate_system_prompt(self):
        for mode in MODES:
            old = installed(RepresentationCheckpoint, base_mode_for(mode))
            new = installed(DeltaEnvelopeCheckpoint, mode)
            a = old.begin(history(9), 20000, repeat_ready=True)
            b = new.begin(history(9), 20000, repeat_ready=True)
            if mode == 'exposure_delta_object':
                self.assertEqual(b['summary_messages'][0]['content'], OBJECT_DELTA_SUMMARY_PROMPT)
                self.assertEqual(a['summary_messages'][0]['content'], DELTA_SUMMARY_PROMPT)
                b['summary_messages'][0] = deepcopy(a['summary_messages'][0])
            self.assertEqual(a, b)
            self.assertEqual(new.pending, old.pending)

    def test_host_still_combines_two_notes_and_rejects_array_without_unwrapping(self):
        for reply, accepted in ((value('new'), True), ([value(), value('new')], False)):
            obj = installed(DeltaEnvelopeCheckpoint, 'exposure_delta_object')
            old_note = deepcopy(obj.summary_notes[0])
            obj.begin(history(9), 20000, repeat_ready=True)
            views = obj.close_separate(history(9), message(reply), 'stop', usage_known=True)
            if accepted:
                self.assertIsNotNone(views)
                obj.decide(20000, 10000)
                self.assertEqual(obj.fragment_count, 2)
                self.assertEqual(obj.summary_notes[0], old_note)
            else:
                self.assertIsNone(views['compacted'])
                self.assertEqual(obj.events[-1]['close_status'], 'invalid_summary')
                self.assertEqual(obj.fragment_count, 1)
            self.assertEqual(obj.opportunities, 2)
            self.assertIsNone(obj.begin(history(12), 50000, repeat_ready=True))

    def test_unchanged_parser_and_combined_character_and_item_caps(self):
        first = {k: [] for k in FIELDS}; second = deepcopy(first)
        first['completed'] = ['x'*2048, 'x'*2048, 'x'*2000]
        second['remaining'] = ['y'*1000]
        second['remaining'][0] += 'y'*(8192-len(serialize_fragment_body([first, second])))
        self.assertEqual(validate_fragment_budget([first, second])['body_characters'], 8192)
        second['remaining'][0] += 'y'
        with self.assertRaisesRegex(ValueError, 'body_too_long'):
            validate_fragment_budget([first, second])
        first = {k: [] for k in FIELDS}; second = deepcopy(first)
        first['remaining'] = ['old']*16; second['remaining'] = ['new']*16
        self.assertEqual(validate_fragment_budget([first, second])['field_item_counts']['remaining'], 32)
        second['remaining'].append('extra')
        with self.assertRaisesRegex(ValueError, 'field_too_long'):
            validate_fragment_budget([first, second])
        bad = value(); bad['usable_state'] = ['x'*2049]
        with self.assertRaises(ValueError): parse_checkpoint(message(bad), 'stop')

    def test_trigger_arithmetic_is_unchanged_under_explicit_new_mode(self):
        for mode in MODES:
            for count, exposure, opportunities in ((16383, 0, 0), (16384, 0, 0),
                    (14000, 20000, 1), (20000, 0, 1), (20000, 20000, 2)):
                args = dict(opportunities=opportunities, fresh_turns=3, eligible_raw=True,
                    measured_input_tokens=count, accumulated_exposure=exposure,
                    previous_focus_cost=20000 if opportunities else None)
                actual = trigger_decision(mode=mode, **args)
                previous = old_trigger(mode=base_mode_for(mode), **args)
                for key in ('version', 'mode'): actual.pop(key); previous.pop(key)
                self.assertEqual(actual, previous)


if __name__ == '__main__': unittest.main()
