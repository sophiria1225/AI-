import copy
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from read_view_input_footprint import (CONTENT_FIELDS, EXPECTED_API, POLICIES,
    REPRESENTATIONS, compare_boundaries, reconstruct, validate_inventory)


def fixture(policy):
    programs = [f'raise AssertionError("saved source must never run: {i}")' for i in range(6)]
    evidences, rows, metadata = [], [], []
    for n, count in enumerate(EXPECTED_API[policy], 1):
        result = dict(status='ok', stdout=f'printed fact {n}', stdout_truncated=False,
                      api_requests=count, declared_complete=False, unknown_effects=False, wall_seconds=.1)
        evidence = dict(result=result, original_generated_source_unchanged=True,
                        control_requests=3, control_request_bytes=100, control_reply_bytes=200)
        evidences.append(evidence)
        metadata.append(dict(**{k: v for k, v in result.items() if k != 'stdout'}, number=n,
            stdout_sha256=hashlib.sha256(result['stdout'].encode()).hexdigest(),
            **{k: evidence[k] for k in ('control_requests', 'control_request_bytes', 'control_reply_bytes')}))
        for _ in range(count):
            rows.append(dict(action=dict(name='spotify__show_song', arguments='{"song_id":1}'),
                observation={'observation': 'PRIVATE_INNER_VALUE', 'declared_complete': False},
                api_request_sent=True, new_tools=[]))
    public = dict(policy=policy, status='complete', programs=metadata,
                  api_rows_recorded=len(rows), api_names=dict(Counter(r['action']['name'] for r in rows)))
    return programs, evidences, rows, public


def build(policy, view='harness', *, data=None, page_limit=24000):
    return reconstruct(policy, view, *(data or fixture(policy)), prompt='shared interface',
                       public_task={'instruction': 'synthetic'}, page_limit=page_limit)


class ReadViewInputFootprintTests(unittest.TestCase):
    def test_saved_programs_and_bridge_are_never_executed(self):
        with patch('container_api_python.run_program', side_effect=AssertionError('execution forbidden')):
            for policy in POLICIES:
                result = build(policy)
                self.assertEqual(len(result), 6)
                self.assertEqual(result[-1]['original_cumulative_API_requests'], sum(EXPECTED_API[policy]))

    def test_all_six_boundaries_include_terminal_without_calling_it_usage(self):
        rows = build('eager')
        self.assertEqual([r['after_program'] for r in rows], list(range(1, 7)))
        self.assertEqual([r['includes_terminal_boundary'] for r in rows], [False] * 5 + [True])
        self.assertNotIn('total_tokens', rows[-1])

    def test_raw_api_values_remain_in_host_archive(self):
        for policy in POLICIES:
            result = build(policy)
            encoded = json.dumps(result)
            self.assertNotIn('PRIVATE_INNER_VALUE', encoded)
            self.assertIn('printed fact 6', encoded)
            last = json.loads(result[-1]['messages'][-1]['content'])
            self.assertEqual(len(last['observation']['api_receipts']), EXPECTED_API[policy][-1])

    def test_production_view_retains_actual_metadata_and_span_ids(self):
        eager, deferred = build('eager'), build('deferred')
        self.assertEqual(eager[0]['messages'], deferred[0]['messages'])
        self.assertNotEqual(eager[1]['messages'], deferred[1]['messages'])
        a = json.loads(eager[1]['messages'][-1]['content'])
        b = json.loads(deferred[1]['messages'][-1]['content'])
        self.assertEqual(a['span_id'], 's9')
        self.assertEqual(b['span_id'], 's8')
        self.assertEqual((a['observation']['api_requests'], b['observation']['api_requests']), (1, 0))

    def test_attribution_removes_only_declared_metadata_and_canonicalizes_outer_ids(self):
        eager = build('eager', 'content_attribution')
        deferred = build('deferred', 'content_attribution')
        self.assertEqual([r['messages'] for r in eager], [r['messages'] for r in deferred])
        for n, row in enumerate(eager, 1):
            outer = json.loads(row['messages'][-1]['content'])
            self.assertEqual(outer['span_id'], f'program_{n}')
            self.assertEqual(set(outer['observation']), set(CONTENT_FIELDS))
            self.assertEqual(outer['observation']['stdout'], f'printed fact {n}')
            self.assertIsNone(outer['observation']['error'])

    def test_inputs_are_not_mutated(self):
        data = fixture('deferred')
        before = copy.deepcopy(data)
        build('deferred', data=data)
        build('deferred', 'content_attribution', data=data)
        self.assertEqual(data, before)

    def test_missing_program_or_extra_receipt_is_rejected(self):
        for kind in ('missing', 'extra'):
            data = fixture('eager')
            if kind == 'missing': data[1].pop()
            else: data[2].append(copy.deepcopy(data[2][-1]))
            with self.assertRaises(ValueError): build('eager', data=data)

    def test_changed_stdout_control_count_or_actual_api_count_is_rejected(self):
        for key, value in (('stdout', 'changed'), ('api_requests', 0), ('wall_seconds', .2)):
            data = fixture('eager')
            data[1][0]['result'][key] = value
            with self.assertRaises(ValueError): build('eager', data=data)
        data = fixture('eager'); data[1][0]['control_requests'] += 1
        with self.assertRaises(ValueError): build('eager', data=data)

    def test_uncertain_or_unsent_api_receipt_is_rejected(self):
        for key, value in (('api_request_sent', False), ('effects_unknown', True)):
            data = fixture('eager'); data[2][0][key] = value
            with self.assertRaises(ValueError): validate_inventory('eager', *data)

    def test_failed_or_truncated_program_is_not_silently_dropped(self):
        for key, value in (('status', 'error'), ('stdout_truncated', True), ('unknown_effects', True)):
            data = fixture('deferred'); data[1][3]['result'][key] = value
            with self.assertRaises(ValueError): build('deferred', data=data)

    def test_existing_paging_is_retained(self):
        rows = build('eager', page_limit=50)
        self.assertEqual(rows[-1]['formatting']['paged_spans'], 6)
        self.assertIn('first_page', json.loads(rows[-1]['messages'][-1]['content']))

    def test_comparison_requires_all_24_counts_and_keeps_each_boundary(self):
        rows = []
        for policy in POLICIES:
            for view in REPRESENTATIONS:
                for row in build(policy, view):
                    rows.append(dict(**{k: v for k, v in row.items() if k != 'messages'},
                        policy=policy, representation=view, input_tokens=100,
                        prompt_sha256=row['messages_sha256'], tokens_sha256=row['messages_sha256'],
                        session_controls_sha256='shared', parsed_non_message_parameters_sha256='shared'))
        compared = compare_boundaries(rows)
        self.assertEqual(len(compared), 12)
        self.assertTrue(all(r['messages_equal'] for r in compared if r['representation'] == 'content_attribution'))
        with self.assertRaises(ValueError): compare_boundaries(rows[:-1])
        bad = copy.deepcopy(rows); bad[-1]['input_tokens'] = None
        with self.assertRaises(ValueError): compare_boundaries(bad)


if __name__ == '__main__':
    unittest.main()
