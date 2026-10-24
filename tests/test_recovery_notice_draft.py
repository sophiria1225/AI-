from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from build_recovery_notice_draft import abstracts, quality_status, sections
from recovery_notice_comparison import cell_id, run_order, summarize
from test_recovery_notice_reporting import fixture_rows


def fixture():
    rows=fixture_rows()
    for row,(n,p) in zip(rows,run_order()):row['run_id']=cell_id(n,p)
    report=dict(rows=rows,**summarize(rows,[]))
    session=dict(wall_seconds=100,load_wall_seconds=1,evaluation_wall_seconds=2,
        cell_full_wall_seconds=90,unmeasured_condition_count=0,
        sampled_peak_rss_bytes=2**30,peak_system_swap_bytes=0)
    notices=dict(rows=[dict(run_id=r['run_id'],record_present=True,
        candidate_counts=dict(exact=0,drop_auth_argument=0,login_request_origin=0),offers=[])
        for r in rows])
    return report,session,notices


class RecoveryNoticeDraftTests(unittest.TestCase):
    def test_complete_negative_result_has_no_improvement_claim(self):
        report,_,_=fixture();ja,en=abstracts(report)
        self.assertIn('満たさなかった',ja);self.assertIn('did not meet',en)
        self.assertLessEqual(len(ja),120);self.assertLessEqual(len(en.split()),50)
        self.assertNotIn('。',ja);self.assertNotIn('・',ja)

    def test_unknown_usage_cannot_turn_into_positive_abstract(self):
        report,_,_=fixture();report['rows'][0]['unknown_usage_calls']=1
        report.update(summarize(report['rows'],[]));ja,en=abstracts(report)
        self.assertIn('確定できなかった',ja);self.assertIn('Missing usage',en)
        self.assertLessEqual(len(ja),120);self.assertLessEqual(len(en.split()),50)

    def test_missing_cell_is_not_described_as_executed(self):
        report,_,_=fixture();report['rows'][0].update(record_status='not_run',success=None,
            known_total_tokens=None,unknown_usage_calls=None)
        report.update(summarize(report['rows'],[]));ja,en=abstracts(report)
        self.assertIn('計画した',ja);self.assertIn('We planned to compare',en)
        self.assertLessEqual(len(ja),120);self.assertLessEqual(len(en.split()),50)

    def test_positive_case_is_only_fixed_development_criteria(self):
        report,_,_=fixture()
        for row in report['rows']:
            row['known_total_tokens']={'none':120,'generic':110,'factual':100}[row['notice_policy']]
            if row['task_id']=='4' and row['notice_policy'] in ('generic','factual'):
                row['dispatched_notice_inputs']=[dict(call_id='call_009',sha256='a'*64)]
        report.update(summarize(report['rows'],[]));ja,en=abstracts(report)
        self.assertTrue(report['factual_notice_benefit_gate_met'])
        self.assertIn('固定基準を満たした',ja)
        self.assertIn('general quality preservation remains untested',en)
        self.assertLessEqual(len(ja),120);self.assertLessEqual(len(en.split()),50)

    def test_all_twelve_costs_and_unexecuted_slot_remain(self):
        report,session,notices=fixture()
        for i,row in enumerate(report['rows']):row['known_total_tokens']=10001+i
        report['rows'][0].update(record_status='not_run',success=None,known_total_tokens=None,
            unknown_usage_calls=None,model_calls=None,api_requests=None)
        report.update(summarize(report['rows'],[]))
        out=sections(report,session,notices)
        self.assertIn('未実行',out['whole_task'])
        for i in range(1,12):self.assertIn(f'{10001+i:,}',out['whole_task'])
        self.assertIn('両未達',out['whole_task']);self.assertIn('未確定',out['whole_task'])

    def test_quality_loss_and_unknown_cost_are_separate(self):
        report,_,_=fixture();pair=report['pairs'][0]
        self.assertEqual(quality_status(pair),'喪失なし')
        pair['tasks'][0].update(left_success=True,right_success=False)
        self.assertEqual(quality_status(pair),'喪失あり')
        pair['tasks'][0]['right_success']=None
        self.assertEqual(quality_status(pair),'未確認')

    def test_candidate_without_attempt_is_not_reported_as_sent(self):
        report,session,notices=fixture()
        notices['rows'][0].update(candidate_counts=dict(exact=0,drop_auth_argument=1,login_request_origin=1),
            offers=[dict(next_call_id='call_073',model_attempted=False)])
        text=sections(report,session,notices)['detection']
        self.assertIn('0/1/1',text);self.assertNotIn('073',text)


if __name__=='__main__':unittest.main()
