import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from protocol_stable_history import StableReferenceConversation
from run_context_comparison import BudgetStop
from single_checkpoint_history import (
    FIELDS, SingleCheckpoint, candidate, closed_turns, parse_checkpoint, project)
from single_checkpoint_inference import SingleCheckpointInference
from checkpoint_attempt_usage import attempt_usage


def append_turn(conversation, number, *, malformed=False, no_tool=False, calls=1):
    if no_tool:
        message = {'role': 'assistant', 'content': 'synthetic planned work',
                   'reasoning_content': 'synthetic future intention'}
        spans = [{'id': f's{number}', 'action': None, 'observation': {'not_executed': True}}]
    else:
        functions = [{'name': 'run_python', 'arguments': 'broken' if malformed else '{"code":"synthetic"}'}
                     for _ in range(calls)]
        message = {'role': 'assistant', 'content': '', 'reasoning_content': 'synthetic future intention',
                   'tool_calls': [{'id': f'c{number}-{i}', 'type': 'function', 'function': f}
                                  for i, f in enumerate(functions)]}
        spans = [{'id': f's{number}-{i}', 'action': f, 'observation': {'status': 'ok', 'stdout': 'fixture'}}
                 for i, f in enumerate(functions)]
    conversation.append(message, spans)
    return message


def history():
    conv = StableReferenceConversation('synthetic system', {'instruction': 'synthetic task'})
    append_turn(conv, 1, calls=2)
    append_turn(conv, 2, malformed=True)
    append_turn(conv, 3, no_tool=True)
    append_turn(conv, 4)
    return conv


VALID = {'role': 'assistant', 'content': json.dumps({k: [f'synthetic {k}'] for k in FIELDS})}


class CheckpointProjectionTests(unittest.TestCase):
    def test_whole_native_and_fallback_turns_recent_two_and_archive_are_preserved(self):
        conv = history()
        original = conv.messages()
        rendered, _ = conv.for_model()
        proposal = candidate(rendered)
        value = parse_checkpoint(VALID, 'stop')
        view = project(rendered, proposal, value)
        self.assertEqual(len(closed_turns(rendered)), 4)
        self.assertEqual(proposal['replaced_turns'], 2)
        self.assertEqual(view[:2], rendered[:2])
        self.assertEqual(view[3:], rendered[proposal['cutoff']:])
        self.assertEqual(conv.messages(), original)
        self.assertFalse(json.loads(view[2]['content'])['semantics_verified'])

    def test_incomplete_or_misbound_tool_result_cannot_be_compacted(self):
        messages, _ = history().for_model()
        bad = copy.deepcopy(messages)
        bad[3]['tool_call_id'] = 'different'
        for value in (messages[:-1], bad):
            with self.assertRaises(ValueError):
                candidate(value)

    def test_accepted_checkpoint_survives_new_turns_but_not_changed_old_records(self):
        conv = history()
        messages, _ = conv.for_model()
        controller = SingleCheckpoint()
        proposal = controller.begin(messages, 16384)
        controller.install(messages, proposal, parse_checkpoint(VALID, 'stop'))
        append_turn(conv, 5)
        later, _ = conv.for_model()
        self.assertEqual(controller.view(later)[3:], later[proposal['cutoff']:])
        changed = copy.deepcopy(later)
        changed[2]['content'] = 'altered old record'
        with self.assertRaisesRegex(ValueError, 'archived_prefix_changed'):
            controller.view(changed)

    def test_one_opportunity_even_when_no_checkpoint_was_installed(self):
        messages, _ = history().for_model()
        controller = SingleCheckpoint()
        self.assertIsNone(controller.begin(messages, 16383))
        self.assertIsNotNone(controller.begin(messages, 16384))
        self.assertIsNone(controller.begin(messages, 60000))
        self.assertEqual(controller.view(messages), messages)

    def test_no_tools_truncation_duplicate_keys_extra_fields_or_nested_values_accepted(self):
        invalid = [({**VALID, 'tool_calls': [{'function': {'name': 'run_python'}}]}, 'stop'),
                   (VALID, 'length'), (VALID, 'tool_calls'),
                   ({**VALID, 'content': '{"completed":[],"completed":[]}'}, 'stop'),
                   ({**VALID, 'content': json.dumps({**{k: [] for k in FIELDS}, 'done': True})}, 'stop'),
                   ({**VALID, 'content': json.dumps({**{k: [] for k in FIELDS}, 'remaining': [{}]})}, 'stop'),
                   ({**VALID, 'content': 'x' * 8193}, 'stop')]
        for message, finish in invalid:
            with self.subTest(message=message, finish=finish), self.assertRaises(ValueError):
                parse_checkpoint(message, finish)


