from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from recovery_notice_comparison import POLICIES, run_order, summarize
from build_recovery_notice_report import totals, contributions, cost
from inspect_recovery_notice_ledger import summarize_monitor
from test_recovery_notices import record, boundary
from recovery_notices import RecoveryMonitor


def fixture_rows():
    return [dict(task_id=str(n),notice_policy=p,record_status='evaluated',success=n!=4,
        known_total_tokens=100+10*POLICIES.index(p),unknown_usage_calls=0,model_calls=2,
        input_tokens=80,cached_input_tokens=40,output_tokens=20+10*POLICIES.index(p),
        api_requests=3,invocation_exceptions=0,setup_wall_seconds=1.,wall_seconds=5.,
        cleanup_wall_seconds=1.,full_wall_seconds=7.) for n,p in run_order()]


class RecoveryReportingTests(unittest.TestCase):
    def test_all_four_cells_sum_including_failed_task(self):
        t=totals(fixture_rows(),'factual')
        self.assertEqual((t['planned'],t['evaluated'],t['successes'],t['failures']),(4,4,3,1))
        self.assertEqual(t['full_logical_tokens'],480)
        self.assertEqual(t['known_uncached_input_tokens'],160)

    def test_unknown_usage_stays_lower_bound(self):
        rows=fixture_rows();rows[0]['unknown_usage_calls']=1
        t=totals(rows,'none');self.assertIsNone(t['full_logical_tokens'])
        self.assertEqual(t['known_total_tokens'],400);self.assertIn('不明1',cost(t))

    def test_missing_cell_is_not_failure_or_zero_cost(self):
        rows=fixture_rows();rows[0].update(record_status='not_run',success=None,known_total_tokens=None,unknown_usage_calls=None)
        t=totals(rows,'none')
        self.assertEqual((t['unmeasured'],t['failures'],t['successes']),(1,1,2))
        self.assertIsNone(t['full_logical_tokens']);self.assertEqual(t['known_total_tokens'],300)
        self.assertIn('未計測1条件',cost(t))

    def test_pair_contributions_add_to_whole_cohort(self):
        report=summarize(fixture_rows(),[]);parts=contributions(report)
        self.assertEqual(len(parts),12)
        for pair in report['pairs']:
            rows=[r for r in parts if (r['left'],r['right'])==(pair['left'],pair['right'])]
            self.assertEqual(sum(r['task_count'] for r in rows),4)
            self.assertEqual(sum(r['right_minus_left_tokens'] for r in rows),pair['aggregate_token_difference'])
            self.assertEqual(next(r['task_count'] for r in rows if r['group']=='both_failed'),1)

    def test_unknown_total_cannot_be_recovered_from_selected_successes(self):
        rows=fixture_rows();rows[-1]['unknown_usage_calls']=1
        parts=contributions(summarize(rows,[]))
        self.assertTrue(all(r['right_minus_left_tokens'] is None for r in parts))

    def test_detector_ledger_does_not_turn_offer_into_dispatch(self):
        m=RecoveryMonitor('factual')
        for _ in range(3):boundary(m,[record()])
        report=summarize_monitor(m.report())
        self.assertEqual(report['candidate_counts']['exact'],1)
        self.assertEqual(report['equal_value_counts']['exact'],2)
        self.assertEqual(report['eligible_read_requests'],3)
        self.assertFalse(report['offers'][0]['model_attempted'])
        self.assertEqual(report['api_elision_count'],0)


if __name__=='__main__':unittest.main()
