import copy
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import build_closed_control_draft as builder
from build_closed_control_draft import sections
from late_clock_comparison import summarize
from summarize_late_clock_resources import resource_cells, comparisons
from test_late_time_draft import evidence
from test_late_clock_resources import fixture as resource_fixture, make_unknown
from test_fallback_output_report import report_fixture


def clock_evidence(unknown=False):
    data = list(evidence())
    cells, calls = resource_fixture()
    if unknown:
        make_unknown(cells, calls, 'late_half', 300)
    data[1] = {**data[1], 'rows': cells, **summarize(cells, [])}
    data[2]['cell_full_wall_seconds'] = sum(c['full_wall_seconds'] for c in cells)
    for c in cells:
        data[3]['traces'][c['run_id']]['known_complete'] = c['unknown_usage_calls'] == 0
    for pair in data[3]['pairs']:
        known = all(data[3]['traces'][rid]['known_complete'] for rid in pair['run_ids'])
        pair['both_known_complete'] = known
        if not known:
            pair['all_requests_equal'] = pair['all_public_outputs_equal'] = None
    rows, decisions = resource_cells(cells, calls)
    resources = dict(rows=rows, comparisons=comparisons(rows), original_decisions=decisions)
    return data, resources


class ClosedControlDraftTests(unittest.TestCase):
    def test_builder_refuses_live_cohort_before_replay_read_or_output(self):
        data, _ = clock_evidence()
        data[1]['batch_status'] = 'running'
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            with patch.object(builder, 'ROOT', root), \
                    patch.object(builder.clock_report, 'validated', return_value=data), \
                    patch.object(builder.fallback_report, 'validated') as replay:
                with self.assertRaisesRegex(ValueError, 'complete_P82_cohort'):
                    builder.build()
                replay.assert_not_called()
                self.assertFalse((root / builder.FOLDER).exists())

    def test_all_24_cells_and_18_slots_reach_separate_sections(self):
        data, resources = clock_evidence()
        with tempfile.TemporaryDirectory() as folder:
            _, replay = report_fixture(Path(folder))
            generated = sections(data, replay, resources)
        self.assertEqual(set(generated), {'whole_task.tex', 'trajectories.tex', 'local_replay.tex'})
        self.assertIn('全24条件で24生成', generated['whole_task.tex'])
        table = generated['whole_task.tex'].split(r'\end{table}')[0]
        self.assertEqual(sum(' & ' in line for line in table.splitlines()), 9)
        self.assertIn('18予定枠中18生成', generated['local_replay.tex'])
        self.assertIn('全15組', generated['local_replay.tex'])
        self.assertEqual(sum(' & ' in line for line in generated['local_replay.tex'].splitlines()), 7)
        self.assertIn('36対は実行を共有', generated['trajectories.tex'])

    def test_unknown_p82_and_p84_do_not_become_positive_claims(self):
        data, resources = clock_evidence(unknown=True)
        with tempfile.TemporaryDirectory() as folder:
            _, replay = report_fixture(Path(folder), unknown=True)
            generated = sections(data, replay, resources)
        self.assertIn('＋不明1', generated['whole_task.tex'])
        self.assertIn('固定基準は未達', generated['whole_task.tex'])
        self.assertIn('使用量不明1生成', generated['local_replay.tex'])
        self.assertIn('ID差だけの効果として結論しない', generated['local_replay.tex'])
        self.assertIn('元の採否は変更しない', generated['whole_task.tex'])

    def test_truncated_or_unattempted_replay_slots_remain_visible(self):
        data, resources = clock_evidence()
        for kwargs in ({'truncated': True}, {'attempted': 1}):
            with self.subTest(kwargs=kwargs), tempfile.TemporaryDirectory() as folder:
                _, replay = report_fixture(Path(folder), **kwargs)
                generated = sections(data, replay, resources)
                self.assertIn('ID差だけの効果として結論しない', generated['local_replay.tex'])
                self.assertIn(f'18予定枠中{replay["model_calls_attempted"]}生成', generated['local_replay.tex'])

    def test_omitted_optional_intervals_are_explicit_and_gates_unchanged(self):
        data, _ = clock_evidence(unknown=True)
        with tempfile.TemporaryDirectory() as folder:
            _, replay = report_fixture(Path(folder))
            text = sections(data, replay, None)['whole_task.tex']
        self.assertIn('補助的な資源区間は本稿に含めず', text)
        self.assertIn('使用量不明1生成', text)
        self.assertIn('固定基準は未達', text)

    def test_changed_gate_resource_or_replay_identity_is_rejected(self):
        for kind in ('gate', 'resource', 'replay', 'effect'):
            data, resources = clock_evidence()
            with tempfile.TemporaryDirectory() as folder:
                _, replay = report_fixture(Path(folder))
                if kind == 'gate': data[1]['all_repetition_gates_met'] = False
                if kind == 'resource': resources['rows'][0]['known_total_tokens'] += 1
                if kind == 'replay': replay['rows'][-1] = copy.deepcopy(replay['rows'][0])
                if kind == 'effect': replay['local_public_output_difference_identified'] = False
                with self.subTest(kind=kind), self.assertRaises(ValueError):
                    sections(data, replay, resources)


if __name__ == '__main__':
    unittest.main()
