import copy
from unittest.mock import patch
import unittest
from rolling_checkpoint_worker_fixture import fixture
from empirical_payback_inference import EmpiricalPaybackInference


def run(mode='rolling_separate', **kwargs):
    instances=[]
    def make(config, output, *, conversation):
        config['payback_mode']=mode
        value=EmpiricalPaybackInference(config,output,conversation=conversation)
        instances.append(value)
        return value
    with patch('run_whole_task_rolling_checkpoint_cell.RollingCheckpointInference', side_effect=make):
        result=fixture(policy='rolling_separate',**kwargs)
    result['payback']=instances[0].payback_summary()
    return result


class EmpiricalInferenceTests(unittest.TestCase):
    def test_ordinary_mode_matches_original_requests_counts_and_usage(self):
        args=dict(actions=('echo',)*9+('finish',),api_limit=32)
        old=fixture(policy='rolling_separate',**args);new=run(**args)
        self.assertEqual(old['captured'],new['captured'])
        self.assertEqual(old['counted'],new['counted'])
        self.assertEqual(old['saved']['usage'],new['saved']['usage'])
        self.assertEqual(old['result']['checkpoint_control'],new['result']['checkpoint_control'])
        self.assertEqual(new['payback']['extra_native_counts'],0)
        self.assertFalse(new['payback']['contract_failed'])

    def test_first_opportunity_identical_in_both_modes(self):
        args=dict(actions=('echo',)*5+('finish',),api_limit=32)
        a=run('rolling_separate',**args);b=run('empirical_payback',**args)
        self.assertEqual(a['captured'],b['captured']);self.assertEqual(a['saved']['usage'],b['saved']['usage'])
        self.assertEqual(b['payback']['evaluated_opportunities'],1)
        self.assertEqual(b['saved']['empirical_payback_events'][0]['reason'],'first_opportunity_ordinary')

    def test_call_horizon_skips_without_fake_usage_and_keeps_actions(self):
        result=run('empirical_payback',actions=('echo',)*8+('finish',),max_calls=10,api_limit=32)
        self.assertEqual(result['result']['stop_reason'],'agent_declared_complete')
        self.assertEqual(result['programs'],['echo']*8+['finish'])
        skipped=[x for x in result['saved']['empirical_payback_events'] if x['status']=='skipped_unstarted']
        self.assertTrue(skipped)
        self.assertTrue(all(not x['model_attempted'] and not x['terminal_usage_recorded'] and x['summary_known_tokens']==0 for x in skipped))
        self.assertEqual(result['payback']['dispatched_focus_calls'],1)
        self.assertEqual(result['result']['model_calls'],10)
        self.assertTrue(result['payback']['accounting_complete'])

    def test_shared_budget_screening_runs_before_new_predictor(self):
        result=run('empirical_payback',actions=('echo',)*3+('finish',),max_calls=4)
        self.assertEqual(result['payback']['evaluated_opportunities'],0)
        self.assertEqual(result['result']['checkpoint_control']['decisions'][0]['reason'],'insufficient_shared_call_budget')
        self.assertEqual(result['result']['model_calls'],4)

    def test_unknown_summary_charged_and_stops_before_actor(self):
        result=run('empirical_payback',actions=('echo',)*9+('finish',),api_limit=32,summary_mode='unknown')
        self.assertEqual(result['result']['unknown_usage_calls'],1)
        self.assertEqual(result['captured'][-1]['role'],'focus')
        self.assertEqual(result['payback']['unknown_focus_usage_calls'],1)
        self.assertTrue(result['saved']['empirical_payback_events'][0]['model_attempted'])
        self.assertEqual(result['saved']['empirical_payback_events'][0]['status'],'aborted')

    def test_predictor_failure_is_sticky_and_has_no_unrecorded_generation(self):
        with patch('empirical_payback_inference.evaluate_payback',side_effect=ValueError('synthetic invalid prefix')):
            result=run('empirical_payback',actions=('echo',)*5+('finish',),api_limit=32)
        self.assertTrue(result['payback']['contract_failed']);self.assertFalse(result['payback']['accounting_complete'])
        self.assertEqual(result['result']['stop_reason'],'runtime_error')
        self.assertTrue(all(x['role']=='agent' for x in result['captured']))

if __name__=='__main__':unittest.main()
