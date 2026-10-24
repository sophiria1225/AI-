import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import build_observed_control_draft as builder


class ObservedControlDraftTests(unittest.TestCase):
    def evidence(self):
        return (json.loads((ROOT / 'reports/P82_comparison.json').read_text()),
                json.loads((ROOT / builder.OBSERVED).read_text()))

    def test_missing_both_sides_stays_unidentified_in_public_table(self):
        audit, observed = self.evidence()
        text = builder.resource_section(audit, observed)
        self.assertIn(r'\geq +197,929', text)
        self.assertIn('未確定', text)
        self.assertNotIn('-22,068', text)
        self.assertIn('成功同士5組', text)
        self.assertIn('失敗同士2組', text)
        self.assertIn('成否不一致1組', text)

    def test_changed_resources_or_adoption_decision_are_rejected(self):
        for kind in ('row', 'comparison', 'decision', 'imputation'):
            audit, observed = self.evidence()
            if kind == 'row': observed['rows'][-1]['known_logical_tokens'] += 1
            if kind == 'comparison': observed['comparisons'][-1]['paired_task_observations'] += 1
            if kind == 'decision': observed['original_decisions']['all_repetition_gates_met'] = True
            if kind == 'imputation': observed['terminal_usage_imputed'] = True
            with self.subTest(kind=kind), self.assertRaisesRegex(ValueError, 'all_closed_receipts'):
                builder.resource_section(audit, observed)

    def test_local_non_identification_does_not_become_a_negative_effect_result(self):
        audit, _ = self.evidence()
        replay = {'diagnostic_usable': False, 'local_public_output_difference_identified': None}
        ja, en, ending = builder.closing_text(audit, replay)
        self.assertIn('判定条件を満たさなかった', ja)
        self.assertIn('did not meet its fixed diagnostic criteria', en)
        self.assertIn('ID差だけの効果として結論しない', ending)
        for effect in (True, False):
            with self.assertRaisesRegex(ValueError, 'diagnostic_state'):
                builder.closing_text(audit, {**replay, 'local_public_output_difference_identified': effect})

    def test_all_closed_outcomes_obey_abstract_limits(self):
        audit, _ = self.evidence()
        for usable, effect in ((False, None), (True, False), (True, True)):
            with self.subTest(usable=usable, effect=effect):
                ja, en, ending = builder.closing_text(audit, {
                    'diagnostic_usable': usable, 'local_public_output_difference_identified': effect})
                self.assertLessEqual(len(ja), 120)
                self.assertLessEqual(len(en.split()), 50)
                self.assertFalse(any(c in ja for c in ('。', '・')))
                self.assertIn('do not establish general quality preservation', en)
                self.assertIn('全４採用基準を満たさず', ending)

    def test_unknown_value_and_repeated_template_boundaries_are_rejected(self):
        with self.assertRaisesRegex(ValueError, 'no_value'):
            builder.quantity({'kind': 'unidentified', 'value': 0, 'missing_usage_imputed': False})
        with self.assertRaisesRegex(ValueError, 'single_known_template'):
            builder.replace_once('marker marker', 'marker', 'new')

    def test_existing_draft_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = root / builder.FOLDER
            folder.mkdir(parents=True)
            (folder / 'draft.tex').write_text('retain the first attempt')
            with patch.object(builder, 'ROOT', root), patch.object(builder.base.clock_report, 'validated') as read_evidence:
                with self.assertRaises(FileExistsError):
                    builder.build()
                read_evidence.assert_not_called()
            self.assertEqual((folder / 'draft.tex').read_text(), 'retain the first attempt')


if __name__ == '__main__':
    unittest.main()
