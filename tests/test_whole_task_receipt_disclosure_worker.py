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
from run_whole_task_receipt_disclosure_cell import run_cell, check_api_accounting
from shared_api_reservations import RequestBudget
from whole_task_receipt_disclosure import cell_id, initial_conversation
from single_checkpoint_worker_fixture import configuration as checkpoint_configuration
from test_single_checkpoint import VALID as VALID_CHECKPOINT
from test_automatic_projection_runtime import LIBRARY
from test_region_projection_runtime import TrustedRegionSession, SOURCE
from test_public_name_catalog import tool
from test_public_read_views_live_probe import Fixture, catalog

ROOT = Path(__file__).resolve().parents[1]
PROGRAMS = (LIBRARY, SOURCE, SOURCE, "call_api('supervisor', 'complete_task')")


def fixture(storage, mode, *, replication=1, unknown=False, unknown_at=2, stop=False, contract_failure=False, unknown_api=False,
            cleanup_bad=False, no_tool=False, checkpoint=False, programs=PROGRAMS, max_calls=5, actor_content=None):
    original = (checkpoint_configuration()[0] if checkpoint else
                json.loads((ROOT / 'configs/P29_stateful_code_v01.json').read_text()))
    task = next(iter(original['api_budget_by_task']))
    plan = dict(phase='budget_observation_connection', experiment='P128',
        known_tasks=[{'task_id': task, 'source_run': 'synthetic'}], model_seeds=[57,157], world_seed=42,
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
                marker = storage / '.runtime/P128.stop'
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
        if unknown and len(captured) == unknown_at:
            raise OSError('synthetic model response lost')
        index = sum(c['role'] == 'agent' for c in captured) - 1
        message = dict(role='assistant', content=actor_content, reasoning_content='synthetic fixture reasoning')
        if role == 'focus':
            message = deepcopy(VALID_CHECKPOINT)
        elif not no_tool:
            function = programs[index] if isinstance(programs[index],dict) else {
                'name':'run_python','arguments':json.dumps({'code':programs[index], 'span_ids':[]})}
            message['tool_calls'] = [{'id':'fixture-'+str(index), 'type':'function', 'function':function}]
        cached = 0 if index == 0 or role == 'focus' else 20
        tokens = count(config, messages, tools, timeout)['input_tokens']
        response = dict(status='ok', input_tokens=tokens, output_tokens=20, wall_seconds=0,
            done_reason='stop' if no_tool or role == 'focus' else 'tool_calls', cached_input_tokens=cached, message=message,
            timings=dict(cache_n=cached, prompt_n=tokens-cached, predicted_n=20, prompt_ms=1, predicted_ms=1))
        (output / 'response.json').write_text(json.dumps(response))
        return response
    tools = list(catalog().catalog.values()) + [tool('supervisor__complete_task')]
    with patch('run_whole_task_receipt_disclosure_cell.TypedBridgeProcess', Raw), \
         patch('run_whole_task_receipt_disclosure_cell.RegionProjectionPython', Session), \
         patch('run_whole_task_receipt_disclosure_cell.verify_joined_implementation', return_value=JOINED_CONTRACT_ID), \
         patch('region_projection_runtime.verify_joined_implementation', return_value=JOINED_CONTRACT_ID), \
         patch('demand_joined_read_adapter.verify_joined_implementation', return_value=JOINED_CONTRACT_ID), \
         patch('receipt_disclosure_rolling_inference.count_agent_input', side_effect=count), \
         patch('receipt_disclosure_rolling_inference.count_summary_input', side_effect=count), \
         patch('fixed_budget_residual.count_input', side_effect=count), \
         patch('fixed_budget_residual.model_call', side_effect=send), \
         patch('tool_choice_residual.count_input', side_effect=count), \
         patch('tool_choice_residual.model_call', side_effect=send):
        result = run_cell(storage, ROOT, plan, original, tools, item, 'error_exception', cell_id(replication, 1, mode),
                          receipt_mode=mode, replication=replication)
    return {'result': result, 'captured': captured, 'folder': storage / 'records/context_pilot' / cell_id(replication, 1, mode),
            'raw': raw_instances[0] if raw_instances else None, 'original': original, 'public': public}


class ReceiptDisclosureWorkerTests(unittest.TestCase):
    def assert_finished(self, data):
        result = data['result']
        error = data['folder'] / 'error_private.json'
        self.assertEqual(result['stop_reason'], 'agent_declared_complete',
                         error.read_text() if error.exists() else result)
        self.assertTrue(result['cleanup_confirmed'])
        return result

    def test_both_modes_keep_raw_receipts_common_runtime_and_initial_input_for_both_seeds(self):
        for rep, seed in enumerate((57, 157), 1):
            starts, raw_observations = [], []
            for mode in ('full', 'disclose'):
                with self.subTest(rep=rep, mode=mode), tempfile.TemporaryDirectory() as temp:
                    data = fixture(Path(temp), mode, replication=rep)
                    result = self.assert_finished(data)
                    self.assertEqual((result['model_seed'], result['replication']), (seed, rep))
                    self.assertEqual(result['receipt_disclosure_policy'], mode)
                    self.assertEqual(result['projection_policy'], 'explicit_joined_fields')
                    self.assertEqual(result['projection_runtime']['automatic_region_partial_hits'], 0)
                    self.assertEqual(result['api_requests'], 5)
                    self.assertEqual(result['request_budget']['spent'], 5)
                    self.assertEqual(result['projection_runtime']['ordinary_complete_cache_hits'], 3)
                    self.assertEqual((result['model_calls'], result['known_total_tokens']), (4, 200))
                    self.assertTrue(result['receipt_disclosure_contract_intact'])
                    meta = result['receipt_disclosure']
                    self.assertEqual(meta['closed_turns'], 4)
                    self.assertEqual(meta['disclosed_turns'] > 0, mode == 'disclose')
                    spans = json.loads((data['folder'] / 'spans.json').read_text())
                    outer = [s['observation'] for s in spans.values()
                             if s.get('action', {}).get('name') == 'run_python']
                    self.assertEqual(sum(len(decode_receipts(o['api_receipts'])) for o in outer), 5)
                    self.assertEqual(len(data['raw'].calls), 5)
                    sidecar = json.loads((data['folder'] / 'receipt_disclosure_sidecar_private.json').read_text())
                    events = json.loads((data['folder'] / 'events.json').read_text())
                    self.assertEqual(sidecar['committed_event_count'], len(events))
                    raw_observations.append(outer)
                    starts.append(data['captured'][0]['messages'])
            self.assertEqual(starts[0], starts[1])
            self.assertEqual(raw_observations[0], raw_observations[1])

    def test_existing_archive_expansion_is_paid_and_preserves_original_page(self):
        from context_preservation import page_span
        expansion = {'name': 'read_span', 'arguments': json.dumps({'span_id': 's2', 'offset': 0})}
        for mode in ('full', 'disclose'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as temp:
                data = fixture(Path(temp), mode, programs=(LIBRARY, SOURCE, expansion, PROGRAMS[-1]))
                result = self.assert_finished(data)
                self.assertEqual((result['model_calls'], result['known_total_tokens']), (4, 200))
                self.assertEqual(result['api_requests'], 5)
                self.assertEqual(result['receipt_disclosure']['receipt_read_span_actions'], 1)
                self.assertGreater(result['receipt_disclosure']['receipt_read_span_returned_characters'], 0)
                spans = json.loads((data['folder'] / 'spans.json').read_text())
                readback = next(s for s in spans.values() if s.get('action', {}).get('name') == 'read_span')
                self.assertEqual(readback['observation'], page_span(spans, 's2', 0, 24000))

    def test_actor_text_survives_inner_first_recorder_and_display_projection(self):
        for mode in ('full', 'disclose'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as temp:
                data = fixture(Path(temp), mode, actor_content='synthetic actor note')
                self.assert_finished(data)
                messages = data['captured'][1]['messages']
                actor = next(m for m in messages if m['role'] == 'assistant')
                self.assertEqual(actor['content'], 'synthetic actor note')
                raw = json.loads((data['folder'] / 'conversation_private.json').read_text())
                self.assertTrue(all(m['content'] == 'synthetic actor note'
                                    for m in raw if m['role'] == 'assistant'))

    def test_rolling_summaries_charge_same_ledger_and_use_the_same_fixed_display(self):
        for mode in ('full', 'disclose'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as temp:
                data = fixture(Path(temp), mode, checkpoint=True,
                               programs=(LIBRARY,) + (SOURCE,) * 7 + (PROGRAMS[-1],), max_calls=12)
                result = self.assert_finished(data)
                self.assertGreaterEqual(result['checkpoint_control']['installations'], 2)
                self.assertGreater(result['usage_by_role']['focus']['calls'], 0)
                self.assertEqual(result['model_calls'], sum(v['calls'] for v in result['usage_by_role'].values()))
                self.assertEqual(result['known_total_tokens'], sum(
                    v['input_tokens'] + v['output_tokens'] for v in result['usage_by_role'].values()))
                focus = next(c for c in data['captured'] if c['role'] == 'focus')
                content = json.loads(focus['messages'][1]['content'])
                receipts = [json.loads(m['content'])['observation']['api_receipts']
                    for m in content['older_history'] + content['recent_context'] if m['role'] == 'tool']
                self.assertTrue(receipts)
                self.assertEqual(any(x.get('format') == 'archived_receipt_index_v1' for x in receipts), mode == 'disclose')
                views = json.loads((data['folder'] / 'receipt_disclosure_inference_views.json').read_text())
                self.assertEqual(len(views), result['usage_by_role']['agent']['calls'])

    def test_unknown_usage_keeps_paid_work_and_stops_without_retry(self):
        with tempfile.TemporaryDirectory() as temp:
            data = fixture(Path(temp), 'disclose', unknown=True)
            result = data['result']
            self.assertEqual((result['model_calls'], result['known_total_tokens'], result['unknown_usage_calls']), (2, 50, 1))
            self.assertEqual((len(data['captured']), result['api_requests']), (2, 1))
            self.assertEqual(result['stop_reason'], 'model_usage_unknown')
            self.assertEqual(result['receipt_disclosure']['closed_turns'], 1)
            self.assertTrue(result['cleanup_confirmed'])

    def test_unknown_API_is_not_disclosed_as_known_success(self):
        with tempfile.TemporaryDirectory() as temp:
            data = fixture(Path(temp), 'disclose', unknown_api=True)
            result = data['result']
            self.assertEqual(result['unknown_effect_requests'], 1)
            self.assertEqual(len(data['captured']), 2)
            self.assertEqual(disposition(result), 'stop_batch')
            meta = json.loads((data['folder'] / 'receipt_disclosure_sidecar_private.json').read_text())
            self.assertFalse(meta['decisions'][-1]['disclosed'])

    def test_first_request_unknown_retains_empty_source_and_unknown_usage(self):
        with tempfile.TemporaryDirectory() as temp:
            data = fixture(Path(temp), 'disclose', unknown=True, unknown_at=1)
            result = data['result']
            self.assertEqual(result['stop_reason'], 'model_usage_unknown')
            self.assertEqual((result['model_calls'], result['known_total_tokens'], result['unknown_usage_calls']), (1, 0, 1))
            self.assertEqual(result['api_requests'], 0)
            self.assertEqual(result['receipt_disclosure']['closed_turns'], 0)
            self.assertEqual(len(json.loads((data['folder'] / 'conversation_private.json').read_text())), 2)
            self.assertEqual(json.loads((data['folder'] / 'events.json').read_text()), [])

    def test_sidecar_write_failure_preserves_summary_cost_and_raw_records(self):
        import run_whole_task_receipt_disclosure_cell as worker
        save = worker.write_json
        def failing(path, value):
            if path.name == 'receipt_disclosure_sidecar_private.json':
                raise OSError('synthetic sidecar persistence failure')
            return save(path, value)
        with tempfile.TemporaryDirectory() as temp, patch.object(worker, 'write_json', failing):
            data = fixture(Path(temp), 'disclose')
            result = data['result']
            self.assertEqual(result['stop_reason'], 'receipt_disclosure_contract_stopped')
            self.assertEqual((result['model_calls'], result['known_total_tokens'], result['api_requests']), (1, 50, 1))
            self.assertEqual(result['sidecar_save_error_type'], 'OSError')
            self.assertFalse(result['receipt_disclosure_contract_intact'])
            self.assertEqual(len(json.loads((data['folder'] / 'events.json').read_text())), 2)
            self.assertTrue((data['folder'] / 'summary.json').is_file())
            self.assertEqual(len(data['captured']), 1)

    def test_malformed_closed_turn_keeps_raw_records_and_usage_but_no_next_request(self):
        from receipt_disclosure_live import ReceiptDisclosureLiveConversation
        original = ReceiptDisclosureLiveConversation.append_closed_turn
        def corrupt(self, response, outer, **kwargs):
            kwargs = deepcopy(kwargs)
            kwargs['events'][-1]['call'] = 'not_the_current_call'
            return original(self, response, outer, **kwargs)
        with tempfile.TemporaryDirectory() as temp, patch.object(
                ReceiptDisclosureLiveConversation, 'append_closed_turn', corrupt):
            data = fixture(Path(temp), 'disclose')
            result = data['result']
            self.assertEqual(result['stop_reason'], 'receipt_disclosure_contract_stopped')
            self.assertEqual((result['model_calls'], result['known_total_tokens'], result['api_requests']), (1, 50, 1))
            self.assertFalse(result['receipt_disclosure_contract_intact'])
            self.assertEqual(len(data['captured']), 1)
            self.assertEqual(len(json.loads((data['folder'] / 'events.json').read_text())), 2)
            self.assertEqual(len(json.loads((data['folder'] / 'spans.json').read_text())), 2)
            self.assertTrue((data['folder'] / 'conversation_private.json').exists())

    def test_stop_no_tool_and_cleanup_failure_remain_distinct(self):
        cases = [({'stop': True}, 'user_stop'),
                 ({'no_tool': True}, 'call_limit'),
                 ({'cleanup_bad': True}, 'cleanup_error')]
        for kwargs, expected in cases:
            with self.subTest(case=kwargs), tempfile.TemporaryDirectory() as temp:
                data = fixture(Path(temp), 'disclose', **kwargs)
                self.assertEqual(data['result']['stop_reason'], expected)
                self.assertEqual(data['result']['projection_runtime']['automatic_region_partial_hits'], 0)

    def test_ledger_mismatch_stops_before_next_request(self):
        class Bridge:
            receipts = []
        budget = RequestBudget(2)
        with self.assertRaisesRegex(RuntimeError, 'ledger_and_receipts'):
            check_api_accounting(budget, 1, [], Bridge())
        self.assertTrue(budget.stopped)


if __name__ == '__main__':
    unittest.main()


