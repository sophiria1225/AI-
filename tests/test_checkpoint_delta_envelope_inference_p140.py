"""Real new worker/admission with handwritten transports, never a model or tokenizer."""
from copy import deepcopy
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from checkpoint_delta_envelope_p140 import MODES, OBJECT_DELTA_SUMMARY_PROMPT
from checkpoint_delta_envelope_inference_p140 import CheckpointDeltaEnvelopeInference
from checkpoint_delta_envelope_worker_fixture_p140 import fixture, configuration, write_wire_fixture
from checkpoint_representation_worker_fixture_p139 import fixture as previous_fixture
from test_checkpoint_representation_inference_p139 import notes
from test_checkpoint_representation_p139 import value
from receipt_reasoning_history import digest
from run_context_comparison import BudgetStop
from whole_task_checkpoint_delta_envelope_p140 import worker_config, initial_conversation, cell_id


class DeltaEnvelopeInferenceTests(unittest.TestCase):
    def test_unchanged_control_arms_preserve_complete_requests_and_usage(self):
        for mode in MODES[:2]:
            opts = dict(mode=mode, actions=('echo',)*10+('finish',))
            before = previous_fixture(**opts); after = fixture(**opts)
            self.assertEqual(after['captured'], before['captured'])
            self.assertEqual(after['saved']['usage'], before['saved']['usage'])
            self.assertEqual(after['result']['checkpoint_control'], before['result']['checkpoint_control'])
            self.assertEqual(after['result']['delta_envelope_control']['object_prompt_offers'], 0)

    def test_candidate_only_second_focus_prompt_diff_and_added_known_cost(self):
        opts = dict(actions=('echo',)*10+('finish',))
        old = fixture(mode='exposure_delta', **opts)
        new = fixture(mode='exposure_delta_object', **opts)
        old_calls = deepcopy(old['captured']); new_calls = deepcopy(new['captured'])
        focuses = [i for i,c in enumerate(new_calls) if c['role']=='focus']
        self.assertEqual(len(focuses), 2)
        second = focuses[1]
        self.assertEqual(old_calls[:second], new_calls[:second])
        self.assertEqual(new_calls[second]['messages'][0]['content'], OBJECT_DELTA_SUMMARY_PROMPT)
        new_calls[second]['messages'][0] = old_calls[second]['messages'][0]
        self.assertEqual(new_calls[:second+1], old_calls[:second+1])
        # Later budget notices honestly reflect the candidate's paid +37 input.
        # No post-intervention trajectory equality is required or claimed.
        a, b = old['saved']['usage'], deepcopy(new['saved']['usage'])
        # The fixture's +37 is a handwritten measurement, not a tokenizer estimate.
        self.assertEqual(b[second]['input_tokens']-a[second]['input_tokens'], 37)
        self.assertEqual(sum(c['input_tokens']+c['output_tokens'] for c in b)-
                         sum(c['input_tokens']+c['output_tokens'] for c in a), 37)
        ctrl = new['result']['delta_envelope_control']
        self.assertEqual(ctrl['object_prompt_offers'], 1)
        self.assertEqual(ctrl['object_prompt_dispatched_focus_calls'], 1)
        self.assertEqual(ctrl['object_prompt_known_focus_calls'], 1)
        self.assertEqual(ctrl['object_prompt_unknown_focus_calls'], 0)
        self.assertTrue(ctrl['accounting_complete'])

    def test_candidate_preserves_old_note_in_full_count_and_sent_two_note_actor(self):
        got = fixture(mode='exposure_delta_object', actions=('echo',)*10+('finish',),
                      summary_payloads=[value('prior'), value('new')])
        actual = [c for c in got['captured'] if c['role']=='agent' and len(notes(c['messages']))==2]
        self.assertTrue(actual)
        first_note = notes(actual[0]['messages'])[0]
        views = [v for v in got['saved']['checkpoint_representation_views'] if v['delta_view'] and v['model_attempted']]
        self.assertEqual(len(actual), len(views))
        for call, view in zip(actual, views, strict=True):
            self.assertEqual(notes(call['messages'])[0], first_note)
            self.assertEqual(view['model_messages_sha256'], digest(call['messages']))
            self.assertIn(call['messages'], got['counted'])
        self.assertEqual(got['result']['delta_envelope_control']['actual_delta_actor_calls'], len(actual))

    def test_array_reply_and_combined_overflow_still_reject_pay_and_do_not_retry(self):
        for second in ([value('prior'), value('new')], {k:['b']*32 for k in value()}):
            got = fixture(mode='exposure_delta_object', actions=('echo',)*12+('finish',),
                          summary_payloads=[value('prior'), second])
            ctrl = got['result']['delta_envelope_control']
            self.assertEqual(ctrl['object_prompt_known_focus_calls'], 1)
            self.assertEqual(ctrl['actual_delta_actor_calls'], 0)
            self.assertEqual(got['result']['checkpoint_representation_control']['delta_installations'], 0)
            self.assertEqual(got['result']['checkpoint_control']['opportunities'], 2)
            self.assertEqual(len([c for c in got['captured'] if c['role']=='focus']), 2)
            self.assertEqual(got['saved']['prefix_exposure_events'][next(i for i,e in enumerate(got['saved']['prefix_exposure_events']) if e['role']=='focus')]['paid_focus_tokens'], 10020)

    def test_unknown_second_focus_cost_stays_unknown_and_stops(self):
        got = fixture(mode='exposure_delta_object', actions=('echo',)*12+('finish',),
                      summary_mode=['valid','unknown'])
        self.assertEqual(got['captured'][-1]['role'], 'focus')
        self.assertEqual(got['result']['unknown_usage_calls'], 1)
        ctrl = got['result']['delta_envelope_control']
        self.assertEqual(ctrl['object_prompt_unknown_focus_calls'], 1)
        self.assertEqual(ctrl['object_prompt_known_focus_calls'], 0)
        self.assertFalse(ctrl['accounting_complete'])
        self.assertTrue(got['result']['cleanup_confirmed'])

    def test_first_invalid_then_second_is_original_summary_prompt(self):
        got = fixture(mode='exposure_delta_object', actions=('echo',)*12+('finish',),
                      summary_mode=['invalid','valid'])
        self.assertEqual(got['result']['checkpoint_control']['opportunities'], 2)
        self.assertEqual(got['result']['delta_envelope_control']['object_prompt_offers'], 0)
        self.assertTrue(all(c['messages'][0]['content']!=OBJECT_DELTA_SUMMARY_PROMPT
                            for c in got['captured'] if c['role']=='focus'))

    def test_prepared_second_prompt_is_not_counted_as_dispatch(self):
        got = fixture(mode='exposure_delta_object', actions=('echo',)*12+('finish',), max_calls=8)
        ctrl = got['result']['delta_envelope_control']
        self.assertEqual(ctrl['object_prompt_offers'], 1)
        self.assertEqual(ctrl['object_prompt_dispatched_focus_calls'], 0)
        self.assertEqual(ctrl['actual_delta_actor_calls'], 0)
        self.assertEqual([e for e in got['saved']['prefix_exposure_events'] if e['role']=='focus'][-1]['status'], 'not_dispatched')

    def test_known_paid_actor_count_failure_withholds_action_without_losing_usage(self):
        with patch.object(CheckpointDeltaEnvelopeInference, '_count_without_raw',
                          side_effect=BudgetStop('synthetic wall limit')):
            got = fixture(mode='exposure_delta_object', actions=('echo',)*9+('finish',))
        self.assertEqual(got['result']['unknown_usage_calls'], 0)
        self.assertFalse(got['result']['delta_envelope_control']['accounting_complete'])
        self.assertEqual(len([c for c in got['saved']['usage'] if c['role']=='agent']), len(got['programs'])+1)
        self.assertTrue(got['result']['cleanup_confirmed'])

    def test_config_is_honest_three_arm_max_two_with_unchanged_output_cap(self):
        original, plan, item = configuration(); mode='exposure_delta_object'
        config = worker_config(original, plan, item['task_id'], 'error_exception', cell_id(1,mode), mode)
        conversation = initial_conversation(original,item['public_task'])
        with tempfile.TemporaryDirectory() as folder:
            for key, val in (('rolling_checkpoint_max_opportunities',3), ('max_output_tokens',8192),
                    ('checkpoint_representation_mode','threshold_delta'), ('checkpoint_timing','threshold')):
                changed = deepcopy(config); changed[key] = val
                with self.subTest(key=key), self.assertRaises(ValueError):
                    CheckpointDeltaEnvelopeInference(changed,Path(folder),conversation=conversation)
            obj = CheckpointDeltaEnvelopeInference(config,Path(folder),conversation=conversation)
            self.assertEqual(obj.checkpoint.max_opportunities, 2)
            self.assertNotIn('prefix_exposure_mode',obj.config)

    def test_wire_fixture_has_new_summary_for_independent_trace(self):
        with tempfile.TemporaryDirectory() as folder:
            got = fixture(mode='exposure_delta_object',actions=('echo',)*10+('finish',),folder=folder)
            trial = write_wire_fixture(folder,got)
            self.assertTrue((trial/'call_001/request.json').is_file())
            self.assertEqual(got['result']['phase'], 'P140')
            self.assertIn('delta_envelope_control',got['saved']['summary'])


if __name__ == '__main__': unittest.main()
