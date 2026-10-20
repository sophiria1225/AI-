import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from audit_native_execution import inspect_history
from native_conversation import NativeConversation
from run_native_batch import PHASES, public_body


class NativeHistoryPlanControls(unittest.TestCase):
    def test_execution_resources_tasks_and_discovery_remain_matched(self):
        before = json.loads((ROOT / 'configs/P8_native_baseline_v01.json').read_text())
        after = json.loads((ROOT / 'configs/P10_native_history_v01.json').read_text())
        for key in ('appworld_version', 'task_ids', 'model_selection', 'model', 'seed',
                    'agent_temperature', 'max_output_tokens', 'max_calls', 'max_total_tokens',
                    'max_wall_seconds', 'max_api_requests', 'observation_page_characters',
                    'discovery_policy'):
            self.assertEqual(before[key], after[key], key)
        self.assertEqual(after['wait_for_cache_probe'], 'P9_01')
        self.assertEqual(PHASES[after['phase']]['issue'], 42)
        self.assertEqual([r[0] for r in after['run_order']], before['task_ids'])

    def test_progress_keeps_its_own_marker_and_never_exports_input(self):
        text = public_body([{'task_number': 1, 'status': 'finished', 'calls': 2,
                             'declared_complete': True, 'instruction': 'PRIVATE_CONTENT'}],
                           {'status': 'running', 'phase': 'P10'})
        self.assertTrue(text.startswith('<!-- harness-native-baseline:P10_batch_v01 -->'))
        self.assertNotIn('PRIVATE_CONTENT', text)
        self.assertIn('未確定', text)

    def test_replay_detects_changed_result_and_keeps_unknown_usage_separate(self):
        task, prompt = {'task': 'private instruction'}, 'system'
        conversation = NativeConversation(prompt, task)
        payloads = {'call_001': {'messages': conversation.for_model()[0]}}
        call = {'id': 'a', 'type': 'function',
                'function': {'name': 'public_read', 'arguments': '{}'}}
        response = {'role': 'assistant', 'content': '', 'tool_calls': [call]}
        span = {'id': 's1', 'assistant': '', 'action': call['function'],
                'observation': {'format_error': 'not executed'}}
        conversation.append(response, [span])
        payloads['call_002'] = {'messages': conversation.for_model()[0]}
        usage = [{'id': 'call_001', 'status': 'ok'}, {'id': 'call_002', 'status': 'error'}]
        args = (task, prompt, usage, [{'call': 'call_001', 'span_id': 's1'}], {'s1': span},
                payloads, {'call_001': {'message': response}}, 24000)
        self.assertEqual(inspect_history(*args)['history_audit_errors'], [])
        payloads['call_002']['messages'][-1]['content'] = 'changed to success'
        failures = inspect_history(*args)['history_audit_errors']
        self.assertEqual(len(failures), 1)
        self.assertNotIn('changed to success', str(failures))


if __name__ == '__main__':
    unittest.main()
