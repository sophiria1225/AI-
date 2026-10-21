import copy
import sys
import json
import subprocess
import tempfile
from pathlib import Path
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from compare_generic_guidance import compare, MATCHED_KEYS


def fixture():
    plans=[]; summaries=[]; budgets=[]
    for arm in ('base','guided'):
        plan={k:None for k in MATCHED_KEYS};plan.update(task_ids=['a','b'],max_calls=80,
            run_order=[['a',arm,arm+'1'],['b',arm,arm+'2']])
        trials=[]; costs=[]
        for i,(task,_,rid) in enumerate(plan['run_order']):
            success=(arm=='base') != bool(i)
            t=dict(task_id=task,arm=arm,run_id=rid,model_calls=2,known_total_tokens=100,
                   unknown_usage_calls=0,declared_complete=True,stop_reason='complete',wall_seconds=5.0,
                   evaluation=dict(official_success=success,evaluation_returned_to_model=False),
                   audit_errors=[],source_hashes={'summary':rid+'s','usage':rid+'u'})
            b={k:t[k] for k in ('run_id','model_calls','known_total_tokens','unknown_usage_calls','declared_complete','stop_reason','wall_seconds')}
            b.update(limits={'max_calls':80},api_requests=4,output_limit_finishes=0,
                     source_sha256={'summary.json':rid+'s','usage.json':rid+'u'})
            trials.append(t);costs.append(b)
        plans.append(plan);summaries.append(dict(trials=trials,pending=[],audit_errors=0,
            total_model_calls=4,known_total_tokens=200,unknown_usage_calls=0));budgets.append(dict(trials=costs))
    return [*plans,*summaries,*budgets]


class GuidanceComparisonTests(unittest.TestCase):
    def test_improvements_and_regressions_preserved(self):
        r=compare(*fixture())
        self.assertEqual(r['outcome_counts'],{'worsened':1,'improved':1})
        self.assertEqual(r['exact_total_token_delta'],0)

    def test_unknown_usage_never_becomes_exact_saving(self):
        x=fixture();x[2]['trials'][0]['unknown_usage_calls']=1;x[2]['unknown_usage_calls']=1
        x[4]['trials'][0]['unknown_usage_calls']=1
        r=compare(*x)
        self.assertIsNone(r['exact_total_token_delta'])
        self.assertFalse(r['totals']['baseline']['tokens_exact'])

    def test_pending_or_missing_task_refused(self):
        x=fixture();x[3]['pending']=['another']
        with self.assertRaises(ValueError):compare(*x)
        x=fixture();x[3]['trials'].pop()
        with self.assertRaises(ValueError):compare(*x)

    def test_order_duplicates_and_budget_changes_refused(self):
        for mutate in (
            lambda x:x[3]['trials'].reverse(),
            lambda x:x[5]['trials'].__setitem__(1,copy.deepcopy(x[5]['trials'][0])),
            lambda x:x[1].__setitem__('max_calls',90)):
            x=fixture();mutate(x)
            with self.assertRaises(ValueError):compare(*x)

    def test_wrong_source_and_exposed_evaluation_refused(self):
        x=fixture();x[4]['trials'][0]['source_sha256']['usage.json']='wrong'
        with self.assertRaises(ValueError):compare(*x)
        x=fixture();x[3]['trials'][0]['evaluation']['evaluation_returned_to_model']=True
        with self.assertRaises(ValueError):compare(*x)

    def test_wrong_totals_and_usage_disagreement_refused(self):
        x=fixture();x[2]['known_total_tokens']=201
        with self.assertRaises(ValueError):compare(*x)
        x=fixture();x[4]['trials'][0]['model_calls']=3
        with self.assertRaises(ValueError):compare(*x)

    def test_cli_refuses_running_batch_before_reading_results(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            for phase in ('P22','P24'):
                p=root/'records/context_pilot'/f'{phase}_batch_v01/status.json'
                p.parent.mkdir(parents=True)
                p.write_text(json.dumps({'status':'complete' if phase=='P22' else 'running'}))
            script=Path(__file__).resolve().parents[1]/'scripts/compare_generic_guidance.py'
            p=subprocess.run([sys.executable,str(script),'--repo-root',d,'--storage-root',d,
                              '--output',str(root/'out.json')],capture_output=True,text=True)
            self.assertNotEqual(p.returncode,0)
            self.assertIn('wait for both full batches',p.stderr)
            self.assertNotIn('FileNotFoundError',p.stderr)
            self.assertFalse((root/'out.json').exists())


if __name__=='__main__':
    unittest.main()
