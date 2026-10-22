import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from run_budget_notification import run_order


class BudgetOrderTests(unittest.TestCase):
    def test_each_original_task_gets_both_arms_with_balanced_first_position(self):
        tasks = [{'source_run': i} for i in range(4)]
        order = run_order(tasks)
        self.assertEqual(len(order), 8)
        self.assertEqual([a for _, _, a in order[::2]],
                         ['plain_keep', 'budget_keep', 'plain_keep', 'budget_keep'])
        self.assertEqual([p for _, p, _ in order[::2]], tasks)
        for i in range(0, 8, 2):
            self.assertEqual({a for _, _, a in order[i:i+2]}, {'plain_keep', 'budget_keep'})


if __name__ == '__main__':
    unittest.main()
