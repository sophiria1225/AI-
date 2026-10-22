import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from audit_documentation_comparison import audit_cell, development_gate, validate_admission, validate_signal
from budget_signal import digest, snapshot
from code_agent_interface import CODE_TOOLS
from documentation_comparison import ARMS, add_notification, build_condition
from inference_cache_control import cache_measurement
from local_llama import parse_response, payload_for
from native_conversation import NativeConversation
from run_context_comparison import write_json
from run_handoff_factors import sha


class DocumentationComparisonAuditTests(unittest.TestCase):
    def limits(self):
        return {'max_api_requests': 80, 'max_calls': 2, 'max_total_tokens': 200,
                'max_wall_seconds': 60, 'max_output_tokens': 40, 'model': {'num_ctx': 1000}}

    def test_counter_or_history_tampering_is_detected(self):
        limits = self.limits(); base = [{'role': 'user', 'content': 'task'}]
        state = snapshot(limits, [], 18, 0, 0); supplied = add_notification(base, state)
        signal = {'notification_supplied': True, 'next_call_id': 'call_001', 'cache_prompt': False,
                  'state': state, 'base_messages_sha256': digest(base),
                  'model_messages_sha256': digest(supplied), 'notification_characters': len(supplied[-1]['content'])}
        expected = {'remaining_api_before': 62, 'remaining_calls_before': 2,
                    'remaining_tokens_before': 200, 'known_tokens_before': 0}
        self.assertEqual(validate_signal(signal, base, expected, limits, 0), supplied)
        for field in ('api_calls', 'model_calls', 'logical_input_plus_output_tokens'):
            bad = copy.deepcopy(signal); bad['state']['remaining'][field] += 1
            with self.assertRaises(ValueError): validate_signal(bad, base, expected, limits, 0)
        with self.assertRaisesRegex(ValueError, 'history'):
            validate_signal(signal, [{'role': 'user', 'content': 'different'}], expected, limits, 0)
        bad = copy.deepcopy(signal); bad['cache_prompt'] = True
        with self.assertRaisesRegex(ValueError, 'cache'):
            validate_signal(bad, base, expected, limits, 0)

    def test_output_reservation_is_recomputed_and_context_stays_a_hard_bound(self):
        limits = self.limits()
        entry = {'policy': 'residual', 'remaining_tokens': 100, 'input_tokens': 75,
                 'configured_output_limit': 40, 'context_limit': 1000,
                 'selected_output_cap': 25, 'admitted': True, 'stop_reason': None}
        validate_admission(entry, 100, limits)
        for key, value in [('selected_output_cap', 40), ('remaining_tokens', 101), ('admitted', False)]:
            with self.assertRaises(ValueError):
                validate_admission({**entry, key: value}, 100, limits)
        bad = {**entry, 'remaining_tokens': 2000, 'input_tokens': 990, 'selected_output_cap': 40}
        with self.assertRaises(ValueError): validate_admission(bad, 2000, limits)

    def cohort(self):
        return [{'task_id': str(n), 'arm': arm, 'record_status': 'evaluated',
                 'success': n % 2 == 0, 'unknown_usage_calls': 0,
                 'known_total_tokens': 100 if arm == ARMS[0] else 90}
                for n in range(4) for arm in ARMS]

    def test_same_success_count_with_different_solved_tasks_cannot_pass(self):
        rows = self.cohort()
        self.assertTrue(development_gate(rows)['development_gate_met'])
        rows[1]['success'] = False; rows[3]['success'] = True
        result = development_gate(rows)
        self.assertEqual(result['paired_success_losses'], 1)
        self.assertFalse(result['development_gate_met'])

    def test_unknown_or_missing_cells_never_pass_the_complete_cohort_gate(self):
        for status, unknown in [('attempted_unevaluated', 1), ('not_run_after_stop', 0), ('evaluated', 1)]:
            rows = self.cohort(); rows[-1].update(record_status=status, unknown_usage_calls=unknown)
            result = development_gate(rows)
            self.assertFalse(result['development_gate_met'])
            self.assertIsNone(result['selective_minus_full_total_tokens'])
        rows = self.cohort()
        for r in rows: r['known_total_tokens'] = 100
        self.assertFalse(development_gate(rows)['development_gate_met'])
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            development_gate([*rows[:-1], rows[0]])

    def fixture(self, folder):
        original = {'seed': 42, 'phase': 'P29', 'draft_temperature': .7, 'agent_temperature': 1,
            'api_budget_by_task': {'fixture': 80}, 'observation_page_characters': 24000,
            'max_calls': 20, 'max_total_tokens': 10000, 'max_wall_seconds': 100,
            'max_output_tokens': 40, 'model': {'model': 'fixture', 'num_ctx': 1000}}
        plan = {'phase': 'P45', 'max_calls': 2, 'max_total_tokens': 200, 'max_wall_seconds': 60}
        limits = {**copy.deepcopy(original), **plan, 'seed': 50, 'max_api_requests': 80}
        task = {'instruction': 'fixture task'}
        prefix_conv = NativeConversation('fixture rules', task)
        prefix_spans, prefix_events = {}, []
        for i in range(1, 9):
            span = {'id': f's{i}', 'action': None, 'observation': {'recorded': i}}
            prefix_spans[span['id']] = span
            prefix_events.append({'call': f'call_{i:03d}', 'span_id': span['id'], 'stage': 'model_tool',
                                  'api_request_sent': False, 'effects_unknown': False})
            prefix_conv.append({'role': 'assistant', 'content': f'fixture {i}'}, [span])
        prefix = {'conversation_private': prefix_conv.messages(), 'public_task': task,
                  'spans': prefix_spans, 'events': prefix_events, 'usage': [],
                  'manifest': {'state': {'api_requests': 0, 'model_calls': 8}}}
        item = {'task_id': 'fixture', 'source_run': 'P29_01_CODE', 'source_sha256': {},
                'boundary_manifest_sha256': 'fixture', 'programs': [], 'prefix': prefix}
        conversation, transfer = build_condition(item, ARMS[0]); base, _ = conversation.for_model()
        state = snapshot(limits, [], 0, 0, 0); messages = add_notification(base, state)
        raw = {'usage': {'prompt_tokens': 50, 'completion_tokens': 1, 'total_tokens': 51,
                        'prompt_tokens_details': {'cached_tokens': 0}},
               'choices': [{'finish_reason': 'stop', 'message': {'role': 'assistant', 'content': 'fixture'}}],
               'timings': {'cache_n': 0, 'prompt_n': 50, 'predicted_n': 1, 'prompt_ms': 100, 'predicted_ms': 10}}
        response = {**parse_response(raw), 'wall_seconds': 1}
        cfg = {**limits['model'], 'temperature': 1, 'seed': 50, 'num_predict': 40, 'cache_prompt': False}
        call = {'id': 'call_001', 'status': 'ok', 'role': 'agent', 'input_tokens': 50, 'output_tokens': 1,
                'cached_input_tokens': 0, 'wall_seconds': 1, 'predicted_input_tokens': 50, 'output_cap': 40}
        notification = {'next_call_id': 'call_001', 'notification_supplied': True, 'cache_prompt': False,
            'state': state, 'base_messages_sha256': digest(base), 'model_messages_sha256': digest(messages),
            'notification_characters': len(messages[-1]['content']), 'model_attempted': True,
            'first_input_measurement': cache_measurement('cold_1', response, 50)}
        entry = {'next_call_id': 'call_001', 'policy': 'residual', 'remaining_tokens': 200,
                 'input_tokens': 50, 'configured_output_limit': 40, 'context_limit': 1000,
                 'selected_output_cap': 40, 'admitted': True, 'stop_reason': None,
                 'model_attempted': True, 'model_request_started': True, 'count_wall_seconds': .01}
        span = {'id': 's9', 'action': None, 'observation': {'status': 'invalid_action'}}
        conversation.append(response['message'], [span])
        setup = {'status': 'matched_observable_prefix', 'wall_seconds': 1,
                 'environment_replay': {'api_requests': 0, 'observation_matches': 0,
                                       'db_files_match': True, 'unknown_effect_requests': 0},
                 'python_replay': {'programs': 0, 'api_requests_sent': 0, 'checks': []}}
        summary = {'run_id': folder.name, 'task_id': 'fixture', 'arm': ARMS[0], 'model_calls': 1,
                   'known_total_tokens': 51, 'unknown_usage_calls': 0, 'api_requests': 0,
                   'prefix_api_requests': 0, 'total_task_api_requests': 0, 'unknown_effect_requests': 0,
                   'stop_reason': 'call_limit', 'python_session': {'container_removed': True},
                   'wall_seconds': 1.1, 'full_wall_seconds': 2.2, 'transfer': transfer}
        records = {'plan.json': limits, 'factor_plan.json': plan, 'summary.json': summary,
                   'usage.json': [call], 'events.json': [{'call': 'call_001', 'span_id': 's9',
                        'stage': 'model_tool', 'api_request_sent': False, 'effects_unknown': False}],
                   'spans.json': {**prefix_spans, 's9': span}, 'setup.json': setup,
                   'source_identity.json': {k: item[k] for k in
                        ('task_id', 'source_run', 'source_sha256', 'boundary_manifest_sha256')},
                   'prefix_events.json': prefix_events, 'prefix_spans.json': prefix_spans,
                   'prefix_usage.json': [], 'public_task.json': task,
                   'budget_signals.json': [notification], 'admissions.json': [entry],
                   'initial_messages_private.json': base, 'conversation_private.json': conversation.messages()}
        for name, value in records.items(): write_json(folder / name, value)
        out = folder / 'call_001'; out.mkdir()
        for name, value in [('request.json', payload_for(cfg, messages, CODE_TOOLS)),
                            ('response.json', response), ('raw_response.json', raw)]: write_json(out / name, value)
        write_json(folder / 'evaluation.json', {'official_success': False, 'evaluation_returned_to_model': False,
                   'execution_summary_sha256': sha(folder / 'summary.json')})
        return item, original, plan, {'base_messages_sha256': digest(base)}

    def test_reconstructs_actual_history_and_detects_changed_request_and_raw_count(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory); item, original, plan, pre = self.fixture(folder)
            result = audit_cell(folder, item, ARMS[0], original, plan, pre, True)
            self.assertEqual(result['known_total_tokens'], 51)
            self.assertFalse(result['success'])
            self.assertTrue(result['request_checks'][0]['raw_terminal_counters_checked'])
            path = folder / 'call_001/request.json'; request = json.loads(path.read_text())
            changed = copy.deepcopy(request); changed['messages'][1]['content'] = 'altered task'
            write_json(path, changed)
            with self.assertRaisesRegex(ValueError, 'actual request'):
                audit_cell(folder, item, ARMS[0], original, plan, pre, True)
            write_json(path, request)
            path = folder / 'call_001/raw_response.json'; raw = json.loads(path.read_text())
            raw['usage'].update(prompt_tokens=51, total_tokens=52); write_json(path, raw)
            with self.assertRaisesRegex(ValueError, 'raw terminal'):
                audit_cell(folder, item, ARMS[0], original, plan, pre, True)

    def test_terminal_timeout_retains_unknown_usage_and_no_evaluation(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory); item, original, plan, pre = self.fixture(folder)
            (folder / 'evaluation.json').unlink()
            limits = json.loads((folder / 'plan.json').read_text())
            usage = json.loads((folder / 'usage.json').read_text())
            from handoff_factors import split_turns
            from native_conversation import recover_turn
            saved = json.loads((folder / 'conversation_private.json').read_text())
            conversation = NativeConversation(saved[0]['content'], item['prefix']['public_task'])
            for turn in split_turns(saved): conversation.append(turn[0], recover_turn(turn))
            base, _ = conversation.for_model()
            state = snapshot(limits, usage, 0, 0, 1); messages = add_notification(base, state)
            signals = json.loads((folder / 'budget_signals.json').read_text())
            signals.append({'next_call_id': 'call_002', 'notification_supplied': True, 'cache_prompt': True,
                'state': state, 'base_messages_sha256': digest(base), 'model_messages_sha256': digest(messages),
                'notification_characters': len(messages[-1]['content']), 'model_attempted': True})
            write_json(folder / 'budget_signals.json', signals)
            entries = json.loads((folder / 'admissions.json').read_text())
            entries.append({**entries[0], 'next_call_id': 'call_002', 'remaining_tokens': 149, 'input_tokens': 75})
            write_json(folder / 'admissions.json', entries)
            usage.append({'id': 'call_002', 'status': 'error', 'role': 'agent', 'input_tokens': None,
                          'output_tokens': None, 'cached_input_tokens': None, 'wall_seconds': 10,
                          'predicted_input_tokens': 75, 'output_cap': 40})
            write_json(folder / 'usage.json', usage)
            summary = json.loads((folder / 'summary.json').read_text())
            summary.update(model_calls=2, unknown_usage_calls=1, stop_reason='wall_limit_during_model_call')
            write_json(folder / 'summary.json', summary)
            out = folder / 'call_002'; out.mkdir()
            cfg = {**limits['model'], 'temperature': 1, 'seed': 51, 'num_predict': 40, 'cache_prompt': True}
            write_json(out / 'request.json', payload_for(cfg, messages, CODE_TOOLS))
            write_json(out / 'response.json', {'status': 'error', 'input_tokens': None, 'output_tokens': None})
            result = audit_cell(folder, item, ARMS[0], original, plan, pre, False)
            self.assertIsNone(result['success'])
            self.assertEqual(result['known_total_tokens'], 51)
            self.assertEqual(result['unknown_usage_calls'], 1)
            self.assertEqual(result['cost_profile']['unknown_usage_calls'], 1)
            usage[-1].update(input_tokens=0, output_tokens=0); write_json(folder / 'usage.json', usage)
            with self.assertRaisesRegex(ValueError, 'imputed'):
                audit_cell(folder, item, ARMS[0], original, plan, pre, False)


if __name__ == '__main__':
    unittest.main()
