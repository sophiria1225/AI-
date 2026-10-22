import copy
import json
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from code_agent_interface import CODE_TOOLS
from probe_public_name_comparison import public_summary
from public_name_comparison import PLAN, can_continue_batch, interface, validate
from run_handoff_factors import ROOT, read
from run_public_name_comparison import run_condition
from test_public_name_catalog import TOOLS, packet


TASK = {'instruction': 'Synthetic task without future receipts', 'ground_truth_loaded': False}


class FakeBridge:
    fail = False
    def __init__(self, *_): self.requests = []
    def request(self, request):
        self.requests.append(request)
        if request['op'] == 'init': return {'ok': True, 'result': copy.deepcopy(TASK)}
        if self.fail: raise TimeoutError('synthetic unknown effect')
        complete = request['call']['api'] == 'complete_task'
        return {'ok': True, 'result': {'observation': '{}', 'declared_complete': complete}}
    def close(self): pass


class FakeInference:
    def __init__(self, config, output): self.calls = []; self.started = time.monotonic()
    @property
    def tokens(self): return len(self.calls)*15
    def call(self, messages, tools):
        n = len(self.calls)+1
        self.calls.append({'id': f'call_{n:03}', 'usage_known': True, 'input_tokens': 10, 'output_tokens': 5})
        return {'role': 'assistant', 'content': '', 'tool_calls': [{'id': f'c{n}', 'type': 'function',
            'function': {'name': 'run_python', 'arguments': json.dumps({
                'code': 'clock' if n == 1 else 'complete', 'span_ids': []})}}]}


class FakeSession:
    def __init__(self, *_):
        self.usable = True
        self.state = {'programs': [], 'status': 'active', 'container_removed': False}
    def run(self, code, observations, channel, *, on_record, **kwargs):
        reply = channel.exchange(packet(app='phone' if code == 'clock' else 'supervisor',
            api='get_current_date_and_time' if code == 'clock' else 'complete_task'))
        for row in channel.rows: on_record(row)
        self.state['programs'].append({'stdout': 'PRIVATE FIXTURE VALUE'})
        return {'status': 'ok' if reply['ok'] else 'error', 'stdout': '', 'stdout_truncated': False,
            'api_requests': sum(r['api_request_sent'] for r in channel.rows),
            'declared_complete': any(r['observation'].get('declared_complete') for r in channel.rows),
            'unknown_effects': channel.fatal}
    def close(self): self.state.update(status='closed', container_removed=True)


