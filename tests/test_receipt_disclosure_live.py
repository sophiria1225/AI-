from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from context_preservation import compact, page_span
from receipt_disclosure_history import FORMAT
from receipt_disclosure_live import (ReceiptDisclosureLiveConversation,
                                    rebuild_disclosure_conversation)
from test_receipt_disclosure_history import fixture


def conversation(mode='disclose', scope='synthetic-live', page_limit=24000):
    return ReceiptDisclosureLiveConversation('instructions', {'synthetic': True},
        execution_scope=scope, mode=mode, page_limit=page_limit)


def append(conv, data, events, spans, call_id=None):
    response, outer, new_events, archive = deepcopy(data)
    call_id = call_id or new_events[0]['call']
    for event in new_events: event['call'] = call_id
    events.extend(new_events); spans.update(archive)
    conv.append_closed_turn(response, outer, call_id=call_id, events=events, spans=spans)
    return {'call_id':call_id,'response':response,'outer_spans':outer,'pending_reads':0}


class LiveReceiptTests(unittest.TestCase):
    def test_both_modes_bind_all_evidence_and_only_index_differs(self):
        full, disclose = conversation('full'), conversation()
        self.assertEqual(full.for_model()[0],disclose.for_model()[0])
        for conv in (full,disclose):
            events,spans=[],{}
            append(conv,fixture(),events,spans)
            append(conv,fixture(2),events,spans)
        self.assertEqual(full.messages(),disclose.messages())
        self.assertEqual(full.archive(),disclose.archive())
        a,b=full.disclosure_snapshot(),disclose.disclosure_snapshot()
        self.assertEqual(a['committed_events_sha256'],b['committed_events_sha256'])
        self.assertEqual((a['eligible_turns'],a['disclosed_turns'],b['eligible_turns'],b['disclosed_turns']),(2,0,2,2))
        f,d=full.for_model()[0],disclose.for_model()[0]
        for i,(x,y) in enumerate(zip(f,d,strict=True)):
            if x==y:continue
            self.assertEqual(x['role'],'tool')
            xv,yv=json.loads(x['content']),json.loads(y['content'])
            self.assertEqual(yv['observation']['api_receipts']['format'],FORMAT)
            xv['observation'].pop('api_receipts');yv['observation'].pop('api_receipts')
            self.assertEqual(xv,yv)

    def test_cumulative_boundary_rejects_tamper_atomically_and_sticky(self):
        for mode in ('full','disclose'):
            for case in ('old_event','old_raw_order','missing_inner','future_call','extra_span','reused_call','wrong_outer'):
                with self.subTest(mode=mode,case=case):
                    c=conversation(mode);events,spans=[],{};append(c,fixture(),events,spans)
                    c.disclosure_snapshot();before=c.messages();archive=c.archive()
                    response,outer,new_events,new_spans=fixture(2)
                    events.extend(new_events);spans.update(new_spans);call_id='call-2'
                    if case=='old_event':events[0]['effects_unknown']=True
                    if case=='old_raw_order':spans['inner-1-0']=dict(reversed(list(spans['inner-1-0'].items())))
                    if case=='missing_inner':spans.pop('inner-2-0')
                    if case=='future_call':events[-1]['call']='future'
                    if case=='extra_span':spans['unbound']={'id':'unbound'}
                    if case=='reused_call':
                        call_id='call-1'
                        for e in new_events:e['call']=call_id
                    if case=='wrong_outer':outer=deepcopy(outer);outer[0]['observation']['stdout']='changed'
                    with self.assertRaises(ValueError):c.append_closed_turn(response,outer,call_id=call_id,events=events,spans=spans)
                    self.assertEqual(c.messages(),before);self.assertEqual(c._archive,archive)
                    self.assertTrue(c.contract_failed)
                    self.assertFalse(c.disclosure_summary()['disclosure_contract_intact'])
                    self.assertEqual(c.disclosure_summary()['closed_turns'],1)
                    with self.assertRaises(ValueError):c.for_model()

    def test_ordinary_append_cannot_silently_disable_disclosure(self):
        for method in ('append','append_recorded'):
            c=conversation()
            with self.assertRaises(ValueError):getattr(c,method)(fixture()[0],fixture()[1])
            self.assertTrue(c.contract_failed)
            self.assertIsNone(c.disclosure_summary()['closed_turns'])

    def test_reconstruction_and_sidecar_are_source_bound(self):
        c=conversation();events,spans=[],{};turns=[]
        for n in (1,2):turns.append(append(c,fixture(n),events,spans))
        snapshot=c.disclosure_snapshot()
        rebuilt=rebuild_disclosure_conversation('instructions',{'synthetic':True},execution_scope='synthetic-live',mode='disclose',page_limit=24000,turns=turns,events=events,spans=spans,expected_snapshot=snapshot)
        self.assertEqual(c.for_model(),rebuilt.for_model())
        self.assertEqual(c.messages(),rebuilt.messages())
        for change in ('snapshot','scope','tail'):
            opts=dict(execution_scope='synthetic-live',mode='disclose',page_limit=24000,turns=turns,events=events,spans=spans,expected_snapshot=deepcopy(snapshot))
            if change=='snapshot':opts['expected_snapshot']['disclosed_turns']=0
            if change=='scope':opts['execution_scope']='other-run'
            if change=='tail':opts['events']=events+fixture(3)[2];opts['spans']={**spans,**fixture(3)[3]}
            with self.assertRaises(ValueError):rebuild_disclosure_conversation('instructions',{'synthetic':True},**opts)

    def test_raw_unicode_page_offsets_and_paid_new_turn_expansion(self):
        c=conversation();events,spans=[],{};append(c,fixture(),events,spans)
        prior=c.for_model()[0]
        for offset in (0,7,31,1000,100000):self.assertEqual(page_span(c.archive(),'outer-1',offset,37),page_span(spans,'outer-1',offset,37))
        page=page_span(spans,'outer-1',7,37)
        fn={'name':'read_span','arguments':compact({'span_id':'outer-1','offset':7})}
        response={'role':'assistant','content':'','tool_calls':[{'id':'paid-expansion','type':'function','function':fn}]}
        row={'id':'read-result','assistant':'','action':fn,'observation':page}
        data=response,[row],[{'call':'read-call','span_id':row['id'],'stage':'model_tool','api_request_sent':False}],{row['id']:row}
        append(c,data,events,spans)
        after=c.for_model()[0]
        self.assertEqual(after[:len(prior)],prior)
        self.assertEqual(json.loads(after[-1]['content'])['observation'],page)
        summary=c.disclosure_summary()
        self.assertEqual(summary['receipt_read_span_actions'],1)
        self.assertEqual(summary['receipt_read_span_returned_characters'],37)
        self.assertEqual(summary['automatic_archive_expansions'],0)

    def test_cache_only_has_zero_rows_and_full_fallback(self):
        c=conversation();events,spans=[],{};append(c,fixture(count=0),events,spans)
        self.assertEqual(c.disclosure_summary()['disclosed_turns'],0)
        self.assertEqual(c.disclosure_snapshot()['committed_event_count'],1)
        self.assertEqual(c.archive()['outer-1']['observation']['api_receipts']['rows'],[])
        self.assertEqual(c.archive()['outer-1']['observation']['api_requests'],0)

    def test_unknown_raised_unsent_and_paging_keep_full(self):
        for case in ('unknown','raised','unsent','paging','mixed'):
            data=fixture();response,outer,events,archive=data
            limit=24000
            if case in ('unknown','raised'):events[0]['api_execution']['status']=case
            if case=='unsent':
                events[0]['api_request_sent']=False;events[0]['api_execution']['bridge_request_sent']=False
                outer[0]['observation']['api_receipts']['rows'][0][2]=False;outer[0]['observation']['api_requests']-=1
            if case=='paging':limit=200
            if case=='mixed':
                other=fixture(2);response['tool_calls'].extend(other[0]['tool_calls']);outer.extend(other[1]);events.extend(other[2]);archive.update(other[3])
                for event in events:event['call']='call-1'
            a,b=conversation('full',page_limit=limit),conversation(page_limit=limit)
            for c in (a,b):c.append_closed_turn(response,outer,call_id='call-1',events=events,spans=archive)
            self.assertEqual(a.for_model()[0],b.for_model()[0]);self.assertEqual(b.disclosure_summary()['disclosed_turns'],0)


if __name__=='__main__':unittest.main()
