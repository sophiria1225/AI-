import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from select_public_appworld_tasks import select_ids


class PublicAppWorldSelectionControls(unittest.TestCase):
    def test_siblings_are_excluded_and_order_does_not_depend_on_input_order(self):
        ids = ['bb_3', 'aa_1', 'bb_1', 'cc_1', 'dd_1', 'aa_2', 'ee_1']
        self.assertEqual(select_ids(ids, ['aa'], 3), ['bb_1', 'cc_1', 'dd_1'])
        self.assertEqual(select_ids(list(reversed(ids)), ['aa'], 3), ['bb_1', 'cc_1', 'dd_1'])

    def test_missing_variant_or_duplicate_does_not_silently_replace_a_task(self):
        with self.assertRaises(ValueError): select_ids(['aa_2', 'bb_1', 'cc_1'], [], 2)
        with self.assertRaises(ValueError): select_ids(['aa_1', 'aa_1'], [], 1)


if __name__ == '__main__':
    unittest.main()
