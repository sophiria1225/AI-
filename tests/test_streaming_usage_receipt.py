import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from streaming_usage_receipt import CompletionReceipt, SSEDecoder, StreamProtocolError


def chunk(delta=None, finish=None, usage=None, **extra):
    result={'id':'chat-1','model':'local','system_fingerprint':'fixed-build',
        'object':'chat.completion.chunk','choices':[] if delta is None else
        [{'index':0,'delta':delta,'finish_reason':finish}]}
    if usage is not None:
        result['usage']=usage
    return json.dumps({**result,**extra},ensure_ascii=False)


def terminal(receipt, reason='stop'):
    receipt.consume(chunk({},reason))
    receipt.consume(chunk(usage={'prompt_tokens':100,'completion_tokens':4,'total_tokens':104,
        'prompt_tokens_details':{'cached_tokens':80}}))


class StreamingUsageReceiptTests(unittest.TestCase):
    def test_utf8_and_crlf_split_at_every_byte(self):
        wire=('data: '+chunk({'content':'日本語'})+'\r\n\r\n: ping\r\n\r\n').encode()
        decoder=SSEDecoder();events=[]
        for b in wire:
            events.extend(decoder.feed(bytes([b])))
        decoder.finish()
        self.assertEqual(len(events),1)
        self.assertEqual(json.loads(events[0])['choices'][0]['delta']['content'],'日本語')

    def test_multiline_data_and_truncated_frame(self):
        decoder=SSEDecoder()
        self.assertEqual(decoder.feed(b'data: {\ndata: "a":1}\n\n'),['{\n"a":1}'])
        decoder.feed(b'data: incomplete')
        with self.assertRaises(StreamProtocolError):decoder.finish()

    def test_incomplete_stream_retains_only_lower_bound(self):
        r=CompletionReceipt()
        r.consume(chunk({'reasoning_content':'working'},timings={'predicted_n':3,'prompt_n':20,'cache_n':80}))
        s=r.summary()
        self.assertIsNone(s['input_tokens']);self.assertIsNone(s['output_tokens'])
        self.assertEqual(s['observed_output_tokens_lower_bound'],3)
        self.assertEqual(s['observed_input_tokens_lower_bound'],0)
        with self.assertRaises(StreamProtocolError):r.final_response()

    def test_terminal_usage_survives_missing_done_but_message_is_quarantined(self):
        r=CompletionReceipt();r.consume(chunk({'content':'Hello'}));terminal(r)
        self.assertTrue(r.summary()['terminal_usage_received'])
        self.assertEqual(r.summary()['input_tokens'],100)
        self.assertFalse(r.summary()['message_ready'])
        with self.assertRaises(StreamProtocolError):r.final_response()
        r.consume('[DONE]')
        self.assertEqual(r.final_response()['choices'][0]['message']['content'],'Hello')

    def test_tool_arguments_are_assembled_only_after_done(self):
        r=CompletionReceipt()
        r.consume(chunk({'tool_calls':[{'index':0,'id':'t1','type':'function',
            'function':{'name':'call','arguments':'{"x":'}}]}))
        r.consume(chunk({'tool_calls':[{'index':0,'function':{'arguments':'1}'}}]}))
        with self.assertRaises(StreamProtocolError):r.final_response()
        terminal(r,'tool_calls');r.consume('[DONE]')
        self.assertEqual(r.final_response()['choices'][0]['message']['tool_calls'][0]['function'],
                         {'name':'call','arguments':'{"x":1}'})

    def test_interleaved_parallel_tool_deltas_keep_identity(self):
        r=CompletionReceipt()
        for idx,name in [(1,'second'),(0,'first')]:
            r.consume(chunk({'tool_calls':[{'index':idx,'id':f't{idx}',
                'function':{'name':name,'arguments':'{}'}}]}))
        terminal(r,'tool_calls');r.consume('[DONE]')
        self.assertEqual([c['id'] for c in r.final_response()['choices'][0]['message']['tool_calls']],['t0','t1'])

    def test_identity_change_and_counter_regression_are_sticky_errors(self):
        for invalid in [chunk({'content':'x'},id='chat-2'),chunk({'content':'x'},timings={'predicted_n':1})]:
            r=CompletionReceipt();r.consume(chunk({'content':'a'},timings={'predicted_n':2}))
            with self.assertRaises(StreamProtocolError):r.consume(invalid)
            self.assertFalse(r.summary()['protocol_valid'])
            with self.assertRaises(StreamProtocolError):r.consume(chunk({}))

    def test_terminal_usage_must_follow_finish_and_match_counts(self):
        for usage in [{'prompt_tokens':100,'completion_tokens':4,'total_tokens':105},
                      {'prompt_tokens':True,'completion_tokens':4,'total_tokens':5},
                      {'prompt_tokens':100,'completion_tokens':1,'total_tokens':101}]:
            r=CompletionReceipt();r.consume(chunk({'content':'x'},timings={'predicted_n':2}));r.consume(chunk({},'stop'))
            with self.assertRaises(StreamProtocolError):r.consume(chunk(usage=usage))
        r=CompletionReceipt()
        with self.assertRaises(StreamProtocolError):r.consume(chunk(usage={'prompt_tokens':1,'completion_tokens':1,'total_tokens':2}))

    def test_wire_and_event_caps(self):
        for decoder,wire in [(SSEDecoder(20,10),b'data: '+b'x'*11),(SSEDecoder(20,10),b':123456\n\n'*3)]:
            with self.assertRaises(StreamProtocolError):decoder.feed(wire)
            with self.assertRaises(StreamProtocolError):decoder.feed(b'')

    def test_missing_done_finish_usage_or_choice_does_not_authorize(self):
        for text in ['[DONE]',chunk({},'unsupported'),chunk({'role':'user'}),
                     chunk({},choices=[{'index':1,'delta':{}}])]:
            r=CompletionReceipt()
            with self.assertRaises(StreamProtocolError):r.consume(text)
            with self.assertRaises(StreamProtocolError):r.final_response()

    def test_invalid_utf8_and_unknown_sse_field(self):
        for wire in [b'data: \xff\n\n',b'event: unknown\n\n']:
            with self.assertRaises(StreamProtocolError):SSEDecoder().feed(wire)

    def test_duplicate_or_incomplete_tool_ids_do_not_return_message(self):
        for calls in [[{'index':2,'id':'t','function':{'name':'f','arguments':'{}'}}],
                      [{'index':0,'function':{'name':'f','arguments':'{}'}}],
                      [{'index':0,'id':'t','function':{'name':'f','arguments':'{}'}},
                       {'index':1,'id':'t','function':{'name':'g','arguments':'{}'}}]]:
            r=CompletionReceipt();r.consume(chunk({'tool_calls':calls}));terminal(r,'tool_calls');r.consume('[DONE]')
            self.assertFalse(r.summary()['message_ready'])
            self.assertTrue(r.summary()['terminal_usage_received'])
            with self.assertRaises(StreamProtocolError):r.final_response()

    def test_duplicate_fields_nonfinite_numbers_and_nonobject_tools_fail_closed(self):
        for text in [chunk({'tool_calls':[None]}), chunk({}).replace('"choices":', '"id":"duplicate","choices":'),
                     chunk({},timings={'predicted_n':float('nan')})]:
            r=CompletionReceipt()
            with self.assertRaises(StreamProtocolError):r.consume(text)
            self.assertFalse(r.summary()['protocol_valid'])


if __name__=='__main__':unittest.main()
