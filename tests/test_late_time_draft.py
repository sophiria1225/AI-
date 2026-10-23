import copy
from itertools import combinations
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from build_late_time_draft import conclusion, numerical_sections
from late_clock_comparison import POLICIES, cell_id, run_order, summarize

ROOT = Path(__file__).resolve().parents[1]


def evidence(unknown=False, unattempted=False, all_success=False):
    plan = json.loads((ROOT / 'configs/P82_late_clock_comparison_v01.json').read_text())
    rows, traces = [], {}
    for rep, n, policy in run_order():
        rid = cell_id(rep, n, policy)
        value = {'measured': 10000, 'not_exposed': 9000, 'late_half': 8000}[policy]
        missing = unknown and rid == cell_id(2, 4, 'late_half')
        absent = unattempted and rid == cell_id(2, 4, 'late_half')
        row = dict(run_id=rid, repetition=rep, task_id=plan['known_tasks'][n-1]['task_id'],
            time_visibility=policy, record_status='not_run' if absent else 'evaluated',
            success=None if absent else n < 4 or all_success,
            known_total_tokens=None if absent else value,
            unknown_usage_calls=None if absent else int(missing))
        if not absent: row.update(model_calls=1, api_requests=1, invocation_exceptions=0, wall_seconds=10)
        rows.append(row)
        active = policy == 'measured' or (policy == 'late_half' and n == 4)
        traces[rid] = dict(run_id=rid, known_complete=not (missing or absent),
            first_measured_notice_call=1 if active and not absent else None,
            calls=[] if absent else [{'effective_time_visibility':'measured' if active else 'not_exposed'}])
    report = dict(rows=rows, audit_errors=[], **summarize(rows, []),
        additional_model_calls=0, additional_api_calls=0, additional_evaluator_calls=0, reserved_scenarios_read=0)
    pairs = []
    for a, b in combinations(rows, 2):
        same = a['time_visibility'] == b['time_visibility']
        if a['task_id'] != b['task_id'] or not (same or a['repetition'] == b['repetition']): continue
        known = traces[a['run_id']]['known_complete'] and traces[b['run_id']]['known_complete']
        pairs.append(dict(run_ids=[a['run_id'], b['run_id']], task_id=a['task_id'],
            relation='same_policy_repetition' if same else 'within_repetition',
            policies=[a['time_visibility'], b['time_visibility']], repetitions=[a['repetition'], b['repetition']],
            both_known_complete=known, all_requests_equal=same if known else None,
            all_public_outputs_equal=same if known else None))
    stability = dict(pairs=pairs, traces=traces, private_reasoning_inspected_semantically=False)
    profile = dict(calls=[{} for _ in range(sum(r.get('model_calls', 0) for r in rows))], P80_P81_calls_included=False)
    session = dict(wall_seconds=300, load_wall_seconds=2, cell_full_wall_seconds=250, evaluation_wall_seconds=1)
    return plan, report, session, stability, profile


class LateTimeDraftTests(unittest.TestCase):
    def test_all_conditions_and_failures_remain_when_development_gates_pass(self):
        data = evidence(); text = numerical_sections(*data)
        self.assertEqual(text['results.tex'].count('未達 10,000'), 2)
        self.assertEqual(text['results.tex'].count('未達 9,000'), 2)
        self.assertEqual(text['results.tex'].count('未達 8,000'), 2)
        self.assertEqual(text['results.tex'].count('成功 10,000'), 6)
        self.assertEqual(text['results.tex'].count('成功 9,000'), 6)
        self.assertEqual(text['results.tex'].count('成功 8,000'), 6)
        self.assertIn('４比較すべて', conclusion(data[1]))
        self.assertIn('一般的な品質維持や新手法の成立を意味しない', text['results.tex'])
        self.assertIn('-8,000 & -6,000 & -2,000', text['results.tex'])
        self.assertEqual(text['stability.tex'].count(' & 未到達'), 6)

    def test_unknown_or_unattempted_cells_do_not_become_zero_cost(self):
        for kind in ('unknown', 'unattempted'):
            with self.subTest(kind=kind):
                data = evidence(**{kind: True}); text = numerical_sections(*data)
                self.assertIn('固定基準は未達', text['results.tex'])
                self.assertEqual(text['results.tex'].count('未確定 & 未確定 & 未確定'), 2)
                expected = r'未達 8,000\\＋不明1' if kind == 'unknown' else '未実行 未計測'
                self.assertIn(expected, text['results.tex'])
                self.assertEqual(len(data[1]['rows']), 24)
                if kind == 'unattempted':self.assertIn('費用記録があるのは23条件', text['results.tex'])

    def test_pair_count_alone_cannot_hide_a_duplicated_or_mislabeled_comparison(self):
        for change in ('duplicate', 'metadata'):
            data = evidence(); pairs = data[3]['pairs']
            if change == 'duplicate':pairs[-1] = copy.deepcopy(pairs[0])
            else:pairs[0]['relation'] = 'wrong'
            with self.subTest(change=change), self.assertRaises(ValueError):numerical_sections(*data)

    def test_transition_and_generation_counts_must_match_closed_trace(self):
        for change in ('transition', 'profile', 'trace'):
            data = evidence(); traces = data[3]['traces']
            if change == 'transition':traces[cell_id(1,4,'late_half')]['first_measured_notice_call'] = None
            elif change == 'profile':data[4]['calls'].pop()
            else:traces[cell_id(1,1,'measured')]['calls'].clear()
            with self.subTest(change=change), self.assertRaises(ValueError):numerical_sections(*data)


if __name__ == '__main__':
    unittest.main()
