"""New max-two worker/inference, with handwritten I/O only; no native/model/API."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from checkpoint_representation_p139 import MODES, summary_note, delta_note
from checkpoint_representation_inference_p139 import CheckpointRepresentationInference
from checkpoint_representation_worker_fixture_p139 import fixture, configuration, write_wire_fixture
from rolling_checkpoint_worker_fixture import fixture as old_fixture
from receipt_reasoning_history import digest
from run_context_comparison import BudgetStop
from whole_task_checkpoint_representation_p139 import worker_config, initial_conversation, cell_id


def notes(messages):
    values = []
    for message in messages:
        content = message.get('content')
        if message['role'] == 'user' and isinstance(content, str) and content.startswith('{'):
            value = json.loads(content)
            if value.get('checkpoint_kind') in ('ordinary_fallible_summary', 'ordinary_fallible_delta_summary'):
                values.append(message)
    return values


class RepresentationInferenceTests(unittest.TestCase):
    def test_first_actual_packet_and_first_focus_are_old_ordinary_bytes_all_modes(self):
        options = dict(actions=('echo',)*5+('finish',), api_limit=160)
        old = old_fixture(policy='rolling_separate', **options)
        for mode in MODES:
            with self.subTest(mode=mode):
                got = fixture(mode=mode, **options)
                self.assertEqual(got['captured'], old['captured'])
                self.assertEqual(got['saved']['usage'], old['saved']['usage'])
                self.assertEqual(got['result']['checkpoint_control']['max_opportunities'], 2)
                self.assertEqual(got['result']['checkpoint_control']['opportunities'], 1)
                self.assertEqual(got['result']['phase'], 'P139')
                self.assertEqual(got['saved']['plan']['checkpoint_representation_mode'], mode)
                self.assertEqual(got['result']['checkpoint_representation_control']['actual_delta_actor_calls'], 0)

    def test_two_notes_preserve_first_bytes_and_full_count_binds_actor(self):
        values = [{k:[f'previous {k}'] for k in ('completed','usable_state','remaining','uncertainties')},
                  {k:[f'new {k}'] for k in ('completed','usable_state','remaining','uncertainties')}]
        got = fixture(mode='threshold_delta', actions=('echo',)*10+('finish',), summary_payloads=values)
        focus = [c for c in got['captured'] if c['role']=='focus']
        self.assertEqual(len(focus), 2)
        packet = json.loads(focus[1]['messages'][1]['content'])
        self.assertEqual(packet['previous_checkpoint'], values[0])
        actual = [c for c in got['captured'] if c['role']=='agent' and len(notes(c['messages']))==2]
        self.assertTrue(actual)
        for call in actual:
            self.assertEqual(notes(call['messages']), [summary_note(values[0]), delta_note(values[1])])
        views = got['saved']['checkpoint_representation_views']
        shown = [v for v in views if v['delta_view'] and v['model_attempted']]
        self.assertEqual(len(shown), len(actual))
        for v, c in zip(shown, actual, strict=True):
            self.assertEqual(v['model_messages_sha256'], digest(c['messages']))
            self.assertEqual(v['summary_notes_sha256'], digest(notes(c['messages'])))
            self.assertEqual(v['fragment_count'], 2)
        extra = [c for c in got['counted'] if len(notes(c))==2]
        self.assertTrue(extra)
        self.assertTrue(all(notes(c)[0]==summary_note(values[0]) for c in extra))
        self.assertEqual(got['result']['checkpoint_representation_control']['delta_installations'], 1)

    def test_recursive_replaces_second_and_no_mode_gets_third_opportunity(self):
        for mode in MODES:
            with self.subTest(mode=mode):
                got = fixture(mode=mode, actions=('echo',)*15+('finish',), max_calls=30)
                self.assertEqual(got['result']['checkpoint_control']['opportunities'], 2)
                self.assertEqual(sum(c['role']=='focus' for c in got['captured']), 2)
                expected = 2 if mode.endswith('_delta') else 1
                self.assertEqual(got['result']['checkpoint_representation_control']['fragment_count'], expected)
                self.assertTrue(got['result']['prefix_exposure_control']['accounting_complete'])
                last = got['saved']['prefix_exposure_events'][-1]
                self.assertEqual(last['role'], 'agent')
                self.assertEqual(last['status'], 'known_paid_actor')

    def test_second_timing_can_differ_without_changing_first_packet(self):
        opts = dict(actions=('echo',)*12+('finish',), focus_input_tokens=30000)
        threshold = fixture(mode='threshold_recursive', **opts)
        exposure = fixture(mode='exposure_recursive', **opts)
        t = [i for i,c in enumerate(threshold['captured']) if c['role']=='focus']
        e = [i for i,c in enumerate(exposure['captured']) if c['role']=='focus']
        self.assertEqual(t[0],e[0]); self.assertGreater(e[1],t[1])
        self.assertEqual(threshold['captured'][:t[0]+1],exposure['captured'][:e[0]+1])
        self.assertGreater(exposure['result']['prefix_exposure_control']['actual_decision_differences_from_threshold'],0)

    def test_combined_oversize_or_nonshrinking_delta_keeps_prior_and_pays(self):
        small={k:['a'] for k in ('completed','usable_state','remaining','uncertainties')}
        too_many={k:['b']*32 for k in small}
        for options in (dict(summary_payloads=[small,too_many]),dict(delta_not_shorter=True)):
            with self.subTest(options=list(options)):
                got=fixture(mode='threshold_delta',actions=('echo',)*10+('finish',),**options)
                ctrl=got['result']['checkpoint_representation_control']
                self.assertEqual(ctrl['delta_installations'],0)
                self.assertEqual(ctrl['actual_delta_actor_calls'],0)
                self.assertEqual(ctrl['fragment_count'],1)
                paid=[e for e in got['saved']['prefix_exposure_events'] if e['role']=='focus']
                self.assertEqual(len(paid),2)
                self.assertTrue(all(e['paid_focus_tokens']==10020 and e['exposure_after']==0 for e in paid))
                self.assertEqual(got['result']['checkpoint_control']['opportunities'],2)

    def test_first_invalid_then_second_is_ordinary_nonintervention(self):
        got=fixture(mode='threshold_delta',actions=('echo',)*12+('finish',),summary_mode=['invalid','valid'])
        offers=got['saved']['rolling_offers_private']
        self.assertEqual(len(offers),2)
        self.assertFalse(offers[1]['offer']['delta_requested'])
        self.assertEqual(got['result']['checkpoint_representation_control']['fragment_count'],1)
        self.assertEqual(got['result']['checkpoint_representation_control']['actual_delta_actor_calls'],0)

    def test_unknown_second_focus_stops_without_imputation_or_third(self):
        got=fixture(mode='threshold_delta',actions=('echo',)*12+('finish',),summary_mode=['valid','unknown'])
        self.assertEqual(got['captured'][-1]['role'],'focus')
        self.assertEqual(got['result']['unknown_usage_calls'],1)
        self.assertEqual(got['saved']['prefix_exposure_events'][-1]['status'],'unknown_terminal')
        self.assertEqual(got['result']['checkpoint_representation_control']['fragment_count'],1)
        self.assertFalse(got['result']['checkpoint_representation_control']['accounting_complete'])
        self.assertTrue(got['result']['cleanup_confirmed'])

    def test_unsubmitted_focus_spends_opportunity_not_tokens(self):
        got=fixture(mode='threshold_delta',actions=('echo',)*3+('finish',),max_calls=4)
        focus=[e for e in got['saved']['prefix_exposure_events'] if e['role']=='focus']
        self.assertEqual([e['status'] for e in focus],['not_dispatched'])
        self.assertIsNone(got['result']['prefix_exposure_control']['previous_focus_cost'])
        self.assertEqual(got['result']['checkpoint_control']['opportunities'],1)
        self.assertEqual(got['result']['checkpoint_representation_control']['actual_delta_actor_calls'],0)

    def test_post_actor_count_failure_preserves_known_cost_and_withholds_action(self):
        for error in (ValueError('synthetic counter failure'),BudgetStop('wall_limit_during_prefix_exposure_count')):
            with self.subTest(error=type(error).__name__),patch.object(CheckpointRepresentationInference,'_count_without_raw',side_effect=error):
                got=fixture(mode='threshold_delta',actions=('echo',)*9+('finish',))
            actors=[c for c in got['saved']['usage'] if c['role']=='agent']
            self.assertEqual(len(actors),len(got['programs'])+1)
            self.assertEqual(got['result']['unknown_usage_calls'],0)
            self.assertFalse(got['result']['checkpoint_representation_control']['accounting_complete'])
            self.assertFalse(got['saved']['prefix_exposure_events'][-1]['action_returned_to_worker'])
            self.assertTrue(got['result']['cleanup_confirmed'])

    def test_actual_delta_activity_requires_dispatch_not_installation(self):
        original=CheckpointRepresentationInference._resolve
        def stop_after_delta(instance,*args):
            result=original(instance,*args)
            if instance.checkpoint.delta_applied:
                raise BudgetStop('synthetic_stop_after_delta_installation')
            return result
        with patch.object(CheckpointRepresentationInference,'_resolve',stop_after_delta):
            got=fixture(mode='threshold_delta',actions=('echo',)*10+('finish',))
        ctrl=got['result']['checkpoint_representation_control']
        self.assertEqual(ctrl['delta_installations'],1)
        self.assertEqual(ctrl['actual_delta_actor_calls'],0)

    def test_unknown_actor_with_delta_counts_exposure_not_known_usage(self):
        got=fixture(mode='threshold_delta',actions=('echo',)*6+('unknown',))
        ctrl=got['result']['checkpoint_representation_control']
        self.assertEqual(ctrl['actual_delta_actor_calls'],1)
        self.assertEqual(ctrl['actual_delta_unknown_actor_calls'],1)
        self.assertEqual(ctrl['actual_delta_known_actor_calls'],0)
        self.assertEqual(got['result']['unknown_usage_calls'],1)
        self.assertFalse(ctrl['accounting_complete'])

    def test_real_max_two_rejects_mislabelled_or_three_configs(self):
        original,plan,item=configuration();mode='threshold_delta'
        config=worker_config(original,plan,item['task_id'],'error_exception',cell_id(1,mode),mode)
        conversation=initial_conversation(original,item['public_task'])
        with tempfile.TemporaryDirectory() as folder:
            for key,value in [('rolling_checkpoint_max_opportunities',3),('rolling_checkpoint_max_opportunities',True),
                              ('checkpoint_timing','exposure'),('checkpoint_representation','recursive')]:
                changed=deepcopy(config);changed[key]=value
                with self.subTest(key=key,value=value),self.assertRaises(ValueError):
                    CheckpointRepresentationInference(changed,Path(folder),conversation=conversation)
            obj=CheckpointRepresentationInference(config,Path(folder),conversation=conversation)
            self.assertEqual(obj.config['rolling_checkpoint_max_opportunities'],2)
            self.assertEqual(obj.checkpoint.max_opportunities,2)
            self.assertNotIn('prefix_exposure_mode',obj.config)

    def test_wire_fixture_preserves_new_summary_fields_for_independent_audit(self):
        with tempfile.TemporaryDirectory() as folder:
            got=fixture(mode='exposure_delta',actions=('echo',)*10+('finish',),folder=folder)
            trial=write_wire_fixture(folder,got)
            self.assertTrue((trial/'call_001/request.json').is_file())
            summary=json.loads((trial/'summary.json').read_text())
            self.assertEqual(summary['checkpoint_representation_mode'],'exposure_delta')
            self.assertIn('checkpoint_representation_control',summary)
            self.assertIn('prefix_exposure_control',summary)


if __name__=='__main__': unittest.main()
