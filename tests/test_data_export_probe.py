import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from data_export_probe import extract_case, inputs, schedule
from evaluate_data_export_probe import check_csv, expected_from_observations, evaluate


class ExportProbeTests(unittest.TestCase):
    def test_input_excludes_auth_export_later_data_and_assistant(self):
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp)
            entries = [('s1', 'spotify__login', {'access_token': 'AUTH_SENTINEL'}),
                       ('s2', 'spotify__show_song_library', []),
                       ('s3', 'file_system__create_file', {'content': 'CSV_SENTINEL'}),
                       ('s4', 'spotify__show_song', {'title': 'LATE_SENTINEL'})]
            spans = {sid: {'action': {'name': api}, 'assistant': 'REASONING_SENTINEL',
                           'observation': {'observation': json.dumps(value)}} for sid, api, value in entries}
            (p/'spans.json').write_text(json.dumps(spans))
            (p/'events.json').write_text(json.dumps([{'span_id': sid, 'api_request_sent': True}
                                                   for sid, _, _ in entries]))
            (p/'public_task.json').write_text(json.dumps({'instruction': 'Export the requested data.'}))
            case, manifest = extract_case(p)
            value = json.dumps(case)
            for forbidden in ('AUTH_SENTINEL', 'CSV_SENTINEL', 'LATE_SENTINEL', 'REASONING_SENTINEL'):
                self.assertNotIn(forbidden, value)
            self.assertEqual(manifest['cut_before_span'], 's3')
            self.assertEqual(len(case['observations']), 1)
            self.assertEqual(inputs(case, 'literal_csv')[0][1], inputs(case, 'data_program')[0][1])

    def test_both_variants_once_per_seed_in_fixed_order(self):
        plan = {'run_id': 'P20_01', 'variants': ['literal_csv', 'data_program'],
                'seeds': [51, 52, 53], 'max_calls': 6}
        rows = schedule(plan)
        self.assertEqual(len(rows), 6)
        for seed in plan['seeds']:
            self.assertEqual({r['variant'] for r in rows if r['seed'] == seed}, set(plan['variants']))
        with self.assertRaises(ValueError):
            schedule(dict(plan, seeds=[51, 52, 54]))

    def test_csv_checks_missing_extra_duplicates_and_artist_order(self):
        expected = {('A, song', ('First', 'Second')), ('Other', ('Third',))}
        good = 'Title,Artists\n"A, song",Second|First\nOther,Third\n'
        self.assertTrue(check_csv(good, expected)['complete_export'])
        r = check_csv('Title,Artists\nOther,Third\nOther,Third\nExtra,Fourth\n', expected)
        self.assertEqual((r['missing'], r['extra'], r['duplicates']), (1, 1, 1))
        self.assertFalse(r['complete_export'])
        with self.assertRaises(ValueError):
            check_csv('Title,Artists\nOther,Third,extra\n', expected)

    def test_expected_set_requires_observed_metadata_and_unambiguous_fields(self):
        case = {'observations': [
            {'api': 'spotify__show_album_library', 'result': [{'song_ids': [1, 2]}]},
            {'api': 'spotify__show_song', 'result': {'song_id': 1, 'title': 'A', 'artists': [{'name': 'B'}]}}]}
        with self.assertRaisesRegex(ValueError, 'not all source metadata'):
            expected_from_observations(case)
        case['observations'].append({'api': 'spotify__show_song', 'result':
                                     {'song_id': 2, 'title': 'A', 'artists': [{'name': 'B'}]}})
        with self.assertRaisesRegex(ValueError, 'ambiguous exported fields'):
            expected_from_observations(case)

    def test_incomplete_batch_not_evaluated(self):
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp)
            (p/'status.json').write_text(json.dumps({'status': 'running'}))
            with self.assertRaisesRegex(ValueError, 'all fixed generations'):
                evaluate(p)
            self.assertFalse((p/'evaluation_v01').exists())


if __name__ == '__main__':
    unittest.main()
