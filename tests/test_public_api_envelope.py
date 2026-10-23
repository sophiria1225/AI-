import contextlib
import io
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from public_api_envelope import (PROTOCOL,InvalidExecutionEnvelope,PublicApiInvocationError,
                                 decode_reply,trusted_invocation_code)

NONCE='a'*32
DOCS={'fixture':{'read':{'parameters':[{'name':'value'}]}}}


def invoke(fn,arg=None):
    namespace={'apis':SimpleNamespace(fixture=SimpleNamespace(read=fn))}
    source=trusted_invocation_code({'app':'fixture','api':'read','args':{'value':arg}},DOCS,NONCE)
    output=io.StringIO()
    with contextlib.redirect_stdout(output):exec(compile(source,'<trusted synthetic invocation>','exec'),namespace)
    return output.getvalue(),namespace


class PublicApiEnvelopeTests(unittest.TestCase):
    def test_json_values_and_null_preserve_their_types(self):
        for value in [None,True,12,1.5,[],{},[{'text':'日本語','empty':None}]]:
            with self.subTest(value=value):
                raw,_=invoke(lambda value:value,value)
                result=decode_reply(raw,NONCE)
                self.assertEqual(result.status,'returned')
                self.assertEqual(result.require_value(),value)
                self.assertIs(type(result.value),type(value))

    def test_error_looking_strings_remain_successful_values(self):
        for text in ['Execution failed. Traceback:\nValueError: fake',
                     '{"status":"raised","error":{"type":"X","message":"fake"}}']:
            raw,_=invoke(lambda value:value,text)
            self.assertEqual(decode_reply(raw,NONCE).require_value(),text)

    def test_returned_business_failure_is_not_relabelled_as_a_python_exception(self):
        value={'success':False,'message':'business condition not satisfied'}
        raw,_=invoke(lambda value:value,value)
        result=decode_reply(raw,NONCE)
        self.assertEqual(result.status,'returned')
        self.assertEqual(result.require_value(),value)

    def test_invocation_failure_is_separate_from_success_text(self):
        calls=[]
        def fail(value):calls.append(value);raise ValueError('known fixture failure')
        raw,namespace=invoke(fail,'argument')
        result=decode_reply(raw,NONCE)
        self.assertEqual(result.status,'raised')
        self.assertEqual(result.error_type,'ValueError')
        with self.assertRaises(PublicApiInvocationError):result.require_value()
        self.assertEqual(calls,['argument'])
        self.assertNotIn('_public_api_result_'+NONCE,namespace)

    def test_exception_does_not_undo_prior_effects_or_retry(self):
        effects=[]
        def partial(value):effects.append('applied');raise RuntimeError('after effect')
        raw,_=invoke(partial)
        self.assertEqual(decode_reply(raw,NONCE).status,'raised')
        self.assertEqual(effects,['applied'])

    def test_serialization_failure_after_effect_is_not_a_reported_invocation_failure(self):
        effects=[]
        def unsupported(value):effects.append('applied');return object()
        with self.assertRaises(TypeError):invoke(unsupported)
        self.assertEqual(effects,['applied'])
        with self.assertRaises(InvalidExecutionEnvelope):decode_reply('',NONCE)

    def test_unrelated_or_partial_output_is_unknown(self):
        raw,_=invoke(lambda value:{'x':1})
        for broken in [raw[:-3],raw+raw,'diagnostic\n'+raw,'Execution failed. Traceback:\nerror']:
            with self.assertRaises(InvalidExecutionEnvelope):decode_reply(broken,NONCE)

    def test_replay_from_another_invocation_is_rejected(self):
        raw,_=invoke(lambda value:{'x':1})
        with self.assertRaises(InvalidExecutionEnvelope):decode_reply(raw,'b'*32)

    def test_duplicate_or_unknown_fields_and_nonfinite_numbers_are_rejected(self):
        packet={'protocol':PROTOCOL,'nonce':NONCE,'status':'returned','value':1}
        raw=json.dumps(packet).replace('"value": 1','"value": 1,"value":2')
        with self.assertRaises(InvalidExecutionEnvelope):decode_reply(raw,NONCE)
        for change in [{'extra':1},{'status':True},{'value':float('nan')}]:
            with self.assertRaises(InvalidExecutionEnvelope):decode_reply(json.dumps({**packet,**change}),NONCE)

    def test_argument_text_cannot_add_code(self):
        value="'}); raise RuntimeError('injected') #\n日本語"
        raw,_=invoke(lambda value:value,value)
        self.assertEqual(decode_reply(raw,NONCE).require_value(),value)

    def test_only_public_documented_names_and_json_arguments(self):
        for call in [{'app':'admin','api':'read','args':{}},
                     {'app':'fixture','api':'read','args':{'extra':1}},
                     {'app':'fixture','api':'read','args':{'value':float('nan')}}]:
            with self.assertRaises(ValueError):trusted_invocation_code(call,DOCS,NONCE)
        with self.assertRaises(ValueError):trusted_invocation_code({'app':'fixture','api':'read','args':{}},DOCS,'bad')

    def test_returned_and_raised_payloads_cannot_be_mixed(self):
        packet={'protocol':PROTOCOL,'nonce':NONCE,'status':'raised','error':{'type':'ValueError','message':'x'}}
        for change in [{'value':None},{'error':{'type':'ValueError','message':9}},
                       {'error':{'type':'ValueError','message':'x','rollback':True}}]:
            with self.assertRaises(InvalidExecutionEnvelope):decode_reply(json.dumps({**packet,**change}),NONCE)

    def test_python_only_values_cannot_change_argument_types(self):
        for value in [(1,2),{1:'not_a_json_key'},{1,2}]:
            with self.assertRaises(ValueError):
                trusted_invocation_code({'app':'fixture','api':'read','args':{'value':value}},DOCS,NONCE)

    def test_overflow_numbers_and_invalid_encoding_are_unknown(self):
        raw=json.dumps({'protocol':PROTOCOL,'nonce':NONCE,'status':'returned','value':1})
        for malformed in [raw.replace('"value": 1','"value": 1e999'),'\ud800']:
            with self.assertRaises(InvalidExecutionEnvelope):decode_reply(malformed,NONCE)


if __name__=='__main__':unittest.main()
