import copy
from pathlib import Path
import sys,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from queue_later_handoff import validate_prior,validate_slots
from handoff_factors import ARMS


class HandoffQueueTests(unittest.TestCase):
    def setUp(self):
        self.status={'status':'merged','head':'a'*40,'pull_request':'https://github.com/sophiria1225/AI-/pull/1'}
        self.report={'phase':'P31','all_sixteen_reviewed':True,'audit_errors':[],
                     'rows':[{'task_id':str(i),'arm':a} for i in range(4) for a in ARMS]}

    def test_complete_authorized_audit_can_proceed(self):
        validate_prior(self.status,self.report)

    def test_wrong_repository_or_unmerged_results_stop(self):
        for key,value in [('pull_request','https://github.com/other/repo/pull/1'),('status','published_waiting_ci'),('head','a'*7)]:
            s={**self.status,key:value}
            with self.assertRaises(ValueError):validate_prior(s,self.report)

    def test_partial_or_duplicate_cells_do_not_count_as_sixteen(self):
        for rows in [self.report['rows'][:-1],self.report['rows'][:-1]+[self.report['rows'][0]]]:
            with self.assertRaises(ValueError):validate_prior(self.status,{**self.report,'rows':rows})

    def test_failed_audit_stops(self):
        with self.assertRaises(ValueError):validate_prior(self.status,{**self.report,'audit_errors':['cost']})

    def test_only_one_known_idle_slot_is_eligible(self):
        validate_slots([{'is_processing':False}])
        for slots in ([],[{}],[{'is_processing':True}],[{'is_processing':False}]*2):
            with self.assertRaises(ValueError):validate_slots(slots)
