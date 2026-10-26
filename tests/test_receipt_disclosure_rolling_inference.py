"""Handwritten integration fixtures: all transport/counting is replaced locally."""
from contextlib import ExitStack
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from checkpoint_attempt_usage import attempt_usage
from code_agent_interface import CODE_TOOLS
from context_preservation import compact,page_span
from receipt_reasoning_history import digest
from receipt_disclosure_rolling_inference import ReceiptDisclosureRollingInference
from receipt_disclosure_live import ReceiptDisclosureLiveConversation
from protocol_stable_history import StableReferenceConversation
from single_checkpoint_history import FIELDS
from test_receipt_disclosure_history import fixture
from test_receipt_disclosure_live import append,conversation


def config(mode='disclose'):
    return dict(receipt_disclosure_policy=mode,observation_page_characters=24000,
        checkpoint_policy='rolling_separate',rolling_checkpoint_max_opportunities=3,
        rolling_min_fresh_turns=3,read_views_enabled=False,inline_checkpoint_requirement='not_applicable',
        max_calls=20,max_total_tokens=450000,max_wall_seconds=1800,max_api_requests=160,
        max_output_tokens=4096,seed=157,agent_temperature=1.0,draft_temperature=0.7,
        model=dict(reasoning_budget_tokens=-1,tool_choice='auto',num_ctx=65536))


def run_fixture(mode='disclose',summary_mode='valid',n=7,expansion_at=5,max_calls=20):
    c=conversation(mode);events,spans=[],{};captured=[];pending=[];descriptors=[]
    counts=[]
    def measured(messages,tools):return 5000+4000*sum(m['role']=='assistant' for m in messages) if tools else 1000
    def count(cfg,messages,tools,timeout):
        counts.append(deepcopy(messages));return dict(input_tokens=measured(messages,tools),wall_seconds=0)
    def send(cfg,messages,output,timeout,tools):
        role='agent' if tools else 'focus';captured.append(dict(role=role,messages=deepcopy(messages),cfg=deepcopy(cfg)))
        tokens=measured(messages,tools)
        if not tools:
            if summary_mode=='unknown':response=dict(status='error',input_tokens=None,output_tokens=None,wall_seconds=0,error_kind='request_or_response')
            else:
                message=dict(role='assistant',content=json.dumps({k:['synthetic'] for k in FIELDS}) if summary_mode=='valid' else '{}')
                response=dict(status='ok',input_tokens=tokens,output_tokens=20,cached_input_tokens=0,wall_seconds=0,done_reason='stop',message=message)
        else:
            number=sum(r['role']=='agent' for r in captured)
            data=fixture(number)
            if number==expansion_at:
                fn={'name':'read_span','arguments':compact({'span_id':'outer-1','offset':7})}
                message={'role':'assistant','content':'','tool_calls':[{'id':f'paid-{number}','type':'function','function':fn}]}
                row={'id':f'expansion-{number}','assistant':'','action':fn,'observation':page_span(spans,'outer-1',7,24000)}
                data=(message,[row],[{'call':'will-bind','span_id':row['id'],'stage':'model_tool','api_request_sent':False}],{row['id']:row})
            pending.append(data)
            response=dict(status='ok',input_tokens=tokens,output_tokens=20,cached_input_tokens=0,wall_seconds=0,done_reason='tool_calls',message=data[0],timings=dict(cache_n=0,prompt_n=tokens,predicted_n=20,prompt_ms=1,predicted_ms=1))
        (output/'response.json').write_text(json.dumps(response))
        return response
    cfg=config(mode);cfg['max_calls']=max_calls
    with tempfile.TemporaryDirectory() as tmp,ExitStack() as stack:
        for target in ('receipt_disclosure_rolling_inference.count_agent_input','receipt_disclosure_rolling_inference.count_summary_input','tool_choice_residual.count_input','fixed_budget_residual.count_input'):stack.enter_context(patch(target,side_effect=count))
        for target in ('tool_choice_residual.model_call','fixed_budget_residual.model_call'):stack.enter_context(patch(target,side_effect=send))
        infer=ReceiptDisclosureRollingInference(cfg,Path(tmp),conversation=c)
        error=None
        for _ in range(n):
            try:message=infer.call('agent',c.for_model()[0],CODE_TOOLS)
            except Exception as exc:error=exc;break
            data=pending.pop(0);assert message==data[0]
            descriptors.append(append(c,data,events,spans,call_id=infer.calls[-1]['id']))
            infer.api_requests=sum(e['api_request_sent'] for e in events)
        saved={p.stem:json.loads(p.read_text()) for p in Path(tmp).glob('*.json')}
        return dict(conversation=c,infer=infer,captured=captured,counts=counts,saved=saved,
                    error=error,events=events,spans=spans,descriptors=descriptors)


