import copy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from fallback_output_replay import CASES, COUNTS, FIXED, equality_summary, request_for, reserve_tokens, schedule, validate_plan
from probe_fallback_output import previous_session_closed


def plan():
    return {**FIXED, 'schedule': schedule(), 'cases': [dict(id=c, expected_input_tokens=n)
            for c, n in zip(CASES, COUNTS)], 'reserved_total_tokens': 481671}


def rows():
    hashes = dict(zip(CASES, ('A', 'B', 'C', 'C', 'A', 'D')))
    return [{**r, 'status': 'ok', 'has_public_output': True, 'complete_generation': True,
             'public_output_sha256': hashes[r['case']], 'opaque_message_sha256': hashes[r['case']]}
            for r in schedule()]


class FallbackOutputTests(unittest.TestCase):
    def test_changes_only_cache_flag_without_mutating_archived_input(self):
        original = dict(model='minimax-m3-iq4xs', seed=70, max_tokens=4096,
            stream=False, cache_prompt=True, temperature=1.0,
            messages=[{'role': 'assistant', 'content': 'opaque saved text',
                       'reasoning_content': 'opaque saved field'}], tools=[{'type': 'function'}])
        before = copy.deepcopy(original)
        changed = request_for(original)
        self.assertEqual(original, before)
        self.assertEqual(changed, {**original, 'cache_prompt': False})
        changed['messages'][0]['content'] = 'different'
        self.assertEqual(original, before)

    def test_refuses_changed_source_seed_or_output_budget(self):
        original = dict(model='minimax-m3-iq4xs', seed=70, max_tokens=4096,
                        stream=False, cache_prompt=True, temperature=1.0)
        for key, value in [('seed', 71), ('max_tokens', 8192), ('temperature', 0),
                           ('cache_prompt', False), ('stream', True), ('model', 'other')]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                request_for({**original, key: value})

    def test_all_six_cases_three_times_and_complete_token_reservation(self):
        self.assertEqual(len(schedule()), 18)
        for case in CASES:
            self.assertEqual([r['repetition'] for r in schedule() if r['case'] == case], [1, 2, 3])
        self.assertEqual(reserve_tokens(COUNTS), 481671)
        validate_plan(plan())
        for counts in (COUNTS[:-1], (True, *COUNTS[1:]), tuple(float(v) for v in COUNTS), tuple(v+1 for v in COUNTS)):
            with self.assertRaises(ValueError):
                reserve_tokens(counts)
        for key, value in [('max_calls', 19), ('seed', 71), ('cache_prompt', True), ('automatic_retries', 1)]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_plan({**plan(), key: value})

    def test_reports_all_fifteen_cross_contrasts_without_independent_sample_claim(self):
        result = equality_summary(rows())
        self.assertEqual(len(result['cross']), 15)
        self.assertTrue(result['stable_complete_public_outputs_and_equivalent_input_controls'])
        self.assertTrue(result['original_fallback_ID_pair_public_outputs_differ'])
        self.assertEqual(sum(p['compared_pairs'] for p in result['cross']), 135)
        self.assertTrue(all(not p['pairs_are_independent_samples'] for p in result['cross']))
        self.assertFalse(result['task_quality_measured'])
        self.assertFalse(result['whole_task_savings_measured'])

    def test_does_not_select_only_matching_repeats_or_ignore_controls(self):
        for case in (CASES[0], CASES[2], CASES[4]):
            changed = rows()
            next(r for r in changed if r['case'] == case)['public_output_sha256'] = 'unstable'
            result = equality_summary(changed)
            self.assertFalse(result['stable_complete_public_outputs_and_equivalent_input_controls'])
            self.assertIsNone(result['original_fallback_ID_pair_public_outputs_differ'])

    def test_unknown_incomplete_or_empty_outputs_preclude_supported_comparison(self):
        for update in ({'status': 'error'}, {'complete_generation': False}, {'has_public_output': False}):
            changed = rows(); changed[-1].update(update)
            result = equality_summary(changed)
            self.assertIsNone(result['original_fallback_ID_pair_public_outputs_differ'])
        self.assertIsNone(equality_summary(rows()[:-1])['original_fallback_ID_pair_public_outputs_differ'])
        changed = rows(); changed[-1]['status'] = 'unattempted'
        self.assertEqual(equality_summary(changed)['within'][CASES[4]]['attempted'], 2)

    def test_refuses_duplicate_or_reassigned_replays(self):
        with self.assertRaises(ValueError):
            equality_summary(rows() + rows()[:1])
        changed = rows(); changed[0]['case'] = CASES[1]
        with self.assertRaises(ValueError):
            equality_summary(changed)

    def test_running_previous_pipeline_cannot_allocate_next_session(self):
        with patch('probe_fallback_output.read', side_effect=[
            {'status': 'batch', 'server_stopped': False}, {'status': 'ready'}]):
            with self.assertRaisesRegex(ValueError, 'must_be_closed'):
                previous_session_closed(Path('/synthetic'), plan())


if __name__ == '__main__':
    unittest.main()
