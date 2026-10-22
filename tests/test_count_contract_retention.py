import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import count_contract_retention as p

class CountRetentionTests(unittest.TestCase):
    def tree(self,root):
        plan=json.loads((p.ROOT/p.PLAN).read_text())
        for relative in plan['implementation_sources']:
            path=root/relative;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('test source')
        (root/'configs').mkdir();p.save(root/p.PLAN,plan)
        (root/'reports').mkdir();p.save(root/'reports/P44_documentation_origin.json',{
            'rows':[{'views':{'full_keep':{'input_tokens':100}}} for _ in range(4)]})
        (root/'.runtime').mkdir();p.save(root/'.runtime/model_server.json',{
            'status':'ready','pid':1,'supervisor_pid':2,'record_directory':'records/server'})
        return root/'records/context_pilot/P53_contract_retention_counts_v01/status.json'

    @contextlib.contextmanager
    def dependencies(self,root,error=False):
        original={'model':{'base_url':'http://127.0.0.1:8011'},'agent_temperature':1,'seed':42,
                  'max_output_tokens':4096,'model_selection':'fixed'}
        inputs=[{'source_run':f'P29_{i:02d}_CODE','boundary_manifest_sha256':'fixed','control':{},
                 'messages':{name:[{'role':'user','content':'test'}] for name in p.MODES}} for i in range(1,5)]
        counts=[{'input_tokens':n,'wall_seconds':0.001} for n in [100,90,95,98]*4]
        with contextlib.ExitStack() as stack:
            stack.enter_context(patch.object(p,'ROOT',root))
            stack.enter_context(patch.object(p.subprocess,'check_output',side_effect=['fixed','']))
            stack.enter_context(patch.object(p,'prepare',return_value=(original,inputs)))
            stack.enter_context(patch.object(p,'check_live_model'))
            stack.enter_context(patch.object(p,'get',side_effect=lambda cfg,path:
                [{'id':0,'is_processing':False}] if path=='/slots' else {}))
            counter=stack.enter_context(patch.object(p,'count_input',side_effect=TimeoutError('test') if error else counts))
            stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
            yield counter

    def test_all_sixteen_counts_and_zero_generations(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);status=self.tree(root)
            with self.dependencies(root) as count:p.run(root,'fixed')
            data=json.loads(status.read_text())
            self.assertEqual(count.call_count,16);self.assertEqual(data['status'],'complete')
            self.assertEqual(data['model_generations'],0)
            self.assertEqual(data['count_requests_completed'],16)
            self.assertEqual(data['rows'][0]['tokens_removed'],{
                'all_documented_details':10,'used_since_document':5,'all_parameters_observed':2})
            self.assertFalse(any(v['passed'] for v in data['allocation_gate'].values()))

    def test_count_failure_stops_without_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);status=self.tree(root)
            with self.dependencies(root,True) as count:
                with self.assertRaises(TimeoutError):p.run(root,'fixed')
            data=json.loads(status.read_text())
            self.assertEqual(data['status'],'stopped');self.assertEqual(count.call_count,1)
            self.assertEqual(data['count_requests_attempted'],1);self.assertEqual(data['count_requests_completed'],0)
            self.assertEqual(data['model_generations'],0)
            self.assertEqual(len(data['not_attempted_inputs']),15)

if __name__=='__main__':unittest.main()
