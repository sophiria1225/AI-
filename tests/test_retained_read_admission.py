"""A finite synthetic check of the stated retained-reference budget identity."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from deferred_read_obligations import Assumptions, BudgetExhausted
from explicit_deferred_read_views import ReadViews


class RetainedReadAdmissionTests(unittest.TestCase):
    def test_all_partial_patterns_same_admission_while_every_root_remains_live(self):
        # Seven distinct reads, every partial-availability pattern, budgets 0..6.
        # No saved code, data, model, service, or complete-cache reuse occurs.
        objects = {str(i): {'title': str(i), 'extra': i} for i in range(7)}
        trusted = Assumptions(True, True, True)
        checked = 0
        for budget in range(7):
            for mask in range(1 << 7):
                admitted = []
                for defer in (False, True):
                    owner = ReadViews(objects, budget, defer=defer); retained = []
                    try:
                        for i in range(7):
                            partial = {'title': str(i)} if mask & (1 << i) else {}
                            retained.append(owner.read(str(i), partial, trusted))
                            self.assertEqual(owner.model.spent + owner.model.pending, len(retained))
                    except BudgetExhausted:
                        pass
                    admitted.append(len(retained))
                    self.assertEqual(len(retained), budget)
                    self.assertEqual(owner.model.available, 0)
                    # All retained snapshots remain demandable inside the same
                    # reservation. Demanding them consumes, rather than saves,
                    # the outstanding obligation.
                    self.assertEqual([dict(v) for v in retained], [objects[str(i)] for i in range(budget)])
                    self.assertEqual(owner.model.spent, budget)
                    self.assertEqual(owner.model.pending, 0)
                    owner.close()
                self.assertEqual(admitted[0], admitted[1]); checked += 1
        self.assertEqual(checked, 896)


if __name__ == '__main__': unittest.main()
