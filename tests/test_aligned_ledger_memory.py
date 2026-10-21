import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from aligned_ledger_memory import AlignedLedgerMemory, aligned_inputs
from ledger_contract import inputs as probe_inputs
from native_ledger_memory import LedgerMemory
from native_memory_view import recorded_turns
from run_context_comparison import BudgetStop
import test_native_ledger_memory as legacy_fixture
import test_native_memory_view as history_fixture


class AlignedLedgerControls(unittest.TestCase):
    config = legacy_fixture.NativeLedgerControls.config

    def draft(self, source='s1', status='pending'):
        return legacy_fixture.NativeLedgerControls().draft(source, status)

    def test_runtime_input_is_exactly_the_calibrated_p17_input(self):
        conv = history_fixture.NativeMemoryViewControls().example()
        spans = {s['id']: s for _, group in recorded_turns(conv) for s in group}
        case = {'task': {'instruction': 'fixture'}, 'spans': spans, 'tools': []}
        expected, tool = probe_inputs(case, 'aligned', 24000)
        actual, contract = aligned_inputs(case['task'], spans, list(spans), None, [], 24000)
        self.assertEqual(actual, expected)
        self.assertEqual(contract.tool(), tool)

    def test_same_retention_costs_and_original_history_for_unchanged_valid_draft(self):
        conv = history_fixture.NativeMemoryViewControls().example(); before = copy.deepcopy(conv.messages())
        legacy, corrected = LedgerMemory(), AlignedLedgerMemory()
        a, b = legacy_fixture.Playback([self.draft()]), legacy_fixture.Playback([self.draft()])
        old_messages, old_info = legacy.prepare(conv, {}, [], a, lambda _: 5000, self.config, lambda _: None)
        new_messages, new_info = corrected.prepare(conv, {}, [], b, lambda _: 5000, self.config, lambda _: None)
        self.assertEqual(old_messages, new_messages)
        self.assertEqual({k: v for k, v in old_info.items() if k != 'selection_rule'},
                         {k: v for k, v in new_info.items() if k != 'selection_rule'})
        self.assertEqual(a.tokens, b.tokens)
        self.assertEqual(conv.messages(), before)
        self.assertEqual(corrected.selected, ['s3', 's4'])
        self.assertFalse(corrected.events[-1]['semantics_verified'])

    def test_previous_sources_survive_but_uncited_archived_sources_are_not_registered(self):
        memory = AlignedLedgerMemory()
        infer = legacy_fixture.Playback([self.draft(), self.draft(), self.draft('s2')])
        conv = history_fixture.NativeMemoryViewControls().example()
        for _ in range(3):
            memory.prepare(conv, {}, [], infer, lambda _: 5000, self.config, lambda _: None)
        allowed = infer.inputs[1][2][0]['function']['parameters']['properties']['items']['items']['properties']['source_ids']['items']['enum']
        self.assertEqual(set(allowed), {'task', 's1', 's3', 's4'})
        self.assertNotIn('s2', allowed)
        self.assertEqual([e['status'] for e in memory.events], ['ok', 'ok', 'invalid_keep_original'])
        self.assertEqual(memory.ledger, self.draft())
        self.assertEqual(infer.tokens, 330)

    def test_requirement_reference_is_valid_but_not_a_semantic_completion_certificate(self):
        memory, infer = AlignedLedgerMemory(), legacy_fixture.Playback([self.draft('task', 'done')])
        memory.prepare(history_fixture.NativeMemoryViewControls().example(), {}, [], infer, lambda _: 5000,
                       self.config, lambda _: None)
        # The structural validator deliberately does not pretend to certify truth.
        self.assertEqual(memory.events[-1]['status'], 'ok')
        self.assertFalse(memory.events[-1]['semantics_verified'])
        self.assertEqual(memory.ledger['items'][0]['source_ids'], ['task'])

    def test_invalid_outputs_keep_history_and_are_not_retried_or_free(self):
        empty, extra, unknown = self.draft(), self.draft(), self.draft('invented')
        empty['items'][0]['source_ids'] = []
        extra['certainty'] = 1
        for value in (empty, extra, unknown):
            with self.subTest(value=value):
                memory, infer = AlignedLedgerMemory(), legacy_fixture.Playback([value])
                conv = history_fixture.NativeMemoryViewControls().example()
                messages, _ = memory.prepare(conv, {}, [], infer, lambda _: 5000, self.config, lambda _: None)
                self.assertEqual(messages, conv.for_model()[0])
                self.assertIsNone(memory.ledger)
                self.assertEqual(memory.events[-1]['status'], 'invalid_keep_original')
                self.assertEqual(memory.events[-1]['known_tokens'], 110)
                self.assertEqual(len(infer.calls), 1)

    def test_no_generation_below_threshold_and_unknown_generation_cost_is_retained(self):
        memory, infer = AlignedLedgerMemory(), legacy_fixture.Playback([])
        conv = history_fixture.NativeMemoryViewControls().example(); saved = []
        messages, _ = memory.prepare(conv, {}, [], infer, lambda _: 10, self.config, saved.append)
        self.assertEqual(messages, conv.for_model()[0])
        self.assertEqual(infer.calls, [])

        def unknown(*_):
            infer.calls.append({'id': 'call_001', 'role': 'ledger', 'status': 'unknown'})
            raise BudgetStop('unknown_usage')
        infer.call = unknown
        with self.assertRaises(BudgetStop):
            memory.prepare(conv, {}, [], infer, lambda _: 5000, self.config, saved.append)
        self.assertEqual(saved[-1][0]['status'], 'aborted')
        self.assertEqual(saved[-1][0]['unknown_usage_calls'], 1)
        self.assertIsNone(memory.ledger)


if __name__ == '__main__':
    unittest.main()
