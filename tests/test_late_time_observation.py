import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from api_error_comparison import task_snapshot
from budget_observation import notification
from budget_visibility_comparison import CanonicalBudgetInference
from late_time_observation import LateClockInference, effective_visibility
from run_context_comparison import BudgetStop


def config():
    return {'model': {'model': 'fixture', 'num_ctx': 1000, 'call_timeout_seconds': 60},
        'seed': 42, 'draft_temperature': .7, 'agent_temperature': 1,
        'max_calls': 4, 'max_wall_seconds': 60, 'max_total_tokens': 300,
        'max_api_requests': 8, 'max_output_tokens': 40}


def sender(captured, *, cached=0):
    def send(cfg, messages, out, wall, tools):
        captured.append({'messages': copy.deepcopy(messages), 'cfg': copy.deepcopy(cfg), 'wall': wall})
        result = {'status': 'ok', 'input_tokens': 60, 'output_tokens': 10,
            'wall_seconds': 1, 'done_reason': 'tool_calls', 'cached_input_tokens': cached,
            'message': {'role': 'assistant', 'content': 'fixture', 'tool_calls': []},
            'timings': {'cache_n': cached, 'prompt_n': 60-cached,
                'predicted_n': 10, 'prompt_ms': 100, 'predicted_ms': 100}}
        (out/'response.json').write_text(json.dumps(result))
        return result
    return send


class LateClockTests(unittest.TestCase):
    def make(self, folder, policy='late_half', cls=LateClockInference):
        with patch('late_time_observation.time.monotonic', return_value=0):
            return cls(config(), Path(folder), time_visibility=policy)

    def test_exact_half_boundary_and_invalid_values(self):
        for remaining, expected in [(60,'not_exposed'),(31,'not_exposed'),(30,'measured'),(0,'measured')]:
            state = task_snapshot(config(), [], 0, 60-remaining)
            self.assertEqual(effective_visibility('late_half',state,60), expected)
            self.assertEqual(effective_visibility('measured',state,60), 'measured')
        for value in (-1,61,True,1.5,None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                effective_visibility('late_half',{'remaining':{'wall_seconds_at_snapshot':value}},60)

    def test_switch_preserves_history_and_all_previous_cost(self):
        history=[{'role':'user','content':'historical wall_seconds_at_snapshot: 59'}]
        original=copy.deepcopy(history)
        with tempfile.TemporaryDirectory() as folder:
            r=self.make(folder); captured=[]
            for elapsed in (29,30):
                with patch('late_time_observation.time.monotonic',return_value=elapsed), \
                     patch('residual_output_budget.count_input',return_value={'input_tokens':60}), \
                     patch('residual_output_budget.model_call',side_effect=sender(captured)):
                    r.call('agent',history,[])
            self.assertEqual(history,original)
            self.assertEqual([s['effective_time_visibility'] for s in r.snapshots],['not_exposed','measured'])
            self.assertEqual([x['wall'] for x in captured],[31,30])
            self.assertNotIn('wall_seconds_at_snapshot',captured[0]['messages'][-1]['content'])
            self.assertIn('wall_seconds_at_snapshot',captured[1]['messages'][-1]['content'])
            self.assertTrue(all(x['messages'][:-1]==history for x in captured))
            self.assertEqual(r.tokens,140)
            self.assertEqual(r.snapshots[1]['measured_state']['used']['logical_input_plus_output_tokens'],70)

    def test_always_measured_matches_prior_canonical_adapter_input_and_admission(self):
        outputs=[]
        history=[{'role':'assistant','tool_calls':[{'id':'opaque-id','function':{'name':'f','arguments':'{}'}}]},
                 {'role':'tool','tool_call_id':'opaque-id','content':'fixture'}]
        for cls in (CanonicalBudgetInference,LateClockInference):
            with tempfile.TemporaryDirectory() as folder:
                r=self.make(folder,'measured',cls)
                with patch('late_time_observation.time.monotonic',return_value=29), \
                     patch('residual_output_budget.count_input',return_value={'input_tokens':60}), \
                     patch('residual_output_budget.model_call',side_effect=sender(outputs)):
                    r.call('agent',history,[])
        self.assertEqual(outputs[0],outputs[1])

    def test_count_crossing_half_does_not_rewrite_sent_snapshot_or_extend_deadline(self):
        with tempfile.TemporaryDirectory() as folder:
            r=self.make(folder); now=[29]; captured=[]
            def count(*a,**kw): now[0]=40;return {'input_tokens':60}
            with patch('late_time_observation.time.monotonic',side_effect=lambda:now[0]), \
                 patch('residual_output_budget.count_input',side_effect=count), \
                 patch('residual_output_budget.model_call',side_effect=sender(captured)):
                r.call('agent',[],[])
            self.assertEqual(r.snapshots[0]['effective_time_visibility'],'not_exposed')
            self.assertEqual(captured[0]['wall'],20)

    def test_real_deadline_rejects_both_policies_before_count_or_dispatch(self):
        for policy in ('measured','late_half'):
            with self.subTest(policy=policy), tempfile.TemporaryDirectory() as folder:
                r=self.make(folder,policy)
                with patch('late_time_observation.time.monotonic',return_value=61), \
                     patch('residual_output_budget.count_input') as count, \
                     patch('residual_output_budget.model_call') as send:
                    with self.assertRaisesRegex(BudgetStop,'wall_limit'):r.call('agent',[],[])
                    count.assert_not_called();send.assert_not_called()
                self.assertFalse(r.snapshots[0]['model_attempted'])

    def test_unknown_dispatch_cannot_be_retried_or_change_policy(self):
        with tempfile.TemporaryDirectory() as folder:
            r=self.make(folder)
            with patch('late_time_observation.time.monotonic',return_value=30), \
                 patch('residual_output_budget.count_input',return_value={'input_tokens':60}) as count, \
                 patch('residual_output_budget.model_call',side_effect=OSError('fixture')) as send:
                with self.assertRaises(OSError):r.call('agent',[],[])
                with self.assertRaisesRegex(RuntimeError,'stopped_after_OSError'):r.call('agent',[],[])
                self.assertEqual(send.call_count,1);self.assertEqual(count.call_count,1)
            self.assertTrue(r.snapshots[0]['usage_unknown'])
            self.assertFalse(r.snapshots[0]['terminal_usage_recorded'])
            with self.assertRaises(AttributeError):r.time_visibility='measured'

    def test_warm_initial_cache_retains_cost_but_stops(self):
        with tempfile.TemporaryDirectory() as folder:
            r=self.make(folder)
            with patch('late_time_observation.time.monotonic',return_value=10), \
                 patch('residual_output_budget.count_input',return_value={'input_tokens':60}), \
                 patch('residual_output_budget.model_call',side_effect=sender([],cached=1)):
                with self.assertRaisesRegex(ValueError,'reused_prior_condition_cache'):r.call('agent',[],[])
            self.assertEqual(r.tokens,70)
            self.assertFalse(r.snapshots[0]['first_input_measurement']['state_confirmed'])


if __name__=='__main__':
    unittest.main()