def fixture(policy='single_checkpoint', *, summary='valid', token_limit=450000, call_limit=80,
            steps=5, not_shorter=False):
    """Real budget adapters, only network counting and generation replaced.

    No model, generated Python or environment API is run. Synthetic token counts
    are test data and never enter experimental reports.
    """
    folder = tempfile.TemporaryDirectory()
    output = Path(folder.name)
    config = {'checkpoint_policy': policy, 'read_views_enabled': False,
              'model': {'model': 'synthetic', 'num_ctx': 65536,
                        'reasoning_budget_tokens': -1, 'tool_choice': 'auto',
                        'thinking_mode': 'enabled', 'call_timeout_seconds': 600},
              'max_calls': call_limit, 'max_api_requests': 80, 'max_total_tokens': token_limit,
              'max_output_tokens': 4096, 'max_wall_seconds': 1800,
              'agent_temperature': 1.0, 'draft_temperature': 0.7, 'seed': 57,
              'observation_page_characters': 24000}
    conv = StableReferenceConversation('synthetic system', {'instruction': 'synthetic task'})
    infer = SingleCheckpointInference(config, output, conversation=conv)
    captured = []

    def count_agent(cfg, messages, tools, timeout):
        checkpoint = any('ordinary_fallible_summary' in (m.get('content') or '') for m in messages)
        value = 5000 + 4000 * sum(m['role'] == 'assistant' for m in messages)
        if checkpoint and not_shorter:
            value = 30000
        return {'input_tokens': value, 'wall_seconds': 0.001}

    def count_summary(cfg, messages, tools, timeout):
        assert tools == []
        return {'input_tokens': 10000, 'wall_seconds': 0.001}

    def send(role, cfg, messages, out, remaining_wall, tools):
        captured.append({'role': role, 'cfg': copy.deepcopy(cfg), 'messages': copy.deepcopy(messages),
                         'tools': copy.deepcopy(tools)})
        if role == 'focus' and summary == 'transport_error':
            raise OSError('synthetic transport loss')
        if role == 'focus' and summary == 'unknown':
            response = {'status': 'error', 'input_tokens': None, 'output_tokens': None,
                        'wall_seconds': 1, 'error_kind': 'request_or_response', 'timeout_scope': None}
        else:
            counter = count_agent if role == 'agent' else count_summary
            count = counter(cfg, messages, tools, 60)['input_tokens']
            message = ({'role': 'assistant', 'content': 'synthetic reply'} if role == 'agent'
                       else copy.deepcopy(VALID))
            if role == 'focus' and summary == 'invalid':
                message['content'] = '{}'
            response = {'status': 'ok', 'input_tokens': count, 'output_tokens': 20,
                        'wall_seconds': 1, 'done_reason': 'stop', 'cached_input_tokens': 0,
                        'message': message,
                        'timings': {'cache_n': 0, 'prompt_n': count, 'predicted_n': 20,
                                    'prompt_ms': 1, 'predicted_ms': 1}}
        (out / 'response.json').write_text(json.dumps(response))
        return response

    errors = []
    # Counting at the trigger, normal agent admission and summary admission all
    # use their real code paths. Only transport I/O is mocked.
    with patch('single_checkpoint_inference.count_agent_input', side_effect=count_agent), \
         patch('single_checkpoint_inference.count_summary_input', side_effect=count_summary), \
         patch('tool_choice_residual.count_input', side_effect=count_agent), \
         patch('fixed_budget_residual.count_input', side_effect=count_summary), \
         patch('tool_choice_residual.model_call', side_effect=lambda *a: send('agent', *a)), \
         patch('fixed_budget_residual.model_call', side_effect=lambda *a: send('focus', *a)):
        for number in range(1, steps + 1):
            messages, _ = conv.for_model()
            try:
                message = infer.call('agent', messages, [{'type': 'function', 'function': {'name': 'run_python'}}])
            except Exception as error:
                errors.append(error)
                break
            conv.append(message, [{'id': f's{number}', 'action': None,
                                   'observation': {'not_executed': True}}])
    result = {'infer': infer, 'captured': captured, 'errors': errors,
              'archive': conv.messages(), 'folder': folder, 'output': output}
    return result


