import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from probe_ranked_subset_access import extract_targets, fixed_access_contract


class TargetBoundaryTests(unittest.TestCase):
    def test_page_local_sort_or_extra_filter_cannot_gain_global_contract(self):
        spec = {'app': 'spotify', 'point_api': 'show_song', 'ranked_api': 'search_songs',
                'id_field': 'song_id', 'score_field': 'like_count', 'value_fields': ['title'],
                'query': '', 'sort_by': '-like_count'}
        self.assertTrue(fixed_access_contract(spec, 'snapshot').permits_ranked_stop)
        for update in ({'query': 'music'}, {'genre': 'rock'}, {'sort_by': '+like_count'}):
            with self.assertRaises(ValueError):
                fixed_access_contract({**spec, **update}, 'snapshot')

    def make(self, rows, index=0, limit=20):
        return {'s5': {'action': {'name': 'spotify__show_playlist_library',
            'arguments': json.dumps({'page_index': index, 'page_limit': limit})},
            'observation': {'observation': json.dumps(rows)}}}

    def test_union_comes_only_from_public_collection_preserving_order(self):
        source = self.make([{'song_ids': [4, 1, 2]}, {'song_ids': [2, 7]}])
        source['s6'] = {'observation': 'unrelated later result must never enter selection'}
        self.assertEqual(extract_targets(source, 10), [4, 1, 2, 7])

    def test_incomplete_or_invalid_collection_is_rejected(self):
        for source in (self.make([{'song_ids': [1]}] * 20), self.make([{'song_ids': [True]}]),
                       self.make([{'song_ids': [1, 2]}]), self.make([{'song_ids': [1]}], index=1)):
            with self.assertRaises(ValueError):
                extract_targets(source, 1)


if __name__ == '__main__':
    unittest.main()
