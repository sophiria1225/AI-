import contextlib
import io
import json
from pathlib import Path
import signal
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import probe_stream_receipts_v02 as p


class ProbeIntegrationTests(unittest.TestCase):
    def setup_tree(self,root):
        (root/'configs').mkdir();(root/'scripts').mkdir();(root/'reports').mkdir()
        (root/'.runtime').mkdir()
        (root/p.PLAN).write_bytes((p.ROOT/p.PLAN).read_bytes())
        for name in ('probe_stream_receipts_v02.py','streaming_usage_receipt.py','local_llama_stream.py',
                     'local_llama.py','inference_cache_control.py','model_provenance.py'):
            (root/'scripts'/name).write_bytes((p.ROOT/'scripts'/name).read_bytes())
        runtime={'status':'ready','pid':1,'supervisor_pid':2,'record_directory':'records/server'}
        p.save(root/'.runtime/model_server.json',runtime)
        return root/'records/context_pilot/P51_stream_receipts_v02/status.json'

    def fake_response(self,cfg,messages,folder,remaining,tools,**kwargs):
        if kwargs.get('stop_after_observed_tokens'):
            result={'status':'error','input_tokens':None,'output_tokens':None,
                'message':{'role':'assistant','content':''},'error_kind':'intentional_probe_disconnect',
                'stream_receipt':{'message_ready':False,'terminal_usage_received':False,
                                  'observed_output_tokens_lower_bound':4}}
        else:
            result={'status':'ok','input_tokens':100,'output_tokens':8,'cached_input_tokens':0,
                'timings':{'cache_n':0,'prompt_n':100,'predicted_n':8,'prompt_ms':1,'predicted_ms':1},
                'message':{'role':'assistant','content':'synthetic'}}
        p.save(folder/'response.json',result)
        return result

    @contextlib.contextmanager
    def dependencies(self,root,check_error=None,model_error=None):
        identity=({'revision':'pinned','quantization':'fixed','runtime':{'commit':'fixed'}},
                  {'status':'verified'},root/'models/weights.gguf')
        with contextlib.ExitStack() as stack:
            stack.enter_context(patch.object(p,'ROOT',root))
            stack.enter_context(patch.object(p.subprocess,'check_output',side_effect=['fixed\n','']))
            checked=stack.enter_context(patch.object(p,'check_live_model',return_value=identity,
                                                    side_effect=check_error))
            stack.enter_context(patch.object(p,'get',side_effect=lambda cfg,path:
                [{'id':0,'is_processing':False}] if path=='/slots' else {}))
            counted=stack.enter_context(patch.object(p,'count_input',return_value={
                'input_tokens':100,'wall_seconds':0.001}))
            model=stack.enter_context(patch.object(p,'model_call',side_effect=model_error or self.fake_response))
            stream=stack.enter_context(patch.object(p,'model_call_stream',side_effect=self.fake_response))
            stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
            yield checked,counted,model,stream

    def test_all_three_cases_persist_real_path_identity_and_unknown_disconnect(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);status=self.setup_tree(root)
            with self.dependencies(root) as (_,count,model,stream):p.run(root,'fixed')
            state=json.loads(status.read_text())
            self.assertEqual(state['status'],'complete')
            self.assertEqual(state['model_identity']['model_path'],'models/weights.gguf')
            self.assertEqual((count.call_count,model.call_count,stream.call_count),(3,1,2))
            self.assertEqual(state['known_total_tokens'],216)
            self.assertEqual(state['unknown_usage_calls'],1)
            self.assertEqual(state['not_attempted'],[])

    def test_initialization_failure_is_preserved_without_generation(self):
        previous=signal.getsignal(signal.SIGALRM)
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);status=self.setup_tree(root)
            with self.dependencies(root,check_error=ValueError('invalid identity')) as (_,count,model,stream):
                with self.assertRaises(ValueError):p.run(root,'fixed')
            state=json.loads(status.read_text())
            self.assertEqual(state['status'],'stopped')
            self.assertEqual(state['model_calls_attempted'],0)
            self.assertEqual((count.call_count,model.call_count,stream.call_count),(0,0,0))
            self.assertEqual(len(state['not_attempted']),3)
        self.assertEqual(signal.getsignal(signal.SIGALRM),previous)

    def test_unexpected_model_failure_stops_without_retry_or_later_cases(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);status=self.setup_tree(root)
            with self.dependencies(root,model_error=TimeoutError('synthetic')) as (_,count,model,stream):
                with self.assertRaises(TimeoutError):p.run(root,'fixed')
            state=json.loads(status.read_text())
            self.assertEqual(state['status'],'stopped')
            self.assertEqual(state['model_calls_attempted'],1)
            self.assertEqual(state['unknown_usage_calls'],1)
            self.assertEqual((count.call_count,model.call_count,stream.call_count),(1,1,0))
            self.assertEqual(state['not_attempted'],['stream_complete','stream_disconnect'])


if __name__=='__main__':unittest.main()
