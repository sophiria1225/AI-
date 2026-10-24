"""Keep the future P99 letter conditional on the entire audited cohort."""
from pathlib import Path
import re
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import build_whole_task_tool_choice_draft as draft
from whole_task_tool_choice import summarize
from run_handoff_factors import read, sha
from test_whole_task_tool_choice_reporting import fixture, synthetic_rows, synthetic_plan, make_unknown

ROOT = Path(__file__).resolve().parents[1]


def manuscript_fixture(base, rows=None):
    root, plan, rows = fixture(base, rows)
    for name in draft.SUPPORT:
        target = root/name; target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT/name, target)
    return root, plan, rows


class WholeTaskToolChoiceDraftTests(unittest.TestCase):
    def test_unattempted_cohort_is_described_as_planned_not_executed(self):
        rows=synthetic_rows(synthetic_plan())
        for row in rows:
            row.update(record_status='not_run',success=None,known_total_tokens=None,unknown_usage_calls=None)
        ja,en=draft.abstracts(dict(rows=rows,**summarize(rows,[])))
        self.assertIn('計画した',ja);self.assertNotIn('比較した',ja)
        self.assertIn('We planned to compare',en)
        self.assertIn('欠測または未評価',ja)

    def test_changed_prior_inventory_cannot_motivate_a_result_paper(self):
        import json
        with tempfile.TemporaryDirectory() as temp:
            root,_,_=manuscript_fixture(Path(temp))
            path=root/'materials/20261024_p98_results/summary.json'
            changed=read(path);changed['no_structured_tool_calls']=0
            path.write_text(json.dumps(changed))
            with self.assertRaisesRegex(ValueError,'closed_P98_motivation'):draft.build(root)
            self.assertFalse((root/draft.FOLDER).exists())

    def test_abstracts_change_with_complete_gate_not_selected_successes(self):
        rows = synthetic_rows(synthetic_plan())
        for kind in ('positive', 'quality_loss', 'unknown'):
            if kind == 'quality_loss': rows[1]['success'] = False
            if kind == 'unknown': make_unknown(rows[-1])
            ja, en = draft.abstracts(dict(rows=rows,**summarize(rows, [])))
            self.assertLessEqual(len(ja), 120); self.assertLessEqual(len(en.split()), 50)
            self.assertNotIn('。', ja); self.assertNotIn('・', ja)
            self.assertIn('一般的な品質維持は未検証', ja)
            if kind == 'positive': self.assertIn('全論理費用を削減した', ja)
            elif kind == 'quality_loss': self.assertIn('事前採用基準を満たさなかった', ja)
            else: self.assertIn('全仕事費用差は確定できなかった', ja)

    def test_unevaluated_and_unknown_sections_keep_eight_rows_and_no_zero_fill(self):
        plan = synthetic_plan(); rows = synthetic_rows(plan)
        rows[-1].update(record_status='not_run', success=None, known_total_tokens=None, unknown_usage_calls=None)
        for key in ('model_calls', 'api_requests', 'wall_seconds','request_checks'): rows[-1].pop(key)
        make_unknown(rows[-2])
        with tempfile.TemporaryDirectory() as temp:
            root, _, _ = fixture(Path(temp), rows); session = read(root/'reports/P99_server_session.json')
        sections = draft.sections(plan, dict(rows=rows, **summarize(rows, [])), session)
        text = sections['whole_task.tex']
        self.assertEqual(sum(text.count(task+' & ') for task in draft.TASKS), 8)
        self.assertIn('未実行 & 未計測 & 未計測 & 未計測', text)
        self.assertIn('$+?$', text)
        self.assertIn('未確定', text)
        self.assertNotIn('全論理費用を減らした', sections['conclusion.tex'])

    def test_build_requires_closed_sources_binds_all_outputs_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as temp:
            root, _, _ = manuscript_fixture(Path(temp)); manifest = draft.build(root)
            folder = root / draft.FOLDER
            for name, expected in manifest['source_sha256'].items(): self.assertEqual(sha(root/name), expected)
            for name, expected in manifest['generated_sha256'].items(): self.assertEqual(sha(folder/name), expected)
            self.assertEqual(manifest['all_planned_rows'], 8)
            self.assertFalse(manifest['submission_ready']); self.assertFalse(manifest['authors_confirmed'])
            self.assertFalse(manifest['novel_method_claim']); self.assertFalse(manifest['general_quality_preservation_claim'])
            self.assertFalse(manifest['professor_brief_changed'])
            source=(folder/'draft.tex').read_text()
            self.assertIn('Evaluating Information Retention and Execution Control in Stateful LLM Agents', source)
            self.assertIn('著者情報未設定', source)
            self.assertEqual(source.count('\\bibitem{'), 8)
            cited = list(dict.fromkeys(re.findall(r'\\cite\{([^}]+)\}', source)))
            self.assertEqual(re.findall(r'\\bibitem\{([^}]+)\}', source), cited)
            with self.assertRaises(FileExistsError): draft.build(root)

    def test_absent_real_audit_cannot_generate_result_manuscript(self):
        with tempfile.TemporaryDirectory() as temp:
            root, _, _ = manuscript_fixture(Path(temp))
            (root/'reports/P99_comparison.json').unlink()
            with self.assertRaises(FileNotFoundError): draft.build(root)
            self.assertFalse((root/draft.FOLDER).exists())


if __name__ == '__main__':
    unittest.main()
