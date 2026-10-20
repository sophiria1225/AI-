import json
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from run_fixed_comparison import SharedModel, SharedEnvironment, DefaultAgent, run_turn, templates_for
from experiment_state import SharedBudget, CompletionState, ProtocolStop


class FixedComparisonControls(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.out = Path(self.temporary.name)
        self.config = dict(max_calls=8, max_total_tokens=4000, num_ctx=2048, num_predict=200,
                           max_wall_seconds=60, visible_checks=[])
        self.summary = {'calls': [], 'tools': [], 'run_id': 'fixture', 'usage_complete': True}
        self.budget = SharedBudget(**{k: self.config[k] for k in ('max_calls', 'max_total_tokens', 'num_ctx', 'num_predict', 'max_wall_seconds')})
        templates = templates_for(self.config, 'single', False)
        self.started = time.monotonic()
        self.model = SharedModel(self.config, templates['model'], self.out, self.summary, self.started, self.budget)
        self.env = SharedEnvironment(object(), self.config, self.out, self.summary, self.started)

    def agent(self, unit):
        a = DefaultAgent(self.model, self.env, system_template='Resolve a fixture.', instance_template='Fixture task', step_limit=0)
        a.messages = [{'role': 'system', 'content': 'Resolve a fixture.'}, {'role': 'user', 'content': 'Fixture task'}]
        self.model.unit = self.env.unit = unit
        return a

    @staticmethod
    def answer(commands, **updates):
        return dict(status='ok', input_tokens=100, output_tokens=20, done_reason='tool_calls',
                    message={'role': 'assistant', 'content': 'Visible result.', 'reasoning_content': 'PRIVATE_FIXTURE_REASONING',
                             'tool_calls': [{'id': f'call{i}', 'function': {'name': 'bash', 'arguments': {'command': c}}}
                                            for i, c in enumerate(commands)]}) | updates

    @staticmethod
    def tool(container, command, config, directory, left):
        return {'command': command, 'output': 'COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT\n' if command == 'submit' else 'ok\n',
                'exit_code': 0, 'exit_code_known': True, 'running': False, 'wall_seconds': 0.001}

    def test_real_agent_steps_charge_one_ledger_and_invalidate_completion(self):
        completion = CompletionState(('implementation', 'validation'), 'a'*64)
        units = ['validation', 'implementation', 'validation', 'implementation']
        commands = ['submit', 'edit', 'submit', 'submit']
        hashes = ['a'*64, 'b'*64, 'b'*64, 'b'*64]
        agents = {unit: self.agent(unit) for unit in completion.units}
        with patch('run_fixed_comparison.local_llama.count_input', return_value={'input_tokens': 100}), \
             patch('run_fixed_comparison.local_llama.model_call', side_effect=[self.answer([c]) for c in commands]), \
             patch('run_fixed_comparison.tool_command', side_effect=self.tool), \
             patch('run_fixed_comparison.capture_artifact', side_effect=[{'artifact_sha256': h} for h in hashes]):
            for n, unit in enumerate(units, 1):
                self.model.unit = self.env.unit = unit
                event = run_turn(agents[unit], self.env, completion, self.out, 'fixture_base', n)
                self.assertNotIn('PRIVATE_FIXTURE_REASONING', json.dumps(event))
                if n == 2:
                    self.assertEqual(completion.votes, {})
                self.assertEqual(completion.complete, n == 4)
        self.assertEqual(self.budget.total_tokens, 480)
        self.assertEqual(len(self.summary['tools']), 4)
        self.assertEqual([c['unit'] for c in self.summary['calls']], units)

    def test_length_completion_is_billed_without_executing_its_tool(self):
        agent = self.agent('single')
        with patch('run_fixed_comparison.local_llama.count_input', return_value={'input_tokens': 100}), \
             patch('run_fixed_comparison.local_llama.model_call', return_value=self.answer(['edit'], done_reason='length')), \
             patch('run_fixed_comparison.tool_command') as command:
            with self.assertRaisesRegex(ProtocolStop, 'generation_limit_incomplete_response'):
                agent.step()
            command.assert_not_called()
        self.assertEqual(self.budget.total_tokens, 120)

    def test_adapter_exception_marks_usage_unknown_and_prevents_tools(self):
        agent = self.agent('single')
        with patch('run_fixed_comparison.local_llama.count_input', return_value={'input_tokens': 100}), \
             patch('run_fixed_comparison.local_llama.model_call', side_effect=OSError('fixture transport error')), \
             patch('run_fixed_comparison.tool_command') as command:
            with self.assertRaisesRegex(ProtocolStop, 'usage_unknown'):
                agent.step()
            command.assert_not_called()
        self.assertFalse(self.summary['usage_complete'])
        self.assertEqual(self.budget.calls, 1)
        self.assertTrue((self.out/'call_001_single/adapter_error.json').exists())

    def test_completion_in_a_batch_cannot_approve_a_later_edit(self):
        agent = self.agent('single')
        state = CompletionState(('single',), 'a'*64)
        with patch('run_fixed_comparison.local_llama.count_input', return_value={'input_tokens': 100}), \
             patch('run_fixed_comparison.local_llama.model_call', return_value=self.answer(['submit', 'edit'])), \
             patch('run_fixed_comparison.tool_command', side_effect=self.tool), \
             patch('run_fixed_comparison.capture_artifact', return_value={'artifact_sha256': 'b'*64}):
            event = run_turn(agent, self.env, state, self.out, 'fixture_base', 1)
        self.assertFalse(state.complete)
        self.assertFalse(event['completion_vote_accepted'])
        self.assertIn('only bash call', agent.messages[-1]['content'])


if __name__ == '__main__':
    unittest.main()
