import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from run_ledger_contract_probe import schedule


class ContractScheduleTests(unittest.TestCase):
    def plan(self):
        return json.loads((Path(__file__).resolve().parents[1] /
                           'configs/P17_ledger_contract_v01.json').read_text())

    def test_pair_coverage_and_alternating_order(self):
        rows = schedule(self.plan())
        self.assertEqual(len(rows), 16)
        self.assertEqual(len({tuple(r.values()) for r in rows}), 16)
        for i in range(0, 16, 2):
            a, b = rows[i:i+2]
            self.assertEqual((a['case_id'], a['seed']), (b['case_id'], b['seed']))
            self.assertNotEqual(a['variant'], b['variant'])
        self.assertEqual(sum(rows[i]['variant'] == 'legacy' for i in range(0, 16, 2)), 4)

    def test_source_or_seed_change_requires_new_design(self):
        for field, value in [('case_ids', ['case_01_recorded']), ('seeds', [46, 48]), ('max_calls', 8)]:
            plan = self.plan(); plan[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                schedule(plan)


if __name__ == '__main__':
    unittest.main()
