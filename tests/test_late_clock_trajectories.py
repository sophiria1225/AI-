import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from api_error_comparison import task_snapshot
from budget_observation import notification
from stable_clock_observation import effective_visibility
from compare_late_clock_trajectories import request_fingerprints,pair


def data(policy,seconds,content='same',used=0):
    config={'max_wall_seconds':60,'max_api_requests':8,'max_calls':4,'max_total_tokens':200,
        'max_output_tokens':40,'model':{'num_ctx':1024}}
    state=task_snapshot(config,[],used,60-seconds);effective=effective_visibility(policy,state,60)
    request={'messages':[{'role':'user','content':content}]+notification([],state,effective)[0]}
    notice={'measured_state':state,'effective_time_visibility':effective}
    return request,notice


class LateClockTrajectoryTests(unittest.TestCase):
    def test_hidden_late_clock_stays_hidden_during_value_only_diagnosis(self):
        a,n=data('late_half',31);b,m=data('not_exposed',40)
        left=request_fingerprints(a,n,'late_half',60);right=request_fingerprints(b,m,'not_exposed',60)
        self.assertEqual(left['request_sha256'],right['request_sha256'])
        self.assertEqual(left['without_current_wall_sha256'],right['without_current_wall_sha256'])
        self.assertEqual(left['effective_time_visibility'],'not_exposed')

    def test_current_treatment_removal_does_not_erase_history_or_other_budgets(self):
        a,n=data('late_half',30);b,m=data('not_exposed',30)
        left=request_fingerprints(a,n,'late_half',60);right=request_fingerprints(b,m,'not_exposed',60)
        self.assertNotEqual(left['without_current_wall_sha256'],right['without_current_wall_sha256'])
        self.assertEqual(left['without_current_time_treatment_sha256'],right['without_current_time_treatment_sha256'])
        for content,used in [('different',0),('same',1)]:
            changed,notice=data('not_exposed',30,content,used)
            value=request_fingerprints(changed,notice,'not_exposed',60)
            self.assertNotEqual(value['without_current_time_treatment_sha256'],left['without_current_time_treatment_sha256'])

    def test_changed_notice_or_effective_policy_is_rejected(self):
        a,n=data('late_half',30)
        bad=copy.deepcopy(a);bad['messages'][-1]['content']+='changed'
        with self.assertRaises(ValueError):request_fingerprints(bad,n,'late_half',60)
        n['effective_time_visibility']='not_exposed'
        with self.assertRaises(ValueError):request_fingerprints(a,n,'late_half',60)

    def test_pair_reports_missing_usage_as_incomplete_and_keeps_first_difference(self):
        calls=[]
        for policy in ('not_exposed','late_half'):
            r,n=data(policy,30);calls.append({**request_fingerprints(r,n,policy,60),
                'public_output_sha256':'same','opaque_message_sha256':'same'})
        a={'run_id':'a','known_complete':False,'calls':[calls[0]],'first_measured_notice_call':None}
        b={'run_id':'b','known_complete':True,'calls':[calls[1]],'first_measured_notice_call':1}
        result=pair(a,b)
        self.assertIsNone(result['all_requests_equal']);self.assertEqual(result['first_request_difference'],1)
        self.assertTrue(result['first_difference_is_current_time_treatment_only'])
        self.assertFalse(result['causal_timing_effect_identified'])


if __name__=='__main__':unittest.main()
