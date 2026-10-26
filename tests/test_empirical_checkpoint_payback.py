import copy
import math
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from empirical_checkpoint_payback import evaluate_payback


def inputs():
    calls=[dict(id='call_001',role='agent',status='ok',input_tokens=100,output_tokens=20,wall_seconds=10),
           dict(id='call_002',role='focus',status='ok',input_tokens=1000,output_tokens=200,wall_seconds=20),
           dict(id='call_003',role='agent',status='ok',input_tokens=500,output_tokens=20,wall_seconds=30)]
    controls=[dict(status='checkpoint_decided',accepted=True,after_model_calls=2,revision=1,
                   ordinary_input_tokens=1000,compacted_input_tokens=500)]
    return dict(mode='empirical_payback',opportunity_index=2,calls=calls,controls=controls,
                summary_input_tokens=1000,output_cap=200,remaining_calls=4,remaining_wall_seconds=110)


class EmpiricalPaybackTests(unittest.TestCase):
    def test_exact_boundary_and_integer_horizon(self):
        args=inputs(); before=copy.deepcopy(args); out=evaluate_payback(**args)
        self.assertEqual(args,before);self.assertEqual(out['predicted_actor_horizon'],3)
        self.assertEqual(out['required_wall_seconds'],110);self.assertTrue(out['admitted'])
        args['remaining_wall_seconds']=109.999
        self.assertEqual(evaluate_payback(**args)['reason'],'payback_insufficient_wall_horizon')
        args.update(remaining_wall_seconds=110,remaining_calls=3)
        self.assertEqual(evaluate_payback(**args)['reason'],'payback_insufficient_call_horizon')

    def test_baseline_keeps_ordinary_dispatch_despite_shadow_reject(self):
        args=inputs();args.update(mode='rolling_separate',remaining_wall_seconds=1)
        out=evaluate_payback(**args);self.assertTrue(out['admitted']);self.assertFalse(out['predicted_admit'])
        self.assertFalse(out['applied']);self.assertFalse(out['prediction_guaranteed'])

    def test_first_opportunity_does_not_add_empirical_restriction(self):
        args=inputs();args.update(opportunity_index=1,calls=args['calls'][:1],controls=[],remaining_calls=2,remaining_wall_seconds=1)
        out=evaluate_payback(**args);self.assertTrue(out['admitted']);self.assertIsNone(out['predicted_actor_horizon'])

    def test_repeat_without_accepted_or_positive_delta_is_not_first(self):
        args=inputs();args['controls']=[]
        self.assertEqual(evaluate_payback(**args)['reason'],'payback_missing_prior_accepted')
        args=inputs();args['controls'][0]['compacted_input_tokens']=1000
        self.assertEqual(evaluate_payback(**args)['reason'],'payback_nonpositive_prior_delta')

    def test_observed_paid_cost_and_latest_three_actor_max(self):
        args=inputs();args['calls'][1]['output_tokens']=4000
        args['calls'][0]['wall_seconds']=999
        for i,w in enumerate([2,3,4],4):
            args['calls'].append(dict(id=f'call_{i:03}',role='agent',status='ok',input_tokens=1,output_tokens=1,wall_seconds=w))
        args.update(remaining_calls=20,remaining_wall_seconds=100)
        out=evaluate_payback(**args);self.assertEqual(out['predicted_focus_token_cost'],5000)
        self.assertEqual(out['predicted_actor_horizon'],10);self.assertEqual(out['actor_wall_estimate'],4)
        self.assertEqual(len(out['actor_wall_samples']),3)

    def test_bad_or_unknown_usage_never_becomes_free(self):
        for field,value in [('status','error'),('input_tokens',None),('output_tokens',True),('wall_seconds',float('nan')),('wall_seconds',float('inf')),('wall_seconds',-1)]:
            with self.subTest(field=field,value=value):
                args=inputs();args['calls'][0][field]=value
                with self.assertRaises(ValueError):evaluate_payback(**args)
        for key,value in [('remaining_calls',True),('remaining_wall_seconds',float('nan')),('summary_input_tokens',0),('output_cap',1.0)]:
            args=inputs();args[key]=value
            with self.assertRaises(ValueError):evaluate_payback(**args)

    def test_accepted_focus_binding_and_first_history_contradictions(self):
        for index in [1,4,True]:
            args=inputs();args['controls'][0]['after_model_calls']=index
            with self.assertRaises(ValueError):evaluate_payback(**args)
        args=inputs();args['opportunity_index']=1
        with self.assertRaises(ValueError):evaluate_payback(**args)
        args=inputs();args['controls'][0]['accepted']='true'
        with self.assertRaises(ValueError):evaluate_payback(**args)
        args=inputs();args['controls'][0]['revision']=True
        with self.assertRaises(ValueError):evaluate_payback(**args)
        args=inputs();args['opportunity_index']=4
        with self.assertRaises(ValueError):evaluate_payback(**args)
        args=inputs();args['calls'][2]['id']='call_001'
        with self.assertRaises(ValueError):evaluate_payback(**args)

if __name__=='__main__':unittest.main()
