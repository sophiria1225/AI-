"""P139 audit fixtures: handwritten I/O only; no model, API, native or code run."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from checkpoint_representation_worker_fixture_p139 import ROOT, fixture, write_wire_fixture
from audit_checkpoint_representation_trace_p139 import (audit_trace, AuditRepresentationCheckpoint,
    _audit_fragment_budget)
from checkpoint_representation_p139 import MODES
from checkpoint_representation_inference_p139 import CheckpointRepresentationInference
from run_context_comparison import BudgetStop
from tool_choice_residual import ToolChoiceResidualInference
from whole_task_rolling_checkpoint import initial_conversation
from whole_task_checkpoint_representation_p139 import representation_prefix_match


def prepare(folder, mode='exposure_delta', **options):
    result = fixture(mode=mode, folder=folder, **options)
    return write_wire_fixture(folder, result), result


def replay(trial):
    config = json.loads((trial/'plan.json').read_text())
    public = json.loads((trial/'public_task.json').read_text())
    original = json.loads((ROOT/'configs/P29_stateful_code_v01.json').read_text())
    return audit_trace(trial, config, initial_conversation(original, public))


def mutate(trial, name, fn):
    path = trial/(name+'.json')
    value = json.loads(path.read_text()); fn(value)
    path.write_text(json.dumps(value))


class RepresentationTraceAuditTests(unittest.TestCase):
    def test_all_four_real_worker_paths_and_delta_actor_exposure(self):
        for mode in MODES:
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as tmp:
                trial, result = prepare(tmp, mode, actions=('echo',)*12+('finish',), max_calls=30)
                checked = replay(trial)
                self.assertEqual(checked['known_total_tokens'], result['result']['known_total_tokens'])
                self.assertEqual(checked['checkpoint_representation_control'],
                                 result['saved']['summary']['checkpoint_representation_control'])
                self.assertLessEqual(checked['checkpoint_opportunity'], 2)
                self.assertEqual(checked['additional_model_calls'], 0)
                self.assertEqual(checked['additional_API_requests'], 0)
                self.assertEqual(checked['additional_tokenizer_calls'], 0)
                self.assertTrue(checked['representation_state_reconstructed_in_auditor'])
                self.assertIsNotNone(checked['representation_second_opportunity'])
                if mode.endswith('delta'):
                    self.assertEqual(checked['fragment_count'], 2)
                    self.assertEqual(checked['delta_installations'], 1)
                    self.assertGreater(checked['actual_delta_known_actor_calls'], 0)
                    self.assertEqual(checked['actual_delta_unknown_actor_calls'], 0)
                else:
                    self.assertEqual(checked['fragment_count'], 1)
                    self.assertEqual(checked['actual_delta_actor_calls'], 0)

    def test_prefix_evidence_compares_observed_inputs_not_seed(self):
        saved = []
        for mode in ('threshold_recursive', 'threshold_delta'):
            with tempfile.TemporaryDirectory() as tmp:
                trial, _ = prepare(tmp, mode, actions=('echo',)*12+('finish',), max_calls=30)
                saved.append(replay(trial)['representation_second_opportunity'])
        a, b = saved
        for key in ('after_model_calls', 'previous_cutoff', 'candidate_cutoff', 'accumulated_exposure',
                    'previous_focus_cost', 'first_checkpoint', 'prior_request_output_sequence'):
            self.assertEqual(a[key], b[key], key)
        self.assertNotEqual(a['candidate_focus_messages_sha256'], b['candidate_focus_messages_sha256'])
        self.assertFalse(a['delta_requested']); self.assertTrue(b['delta_requested'])
        with tempfile.TemporaryDirectory() as tmp:
            trial, _ = prepare(tmp, actions=('finish',))
            checked = replay(trial)
            self.assertIsNone(checked['representation_second_opportunity'])
            self.assertFalse(checked['representation_prefix_evidence']['second_opportunity_offered'])

    def test_paid_invalid_combined_oversize_and_nonshrinking_preserve_previous(self):
        fields = ('completed','usable_state','remaining','uncertainties')
        first = {k: [] for k in fields}; first['remaining']=['x']*20
        second = {k: [] for k in fields}; second['remaining']=['y']*20
        large1 = {k: [] for k in fields}; large1['remaining']=['x'*2000]*3
        large2 = {k: [] for k in fields}; large2['remaining']=['y'*2000]*2
        cases = [dict(summary_mode=('valid','invalid')),
                 dict(summary_payloads=[first,second]),
                 dict(summary_payloads=[large1,large2]),
                 dict(delta_not_shorter=True)]
        for options in cases:
            with self.subTest(options=list(options)), tempfile.TemporaryDirectory() as tmp:
                trial, result = prepare(tmp, 'threshold_delta', actions=('echo',)*10+('finish',),
                                        max_calls=30, **options)
                checked = replay(trial)
                self.assertEqual(checked['checkpoint_opportunity'], 2)
                self.assertEqual(checked['checkpoint_installations'], 1)
                self.assertEqual(checked['actual_delta_actor_calls'], 0)
                paid = [e for e in result['saved']['prefix_exposure_events'] if e['status']=='known_paid_focus']
                self.assertEqual(len(paid), 2)
                self.assertEqual(paid[-1]['exposure_after'], 0)
                self.assertEqual(checked['prefix_exposure_control']['previous_focus_cost'],paid[-1]['paid_focus_tokens'])

    def test_first_invalid_then_second_has_no_delta(self):
        with tempfile.TemporaryDirectory() as tmp:
            trial, _ = prepare(tmp, 'threshold_delta', summary_mode=('invalid','valid'),
                               actions=('echo',)*10+('finish',), max_calls=30)
            checked = replay(trial)
            self.assertFalse(checked['representation_second_opportunity']['delta_requested'])
            self.assertIsNone(checked['representation_second_opportunity']['first_checkpoint'])
            self.assertEqual(checked['actual_delta_actor_calls'], 0)

    def test_negative_measured_delta_keeps_signed_value_but_adds_zero(self):
        ordinary_count = CheckpointRepresentationInference._count_without_raw
        def negative_count(infer, messages, tools, call):
            ordinary_count(infer, messages, tools, call)
            # A handwritten native-count fixture, not an executed tokenizer.
            value = call['input_tokens'] + 7
            infer.exposure_counts[-1]['input_tokens'] = value
            return value
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(CheckpointRepresentationInference, '_count_without_raw', negative_count):
                trial, result = prepare(tmp, actions=('echo',)*9+('finish',), max_calls=30)
            checked = replay(trial)
            negative = [e for e in result['saved']['prefix_exposure_events']
                        if e.get('raw_delta') is not None and e['raw_delta'] < 0]
            self.assertTrue(negative)
            self.assertTrue(all(e['raw_delta'] == -7 and e['positive_part'] == 0
                                and e['exposure_after'] == e['exposure_before'] for e in negative))
            self.assertEqual(checked['prefix_exposure_control']['negative_raw_deltas'], len(negative))
            self.assertEqual(checked['checkpoint_opportunity'], 1)

    def test_installed_delta_without_actor_dispatch_is_not_exposure(self):
        ordinary_call = ToolChoiceResidualInference.call
        def stop_before_delta_dispatch(infer, role, messages, tools):
            if infer.checkpoint.delta_applied:
                raise BudgetStop('wall_limit')
            return ordinary_call(infer, role, messages, tools)
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(ToolChoiceResidualInference, 'call', stop_before_delta_dispatch):
                trial, result = prepare(tmp, 'threshold_delta', actions=('echo',)*10, max_calls=30)
            checked = replay(trial)
            self.assertEqual(checked['delta_installations'], 1)
            self.assertEqual(checked['fragment_count'], 2)
            self.assertEqual(checked['actual_delta_actor_calls'], 0)
            final_view = result['saved']['checkpoint_representation_views'][-1]
            self.assertTrue(final_view['delta_view'])
            self.assertFalse(final_view['model_attempted'])

    def test_observed_prefix_mismatch_and_nonactivation_are_not_equal(self):
        rows = []
        for mode, action in (('threshold_recursive', 'echo'), ('threshold_delta', 'fail')):
            with tempfile.TemporaryDirectory() as tmp:
                trial, _ = prepare(tmp, mode, actions=('echo',action)+('echo',)*10+('finish',), max_calls=30)
                rows.append(replay(trial))
        self.assertFalse(representation_prefix_match(*rows))
        with tempfile.TemporaryDirectory() as tmp:
            trial, _ = prepare(tmp, actions=('finish',))
            missing = replay(trial)
            self.assertIsNone(representation_prefix_match(missing, missing))

    def test_unsent_focus_consumes_opportunity_without_cost_or_exposure_reset(self):
        for options in (dict(max_calls=4),dict(token_limit=55000),dict(focus_input_tokens=64000)):
            with self.subTest(options=options), tempfile.TemporaryDirectory() as tmp:
                trial, result = prepare(tmp, actions=('echo',)*3+('finish',), **options)
                checked = replay(trial)
                unsent=[e for e in result['saved']['prefix_exposure_events'] if e['status']=='not_dispatched']
                self.assertTrue(unsent)
                for e in unsent:
                    self.assertEqual(e['exposure_before'],e['exposure_after'])
                    self.assertEqual(e['focus_cost_before'],e['focus_cost_after'])
                self.assertEqual(checked['usage_by_role']['focus']['calls'],0)

    def test_unknown_actor_focus_and_lost_terminal_keep_cost_and_stop(self):
        cases = [dict(summary_mode='unknown', actions=('echo',)*9),
                 dict(summary_mode='transport_error', actions=('echo',)*9),
                 dict(actions=('echo',)*8+('unknown',)),
                 dict(actions=('echo',)*8+('transport_error',))]
        for options in cases:
            with self.subTest(options=options), tempfile.TemporaryDirectory() as tmp:
                trial, result = prepare(tmp, 'threshold_delta', max_calls=30, **options)
                checked=replay(trial)
                self.assertEqual(checked['unknown_usage_calls'],1)
                self.assertFalse(checked['checkpoint_representation_accounting_complete'])
                self.assertEqual(checked['known_total_tokens'],result['result']['known_total_tokens'])
                if checked['actual_delta_actor_calls']:
                    self.assertEqual(checked['actual_delta_unknown_actor_calls'],1)

    def test_paid_measurement_failure_withholds_action_without_erasing_usage(self):
        for error in (ValueError('synthetic count error'),BudgetStop('wall_limit_before_prefix_exposure_count')):
            with self.subTest(error=type(error).__name__), tempfile.TemporaryDirectory() as tmp:
                with patch.object(CheckpointRepresentationInference,'_count_without_raw',side_effect=error):
                    trial,result=prepare(tmp,actions=('echo',)*10+('finish',),max_calls=30)
                checked=replay(trial)
                self.assertFalse(checked['prefix_exposure_accounting_complete'])
                self.assertEqual(checked['unknown_usage_calls'],0)
                self.assertEqual(checked['prefix_exposure_control']['incomplete_paid_actor_measurements'],1)
                self.assertEqual(checked['known_total_tokens'],result['result']['known_total_tokens'])

    def test_tampered_note_cutoff_native_input_and_actual_dispatch_rejected(self):
        changes = [
            ('rolling_offers_private',lambda a:a[1]['offer'].__setitem__('previous_cutoff',2)),
            ('rolling_offers_private',lambda a:a[1]['offer'].__setitem__('prior_summary_notes_sha256','bad')),
            ('rolling_offers_private',lambda a:a[1]['offer'].__setitem__('delta_requested',1)),
            ('rolling_closed_private',lambda a:a[-1].__setitem__('compacted_sha256','bad')),
            ('prefix_exposure_counts',lambda a:a[-1].__setitem__('messages_sha256','bad')),
            ('prefix_exposure_events',lambda a:next(x for x in a if x['status']=='known_paid_actor').__setitem__('positive_part',-1)),
            ('prefix_exposure_decisions',lambda a:a[-1].__setitem__('opportunities',3)),
            ('checkpoint_representation_views',lambda a:a[-1].__setitem__('summary_notes_sha256','bad')),
            ('checkpoint_representation_views',lambda a:a[-1].__setitem__('model_attempted',False)),
            ('summary',lambda a:a['checkpoint_representation_control'].__setitem__('actual_delta_actor_calls',999)),
            ('summary',lambda a:a['checkpoint_control'].__setitem__('max_opportunities',3)),
            ('summary',lambda a:a['checkpoint_control']['decisions'][0].__setitem__('accepted',1)),
        ]
        for name,change in changes:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp:
                trial,_=prepare(tmp,'threshold_delta',actions=('echo',)*10+('finish',),max_calls=30)
                replay(trial);mutate(trial,name,change)
                with self.assertRaises(ValueError):replay(trial)

    def test_actual_focus_and_actor_payloads_must_match_full_projected_view(self):
        for role in ('agent','focus'):
            with self.subTest(role=role), tempfile.TemporaryDirectory() as tmp:
                trial,result=prepare(tmp,'threshold_delta',actions=('echo',)*10+('finish',),max_calls=30)
                checked=replay(trial)
                cid=next(c['call_id'] for c in reversed(checked['request_checks']) if c['role']==role)
                mutate(trial/cid,'request',lambda p:p.__setitem__('max_tokens',1))
                with self.assertRaisesRegex(ValueError,'actual_rolling_request_differs'):replay(trial)

    def test_independent_combined_budget_is_not_per_fragment(self):
        value={k:[] for k in ('completed','usable_state','remaining','uncertainties')}
        first=dict(value,remaining=['a']*20);second=dict(value,remaining=['b']*20)
        _audit_fragment_budget([first]);_audit_fragment_budget([second])
        with self.assertRaises(ValueError):_audit_fragment_budget([first,second])
        first=dict(value,remaining=['a'*2000]*3);second=dict(value,remaining=['b'*2000]*2)
        _audit_fragment_budget([first]);_audit_fragment_budget([second])
        with self.assertRaises(ValueError):_audit_fragment_budget([first,second])
        with self.assertRaises(ValueError):AuditRepresentationCheckpoint('fixed_interval')


if __name__=='__main__':unittest.main()
