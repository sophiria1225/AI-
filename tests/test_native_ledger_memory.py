import copy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import test_native_memory_view as fixtures
from native_ledger_memory import LedgerMemory
from run_context_comparison import BudgetStop


class Playback:
    def __init__(self, drafts):
        self.drafts, self.calls, self.tokens, self.inputs = iter(drafts), [], 0, []

    def call(self, role, messages, tools):
        self.inputs.append((role, messages, tools))
        draft = next(self.drafts)
        if isinstance(draft, Exception):
            raise draft
        self.calls.append({'id': f'call_{len(self.calls)+1:03d}', 'role': role, 'status': 'ok'})
        self.tokens += 110
        return {'tool_calls': [{'function': {'name': 'submit_ledger', 'arguments': json.dumps(draft)}}]}


class NativeLedgerControls(unittest.TestCase):
    config = {'history_budget_tokens': 4096, 'observation_page_characters': 24000,
              'ledger_recent_spans': 2}

    def draft(self, source='s1', status='pending'):
        return {'items': [{'key': 'observed_target', 'requirement': 'public fixture',
                           'status': status, 'source_ids': [source]}],
                'constraints': ['public fixture condition'], 'unresolved': []}

    def test_incremental_ledger_keeps_archived_provenance_without_mutating_history(self):
        memory, infer = LedgerMemory(), Playback([self.draft(), self.draft(status='uncertain')])
        conversation = fixtures.NativeMemoryViewControls().example()
        before = copy.deepcopy(conversation.messages()); saved = []
        first, selection = memory.prepare(conversation, {}, [], infer, lambda _: 5000,
                                          self.config, saved.append)
        frozen = copy.deepcopy(saved[0])
        self.assertEqual(conversation.messages(), before)
        self.assertEqual(infer.tokens, 110)
        self.assertTrue(selection['memory_note_added'])
        self.assertEqual(json.loads(first[-1]['content'])['memory_note']['working_ledger'], self.draft())
        memory.prepare(conversation, {}, [], infer, lambda _: 5000, self.config, saved.append)
        self.assertEqual(saved[0], frozen)
        self.assertEqual(memory.ledger, self.draft(status='uncertain'))
        self.assertFalse(memory.events[-1]['semantics_verified'])
        self.assertEqual(infer.inputs[0][2][0]['function']['name'], 'submit_ledger')

    def test_invented_source_is_rejected_and_generation_is_not_free(self):
        memory, infer = LedgerMemory(), Playback([self.draft(source='unseen')])
        conversation = fixtures.NativeMemoryViewControls().example()
        messages, selection = memory.prepare(conversation, {}, [], infer, lambda _: 5000,
                                              self.config, lambda _: None)
        self.assertEqual(messages, conversation.for_model()[0])
        self.assertFalse(selection['memory_note_added'])
        self.assertIsNone(memory.ledger)
        self.assertEqual(memory.events[0]['status'], 'invalid_keep_original')
        self.assertEqual(memory.events[0]['known_tokens'], 110)

    def test_under_threshold_is_identical_and_aborted_generation_is_recorded(self):
        memory, infer = LedgerMemory(), Playback([BudgetStop('budget')])
        conversation = fixtures.NativeMemoryViewControls().example(); saved = []
        messages, _ = memory.prepare(conversation, {}, [], infer, lambda _: 10,
                                     self.config, saved.append)
        self.assertEqual(messages, conversation.for_model()[0])
        self.assertEqual(infer.calls, [])
        with self.assertRaises(BudgetStop):
            memory.prepare(conversation, {}, [], infer, lambda _: 5000, self.config, saved.append)
        self.assertEqual(saved[-1][0]['status'], 'aborted')
        self.assertEqual(saved[-1][0]['known_tokens'], 0)


if __name__ == '__main__':
    unittest.main()