class CheckpointCostTests(unittest.TestCase):
    def run_fixture(self, **kwargs):
        value = fixture(**kwargs)
        self.addCleanup(value['folder'].cleanup)
        return value

    def test_one_shared_ledger_includes_summary_cost_and_keeps_agent_seed_schedule(self):
        result = self.run_fixture()
        infer = result['infer']
        self.assertEqual(result['errors'], [])
        self.assertEqual([c['role'] for c in infer.calls], ['agent'] * 3 + ['focus'] + ['agent'] * 2)
        self.assertEqual([c['cfg']['seed'] for c in result['captured'] if c['role'] == 'agent'],
                         [57, 58, 59, 60, 61])
        self.assertEqual(infer.tokens, sum(c['input_tokens'] + c['output_tokens'] for c in infer.calls))
        self.assertEqual(infer.snapshots[3]['measured_state']['used']['model_calls'], 4)
        self.assertEqual(infer.snapshots[3]['measured_state']['used']['logical_input_plus_output_tokens'],
                         sum(c['input_tokens'] + c['output_tokens'] for c in infer.calls[:4]))
        self.assertTrue(infer.checkpoint.proposal)
        self.assertEqual(sum(m['role'] == 'assistant' for m in result['archive']), 5)
        self.assertEqual([c['tools'] for c in result['captured'] if c['role'] == 'focus'], [[]])

    def test_full_and_checkpoint_have_identical_inputs_before_opportunity(self):
        a = self.run_fixture(policy='full')
        b = self.run_fixture()
        self.assertEqual([c['messages'] for c in a['captured'][:3]],
                         [c['messages'] for c in b['captured'][:3]])
        self.assertFalse(a['captured'][0]['cfg']['cache_prompt'])
        self.assertTrue(all(c['role'] == 'agent' for c in a['captured']))
        self.assertEqual(a['infer'].controls[-1]['status'], 'full_control_retains_archive')

    def test_invalid_and_nonshrinking_summary_are_charged_once_without_deleting_history(self):
        for options, expected in [({'summary': 'invalid'}, 'invalid_summary_keep_original'),
                                  ({'not_shorter': True}, 'not_shorter_keep_original')]:
            result = self.run_fixture(**options)
            self.assertEqual(result['errors'], [])
            infer = result['infer']
            self.assertIsNone(infer.checkpoint.proposal)
            self.assertEqual(infer.controls[-1]['status'], expected)
            self.assertEqual(infer.controls[-1]['summary_known_tokens'], 10020)
            self.assertEqual(sum(c['role'] == 'focus' for c in infer.calls), 1)
            self.assertFalse(infer.projections[-1]['checkpoint_used'])

    def test_summary_screening_cannot_obtain_a_separate_token_or_call_allowance(self):
        for options, expected in [({'token_limit': 50000}, 'insufficient_shared_token_budget'),
                                  ({'call_limit': 4}, 'insufficient_shared_call_budget')]:
            result = self.run_fixture(steps=4, **options)
            self.assertEqual(result['errors'], [])
            self.assertEqual(result['infer'].controls[-1]['status'], expected)
            self.assertEqual(len(result['infer'].calls), 4)
            self.assertTrue(all(c['role'] == 'agent' for c in result['captured']))

    def test_unknown_summary_usage_and_missing_terminal_response_stop_before_next_action(self):
        for mode in ('unknown', 'transport_error'):
            result = self.run_fixture(summary=mode)
            infer = result['infer']
            self.assertEqual(len(result['errors']), 1)
            self.assertEqual([c['role'] for c in result['captured']], ['agent'] * 3 + ['focus'])
            self.assertEqual(infer.controls[-1]['unknown_usage_calls'], 1)
            self.assertEqual(infer.controls[-1]['dispatched_without_terminal_usage'],
                             int(mode == 'transport_error'))
            attempts = attempt_usage(infer)
            self.assertEqual(len(attempts), 4)
            self.assertEqual(attempts[-1]['role'], 'focus')
            self.assertEqual(attempts[-1]['status'], 'error')
            self.assertIsNone(attempts[-1]['input_tokens'])
            with self.assertRaisesRegex(ValueError, 'already_stopped'):
                infer.call('agent', [], [])

    def test_runtime_configuration_change_is_rejected(self):
        result = self.run_fixture(steps=1)
        infer = result['infer']
        infer.config['max_total_tokens'] += 1
        with self.assertRaisesRegex(ValueError, 'fixed_checkpoint_config_changed'):
            infer.call('agent', [], [])


if __name__ == '__main__':
    unittest.main()
