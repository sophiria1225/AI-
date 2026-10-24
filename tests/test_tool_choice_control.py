import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import tool_choice_local_llama as transport
from whole_task_tool_choice import summarize, run_order, cell_id
from run_whole_task_tool_choice import predecessor_closed


def config(choice):
    return dict(model='synthetic', temperature=1.0, seed=57, num_predict=4096,
                reasoning_budget_tokens=-1, tool_choice=choice, call_timeout_seconds=600)


def result_rows():
    return [dict(task_id=str(n), tool_choice_policy=p, record_status='evaluated',
        success=True, known_total_tokens=100 if p == 'auto' else 90,
        unknown_usage_calls=0, model_calls=1, api_requests=1, wall_seconds=1,
        cached_input_tokens=0, input_tokens=50, output_tokens=50 if p == 'auto' else 40)
        for n, p in run_order()]


class ToolChoiceControlTests(unittest.TestCase):
    def test_counting_and_generation_send_identical_control_and_usage(self):
        messages = [dict(role='user', content='synthetic fixture')]
        tools = [dict(type='function', function=dict(name='fixture', parameters=dict(type='object')))]
        starts = []
        for choice in ('auto', 'required'):
            seen = []
            def post(cfg, endpoint, payload, timeout):
                seen.append(copy.deepcopy(payload))
                if endpoint.endswith('/input_tokens'): return dict(input_tokens=12)
                return dict(usage=dict(prompt_tokens=12, completion_tokens=3, total_tokens=15),
                    choices=[dict(finish_reason='tool_calls', message=dict(role='assistant', content=''))])
            with tempfile.TemporaryDirectory() as directory, patch.object(transport, 'post', side_effect=post):
                count = transport.count_input(config(choice), messages, tools)
                result = transport.model_call(config(choice), messages, Path(directory), 60, tools)
                actual = json.loads((Path(directory) / 'request.json').read_text())
            self.assertEqual(seen[0], seen[1]); self.assertEqual(seen[1], actual)
            self.assertEqual(actual['tool_choice'], choice)
            self.assertEqual(actual['reasoning_budget_tokens'], -1)
            self.assertEqual(count['input_tokens'], result['input_tokens'])
            starts.append(actual)
        self.assertEqual({k: v for k, v in starts[0].items() if k != 'tool_choice'},
                         {k: v for k, v in starts[1].items() if k != 'tool_choice'})

    def test_unknown_usage_is_not_replaced_by_reservation_or_retried(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(transport, 'post', side_effect=TimeoutError) as post:
            result = transport.model_call(config('required'), [], Path(directory), 5, ['synthetic'])
        self.assertEqual(post.call_count, 1)
        self.assertIsNone(result['input_tokens']); self.assertIsNone(result['output_tokens'])
        self.assertEqual(result['timeout_scope'], 'run_wall')

    def test_conflicting_or_unfixed_controls_fail_before_dispatch(self):
        with patch.object(transport, 'post') as post:
            for extra in ({'tool_choice': 'none'}, {'reasoning_budget_tokens': 2048},
                          {'grammar': 'synthetic'}, {'thinking_mode': 'disabled'}):
                with self.subTest(extra=extra), self.assertRaises(ValueError):
                    transport.count_input({**config('required'), **extra}, [], ['synthetic'])
            with self.assertRaises(ValueError): transport.count_input(config('required'), [], [])
        post.assert_not_called()

    def test_successful_part_alone_cannot_establish_whole_task_savings(self):
        rows = result_rows(); self.assertTrue(summarize(rows, [])['development_gate_met'])
        # On the last task both fail and the proposed setting costs much more.
        for r in rows:
            if r['task_id'] == '4':
                r['success'] = False
                if r['tool_choice_policy'] == 'required': r['known_total_tokens'] = 500
        result = summarize(rows, [])
        self.assertFalse(result['development_gate_met'])
        self.assertEqual(result['paired_successful_token_difference'], -30)
        self.assertEqual(result['both_failed_token_difference'], 400)
        rows[-1]['unknown_usage_calls'] = 1
        result = summarize(rows, [])
        self.assertFalse(result['all_eight_complete_with_known_usage'])
        self.assertIsNone(result['paired_successful_token_difference'])

    def test_all_eight_fresh_slots_and_success_preservation_required(self):
        self.assertEqual(len(set(cell_id(*v) for v in run_order())), 8)
        rows = result_rows(); rows[1]['success'] = False
        self.assertFalse(summarize(rows, [])['development_gate_met'])
        with self.assertRaises(ValueError): summarize(rows[:-1], [])

    def test_running_predecessor_prevents_any_process_check(self):
        data = [dict(audit_errors=[], rows=[{}] * 12, owned_processes_absent=True),
                dict(status='running', owned_processes_absent=False),
                dict(status='batch', server_stopped=False), dict(status='ready')]
        with patch('run_whole_task_tool_choice.read', side_effect=data), \
             patch('run_whole_task_tool_choice.subprocess.run') as run:
            with self.assertRaisesRegex(ValueError, 'closed_owned_audited'):
                predecessor_closed(Path('/synthetic'), Path('/synthetic'))
        run.assert_not_called()

    def test_closed_predecessor_requires_bound_records_and_both_pids_absent(self):
        data = [dict(audit_errors=[], rows=[{}] * 12, owned_processes_absent=True,
                     server_final_sha256='f', pipeline_status_sha256='p'),
                dict(status='stopped', owned_processes_absent=True, audit_source_sha256='a'),
                dict(status='complete', server_stopped=True, server_supervisor_pid=12,
                     git_commit='46dcfd3f3d2b79214b8601618f40ee6083e67452'),
                dict(status='stopped', pid=11, supervisor_pid=12)]
        def checksum(path):
            return {'P97_comparison.json':'a', 'status.json':'p', 'server_final.json':'f'}[path.name]
        from types import SimpleNamespace
        with patch('run_whole_task_tool_choice.read', side_effect=data), \
             patch('run_whole_task_tool_choice.sha', side_effect=checksum), \
             patch('run_whole_task_tool_choice.subprocess.run',
                   return_value=SimpleNamespace(returncode=1, stdout='')) as run:
            result = predecessor_closed(Path('/synthetic'), Path('/synthetic'))
        self.assertEqual(result['server_final_sha256'], 'f'); self.assertEqual(run.call_count, 2)
        for change in ('wrong_final_binding', 'wrong_owner', 'still_running'):
            altered = copy.deepcopy(data)
            if change == 'wrong_final_binding': altered[0]['server_final_sha256'] = 'changed'
            if change == 'wrong_owner': altered[-1]['supervisor_pid'] = 999
            with self.subTest(change=change), \
                 patch('run_whole_task_tool_choice.read', side_effect=altered), \
                 patch('run_whole_task_tool_choice.sha', side_effect=checksum), \
                 patch('run_whole_task_tool_choice.subprocess.run',
                       return_value=SimpleNamespace(returncode=0, stdout='owned fixture')) as run:
                with self.assertRaises(ValueError): predecessor_closed(Path('/synthetic'), Path('/synthetic'))
                self.assertEqual(run.call_count, 1 if change == 'still_running' else 0)


if __name__ == '__main__': unittest.main()
