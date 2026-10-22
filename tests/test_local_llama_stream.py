import json
from pathlib import Path
import signal
import sys
import tempfile
import time
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from local_llama import payload_for
from local_llama_stream import model_call_stream,stream_payload
from test_streaming_usage_receipt import chunk


class FakeResponse:
    def __init__(self,events):
        self.chunks=iter(('data: '+e+'\n\n').encode() for e in events)
        self.headers={'Content-Type':'text/event-stream; charset=utf-8'}
    def read1(self,n):return next(self.chunks,b'')
    def __enter__(self):return self
    def __exit__(self,*args):return False


class LocalLlamaStreamTests(unittest.TestCase):
    def config(self):
        return {'model':'local','seed':1,'temperature':1.0,'num_predict':128,
            'call_timeout_seconds':10,'expected_system_fingerprint':'fixed-build'}
    def events(self,done=True):
        values=[chunk({'content':'hello'},timings={'predicted_n':2,'prompt_n':20,'cache_n':80}),
            chunk({},'stop'),chunk(usage={'prompt_tokens':100,'completion_tokens':4,'total_tokens':104})]
        return values+(['[DONE]'] if done else [])

    def test_payload_only_changes_transport_and_telemetry(self):
        config=self.config();messages=[{'role':'user','content':'test'}]
        base=payload_for(config,messages,[]);stream=stream_payload(config,messages,[])
        self.assertEqual({k for k in stream if stream.get(k)!=base.get(k)},
            {'stream','stream_options','timings_per_token','return_progress'})

    def test_complete_response_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as d:
            result=model_call_stream(self.config(),[],d,10,[],opener=lambda *a,**k:FakeResponse(self.events()))
            self.assertEqual(result['status'],'ok');self.assertEqual(result['input_tokens'],100)
            self.assertEqual(result['message']['content'],'hello')
            self.assertTrue((Path(d)/'wire_private.sse').exists())
            with self.assertRaises(FileExistsError):model_call_stream(self.config(),[],d,10,[])

    def test_disconnect_does_not_promote_partial_counts_or_message(self):
        with tempfile.TemporaryDirectory() as d:
            result=model_call_stream(self.config(),[],d,10,[],stop_after_observed_tokens=2,
                opener=lambda *a,**k:FakeResponse(self.events()))
            self.assertEqual(result['error_kind'],'intentional_probe_disconnect')
            self.assertIsNone(result['output_tokens']);self.assertEqual(result['message']['content'],'')
            self.assertEqual(result['stream_receipt']['observed_output_tokens_lower_bound'],2)

    def test_missing_done_keeps_terminal_cost_and_quarantines_message(self):
        with tempfile.TemporaryDirectory() as d:
            result=model_call_stream(self.config(),[],d,10,[],opener=lambda *a,**k:FakeResponse(self.events(False)))
            self.assertEqual(result['status'],'error');self.assertEqual(result['output_tokens'],4)
            self.assertEqual(result['message']['content'],'')

    def test_deadline_handler_is_restored_and_remote_backend_refused(self):
        previous=signal.getsignal(signal.SIGALRM)
        with tempfile.TemporaryDirectory() as d:
            def fail(*a,**k):raise TimeoutError('test')
            result=model_call_stream(self.config(),[],d,10,[],opener=fail)
            self.assertEqual(result['error_kind'],'timeout')
        self.assertEqual(signal.getsignal(signal.SIGALRM),previous)
        self.assertEqual(signal.getitimer(signal.ITIMER_REAL),(0.0,0.0))
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):model_call_stream({**self.config(),'base_url':'https://example.com'},[],d,10,[])

    def test_absolute_deadline_interrupts_a_blocked_transport(self):
        with tempfile.TemporaryDirectory() as d:
            def blocked(*a,**k):
                time.sleep(1)
                return FakeResponse(self.events())
            result=model_call_stream(self.config(),[],d,0.02,[],opener=blocked)
            self.assertEqual(result['error_kind'],'timeout')
            self.assertLess(result['wall_seconds'],0.5)

    def test_changed_server_fingerprint_quarantines_response(self):
        with tempfile.TemporaryDirectory() as d:
            result=model_call_stream({**self.config(),'expected_system_fingerprint':'different'},[],d,10,[],
                opener=lambda *a,**k:FakeResponse(self.events()))
            self.assertEqual(result['status'],'error')
            self.assertFalse(result['stream_receipt']['protocol_valid'])
            self.assertEqual(result['message']['content'],'')


if __name__=='__main__':unittest.main()
