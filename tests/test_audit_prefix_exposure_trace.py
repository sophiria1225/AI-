"""Handwritten rolling worker fixtures only; no model/API/tokenizer/program runs."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from rolling_checkpoint_worker_fixture import ROOT, audit_fixture
from test_prefix_exposure_inference import run
from audit_prefix_exposure_trace import audit_trace
from prefix_exposure_inference import PrefixExposureInference
from run_context_comparison import BudgetStop
from whole_task_rolling_checkpoint import initial_conversation


def prepare(folder, mode='prefix_exposure', **kwargs):
    result = run(mode, folder=folder, **kwargs)
    trial = Path(folder)/'records/context_pilot'/result['result']['run_id']
    # The historical fixture has no new worker summary field. Augment this
    # handwritten producer, then encode its fake responses as raw wire JSON.
    summary = json.loads((trial/'summary.json').read_text())
    summary['prefix_exposure_control'] = result['exposure']
    (trial/'summary.json').write_text(json.dumps(summary))
    config = json.loads((trial/'plan.json').read_text())
    config['prefix_exposure_mode'] = mode
    (trial/'plan.json').write_text(json.dumps(config))
    with patch('audit_rolling_checkpoint_trace.audit_trace', return_value=None):
        audit_fixture(folder, result)
    return trial, result


def replay(trial):
    config = json.loads((trial/'plan.json').read_text())
    public = json.loads((trial/'public_task.json').read_text())
    original = json.loads((ROOT/'configs/P29_stateful_code_v01.json').read_text())
    return audit_trace(trial, config, initial_conversation(original, public))


def mutate(trial, name, fn):
    path = trial/(name+'.json')
    value = json.loads(path.read_text())
    fn(value)
    path.write_text(json.dumps(value))


class PrefixExposureAuditTests(unittest.TestCase):
    def test_three_modes_replay_paid_roles_and_decision_differences(self):
        for mode in ('rolling_separate', 'fixed_interval', 'prefix_exposure'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as tmp:
                trial, result = prepare(tmp, mode, actions=('echo',)*10+('finish',),
                                        api_limit=32, focus_input_tokens=30000)
                checked = replay(trial)
                self.assertEqual(checked['known_total_tokens'], result['result']['known_total_tokens'])
                self.assertEqual(checked['prefix_exposure_control'], result['exposure'])
                self.assertEqual(checked['additional_model_calls'], 0)
                self.assertEqual(checked['additional_API_requests'], 0)
                self.assertEqual(checked['additional_tokenizer_calls'], 0)
                self.assertTrue(checked['prefix_exposure_accounting_complete'])
                if mode == 'prefix_exposure':
                    self.assertGreater(checked['decision_differences_from_rolling_separate'], 0)
                    self.assertGreater(checked['decision_differences_from_fixed_interval'], 0)

    def test_paid_invalid_focus_resets_and_unsubmitted_focus_never_pays(self):
        cases = [dict(summary_mode='invalid', actions=('echo',)*9+('finish',), api_limit=32),
                 dict(actions=('echo',)*3+('finish',), max_calls=4),
                 dict(actions=('echo',)*3+('finish',), token_limit=55000),
                 dict(actions=('echo',)*3+('finish',), focus_input_tokens=64000)]
        for options in cases:
            with self.subTest(options=options), tempfile.TemporaryDirectory() as tmp:
                trial, result = prepare(tmp, **options)
                self.assertEqual(replay(trial)['prefix_exposure_control'], result['exposure'])

    def test_unknown_actor_focus_and_undispatched_counts_keep_cost(self):
        cases = [dict(summary_mode='unknown', actions=('echo',)*9),
                 dict(summary_mode='transport_error', actions=('echo',)*9),
                 dict(actions=('echo',)*3+('unknown',)),
                 dict(actions=('echo',)*3+('transport_error',)),
                 dict(count_delay=61), dict(first_cached=1),
                 dict(stop_after_api=True), dict(unknown_api=True), dict(cleanup_ok=False)]
        for options in cases:
            with self.subTest(options=options), tempfile.TemporaryDirectory() as tmp:
                trial, result = prepare(tmp, api_limit=32, **options)
                checked = replay(trial)
                self.assertEqual(checked['known_total_tokens'], result['result']['known_total_tokens'])
                self.assertEqual(checked['unknown_usage_calls'], result['result']['unknown_usage_calls'])
                self.assertEqual(checked['prefix_exposure_control'], result['exposure'])

    def test_known_paid_actor_withheld_after_counter_failure_and_wall_stop(self):
        for error in (ValueError('synthetic bad counter'), BudgetStop('wall_limit_before_prefix_exposure_count')):
            with self.subTest(error=type(error).__name__), tempfile.TemporaryDirectory() as tmp:
                with patch.object(PrefixExposureInference, '_count_without_raw', side_effect=error):
                    trial, result = prepare(tmp, actions=('echo',)*9+('finish',), api_limit=32)
                checked = replay(trial)
                self.assertFalse(checked['prefix_exposure_accounting_complete'])
                self.assertEqual(checked['known_total_tokens'], result['result']['known_total_tokens'])
                self.assertEqual(checked['unknown_usage_calls'], 0)
                self.assertEqual(checked['prefix_exposure_control']['incomplete_paid_actor_measurements'], 1)

    def test_counter_request_ledger_decision_and_summary_tampering_rejected(self):
        cases = [
            ('prefix_exposure_counts', lambda a: a[0].__setitem__('messages_sha256','bad')),
            ('prefix_exposure_counts', lambda a: a[0].__setitem__('model_config_sha256','bad')),
            ('prefix_exposure_counts', lambda a: a[0].__setitem__('count_only',False)),
            ('prefix_exposure_counts', lambda a: a[0].__setitem__('input_tokens',True)),
            ('prefix_exposure_events', lambda a: next(x for x in a if x['status']=='known_paid_actor').__setitem__('raw_delta',999999)),
            ('prefix_exposure_events', lambda a: next(x for x in a if x['status']=='known_paid_focus').__setitem__('paid_focus_tokens',1)),
            ('prefix_exposure_decisions', lambda a: a[-1].__setitem__('offer',not a[-1]['offer'])),
            ('summary', lambda a: a['prefix_exposure_control'].__setitem__('accumulated_exposure',0)),
            ('summary', lambda a: a.__setitem__('known_total_tokens',a['known_total_tokens']-10020)),
        ]
        for name, change in cases:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp:
                trial, _ = prepare(tmp, actions=('echo',)*10+('finish',), api_limit=32)
                replay(trial)
                mutate(trial, name, change)
                with self.assertRaises(ValueError):
                    replay(trial)

    def test_recorded_extra_count_failure_and_negative_raw_delta(self):
        original = PrefixExposureInference._count_without_raw
        def fail_counter(instance, messages, tools, call):
            with patch('rolling_checkpoint_inference.count_agent_input',
                       side_effect=ValueError('synthetic native count failure')):
                return original(instance, messages, tools, call)
        def negative_counter(instance, messages, tools, call):
            with patch('rolling_checkpoint_inference.count_agent_input',
                       return_value={'input_tokens': call['input_tokens']+7, 'wall_seconds': 0}):
                return original(instance, messages, tools, call)
        for replacement, negative in ((fail_counter, False), (negative_counter, True)):
            with self.subTest(negative=negative), tempfile.TemporaryDirectory() as tmp:
                with patch.object(PrefixExposureInference, '_count_without_raw', replacement):
                    trial, result = prepare(tmp, actions=('echo',)*9+('finish',), api_limit=32)
                checked = replay(trial)
                self.assertEqual(checked['known_total_tokens'], result['result']['known_total_tokens'])
                if negative:
                    self.assertGreater(checked['prefix_exposure_control']['negative_raw_deltas'], 0)
                    self.assertEqual(checked['prefix_exposure_control']['accumulated_exposure'], 0)
                    self.assertTrue(checked['prefix_exposure_accounting_complete'])
                else:
                    self.assertEqual(result['saved']['prefix_exposure_counts'][-1]['status'], 'failed')
                    self.assertFalse(checked['prefix_exposure_accounting_complete'])
                    self.assertEqual(checked['unknown_usage_calls'], 0)

    def test_bool_is_not_an_integer_in_exact_exposure_sidecars(self):
        for name, change in (
            ('prefix_exposure_events', lambda a: a[0].__setitem__('exposure_before', False)),
            ('prefix_exposure_decisions', lambda a: a[0].__setitem__('opportunities', False)),
            ('summary', lambda a: a['prefix_exposure_control'].__setitem__('event_count', True)),
        ):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp:
                trial, _ = prepare(tmp, actions=('finish',))
                replay(trial)
                mutate(trial, name, change)
                with self.assertRaises(ValueError):
                    replay(trial)

    def test_shadow_offer_without_focus_dispatch_is_not_actual_difference(self):
        original = PrefixExposureInference._count
        def trigger(instance, role, purpose, messages, tools):
            result = original(instance, role, purpose, messages, tools)
            if purpose == 'trigger' and instance.checkpoint.opportunities:
                result = dict(result, input_tokens=12000)
                instance.input_counts[-1]['input_tokens'] = 12000
                from run_context_comparison import write_json
                write_json(instance.output/'rolling_input_counts.json', instance.input_counts)
            return result
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(PrefixExposureInference, '_count', trigger):
                trial, result = prepare(tmp, actions=('echo',)*6+('finish',),
                                        api_limit=32, max_calls=8)
            checked = replay(trial)
            self.assertGreater(checked['decision_differences_from_rolling_separate'], 0)
            self.assertEqual(checked['actual_decision_differences_from_rolling_separate'], 0)
            last = next(x for x in reversed(result['saved']['prefix_exposure_events']) if x['role']=='focus')
            self.assertEqual(last['status'], 'not_dispatched')

    def test_skipped_repeat_with_actual_actor_dispatch_is_counted(self):
        with tempfile.TemporaryDirectory() as tmp:
            trial, _ = prepare(tmp, actions=('echo',)*10+('finish',), api_limit=32,
                               focus_input_tokens=30000)
            checked = replay(trial)
            self.assertGreater(checked['actual_decision_differences_from_fixed_interval'], 0)
            self.assertLessEqual(checked['actual_decision_differences_from_fixed_interval'],
                                 checked['decision_differences_from_fixed_interval'])

    def test_new_p138_worker_entrypoint_saves_control_and_replays(self):
        import run_whole_task_prefix_exposure_cell_p138 as worker
        import run_whole_task_rolling_checkpoint_cell as previous
        from rolling_checkpoint_worker_fixture import fixture
        from whole_task_prefix_exposure_p138 import cell_id
        from contextlib import ExitStack
        mode = 'prefix_exposure'
        rid = cell_id(4, mode)
        def execute(storage, root, plan, original, tools, item, arm, run_id, **unused):
            # Real new domain/helper and worker; only external fixture transports
            # and the three unused task identities are synthetic.
            plan = dict(plan, experiment='P138', known_tasks=[
                {'task_id':'fixture-photo'}, {'task_id':'fixture-expenses'},
                {'task_id':'fixture-refund'}, item])
            with ExitStack() as stack:
                for name in ('RecordedBridge', 'TypedBridgeProcess', 'PersistentApiPython'):
                    stack.enter_context(patch.object(worker, name, getattr(previous, name)))
                return worker.run_cell(storage, root, plan, original, tools, item, arm,
                                       run_id, prefix_exposure_mode=mode)
        with tempfile.TemporaryDirectory() as tmp:
            with patch('rolling_checkpoint_worker_fixture.run_cell', execute), \
                 patch('rolling_checkpoint_worker_fixture.cell_id', return_value=rid):
                result = fixture(policy='rolling_separate', actions=('echo',)*9+('finish',),
                                 api_limit=80, folder=tmp)
            trial = Path(tmp)/'records/context_pilot'/rid
            with patch('audit_rolling_checkpoint_trace.audit_trace', return_value=None):
                audit_fixture(tmp, result)
            checked = replay(trial)
            self.assertEqual(result['result']['phase'], 'P138')
            self.assertEqual(result['result']['prefix_exposure_mode'], mode)
            self.assertTrue(result['result']['cleanup_confirmed'])
            self.assertEqual(checked['prefix_exposure_control'],
                             result['saved']['summary']['prefix_exposure_control'])
            self.assertGreater(checked['prefix_exposure_control']['known_paid_focuses'], 0)
            self.assertEqual(checked['known_total_tokens'], result['result']['known_total_tokens'])
            self.assertTrue(checked['prefix_exposure_accounting_complete'])
            from audit_whole_task_prefix_exposure_p138 import audit_cell
            from whole_task_prefix_exposure_p138 import initial_conversation as initial
            from receipt_reasoning_history import digest
            plan = json.loads((trial/'comparison_plan.json').read_text())
            original = json.loads((ROOT/'configs/P29_stateful_code_v01.json').read_text())
            original['api_budget_by_task'] = {'34d9492_1': 80}
            original['max_output_tokens'] = 4096
            item = plan['known_tasks'][3]
            messages, _ = initial(original, item['public_task']).for_model(
                json.loads((trial/'plan.json').read_text())['observation_page_characters'])
            row = audit_cell(trial, ROOT, plan, original, item, mode,
                             {'base_messages_sha256': digest(messages)}, False)
            self.assertEqual(row['record_status'], 'unevaluated')
            self.assertIsNone(row['success'])
            self.assertEqual(row['known_total_tokens'], checked['known_total_tokens'])
            self.assertEqual(row['actual_decision_differences_from_fixed_interval'],
                             checked['actual_decision_differences_from_fixed_interval'])

    def test_actual_actor_and_summary_requests_remain_exact(self):
        for role in ('agent','focus'):
            with self.subTest(role=role), tempfile.TemporaryDirectory() as tmp:
                trial, result = prepare(tmp, actions=('echo',)*9+('finish',), api_limit=32)
                replay(trial)
                cid = next(c['id'] for c in result['saved']['usage'] if c['role']==role)
                mutate(trial/cid, 'request', lambda x: x.__setitem__('max_tokens',1))
                with self.assertRaisesRegex(ValueError, 'actual_rolling_request_differs'):
                    replay(trial)


if __name__ == '__main__':
    unittest.main()
