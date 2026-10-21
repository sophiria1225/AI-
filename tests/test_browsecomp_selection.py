from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from select_browsecomp_development import choose


class DevelopmentSelectionControls(unittest.TestCase):
    def test_selection_ignores_order_and_refuses_content_duplicates_or_revision_change(self):
        rows = [{'query_id': str(i)} for i in range(8)]
        policy = {'revision':'r1','salt':'fixed','expected_unique_ids':8,'development_count':2}
        self.assertEqual(choose(rows,policy,'r1'), choose(rows[::-1],policy,'r1'))
        for bad in (rows[:-1], rows[:-1]+[rows[0]], [dict(rows[0],answer='PRIVATE')]+rows[1:]):
            with self.assertRaises(ValueError): choose(bad,policy,'r1')
        with self.assertRaises(ValueError): choose(rows,policy,'r2')
        out=choose(rows,policy,'r1')
        self.assertFalse(set(out['selected_ids']) & set(out['unused_candidate_ids']))
