import copy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import test_native_memory_view as fixtures
from native_focus_memory import FocusMemory
from run_context_comparison import BudgetStop


class Playback:
    def __init__(self, drafts):
        self.drafts, self.calls, self.tokens, self.inputs = iter(drafts), [], 0, []

    def call(self, role, messages, tools):
        draft = next(self.drafts)
        if isinstance(draft, Exception):
            raise draft
        self.inputs.append((role, messages, tools))
        self.calls.append({'id': f'call_{len(self.calls)+1:03d}', 'role': role,
                           'status': 'ok', 'input_tokens': 100, 'output_tokens': 10})
        self.tokens += 110
        return {'tool_calls': [{'function': {'name': 'submit_selection',
                                             'arguments': json.dumps(draft)}}]}


class NativeFocusControls(unittest.TestCase):
    config = {'focus_rollouts': 3, 'focus_threshold': 0.3,
              'history_budget_tokens': 4096, 'observation_page_characters': 24000}

    def draft(self, ids):
        return {'steps': [{'plan': 'continue', 'depends_on': ids}], 'rescued': [], 'rescue_reason': ''}

    def run_memory(self, drafts, count=lambda s: 5000):
        memory, infer = FocusMemory(), Playback(drafts)
        conversation = fixtures.NativeMemoryViewControls().example()
        archived = copy.deepcopy(conversation.messages()); saved = []
        messages, result = memory.prepare(conversation, {'instruction': 'fixture'},
            [{'type': 'function', 'function': {'name': 'public_fixture'}}], infer, count,
            self.config, lambda events: saved.append(events))
        self.assertEqual(conversation.messages(), archived)
        return memory, infer, messages, result, saved

    def test_certified_full_retention_skips_only_unneeded_drafts(self):
        m, infer, _, result, _ = self.run_memory([self.draft(['s1', 's2', 's3', 's4'])])
        self.assertEqual(len(infer.calls), 1)
        self.assertTrue(m.events[0]['early_all_retained'])
        self.assertEqual(m.events[0]['known_tokens'], 110)
        self.assertFalse(result['memory_note_added'])
        payload = json.loads(infer.inputs[0][1][1]['content'])
        self.assertEqual(payload['available_api_schemas'][0]['function']['name'], 'public_fixture')
        self.assertEqual(infer.inputs[0][2][0]['function']['name'], 'submit_selection')

    def test_three_draft_union_is_closed_over_original_response_groups(self):
        m, infer, _, result, _ = self.run_memory([self.draft(['s1'])] * 3)
        self.assertEqual(len(infer.calls), 3)
        self.assertEqual(result['requested_span_ids'], ['s1'])
        self.assertEqual(m.selected, ['s1', 's2'])
        self.assertEqual(result['retained_turns'], 1)
        self.assertEqual(m.events[0]['known_tokens'], 330)

    def test_invalid_draft_preserves_original_and_counts_failed_generation(self):
        m, infer, _, result, saved = self.run_memory([self.draft(['unknown'])])
        self.assertEqual(m.events[0]['status'], 'invalid_keep_original')
        self.assertEqual(m.selected, ['s1', 's2', 's3', 's4'])
        self.assertEqual(len(infer.calls), 1)
        self.assertFalse(result['memory_note_added'])
        self.assertEqual(saved[-1][0]['known_tokens'], 110)

    def test_no_generation_under_trigger_and_aborted_work_is_saved(self):
        m, infer, _, _, _ = self.run_memory([], count=lambda s: 10)
        self.assertEqual(infer.calls, [])
        self.assertEqual(m.events, [])
        m, infer = FocusMemory(), Playback([self.draft(['s1']), BudgetStop('budget')])
        saved = []
        with self.assertRaises(BudgetStop):
            m.prepare(fixtures.NativeMemoryViewControls().example(), {}, [], infer,
                      lambda s: 5000, self.config, saved.append)
        self.assertEqual(saved[-1][0]['status'], 'aborted')
        self.assertEqual(saved[-1][0]['known_tokens'], 110)
        self.assertEqual(m.selected, ['s1', 's2', 's3', 's4'])

    def test_later_observations_cannot_mutate_an_earlier_selection_record(self):
        conversation = fixtures.NativeMemoryViewControls().example()
        memory, infer = FocusMemory(), Playback([])
        _, old = memory.prepare(conversation, {}, [], infer, lambda s: 1, self.config, lambda e: None)
        frozen = copy.deepcopy(old)
        fn = {'name': 'app__read', 'arguments': '{}'}
        conversation.append({'role': 'assistant', 'content': '', 'tool_calls': [
            {'id': 'c5', 'type': 'function', 'function': fn}]},
            [{'id': 's5', 'assistant': '', 'action': fn, 'observation': {'value': 'new'}}])
        memory.prepare(conversation, {}, [], infer, lambda s: 1, self.config, lambda e: None)
        self.assertEqual(old, frozen)
        self.assertEqual(memory.selected, ['s1', 's2', 's3', 's4', 's5'])


if __name__ == '__main__':
    unittest.main()
