import copy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from export_acquisition_scope import analyze
from inspect_export_acquisition_scope import inspect
from test_public_export_evidence import TASK, records

SONG = {'song_id': 1, 'title': 'One', 'artists': [{'name': 'A'}]}
LIB_ARGS = {'access_token': 'synthetic', 'page_index': 0, 'page_limit': 20}


def run(calls):
    return analyze(copy.deepcopy(TASK), *records(calls))


class ExportAcquisitionTests(unittest.TestCase):
    def test_known_csv_columns_do_not_substitute_the_complete_api_response(self):
        listing = {**SONG, 'added_at': '2020-01-01'}
        detail = {**SONG, 'genre': 'Synthetic', 'rating': 4}
        r = run([('spotify__show_song_library', LIB_ARGS, [listing]),
                 ('spotify__show_song', {'song_id': 1}, detail)])
        row = r['requests'][0]
        self.assertTrue(row['task_fields_known_before'])
        self.assertTrue(row['task_fields_unchanged_after'])
        self.assertFalse(row['same_request_response_known_before'])
        self.assertFalse(row['prior_complete_object_equal_after'])
        self.assertEqual(r['preknown_task_fields_without_equal_complete_object'], 1)
        self.assertIsNone(r['measured_savings'])
        self.assertFalse(r['can_remove_any_model_generation_established'])

    def test_exact_prior_request_and_later_full_equality_are_distinct_facts(self):
        r = run([('spotify__show_song', {'song_id': 1}, SONG)] * 2)
        self.assertFalse(r['requests'][0]['same_request_response_known_before'])
        self.assertTrue(r['requests'][1]['same_request_response_known_before'])
        self.assertTrue(r['requests'][1]['same_request_response_equal_after'])
        self.assertEqual(r['same_request_response_matching_after'], 1)

    def test_exact_reuse_does_not_establish_membership_in_requested_sources(self):
        r = run([('spotify__show_song', {'song_id': 1}, SONG)] * 2)
        self.assertTrue(r['requests'][1]['same_request_response_known_before'])
        self.assertFalse(r['requests'][1]['source_membership_observed_before'])
        self.assertFalse(r['requests'][1]['task_fields_known_before'])

    def test_future_receipts_do_not_change_earlier_coverage_or_input_records(self):
        calls = [('spotify__show_song', {'song_id': 1}, SONG),
                 ('spotify__show_song_library', LIB_ARGS, [SONG])]
        spans, events, usage = records(calls); before = copy.deepcopy((spans, events, usage))
        r = analyze(TASK, spans, events, usage)
        self.assertFalse(r['requests'][0]['task_fields_known_before'])
        self.assertEqual((spans, events, usage), before)
        events.reverse()
        with self.assertRaises(ValueError): analyze(TASK, spans, events, usage)

    def test_mixed_generation_is_not_counted_as_fully_covered(self):
        two = {**SONG, 'song_id': 2, 'title': 'Two'}
        spans, events, usage = records([
            ('spotify__show_song_library', LIB_ARGS, [SONG]),
            ('spotify__show_song', {'song_id': 1}, SONG),
            ('spotify__show_song', {'song_id': 2}, two)])
        events[2]['call'] = events[1]['call']; usage = usage[:2]
        r = analyze(TASK, spans, events, usage)
        self.assertEqual([x['task_fields_known_before'] for x in r['requests']], [True, False])
        self.assertFalse(r['model_boundaries'][1]['all_sent_requests_are_show_song_with_preknown_task_fields'])

    def test_mutation_invalidates_further_reuse_candidates(self):
        r = run([('spotify__show_song', {'song_id': 1}, SONG),
                 ('spotify__like_song', {'song_id': 1, 'access_token': 'synthetic'}, {'message': 'ok'}),
                 ('spotify__show_song', {'song_id': 1}, SONG)])
        self.assertFalse(r['requests'][1]['task_fields_known_before'])
        self.assertFalse(r['requests'][1]['same_request_response_known_before'])
        self.assertIn('unhandled_effect:spotify__like_song', r['final_taint_reasons'])

    def test_unknown_current_effect_is_not_used_as_prior_evidence(self):
        spans, events, usage = records([('spotify__show_song', {'song_id': 1}, SONG)] * 3)
        events[1]['effects_unknown'] = True
        r = analyze(TASK, spans, events, usage)
        self.assertTrue(r['requests'][1]['same_request_response_known_before'])
        self.assertFalse(r['requests'][1]['response_supported'])
        self.assertIsNone(r['requests'][1]['same_request_response_equal_after'])
        self.assertFalse(r['requests'][2]['same_request_response_known_before'])

    def test_changed_nonprojected_fields_are_not_hidden_by_equal_csv_columns(self):
        old = {**SONG, 'rating': 1}; new = {**SONG, 'rating': 2}
        r = run([('spotify__show_song', {'song_id': 1}, old),
                 ('spotify__show_song', {'song_id': 1}, new),
                 ('spotify__show_song', {'song_id': 1}, new)])
        self.assertTrue(r['requests'][1]['task_fields_unchanged_after'])
        self.assertFalse(r['requests'][1]['same_request_response_equal_after'])
        self.assertIn('changed_same_request_response', r['final_taint_reasons'])
        self.assertFalse(r['requests'][2]['task_fields_known_before'])

    def test_identity_mismatch_and_failed_receipts_are_not_valid_metadata(self):
        spans, events, usage = records([
            ('spotify__show_song', {'song_id': 2}, SONG),
            ('spotify__show_song', {'song_id': 1}, SONG)])
        spans['s2']['observation']['api_error'] = 'synthetic failed read'
        r = analyze(TASK, spans, events, usage)
        self.assertEqual(r['unsupported_responses'], 2)
        self.assertEqual(r['task_metadata_ids_observed'], 0)

    def test_missing_usage_remains_missing_and_known_cost_is_not_allocated_to_reads(self):
        spans, events, usage = records([('spotify__show_song', {'song_id': 1}, SONG)] * 2)
        usage[1].update(usage_known=False, input_tokens=None, output_tokens=None)
        r = analyze(TASK, spans, events, usage)
        self.assertEqual(r['observed_logical_tokens'], 11)
        self.assertEqual(r['unknown_usage_calls'], 1)
        self.assertIsNone(r['model_boundaries'][1]['known_total_tokens'])

    def test_fixed_scope_and_capacity_are_enforced_before_source_reads(self):
        spans, events, usage = records([('spotify__show_song', {'song_id': 1}, SONG)])
        with self.assertRaises(ValueError): analyze(TASK, spans, events * 4001, usage)
        with self.assertRaises(ValueError): analyze({**TASK, 'instruction': 'Another task'}, spans, events, usage)
        path = Path(__file__).resolve().parents[1] / 'configs/P69_export_acquisition_scope_v01.json'
        plan = json.loads(path.read_text()); plan['max_wall_seconds'] = 121
        with patch('inspect_export_acquisition_scope.read', return_value=plan), patch('inspect_export_acquisition_scope.sha') as source_hash:
            with self.assertRaises(ValueError): inspect(Path('/unused'))
            source_hash.assert_not_called()


if __name__ == '__main__': unittest.main()
