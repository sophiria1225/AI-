"""Actual worker with synthetic model/API replies and trusted handwritten code."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from api_error_comparison import disposition
from compact_api_receipts import decode_receipts
from joined_public_read_views import JOINED_CONTRACT_ID
from public_api_envelope import PROTOCOL
from run_whole_task_region_projection_cell import run_cell, check_api_accounting
from shared_api_reservations import RequestBudget
from whole_task_region_projection import cell_id, initial_conversation
from single_checkpoint_worker_fixture import configuration as checkpoint_configuration
from test_single_checkpoint import VALID as VALID_CHECKPOINT
from test_automatic_projection_runtime import LIBRARY
from test_region_projection_runtime import TrustedRegionSession, SOURCE
from test_public_name_catalog import tool
from test_public_read_views_live_probe import Fixture, catalog

ROOT = Path(__file__).resolve().parents[1]
PROGRAMS = (LIBRARY, SOURCE, SOURCE, "call_api('supervisor', 'complete_task')")


def fixture(storage, policy, *, unknown=False, stop=False, contract_failure=False, unknown_api=False,
            cleanup_bad=False, no_tool=False, checkpoint=False, programs=PROGRAMS, max_calls=5):
    original = (checkpoint_configuration()[0] if checkpoint else
                json.loads((ROOT / 'configs/P29_stateful_code_v01.json').read_text()))
    task = next(iter(original['api_budget_by_task']))
    plan = dict(phase='budget_observation_connection', experiment='P127',
        known_tasks=[{'task_id': task, 'source_run': 'synthetic'}], model_seed=157, world_seed=42,
        api_budget_by_task_slot=[160,80,80,120],
        max_calls=max_calls, max_total_tokens=450000 if checkpoint else 500, max_wall_seconds=60,
        max_setup_seconds=120, max_cleanup_seconds=180, automatic_retries=0,
        reserved_scenarios_read=0, history_policy='all_returned_reasoning_from_start')
    public = dict(instruction='Complete the synthetic fixture', ground_truth_loaded=False)
    item = dict(task_id=task, source_run='synthetic', known_public_task_sha256='synthetic', public_task=public)
    captured, raw_instances = [], []
    class Raw(Fixture):
        timeout_seconds = 90
        def __init__(self, *args, **kwargs):
            super().__init__()
            raw_instances.append(self)
        def request(self, command):
            if command['op'] == 'init':
                return {'ok': True, 'result': {**public, 'api_result_protocol': PROTOCOL}}
            action = command['call']
            if unknown_api and action['api'] == 'show_song' and action['args']['song_id'] == 12:
                self.calls.append(deepcopy(action))
                raise OSError('synthetic unknown API transport outcome')
            if contract_failure and action['api'] == 'show_song' and action['args']['song_id'] == 12:
                self.calls.append(deepcopy(action))
                envelope = dict(protocol=PROTOCOL, nonce=command['nonce'], status='raised',
                    error={'type': 'RuntimeError', 'message': 'synthetic total-read contract failure'})
                return {'ok': True, 'result': dict(protocol=PROTOCOL, observation=json.dumps(envelope),
                                                   declared_complete=False)}
            if action['api'] == 'complete_task':
                self.calls.append(deepcopy(action))
                envelope = dict(protocol=PROTOCOL, nonce=command['nonce'], status='returned', value={'done': True})
                return {'ok': True, 'result': dict(protocol=PROTOCOL, observation=json.dumps(envelope),
                                                   declared_complete=True)}
            return super().request(command)
        def close(self):
            return dict(graceful=not cleanup_bad, process_stopped=True, transport_failed=cleanup_bad)
    class Session(TrustedRegionSession):
        def __init__(self, storage_root, folder, *, policy):
            super().__init__(folder, policy)
            self.storage_root = storage_root
        def run(self, source, *args, **kwargs):
            result = super().run(source, *args, **kwargs)
            if stop and source == LIBRARY:
                marker = storage / '.runtime/P127.stop'
                marker.parent.mkdir(exist_ok=True)
                marker.touch()
            return result
        def close(self):
            result = super().close()
            self.state.update(status='closed', container_removed=True)
            self._save()
            return result
    def count(config, messages, tools, timeout):
        # Same bounded synthetic count schedule as the P118 worker fixture.
        tokens = (5000 + 4000 * sum(m['role'] == 'assistant' for m in messages)
                  if tools else 10000) if checkpoint else 30
        return dict(input_tokens=tokens, wall_seconds=0)
    def send(config, messages, output, timeout, tools):
        role = 'agent' if tools else 'focus'
        captured.append({'config': deepcopy(config), 'messages': deepcopy(messages), 'role': role})
        if unknown and len(captured) == 2:
            raise OSError('synthetic model response lost')
        index = sum(c['role'] == 'agent' for c in captured) - 1
        message = dict(role='assistant', content=None, reasoning_content='synthetic fixture reasoning')
        if role == 'focus':
            message = deepcopy(VALID_CHECKPOINT)
        elif not no_tool:
            message['tool_calls'] = [{'id': 'fixture-' + str(index), 'type': 'function', 'function': {
                'name': 'run_python', 'arguments': json.dumps({'code': programs[index], 'span_ids': []})}}]
        cached = 0 if index == 0 or role == 'focus' else 20
        tokens = count(config, messages, tools, timeout)['input_tokens']
        response = dict(status='ok', input_tokens=tokens, output_tokens=20, wall_seconds=0,
            done_reason='stop' if no_tool or role == 'focus' else 'tool_calls', cached_input_tokens=cached, message=message,
            timings=dict(cache_n=cached, prompt_n=tokens-cached, predicted_n=20, prompt_ms=1, predicted_ms=1))
        (output / 'response.json').write_text(json.dumps(response))
        return response
    tools = list(catalog().catalog.values()) + [tool('supervisor__complete_task')]
    with patch('run_whole_task_region_projection_cell.TypedBridgeProcess', Raw), \
         patch('run_whole_task_region_projection_cell.RegionProjectionPython', Session), \
         patch('run_whole_task_region_projection_cell.verify_joined_implementation', return_value=JOINED_CONTRACT_ID), \
         patch('region_projection_runtime.verify_joined_implementation', return_value=JOINED_CONTRACT_ID), \
         patch('demand_joined_read_adapter.verify_joined_implementation', return_value=JOINED_CONTRACT_ID), \
         patch('rolling_checkpoint_inference.count_agent_input', side_effect=count), \
         patch('rolling_checkpoint_inference.count_summary_input', side_effect=count), \
         patch('fixed_budget_residual.count_input', side_effect=count), \
         patch('fixed_budget_residual.model_call', side_effect=send), \
         patch('tool_choice_residual.count_input', side_effect=count), \
         patch('tool_choice_residual.model_call', side_effect=send):
        result = run_cell(storage, ROOT, plan, original, tools, item, 'error_exception', cell_id(1, policy),
                          projection_policy=policy)
    return {'result': result, 'captured': captured, 'folder': storage / 'records/context_pilot' / cell_id(1, policy),
            'raw': raw_instances[0] if raw_instances else None, 'original': original, 'public': public}


class WholeTaskProjectionWorkerTests(unittest.TestCase):
    def test_explicit_fields_is_real_shared_reuse_with_no_synthetic_receipt_rows(self):
        field_call = "print(read_fields('spotify', 'show_song', ['title', 'artists'], song_id=10))"
        starts = []
        for policy in ('explicit_joined_fields', 'automatic_region_joined_fields'):
            with tempfile.TemporaryDirectory() as temp:
                data = fixture(Path(temp), policy, programs=(LIBRARY, field_call, field_call, PROGRAMS[-1]))
                result = data['result']
                self.assertEqual(result['stop_reason'], 'agent_declared_complete')
                self.assertEqual(result['api_requests'], 2)
                self.assertEqual(result['projection_runtime']['explicit_field_partial_hits'], 2)
                self.assertEqual(result['projection_runtime']['projection_partial_hits'], 0)
                self.assertEqual(result['compact_receipts']['receipt_rows'], 2)
                self.assertEqual(result['known_total_tokens'], 200)
                fields = json.loads((data['folder'] / 'joined_field_events_private.json').read_text())
                self.assertEqual([row['origin'] for row in fields], ['explicit_fields'] * 2)
                starts.append(data['captured'][0])
        self.assertEqual(*starts)

    def test_repeated_rolling_summaries_share_the_same_call_and_token_ledger(self):
        for policy in ('explicit_joined_fields', 'automatic_region_joined_fields'):
            with tempfile.TemporaryDirectory() as temp:
                data = fixture(Path(temp), policy, checkpoint=True,
                               programs=(LIBRARY,) + (SOURCE,) * 7 + (PROGRAMS[-1],), max_calls=12)
                result = data['result']
                self.assertEqual(result['stop_reason'], 'agent_declared_complete')
                self.assertGreaterEqual(result['checkpoint_control']['installations'], 2)
                self.assertLessEqual(result['usage_by_role']['focus']['calls'], 3)
                self.assertEqual(result['model_calls'], sum(row['calls'] for row in result['usage_by_role'].values()))
                self.assertEqual(result['known_total_tokens'], sum(
                    row['input_tokens'] + row['output_tokens'] for row in result['usage_by_role'].values()))

    def test_both_arms_share_initial_request_and_account_actual_calls_and_compact_receipts(self):
        starts = []
        for policy in ('explicit_joined_fields', 'automatic_region_joined_fields'):
            with tempfile.TemporaryDirectory() as temp:
                data = fixture(Path(temp), policy)
                result = data['result']
                self.assertEqual(result['stop_reason'], 'agent_declared_complete',
                                 (data['folder'] / 'error_private.json').read_text() if (data['folder'] / 'error_private.json').exists() else result)
                optimized = policy == 'automatic_region_joined_fields'
                self.assertEqual((result['model_calls'], result['known_total_tokens'], result['unknown_usage_calls']), (4, 200, 0))
                self.assertEqual(result['api_requests'], 3 if optimized else 5)
                self.assertEqual(result['request_budget']['spent'], result['api_requests'])
                self.assertEqual(result['request_budget']['pending'], 0)
                self.assertEqual(result['projection_runtime']['projection_partial_hits'], 4 if optimized else 0)
                self.assertEqual(result['projection_runtime']['ordinary_complete_cache_hits'], 1 if optimized else 3)
                self.assertEqual(result['checkpoint_policy'], 'rolling_separate')
                self.assertEqual(result['projection_policy'], policy)
                self.assertEqual(result['compact_receipts']['transformed_observations'], 4)
                self.assertEqual(result['compact_receipts']['receipt_rows'], result['api_requests'])
                self.assertTrue(result['cleanup_confirmed'])
                self.assertTrue(result['projection_runtime']['control_accounting_complete'])
                self.assertEqual(result['contract_feedback']['feedback_events'], [])
                spans = json.loads((data['folder'] / 'spans.json').read_text())
                outers = [span['observation'] for span in spans.values()
                          if span['action'] and span['action'].get('name') == 'run_python']
                self.assertEqual(sum(len(decode_receipts(row['api_receipts'])) for row in outers), result['api_requests'])
                ledger = json.loads((data['folder'] / 'request_budget_events_private.json').read_text())
                self.assertEqual(sum(event['kind'] == 'sent' for event in ledger), result['api_requests'])
                self.assertEqual(len(data['raw'].calls), result['api_requests'])
                starts.append(data['captured'][0])
        self.assertEqual(starts[0], starts[1])

    def test_rolling_checkpoint_charges_shared_focus_cost_after_compact_receipts(self):
        from audit_rolling_checkpoint_trace import audit_trace
        from fixed_budget_local_llama import payload_for as summary_payload
        from tool_choice_local_llama import payload_for as agent_payload
        from public_display import CODE_TOOLS
        for policy in ('explicit_joined_fields', 'automatic_region_joined_fields'):
            with self.subTest(policy=policy), tempfile.TemporaryDirectory() as temp:
                data = fixture(Path(temp), policy, checkpoint=True)
                result, folder = data['result'], data['folder']
                self.assertEqual(result['stop_reason'], 'agent_declared_complete')
                self.assertTrue(result['checkpoint_control']['checkpoint_installed'])
                self.assertEqual([c['role'] for c in data['captured']], ['agent'] * 3 + ['focus', 'agent'])
                self.assertEqual(result['model_calls'], 5)
                self.assertEqual(result['projection_runtime']['program_attempts'], 4)
                self.assertEqual(result['usage_by_role']['focus']['calls'], 1)
                self.assertEqual(result['usage_by_role']['focus']['input_tokens'] +
                                 result['usage_by_role']['focus']['output_tokens'], 10020)
                self.assertEqual(result['known_total_tokens'], sum(
                    row['input_tokens'] + row['output_tokens'] for row in result['usage_by_role'].values()))
                focus = json.loads(data['captured'][3]['messages'][1]['content'])
                receipts = [json.loads(m['content'])['observation']['api_receipts']
                            for m in focus['older_history'] + focus['recent_context'] if m['role'] == 'tool']
                self.assertEqual(len(receipts), 3)
                self.assertTrue(all(type(table) is dict and decode_receipts(table) is not None for table in receipts))
                # Materialize only synthetic transport receipts, as P118's audit fixture does.
                for number, capture in enumerate(data['captured'], 1):
                    call = folder / f'call_{number:03d}'
                    actor = capture['role'] == 'agent'
                    payload = agent_payload if actor else summary_payload
                    (call / 'request.json').write_text(json.dumps(payload(
                        capture['config'], capture['messages'], CODE_TOOLS if actor else [])))
                    path = call / 'response.json'
                    response = json.loads(path.read_text())
                    usage = {'prompt_tokens': response['input_tokens'], 'completion_tokens': response['output_tokens'],
                             'total_tokens': response['input_tokens'] + response['output_tokens'],
                             'prompt_tokens_details': {'cached_tokens': response['cached_input_tokens']}}
                    response['usage_details'] = usage
                    path.write_text(json.dumps(response))
                    (call / 'raw_response.json').write_text(json.dumps({'usage': usage, 'timings': response['timings'],
                        'choices': [{'message': response['message'], 'finish_reason': response['done_reason']}]}))
                config = json.loads((folder / 'plan.json').read_text())
                checked = audit_trace(folder, config, initial_conversation(data['original'], data['public']))
                self.assertTrue(checked['checkpoint_installed'])
                self.assertEqual(checked['known_total_tokens'], result['known_total_tokens'])
                self.assertEqual(checked['usage_by_role'], result['usage_by_role'])
                self.assertEqual(checked['suffix_api_requests'], result['request_budget']['spent'])
                self.assertEqual(result['compact_receipts']['transformed_observations'], 4)

    def test_unknown_model_usage_keeps_known_cost_and_does_not_retry(self):
        with tempfile.TemporaryDirectory() as temp:
            data = fixture(Path(temp), 'automatic_region_joined_fields', unknown=True)
            result = data['result']
            self.assertEqual((result['model_calls'], result['known_total_tokens'], result['unknown_usage_calls']), (2, 50, 1))
            self.assertEqual(result['api_requests'], 1)
            self.assertEqual(result['projection_runtime']['program_attempts'], 1)
            self.assertEqual(len(data['captured']), 2)
            self.assertTrue(result['cleanup_confirmed'])

    def test_explicit_stop_does_not_execute_next_model_or_restore_omitted_reads(self):
        with tempfile.TemporaryDirectory() as temp:
            data = fixture(Path(temp), 'automatic_region_joined_fields', stop=True)
            result = data['result']
            self.assertEqual(result['stop_reason'], 'user_stop')
            self.assertEqual((result['model_calls'], result['api_requests']), (1, 1))
            self.assertEqual(len(data['captured']), 1)
            self.assertEqual(result['request_budget']['pending'], 0)

    def test_partial_contract_failure_stops_before_next_model_and_keeps_known_exception(self):
        with tempfile.TemporaryDirectory() as temp:
            data = fixture(Path(temp), 'automatic_region_joined_fields', contract_failure=True)
            result = data['result']
            self.assertEqual(result['stop_reason'], 'projection_contract_stopped')
            self.assertEqual(disposition(result), 'evaluate')
            self.assertEqual((result['model_calls'], result['api_requests']), (2, 2))
            self.assertEqual(result['unknown_effect_requests'], 0)
            self.assertTrue(result['projection_runtime']['projection_failed'])
            self.assertTrue(result['request_budget']['stopped'])
            self.assertEqual(result['projection_runtime']['projection_partial_hits'], 2)
            self.assertEqual(len(data['captured']), 2)
            self.assertTrue(result['cleanup_confirmed'])

    def test_unknown_API_effect_stops_batch_even_after_partial_hit(self):
        with tempfile.TemporaryDirectory() as temp:
            data = fixture(Path(temp), 'automatic_region_joined_fields', unknown_api=True)
            result = data['result']
            self.assertEqual(result['stop_reason'], 'runtime_error')
            self.assertEqual(disposition(result), 'stop_batch')
            self.assertEqual(result['unknown_effect_requests'], 1)
            self.assertEqual(len(data['captured']), 2)
            self.assertEqual(result['api_requests'], 2)
            self.assertTrue(result['request_budget']['stopped'])

    def test_cleanup_failure_cannot_be_evaluated_as_a_known_contract_stop(self):
        with tempfile.TemporaryDirectory() as temp:
            data = fixture(Path(temp), 'automatic_region_joined_fields', contract_failure=True, cleanup_bad=True)
            result = data['result']
            self.assertEqual(result['stop_reason'], 'cleanup_error')
            self.assertFalse(result['cleanup_confirmed'])
            self.assertEqual(disposition(result), 'stop_batch')
            self.assertEqual(len(data['captured']), 2)

    def test_no_tool_call_is_not_a_projection_success(self):
        with tempfile.TemporaryDirectory() as temp:
            data = fixture(Path(temp), 'automatic_region_joined_fields', no_tool=True)
            result = data['result']
            self.assertEqual((result['model_calls'], result['api_requests']), (5, 0))
            self.assertEqual(result['projection_runtime']['projection_partial_hits'], 0)
            self.assertEqual(result['compact_receipts']['transformed_observations'], 0)

    def test_ledger_mismatch_stops_request_budget(self):
        class Bridge:
            receipts = []
        budget = RequestBudget(2)
        with self.assertRaisesRegex(RuntimeError, 'ledger_and_receipts'):
            check_api_accounting(budget, 1, [], Bridge())
        self.assertTrue(budget.stopped)


if __name__ == '__main__':
    unittest.main()