class ReceiptRollingTests(unittest.TestCase):
    def test_exact_class_and_configuration_required(self):
        class Sub(ReceiptDisclosureLiveConversation):pass
        for c,cfg in [(StableReferenceConversation('instructions',{}),config()),
                      (Sub('instructions',{},execution_scope='s',mode='disclose'),config()),
                      (conversation('full'),config()),(conversation(),dict(config(),checkpoint_policy='rolling_inline')),
                      (conversation(),dict(config(),observation_page_characters=12000))]:
            with tempfile.TemporaryDirectory() as tmp,self.assertRaises(ValueError):ReceiptDisclosureRollingInference(cfg,Path(tmp),conversation=c)

    def test_real_inference_admission_summary_and_disclosure_prefix(self):
        for mode in ('full','disclose'):
            r=run_fixture(mode);self.assertIsNone(r['error'])
            infer=r['infer'];conv=r['conversation']
            self.assertGreaterEqual(infer.checkpoint.revision,1)
            self.assertEqual(conv.disclosure_summary()['receipt_read_span_actions'],1)
            actors=[x for x in r['captured'] if x['role']=='agent'];focus=[x for x in r['captured'] if x['role']=='focus']
            self.assertEqual(len(actors),7);self.assertGreaterEqual(len(focus),1)
            self.assertEqual(len(attempt_usage(infer)),len(r['captured']))
            self.assertEqual(infer.tokens,sum(x['input_tokens']+x['output_tokens'] for x in infer.calls))
            self.assertEqual(infer.api_requests,24) # six actual fixture turns; explicit expansion sends no API.
            self.assertEqual(conv.disclosure_summary()['disclosed_turns'],6 if mode=='disclose' else 0)
            self.assertEqual(len(r['saved']['receipt_disclosure_inference_views']),7)
            for receipt,projection in zip(infer.receipt_views,infer.projections,strict=True):
                self.assertEqual(receipt['next_agent_call_id'],projection['next_agent_call_id'])
                self.assertEqual(receipt['normalized_history_sha256'],projection['original_history_sha256'])
            self.assertEqual([x['cfg']['seed'] for x in actors],list(range(157,164)))
            self.assertEqual([x['cfg']['seed'] for x in focus],list(range(157,157+len(focus))))
            self.assertNotIn('archived_receipt_index_v1',actors[0]['messages'][-1]['content'])
            self.assertEqual('archived_receipt_index_v1' in json.dumps(actors[1]['messages'][2:]),mode=='disclose')
            # Existing raw archive is complete even after a rolling summary installation.
            self.assertEqual(conv.archive(),r['spans'])
            self.assertEqual(len([m for m in conv.messages() if m['role']=='assistant']),7)

    def test_unknown_summary_cost_kept_and_no_next_action(self):
        r=run_fixture(summary_mode='unknown')
        self.assertIsNotNone(r['error']);self.assertEqual(r['captured'][-1]['role'],'focus')
        self.assertEqual(sum(x['role']=='agent' for x in r['captured']),3)
        usage=attempt_usage(r['infer']);self.assertEqual(len(usage),4)
        self.assertEqual(sum(x['status']!='ok' for x in usage),1)
        self.assertIsNone(usage[-1]['input_tokens']);self.assertIsNone(usage[-1]['output_tokens'])
        self.assertEqual(r['conversation'].disclosure_summary()['closed_turns'],3)
        self.assertFalse(r['conversation'].contract_failed)
        with self.assertRaises(ValueError):r['infer'].call('agent',r['conversation'].for_model()[0],CODE_TOOLS)

    def test_invalid_summary_keeps_view_and_charges_focus(self):
        r=run_fixture(summary_mode='invalid')
        self.assertIsNone(r['error']);self.assertEqual(r['infer'].checkpoint.revision,0)
        self.assertGreater(sum(c['role']=='focus' for c in r['infer'].calls),0)
        self.assertEqual(r['infer'].tokens,sum(c['input_tokens']+c['output_tokens'] for c in r['infer'].calls))

    def test_no_room_for_summary_is_not_a_free_generated_reply(self):
        r=run_fixture(n=4,max_calls=4)
        self.assertIsNone(r['error']);self.assertEqual(len(r['captured']),4)
        self.assertTrue(all(x['role']=='agent' for x in r['captured']))
        self.assertEqual(r['infer'].checkpoint.events[0]['reason'],'insufficient_shared_call_budget')

    def test_snapshot_matches_reconstruction_at_every_agent_projection(self):
        from receipt_disclosure_live import rebuild_disclosure_conversation
        r=run_fixture(n=7)
        for view in r['infer'].receipt_views:
            n=view['closed_turns'];turns=r['descriptors'][:n]
            calls={t['call_id'] for t in turns};events=[e for e in r['events'] if e['call'] in calls]
            spans={e['span_id']:r['spans'][e['span_id']] for e in events}
            c=rebuild_disclosure_conversation('instructions',{'synthetic':True},execution_scope='synthetic-live',mode='disclose',page_limit=24000,turns=turns,events=events,spans=spans)
            self.assertEqual(digest(c.disclosure_snapshot()),view['receipt_snapshot_sha256'])
            self.assertEqual(digest(c.for_model()[0]),view['normalized_history_sha256'])


if __name__=='__main__':unittest.main()
