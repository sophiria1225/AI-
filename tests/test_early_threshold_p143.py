"""Handwritten threshold boundaries and live/audit controller agreement; no I/O."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import checkpoint_early_threshold_p143 as core
from checkpoint_object_timing_p141 import DeltaEnvelopeCheckpoint as PreviousCheckpoint
from audit_early_threshold_trace_p143 import AuditRepresentationCheckpoint, RepresentationExposureAudit, audit_trace
from checkpoint_early_threshold_inference_p143 import CheckpointDeltaEnvelopeInference
from test_checkpoint_representation_p139 import history, value, message
from single_checkpoint_history import candidate


def decision(mode, **changes):
    args=dict(mode=mode,opportunities=0,fresh_turns=3,eligible_raw=True,
        measured_input_tokens=8192,accumulated_exposure=0,previous_focus_cost=None)
    args.update(changes)
    return core.trigger_decision(**args)


def first(cls,mode):
    c=cls(mode);raw=history(6)
    c.begin(raw,8192)
    c.close_separate(raw,message(value()),'stop',usage_known=True)
    c.decide(8192,4000)
    return c


class EarlyThresholdTests(unittest.TestCase):
    def test_first_and_repeat_exact_threshold_for_both_modes(self):
        for mode in core.MODES:
            for opportunity in (0,1):
                self.assertFalse(decision(mode,opportunities=opportunity,measured_input_tokens=8191)['offer'])
                self.assertTrue(decision(mode,opportunities=opportunity,measured_input_tokens=8192)['offer'])
                self.assertTrue(decision(mode,opportunities=opportunity,measured_input_tokens=12000)['offer'])
            for cls in (core.DeltaEnvelopeCheckpoint,AuditRepresentationCheckpoint):
                with self.subTest(mode=mode,cls=cls.__name__):
                    c=cls(mode);self.assertIsNone(c.begin(history(6),8191));self.assertIsNotNone(c.begin(history(6),8192))
                    c=first(cls,mode);self.assertIsNone(c.begin(history(9),8191,repeat_ready=True));self.assertIsNotNone(c.begin(history(9),8192))
            self.assertIsNone(PreviousCheckpoint(mode).begin(history(6),8192))

    def test_fresh_raw_and_max_two_constraints_remain(self):
        for change in ({'fresh_turns':2},{'eligible_raw':False},{'opportunities':2}):
            for mode in core.MODES:self.assertFalse(decision(mode,measured_input_tokens=50000,**change)['offer'])
        for cls in (core.DeltaEnvelopeCheckpoint,AuditRepresentationCheckpoint):
            c=first(cls,core.MODES[1]);c.begin(history(9),8192)
            c.close_separate(history(9),message(value('delta')),'stop',usage_known=True);c.decide(8192,4000)
            self.assertIsNone(c.begin(history(12),50000));self.assertEqual(c.opportunities,2)

    def test_live_and_independent_audit_transitions_match(self):
        for mode in core.MODES:
            live=core.DeltaEnvelopeCheckpoint(mode);audit=AuditRepresentationCheckpoint(mode)
            for raw,text,ordinary in [(history(6),'first',8192),(history(9),'second',9000)]:
                self.assertEqual(live.begin(raw,ordinary),audit.begin(raw,ordinary))
                self.assertEqual(live.close_separate(raw,message(value(text)),'stop',usage_known=True),audit.close_separate(raw,message(value(text)),'stop',usage_known=True))
                self.assertEqual(live.decide(ordinary,4000),audit.decide(ordinary,4000))
                self.assertEqual(live.view(raw),audit.view(raw))

    def test_object_prompt_and_immutable_first_note(self):
        c=first(core.DeltaEnvelopeCheckpoint,core.MODES[1]);note=deepcopy(c.summary_notes[0]);raw=history(9);before=deepcopy(raw)
        offered=c.begin(raw,8192)
        self.assertEqual(offered['summary_messages'][0]['content'],core.OBJECT_DELTA_SUMMARY_PROMPT)
        c.close_separate(raw,message(value('delta')),'stop',usage_known=True);c.decide(8192,4000)
        self.assertEqual(c.summary_notes[0],note);self.assertEqual(c.fragment_count,2);self.assertEqual(raw,before)
        prior=PreviousCheckpoint(core.MODES[1]);old=prior.begin(history(6),20000)
        self.assertEqual(old['summary_messages'],core.DeltaEnvelopeCheckpoint(core.MODES[1]).begin(history(6),8192)['summary_messages'])

    def test_rejected_first_uses_ordinary_second_without_delta(self):
        for cls in (core.DeltaEnvelopeCheckpoint,AuditRepresentationCheckpoint):
            c=cls(core.MODES[1]);c.begin(history(6),8192);c.close_separate(history(6),message(value()),'stop',usage_known=True);c.decide(8192,9000)
            offer=c.begin(history(9),8192)
            self.assertFalse(offer['delta_requested']);self.assertEqual(offer['summary_messages'],candidate(history(9))['summary_messages'])

    def test_strict_types_and_no_exposure_arm(self):
        for changes in ({'measured_input_tokens':True},{'opportunities':False},{'eligible_raw':1},{'previous_focus_cost':0}):
            with self.assertRaises(ValueError):decision(core.MODES[0],**changes)
        for constructor in (core.DeltaEnvelopeCheckpoint,core.DeltaEnvelopeExposureLedger,AuditRepresentationCheckpoint):
            with self.assertRaises(ValueError):constructor('exposure_delta_object')
        with self.assertRaises(ValueError):decision('exposure_delta_object')

    def test_independent_predicate_reconstruction_matches_first_and_repeat(self):
        for mode in core.MODES:
            for repeated in (False,True):
                control=first(AuditRepresentationCheckpoint,mode) if repeated else AuditRepresentationCheckpoint(mode)
                raw=history(9 if repeated else 6)
                audit=RepresentationExposureAudit(None,{'checkpoint_representation_mode':mode},{},[],lambda name,default=None:[])
                audit.cost=500;audit.exposure=999
                for measured in (8191,8192,12000):
                    actual=audit.decision(control,raw,measured,3)
                    expected=core.trigger_decision(mode=mode,opportunities=control.opportunities,
                        fresh_turns=3 if repeated else 6,eligible_raw=True,measured_input_tokens=measured,
                        accumulated_exposure=999,previous_focus_cost=500)
                    self.assertEqual({k:actual[k] for k in expected},expected)

    def test_inference_rejects_old_or_untyped_threshold_before_initializing(self):
        for threshold in (None,16384,True,'8192'):
            with self.assertRaisesRegex(ValueError,'fixed_P143_8192_threshold_required'):
                CheckpointDeltaEnvelopeInference({'checkpoint_trigger_input_tokens':threshold},Path('/nonexistent/synthetic'),conversation=None)

    def test_audit_rejects_wrong_threshold_before_any_file_reads(self):
        for threshold in (None,16384,True,'8192'):
            with self.assertRaisesRegex(ValueError,'fixed_P143_audit_8192_threshold'):
                audit_trace(Path('/nonexistent/synthetic'),{'checkpoint_trigger_input_tokens':threshold},None)

if __name__=='__main__':unittest.main()
