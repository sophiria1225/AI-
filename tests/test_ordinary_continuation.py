import copy
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from native_conversation import NativeConversation
from ordinary_continuation import OrdinaryInference, conversation
from probe_ordinary_continuation import public_summary
from run_context_comparison import BudgetStop, write_json
from run_ordinary_continuation import replay


class OrdinaryContinuationTests(unittest.TestCase):
    def prefix(self):
        v = NativeConversation('original system', {'instruction': 'fixture task'})
        for i in range(2):
            fn = {'name': 'fixture__read', 'arguments': '{}'}
            v.append({'role': 'assistant', 'content': '', 'tool_calls': [
                {'id': f'c{i}', 'type': 'function', 'function': fn}]}, [
                {'id': f's{i}', 'action': fn, 'observation': {'observation': 'fixture'}, 'assistant': ''}])
        return {'conversation_private': v.messages(), 'public_task': {'instruction': 'fixture task'}}

    def test_both_interfaces_keep_identical_task_actions_and_observations(self):
        p = self.prefix(); original = copy.deepcopy(p)
        a, b = [conversation(p, arm).messages() for arm in ('native', 'python')]
        self.assertEqual(a[1:], b[1:]); self.assertEqual(a[1:], p['conversation_private'][1:])
        self.assertNotEqual(a[0], b[0]); self.assertEqual(p, original)
        self.assertIn('no user-defined variables exist yet', b[0]['content'])
        self.assertNotIn('roommate', b[0]['content']); self.assertNotIn('P60', b[0]['content'])

    def test_unknown_arm_or_changed_task_is_rejected(self):
        p = self.prefix()
        with self.assertRaises(ValueError): conversation(p, 'new_method')
        p['public_task'] = {'instruction': 'changed'}
        with self.assertRaises(ValueError): conversation(p, 'native')

    def replay_fixture(self):
        catalog = Mock(visible={'fixture__read'})
        catalog.decode.return_value = {'app': 'fixture', 'api': 'read', 'args': {}}
        catalog.expose_requested_document.return_value = []
        bridge = Mock(); bridge.request.return_value = {'ok': True, 'result': {'observation': '[]'}}
        p = {'events': [{'span_id': 's1', 'api_request_sent': True, 'new_tools': []},
                        {'span_id': 's2', 'api_request_sent': False, 'new_tools': []}],
             'spans': {'s1': {'action': {'name': 'fixture__read', 'arguments': '{}'},
                               'observation': {'observation': '[]'}}},
             'manifest': {'files': {'dbs/fixture': {'sha256': 'hash'}},
                          'state': {'visible_api_schemas': ['fixture__read']}}}
        return p, catalog, bridge

    def test_replay_accounts_only_sent_calls_and_checks_database_bytes(self):
        p, c, b = self.replay_fixture(); a = {}
        with patch('run_ordinary_continuation.db_hashes', return_value={'dbs/fixture': 'hash'}):
            replay(p, c, b, Path('/fixture'), a)
        self.assertEqual(b.request.call_count, 1); self.assertEqual(a['observation_matches'], 1)
        self.assertTrue(a['db_files_match'])
        with patch('run_ordinary_continuation.db_hashes', return_value={'dbs/fixture': 'changed'}):
            with self.assertRaises(ValueError): replay(p, c, b, Path('/fixture'), {})

    def test_replay_response_mismatch_stops_before_success(self):
        p, c, b = self.replay_fixture(); a = {}; b.request.return_value['result'] = {'observation': '[1]'}
        with self.assertRaises(ValueError): replay(p, c, b, Path('/fixture'), a)
        self.assertEqual(a['api_requests'], 1); self.assertEqual(a['observation_matches'], 0)
        self.assertFalse(a['db_files_match'])

    def test_unknown_replay_effect_is_counted_and_not_retried(self):
        p, c, b = self.replay_fixture(); a = {}; b.request.side_effect = TimeoutError()
        with self.assertRaises(TimeoutError): replay(p, c, b, Path('/fixture'), a)
        self.assertEqual(a['unknown_effect_requests'], 1); self.assertEqual(b.request.call_count, 1)

    def inference(self, out, **changes):
        config = {'model': {'num_ctx': 2000}, 'agent_temperature': 1.0, 'seed': 54,
            'max_output_tokens': 10, 'max_calls': 3, 'max_total_tokens': 1000, 'max_wall_seconds': 60}
        return OrdinaryInference(config | changes, Path(out))

    def response(self, **changes):
        return {'status': 'ok', 'input_tokens': 10, 'output_tokens': 2, 'cached_input_tokens': 0,
            'wall_seconds': .01, 'message': {'role': 'assistant', 'content': 'fixture'},
            'timings': {'cache_n': 0, 'prompt_n': 10, 'predicted_n': 2, 'prompt_ms': 1, 'predicted_ms': 1}} | changes

    def test_first_cold_then_warm_seeds_and_all_logical_tokens_counted(self):
        with tempfile.TemporaryDirectory() as out, patch('ordinary_continuation.count_input', return_value={'input_tokens': 10}), \
                patch('ordinary_continuation.model_call_stream', return_value=self.response()) as model:
            i = self.inference(out); i.call([], []); i.call([], [])
            self.assertEqual([r.args[0]['cache_prompt'] for r in model.call_args_list], [False, True])
            self.assertEqual([r.args[0]['seed'] for r in model.call_args_list], [54, 55])
            self.assertEqual(i.tokens, 24)

    def test_token_admission_blocks_generation_before_dispatch(self):
        with tempfile.TemporaryDirectory() as out, patch('ordinary_continuation.count_input', return_value={'input_tokens': 10}), \
                patch('ordinary_continuation.model_call_stream') as model:
            i = self.inference(out, max_total_tokens=19)
            with self.assertRaises(BudgetStop): i.call([], [])
            model.assert_not_called(); self.assertEqual(i.calls, [])

    def test_unknown_usage_cannot_return_a_message_or_request_again(self):
        with tempfile.TemporaryDirectory() as out, patch('ordinary_continuation.count_input', return_value={'input_tokens': 10}), \
                patch('ordinary_continuation.model_call_stream', return_value=self.response(status='error', input_tokens=None, output_tokens=None)) as model:
            i = self.inference(out)
            with self.assertRaisesRegex(BudgetStop, 'model_usage_unknown'): i.call([], [])
            with self.assertRaises(RuntimeError): i.call([], [])
            self.assertEqual(model.call_count, 1); self.assertFalse(i.calls[0]['usage_known'])

    def test_quarantined_response_with_terminal_usage_still_costs_tokens(self):
        with tempfile.TemporaryDirectory() as out, patch('ordinary_continuation.count_input', return_value={'input_tokens': 10}), \
                patch('ordinary_continuation.model_call_stream', return_value=self.response(status='error')):
            i = self.inference(out)
            with self.assertRaisesRegex(BudgetStop, 'model_response_unusable'): i.call([], [])
            self.assertEqual(i.tokens, 12); self.assertTrue(i.calls[0]['usage_known'])

    def test_count_mismatch_or_output_overrun_cannot_execute_response(self):
        for change in ({'input_tokens': 11}, {'output_tokens': 11}):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as out, \
                    patch('ordinary_continuation.count_input', return_value={'input_tokens': 10}), \
                    patch('ordinary_continuation.model_call_stream', return_value=self.response(**change)):
                with self.assertRaises(RuntimeError): self.inference(out).call([], [])

    def test_warm_first_response_is_quarantined(self):
        response = self.response(cached_input_tokens=9, timings={'cache_n': 9, 'prompt_n': 1,
            'predicted_n': 2, 'prompt_ms': 1, 'predicted_ms': 1})
        with tempfile.TemporaryDirectory() as out, patch('ordinary_continuation.count_input', return_value={'input_tokens': 10}), \
                patch('ordinary_continuation.model_call_stream', return_value=response):
            with self.assertRaises(RuntimeError): self.inference(out).call([], [])

    def test_interrupt_preserves_adapter_receipt_and_does_not_return_message(self):
        with tempfile.TemporaryDirectory() as out, patch('ordinary_continuation.count_input', return_value={'input_tokens': 10}):
            def interrupted(cfg, messages, folder, remaining, tools):
                folder.mkdir(); write_json(folder / 'response.json', self.response(status='error', input_tokens=None, output_tokens=None))
                raise KeyboardInterrupt()
            with patch('ordinary_continuation.model_call_stream', side_effect=interrupted):
                i = self.inference(out)
                with self.assertRaises(KeyboardInterrupt): i.call([], [])
                self.assertEqual(len(i.calls), 1); self.assertFalse(i.calls[0]['usage_known'])

    def test_public_result_excludes_interpreter_output_and_extra_private_fields(self):
        from collections import defaultdict
        s = defaultdict(lambda: 0)
        s.update(python_session={'programs': [{'stdout': 'private-fixture-value'}],
                                'status': 'closed', 'container_removed': True}, private='private-fixture-value')
        public = public_summary(s)
        self.assertNotIn('private-fixture-value', str(public)); self.assertNotIn('python_session', public)
        self.assertEqual(public['python']['program_count'], 1)
