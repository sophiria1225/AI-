import copy
import sys
import tempfile
import unittest
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from export_robustness import inspect_program, static_case, transformed_cases
from evaluate_export_robustness import evaluate


def case():
    def song(sid, title):
        return {'song_id': sid, 'title': title, 'artists': [{'name': 'Artist'}]}
    return {'instruction': 'Export the union once.', 'observations': [
        {'span_id': 'a', 'api': 'spotify__show_song_library', 'result': [song(1, 'One')]},
        {'span_id': 'b', 'api': 'spotify__show_album_library', 'result': [{'song_ids': [1, 2]}]},
        {'span_id': 'c', 'api': 'spotify__show_playlist_library', 'result': [{'song_ids': [2, 3]}]},
        {'span_id': 'd', 'api': 'spotify__show_song', 'result': song(2, 'Two')},
        {'span_id': 'e', 'api': 'spotify__show_song', 'result': song(3, 'Three')}]}


PROGRAM = '''wanted = set()
known = {}
for obs in observations:
    api = obs['api']
    value = obs['result']
    if api == 'spotify__show_song_library':
        for song in value:
            wanted.add(song['song_id'])
            known[song['song_id']] = song
    if api == 'spotify__show_album_library' or api == 'spotify__show_playlist_library':
        for group in value:
            wanted.update(group['song_ids'])
    if api == 'spotify__show_song':
        known[value['song_id']] = value
rows = []
for sid in sorted(wanted):
    song = known[sid]
    rows.append([song['title'], '|'.join([a['name'] for a in song['artists']])])
result = csv_text(rows, ['Title', 'Artists'])
'''


class RobustnessTests(unittest.TestCase):
    def test_correct_transformer_passes_without_input_mutation(self):
        original = case()
        saved = copy.deepcopy(original)
        results = inspect_program(PROGRAM, original)
        self.assertEqual(len(results), 4)
        self.assertTrue(all(r['complete_export'] for r in results))
        self.assertEqual(original, saved)

    def test_nominally_correct_all_metadata_program_fails_decoy(self):
        source = PROGRAM.replace('for sid in sorted(wanted):', 'for sid in sorted(known):')
        results = {r['transformation']: r for r in inspect_program(source, case())}
        self.assertFalse(results['irrelevant_metadata']['complete_export'])
        self.assertEqual(results['irrelevant_metadata']['extra'], 1)
        self.assertTrue(results['rename_title']['complete_export'])

    def test_hardcoded_csv_fails_rename_but_not_invariance(self):
        source = "result = 'Title,Artists\\nOne,Artist\\nTwo,Artist\\nThree,Artist\\n'"
        results = {r['transformation']: r for r in inspect_program(source, case())}
        self.assertFalse(results['rename_title']['complete_export'])
        self.assertEqual((results['rename_title']['missing'], results['rename_title']['extra']), (1, 1))
        self.assertTrue(results['reverse_order']['complete_export'])

    def test_conflicting_metadata_not_treated_as_static(self):
        value = case()
        row = copy.deepcopy(value['observations'][-1])
        row['result']['title'] = 'Changed'
        value['observations'].append(row)
        with self.assertRaisesRegex(ValueError, 'metadata changed'):
            static_case(value)

    def test_transformations_do_not_rewrite_original_expected_result(self):
        value = case()
        _, _, before = static_case(value)
        transformed = transformed_cases(value)
        self.assertEqual([len(e) for _, _, e in transformed], [3, 3, 3, 3])
        for _, _, expected in transformed[:3]:
            self.assertEqual(expected, before)
        self.assertEqual(len(before - transformed[-1][2]), 1)

    def test_execution_error_is_reported_for_every_transform(self):
        rows = inspect_program('import os', case())
        self.assertEqual(len(rows), 4)
        self.assertTrue(all(not r['executed'] and r['error_type'] == 'DataProgramError' for r in rows))

    def test_running_batch_cannot_open_program_or_primary_result(self):
        with tempfile.TemporaryDirectory() as name:
            path = Path(name)
            (path/'status.json').write_text(json.dumps({'status': 'running'}))
            with self.assertRaisesRegex(ValueError, 'all fixed generations'):
                evaluate(path, path/'absent_primary', path/'absent_freeze', path/'absent_plan')


if __name__ == '__main__':
    unittest.main()
