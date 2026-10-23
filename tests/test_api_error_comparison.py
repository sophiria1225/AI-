import copy
import json
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from api_error_comparison import (ARMS, ErrorPresentationProgram, FromStartInference,
    add_notification, cell_id, config_for, disposition, initial_conversation, run_order,
    task_snapshot, validate_plan)
from container_api_python import ApiChannel
from public_api_result_transport import PublicResultTransport
from residual_output_budget import ResidualInference
from audit_api_error_comparison import development_gate
from run_api_error_cell import run_cell
from public_api_envelope import PROTOCOL
from run_context_comparison import BudgetStop
from test_public_api_result_transport import FixtureTransport, catalog, exchange

ROOT = Path(__file__).resolve().parents[1]


def channel(arm, raw=None, remaining=8):
    raw = raw or FixtureTransport()
    transport = PublicResultTransport(raw)
    base = ApiChannel(catalog(), transport, remaining)
    exposed = Mock(wraps=base.catalog.expose_requested_document)
    base.catalog.expose_requested_document = exposed
    wrapped = ErrorPresentationProgram(lambda source, observations, wrapped: wrapped, arm)('', [], base)
    return wrapped, transport, raw, exposed


class ApiErrorComparisonTests(unittest.TestCase):
    def test_every_normal_value_is_identical_in_both_arms(self):
        values = ['1', 'null', 'ValueError: ordinary text', {'success': False},
                  None, [True, 12, '日本語'], {'nested': ['a', False]}]
        a, b = [channel(arm)[0] for arm in ARMS]
        for value in values:
            left, right = exchange(a, value=value), exchange(b, value=value)
            self.assertEqual(left, right)
            self.assertEqual(left['value'], value)
            self.assertIs(type(left['value']), type(value))
            self.assertEqual(a.rows[-1]['observation'], b.rows[-1]['observation'])

    def test_confirmed_exception_changes_only_value_vs_error_not_dispatch_or_schema(self):
        channels = [channel(arm) for arm in ARMS]
        returned = [exchange(ch, api='fail', value=7) for ch, _, _, _ in channels]
        self.assertTrue(returned[0]['ok'])
        self.assertFalse(returned[1]['ok'])
        self.assertEqual(returned[0]['value'], returned[1]['error'])
        for ch, transport, raw, exposed in channels:
            self.assertEqual(raw.world.effects, [('fail', 7)])
            self.assertEqual(len(raw.commands), 1)
            self.assertEqual(transport.receipts[0]['status'], 'raised')
            self.assertFalse(transport.receipts[0]['rollback_guaranteed'])
            self.assertEqual(ch.remaining, 7)
            self.assertFalse(ch.fatal)
            exposed.assert_not_called()
            self.assertEqual(exchange(ch, value=9)['value'], 9)

    def test_completion_with_exception_blocks_next_dispatch_in_both_arms(self):
        for arm in ARMS:
            with self.subTest(arm=arm):
                ch, transport, raw, _ = channel(arm)
                exchange(ch, api='finish_fail')
                self.assertTrue(ch.complete)
                self.assertTrue(transport.complete)
                self.assertFalse(exchange(ch, value=2)['ok'])
                self.assertEqual(len(raw.commands), 1)

    def test_corrupt_or_missing_result_stays_unknown_and_never_becomes_error_value(self):
        for arm in ARMS:
            with self.subTest(arm=arm):
                raw = FixtureTransport(transform=lambda _: {'ok': True, 'result': 'lost envelope'})
                ch, transport, _, _ = channel(arm, raw)
                reply = exchange(ch)
                self.assertFalse(reply['ok'])
                self.assertTrue(ch.fatal)
                self.assertTrue(transport.fatal)
                self.assertTrue(ch.rows[-1]['effects_unknown'])
                self.assertFalse(exchange(ch)['ok'])
                self.assertEqual(len(raw.commands), 1)

    def test_undispatched_validation_and_budget_rejections_remain_errors(self):
        for arm in ARMS:
            for remaining in (0, 8):
                with self.subTest(arm=arm, remaining=remaining):
                    ch, _, raw, _ = channel(arm, remaining=remaining)
                    reply = ch.exchange({'kind': 'api', 'id': 1, 'app': 'fixture', 'api': 'echo',
                                         'arguments': {'not_a_parameter': 3}})
                    self.assertFalse(reply['ok'])
                    self.assertFalse(ch.rows[-1]['api_request_sent'])
                    self.assertEqual(raw.commands, [])
                    self.assertEqual(ch.remaining, remaining)

    def test_frozen_cohort_order_budget_and_initial_input(self):
        plan = json.loads((ROOT / 'configs/P78_api_error_v01.json').read_text())
        original = json.loads((ROOT / plan['source_plan']).read_text())
        validate_plan(plan)
        order = run_order()
        self.assertEqual(len(order), 8)
        self.assertEqual(len({cell_id(n, arm) for n, arm in order}), 8)
        self.assertEqual(order[:4], [(1, ARMS[0]), (1, ARMS[1]), (2, ARMS[1]), (2, ARMS[0])])
        cfg = config_for(original, plan, original['task_ids'][0])
        self.assertEqual((cfg['seed'], cfg['max_api_requests']), (51, 160))
        public = {'instruction': 'fixture', 'ground_truth_loaded': False}
        messages = [initial_conversation(original, public).messages() for _ in ARMS]
        self.assertEqual(messages[0], messages[1])
        self.assertFalse(any(arm in json.dumps(messages[0]) for arm in ARMS))
        for key in ('max_total_tokens', 'model_seed', 'max_calls', 'max_cells'):
            changed = copy.deepcopy(plan); changed[key] += 1
            with self.assertRaises(ValueError):
                validate_plan(changed)

    def test_from_start_notice_charges_all_known_usage_and_rejects_unknown(self):
        plan = json.loads((ROOT / 'configs/P78_api_error_v01.json').read_text())
        original = json.loads((ROOT / plan['source_plan']).read_text())
        cfg = config_for(original, plan, original['task_ids'][0])
        calls = [{'status': 'ok', 'input_tokens': 123, 'output_tokens': 456}]
        state = task_snapshot(cfg, calls, 7, 12.25)
        self.assertEqual(state['used'], {'api_calls': 7, 'model_calls': 1,
                                       'logical_input_plus_output_tokens': 579})
        self.assertEqual(state['remaining']['wall_seconds_at_snapshot'], 1787)
        original_messages = [{'role': 'user', 'content': 'fixture'}]
        supplied = add_notification(original_messages, state)
        self.assertEqual(len(original_messages), 1)
        self.assertEqual(len(supplied), 2)
        with self.assertRaises(ValueError):
            task_snapshot(cfg, [{'status': 'error'}], 7, 12.25)

    def test_unknown_usage_is_evaluable_only_after_known_effects_and_cleanup(self):
        base = {'setup': {'status': 'initial_public_state_matched'}, 'unknown_effect_requests': 0,
                'cleanup_confirmed': True, 'stop_reason': 'model_usage_unknown', 'unknown_usage_calls': 1}
        self.assertEqual(disposition(base), 'evaluate_unknown_usage')
        for change in ({'cleanup_confirmed': False}, {'unknown_effect_requests': 1},
                       {'stop_reason': 'runtime_error'}, {'stop_reason': 'user_stop'},
                       {'setup': {'status': 'failed'}}):
            self.assertEqual(disposition({**base, **change}), 'stop_batch')

    def test_first_call_cache_policy_and_failed_admission_are_recorded(self):
        plan = json.loads((ROOT / 'configs/P78_api_error_v01.json').read_text())
        original = json.loads((ROOT / plan['source_plan']).read_text())
        cfg = config_for(original, plan, original['task_ids'][0])
        with tempfile.TemporaryDirectory() as folder:
            infer = FromStartInference(cfg, Path(folder))
            with patch.object(ResidualInference, 'call', side_effect=BudgetStop('token_reservation_limit')):
                with self.assertRaises(BudgetStop):
                    infer.call('agent', [{'role': 'user', 'content': 'fixture'}], [])
            saved = json.loads((Path(folder) / 'budget_signals.json').read_text())
            self.assertFalse(saved[0]['cache_prompt'])
            self.assertFalse(saved[0]['model_attempted'])
            self.assertEqual(infer.calls, [])

    def test_savings_gate_rejects_missing_cost_quality_loss_and_unexercised_treatment(self):
        rows = [{'task_id': f't{n}', 'arm': arm, 'record_status': 'evaluated', 'success': True,
                 'unknown_usage_calls': 0, 'known_total_tokens': 100 if arm == ARMS[0] else 90,
                 'invocation_exceptions': 1} for n in range(4) for arm in ARMS]
        self.assertTrue(development_gate(rows, [])['development_gate_met'])
        self.assertFalse(development_gate(rows, ['audit mismatch'])['development_gate_met'])
        for change in ({'unknown_usage_calls': 1}, {'success': False}, {'record_status': 'not_run'}):
            changed = copy.deepcopy(rows); changed[1].update(change)
            result = development_gate(changed, [])
            self.assertFalse(result['development_gate_met'])
            if 'unknown_usage_calls' in change:
                self.assertIsNone(result['exception_minus_value_whole_task_tokens'])
                self.assertIsNone(result['paired_results'][0]['exception_minus_value_tokens'])
        for row in rows:
            row['invocation_exceptions'] = 0
        self.assertFalse(development_gate(rows, [])['development_gate_met'])

    def test_unknown_model_call_is_not_executed_retried_or_erased_during_cleanup(self):
        plan = json.loads((ROOT / 'configs/P78_api_error_v01.json').read_text())
        original = json.loads((ROOT / plan['source_plan']).read_text())
        public = {'instruction': 'fixture', 'ground_truth_loaded': False}
        item = {'task_id': original['task_ids'][0], 'source_run': 'fixture',
                'known_public_task_sha256': 'fixture-hash', 'public_task': public}
        sent = []
        class Raw:
            timeout_seconds = 90
            def __init__(self, *args, **kwargs): pass
            def request(self, command):
                sent.append(command['op'])
                return {'ok': True, 'result': {**public, 'api_result_protocol': PROTOCOL}}
            def close(self):
                return {'graceful': True, 'process_stopped': True, 'transport_failed': False}
        class Session:
            def __init__(self, *args): self.state = {'container_removed': False}
            def run(self, *args, **kwargs):
                raise AssertionError('unknown response must not execute')
            def close(self): self.state['container_removed'] = True
        class UnknownInference:
            def __init__(self, *args):
                self.started = time.monotonic(); self.calls = []; self.tokens = 0
            def call(self, *args):
                self.calls.append({'id': 'call_001', 'role': 'agent', 'status': 'error',
                                   'input_tokens': None, 'output_tokens': None})
                raise RuntimeError('model failure; usage unknown, no free retry')
        for arm in ARMS:
            with self.subTest(arm=arm), tempfile.TemporaryDirectory() as folder:
                with patch('run_api_error_cell.TypedBridgeProcess', Raw), \
                     patch('run_api_error_cell.PersistentApiPython', Session), \
                     patch('run_api_error_cell.FromStartInference', UnknownInference):
                    result = run_cell(Path(folder), ROOT, plan, original, [], item, arm, cell_id(1, arm))
                self.assertEqual(result['stop_reason'], 'model_usage_unknown')
                self.assertEqual(result['model_calls'], 1)
                self.assertEqual(result['unknown_usage_calls'], 1)
                self.assertEqual(result['api_requests'], 0)
                self.assertTrue(result['cleanup_confirmed'])
                self.assertEqual(disposition(result), 'evaluate_unknown_usage')
                saved = json.loads((Path(folder) / 'records/context_pilot' / cell_id(1, arm) / 'usage.json').read_text())
                self.assertIsNone(saved[0]['input_tokens'])
        self.assertEqual(sent, ['init', 'init'])


if __name__ == '__main__':
    unittest.main()