class PublicNameComparisonTests(unittest.TestCase):
    def setUp(self):
        self.plan = read(ROOT / PLAN); self.original = read(ROOT / self.plan['source_config'])
        FakeBridge.fail = False

    def test_fixed_selection_order_and_budget_reject_drift(self):
        validate(self.plan, self.original)
        for key, value in [('seed', 43), ('max_total_tokens', 450001), ('reserved_scenarios_read', 1),
                           ('run_order', self.plan['run_order'][::-1]), ('task_ids', ['unseen'])]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate({**self.plan, key: value}, self.original)

    def test_prompts_are_accurate_without_changing_other_guidance_or_tool_schema(self):
        original = copy.deepcopy(self.original)
        old, old_tools = interface('documented', original)
        new, new_tools = interface('named', original)
        self.assertIn('one discovered public API', old)
        self.assertIn('may be called before reading their', new)
        self.assertNotIn('only\napi_docs and supervisor APIs are available', new)
        self.assertIn('Initially\nonly api_docs and supervisor definitions are visible', new)
        self.assertEqual(old_tools, CODE_TOOLS)
        self.assertEqual(old_tools[0]['function']['parameters'], new_tools[0]['function']['parameters'])
        self.assertEqual(old_tools[1], new_tools[1]); self.assertEqual(original, self.original)
        for phrase in ('Get the current simulated date', 'variables, imports and functions persist', '450000', '1800'):
            self.assertIn(phrase, old); self.assertIn(phrase, new)
        with self.assertRaises(ValueError): interface('invented', original)

    def run_fixture(self, folder, arm='named', budget=None, initial_hash='hash'):
        tid, _, rid = next(r for r in self.plan['run_order'] if r[0] == '34d9492_1' and r[1] == arm)
        plan = copy.deepcopy(self.plan)
        if budget is not None: plan['api_budget_by_task'][tid] = budget
        (Path(folder) / 'records/context_pilot').mkdir(parents=True, exist_ok=True)
        with patch('run_public_name_comparison.Bridge', FakeBridge), \
             patch('run_public_name_comparison.PersistentApiPython', FakeSession), \
             patch('run_public_name_comparison.db_hashes', return_value={'dbs/fixture': 'hash'}), \
             patch('run_public_name_comparison.OrdinaryInference', FakeInference):
            summary = run_condition(Path(folder), plan, self.original,
                {tid: {'public_task': TASK, 'initial_database_hashes': {'dbs/fixture': initial_hash}}}, TOOLS, tid, arm, rid)
        return summary, Path(folder) / 'records/context_pilot' / rid

    def test_fresh_task_and_admission_difference_are_recorded_end_to_end(self):
        for arm, expected in [('documented', 1), ('named', 2)]:
            with self.subTest(arm=arm), tempfile.TemporaryDirectory() as folder:
                s, trial = self.run_fixture(folder, arm)
                self.assertEqual(s['api_requests'], expected); self.assertEqual(s['model_calls'], 2)
                self.assertEqual(s['known_total_tokens'], 30); self.assertTrue(can_continue_batch(s))
                self.assertEqual(read(trial / 'public_task.json'), TASK)
                conversation = read(trial / 'conversation_private.json')
                self.assertEqual(json.loads(conversation[1]['content']), {'task': TASK})
                events = read(trial / 'events.json')
                self.assertEqual(events[0]['api_request_sent'], arm == 'named')
                self.assertEqual(s['setup']['future_receipts_supplied'], 0)
                self.assertTrue(s['python_session']['container_removed'])

    def test_real_inner_request_budget_stops_before_more_generation(self):
        with tempfile.TemporaryDirectory() as folder:
            s, _ = self.run_fixture(folder, budget=1)
            self.assertEqual(s['stop_reason'], 'api_request_limit')
            self.assertEqual(s['api_requests'], 1); self.assertEqual(s['model_calls'], 1)
            self.assertFalse(s['declared_complete']); self.assertTrue(can_continue_batch(s))

    def test_unknown_effect_records_one_request_and_stops_condition_and_batch(self):
        with tempfile.TemporaryDirectory() as folder:
            FakeBridge.fail = True
            s, _ = self.run_fixture(folder)
            self.assertEqual(s['model_calls'], 1); self.assertEqual(s['api_requests'], 1)
            self.assertEqual(s['unknown_effect_requests'], 1)
            self.assertFalse(can_continue_batch(s)); self.assertFalse(s['declared_complete'])

    def test_existing_trial_cannot_be_replaced(self):
        with tempfile.TemporaryDirectory() as folder:
            self.run_fixture(folder)
            with self.assertRaises(FileExistsError): self.run_fixture(folder)

    def test_mismatched_start_stops_before_any_generation_or_api(self):
        with tempfile.TemporaryDirectory() as folder:
            s, _ = self.run_fixture(folder, initial_hash='different')
            self.assertEqual(s['stop_reason'], 'setup_failure')
            self.assertEqual(s['model_calls'], 0); self.assertEqual(s['api_requests'], 0)
            self.assertFalse(can_continue_batch(s))

    def test_public_export_omits_interpreter_values(self):
        with tempfile.TemporaryDirectory() as folder:
            s, _ = self.run_fixture(folder)
            exported = public_summary(s)
            self.assertNotIn('PRIVATE FIXTURE VALUE', json.dumps(exported))
            self.assertEqual(exported['python']['program_count'], 2)

    def test_only_declared_task_failures_allow_next_fixed_condition(self):
        s = {'setup': {'status': 'matched_public_task_start'}, 'unknown_effect_requests': 0}
        for reason in ('token_reservation_limit', 'context_limit', 'model_usage_unknown', 'model_response_unusable'):
            self.assertTrue(can_continue_batch({**s, 'stop_reason': reason}))
        for reason in ('runtime_error', 'setup_failure', 'cleanup_error', 'explicit_stop', 'unrecognized'):
            self.assertFalse(can_continue_batch({**s, 'stop_reason': reason}))


if __name__ == '__main__': unittest.main()
