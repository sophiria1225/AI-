import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from analyze_p18_public_evidence import song_coverage, recorded_operations


def fixture(csv_text):
    rows = [{'song_id': 1, 'title': 'First', 'artists': [{'name': 'A'}]},
            {'song_id': 2, 'title': 'Second', 'artists': [{'name': 'B'}]}]
    entries = [('spotify__show_song_library', {}, rows),
               ('spotify__show_album_library', {}, [{'song_ids': [1, 2]}]),
               ('spotify__show_playlist_library', {}, [{'song_ids': [2]}]),
               ('file_system__create_file', {'content': csv_text}, {'message': 'created'}),
               ('file_system__show_file', {}, {'content': csv_text})]
    return {f's{i}': {'id': f's{i}', 'action': {'name': name, 'arguments': json.dumps(args)},
                     'observation': {'observation': json.dumps(obs)}}
            for i, (name, args, obs) in enumerate(entries, 1)}


class EvidenceDiagnosisTests(unittest.TestCase):
    def test_union_deduplicates_sources_but_detects_one_export_omission(self):
        r = song_coverage(fixture('Title,Artists\nFirst,A\n'))
        self.assertEqual(r['union_unique_ids'], 2)
        self.assertEqual(r['missing_known_pairs'], 1)
        self.assertEqual(r['missing_id_membership_counts'], {'song': 1, 'album': 1, 'playlist': 1})
        self.assertNotIn('Second', json.dumps(r))

    def test_extra_and_duplicate_rows_not_mistaken_for_full_coverage(self):
        r = song_coverage(fixture('Title,Artists\nFirst,A\nFirst,A\nUnknown,C\n'))
        self.assertEqual(r['export_rows'], 3)
        self.assertEqual(r['export_unique_pairs'], 2)
        self.assertEqual(r['missing_known_pairs'], 1)
        self.assertEqual(r['unmatched_export_pairs'], 1)

    def test_reject_changed_reread_and_missing_metadata(self):
        s = fixture('Title,Artists\nFirst,A\nSecond,B\n')
        s['s5']['observation']['observation'] = json.dumps({'content': 'changed'})
        with self.assertRaisesRegex(ValueError, 'reread differs'):
            song_coverage(s)
        s = fixture('Title,Artists\nFirst,A\nSecond,B\n')
        s['s3']['observation']['observation'] = json.dumps([{'song_ids': [3]}])
        with self.assertRaisesRegex(ValueError, 'known metadata'):
            song_coverage(s)

    def test_unsent_request_does_not_count_as_api_execution(self):
        s = fixture('Title,Artists\nFirst,A\n')
        events = [{'span_id': k, 'api_request_sent': k != 's4'} for k in s]
        r = recorded_operations(s, events)
        self.assertNotIn('file_system__create_file', r['sent_counts'])
        self.assertEqual(r['not_sent_spans'], ['s4'])


if __name__ == '__main__':
    unittest.main()
