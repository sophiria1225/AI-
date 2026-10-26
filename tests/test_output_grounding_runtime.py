"""Handwritten records and typed replies; no external API/model/code execution."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from automatic_projection_runtime import ProjectionApiChannel
from container_api_python import ApiChannel
from output_grounding_runtime import OutputGroundingController, GroundedReceiptExchange
from public_api_envelope import PROTOCOL
from public_api_result_transport import PublicResultTransport
from public_name_catalog import PublicNameCatalog
from public_output_grounding import PublicExportMonitor, digest, csv_compare
from shared_api_reservations import RequestBudget
from test_public_output_grounding import Fixture, TASK, SONGS


def controller(mode,complete=True):
    original=Fixture().ready(complete=complete)
    result=OutputGroundingController(PublicExportMonitor(TASK,execution_scope='synthetic'),mode=mode)
    for event,span in original.rows:result.observe(event,span)
    return result


class Raw:
    def __init__(self,status='returned',message='File created.'):
        self.commands=[];self.status=status;self.message=message
    def request(self,command):
        self.commands.append(deepcopy(command))
        if self.status=='unknown':raise OSError('synthetic lost reply')
        call=command['call']
        if self.status=='raised':
            envelope=dict(protocol=PROTOCOL,nonce=command['nonce'],status='raised',
                          error={'type':'ValueError','message':'synthetic write rejected'})
        else:
            envelope=dict(protocol=PROTOCOL,nonce=command['nonce'],status='returned',
                value={'message':self.message,'file_path':'/home/synthetic/backup/export.csv'})
        return {'ok':True,'result':{'protocol':PROTOCOL,'observation':json.dumps(envelope),'declared_complete':False}}


def channel(mode='repair',*,complete=True,status='returned',limit=5,message='File created.'):
    c=controller(mode,complete);raw=Raw(status,message);bridge=PublicResultTransport(raw)
    names={'file_system__create_file':('access_token','file_path','content','overwrite'),
           'file_system__update_file':('access_token','file_path','content'),
           'spotify__delete_account':('access_token',)}
    catalog=PublicNameCatalog([{'type':'function','function':{'name':name,'parameters':{
        'type':'object','properties':{k:{} for k in fields},'additionalProperties':False}}}
        for name,fields in names.items()]);catalog.visible.update(names)
    base=ApiChannel(catalog,bridge,limit);budget=RequestBudget(limit)
    wrapped=ProjectionApiChannel(base,budget)
    wrapped.receipted=GroundedReceiptExchange(wrapped.receipted,base,c)
    return wrapped,c,raw,bridge,budget


def dispatch(ch,c,args=None,*,api='create_file',app='file_system'):
    args=Fixture().arguments() if args is None else args
    packet=dict(kind='api',id=ch.last_id+1,app=app,api=api,arguments=deepcopy(args));before=deepcopy(packet)
    reply=ch.exchange(packet)
    assert packet==before
    row=ch.rows[-1];sid='record-'+str(len(ch.rows))
    event=dict(call='call_001',span_id=sid,stage='python_api',api_request_sent=row['api_request_sent'],
        new_tools=row['new_tools'],effects_unknown=row.get('effects_unknown',False))
    if 'api_execution' in row:event['api_execution']=row['api_execution']
    if 'output_grounding_entry' in row:event['output_grounding_entry']=row['output_grounding_entry']
    span=dict(id=sid,action=row['action'],observation=row['observation'])
    c.observe(event,span,entry_index=row.get('output_grounding_entry'))
    return reply,row,event,span


class OutputGroundingRuntimeTests(unittest.TestCase):
    def test_off_keeps_actual_payload_and_typed_receipt(self):
        ch,c,raw,bridge,budget=channel('off');args=Fixture().arguments()
        reply,row,event,span=dispatch(ch,c,args)
        self.assertTrue(reply['ok']);self.assertEqual(raw.commands[0]['call']['args'],args)
        self.assertEqual((budget.spent,len(bridge.receipts)),(1,1))
        self.assertIsNone(c.take_notice());self.assertFalse(c.entries[0]['supported_backup_confirmed'])
        self.assertEqual(c.entries[0]['api_execution_nonce'],event['api_execution']['nonce'])

    def test_feedback_is_one_unsent_record_without_invocation_nonce_and_channel_remains_usable(self):
        ch,c,raw,bridge,budget=channel('feedback')
        reply,row,event,span=dispatch(ch,c)
        self.assertFalse(reply['ok']);self.assertFalse(row['api_request_sent'])
        self.assertNotIn('api_execution',row);self.assertEqual((raw.commands,bridge.receipts,budget.spent),([],[],0))
        self.assertEqual(budget.events[-1]['kind'],'not_dispatched')
        self.assertEqual(c.take_notice()['interventions'][0]['decision'],'feedback')
        self.assertIsNone(c.take_notice())
        good=c.monitor.propose('file_system__create_file',Fixture().arguments(),mode='repair')['replacement_args']
        self.assertTrue(dispatch(ch,c,good)[0]['ok']);self.assertEqual(budget.spent,1)

    def test_repair_only_changes_content_and_is_bound_to_effective_record_and_prior_evidence(self):
        ch,c,raw,bridge,budget=channel();args=Fixture().arguments();prior=c.observed_events
        reply,row,event,span=dispatch(ch,c,args)
        effective=raw.commands[0]['call']['args'];entry=c.entries[0]
        self.assertEqual({k:v for k,v in effective.items() if k!='content'},
                         {k:v for k,v in args.items() if k!='content'})
        self.assertNotEqual(effective['content'],args['content']);self.assertTrue(reply['ok'])
        self.assertEqual(json.loads(row['action']['arguments']),effective)
        self.assertEqual(entry['prior_record_count'],prior)
        self.assertEqual(entry['effective_payload_sha256'],digest(effective))
        self.assertEqual(entry['effective_span_sha256'],digest(span))
        self.assertEqual(entry['host_event_sha256'],digest(event))
        self.assertEqual((c.summary()['grounding_repairs'],c.summary()['grounding_sent_repairs']),(1,1))
        notice=c.take_notice();self.assertTrue(notice['interventions'][0]['supported_backup_confirmed'])
        self.assertFalse(notice['account_deletion_authorized'])

    def test_incomplete_source_is_unknown_and_passes_original(self):
        ch,c,raw,bridge,budget=channel(complete=False);args=Fixture().arguments()
        dispatch(ch,c,args)
        self.assertEqual(raw.commands[0]['call']['args'],args)
        self.assertEqual(c.entries[0]['assessment']['status'],'unknown')
        self.assertEqual(c.summary()['grounding_repairs'],0);self.assertIsNone(c.take_notice())

    def test_schema_rejection_and_exhausted_budget_precede_grounding(self):
        for kind in ('schema','budget'):
            ch,c,raw,bridge,budget=channel(limit=0 if kind=='budget' else 5)
            args=Fixture().arguments()
            if kind=='schema':args['extra']=1
            dispatch(ch,c,args)
            self.assertEqual((c.entries,raw.commands,bridge.receipts,budget.spent),([],[],[],0))

    def test_raised_write_is_paid_and_never_successful_repair(self):
        ch,c,raw,bridge,budget=channel(status='raised')
        self.assertFalse(dispatch(ch,c)[0]['ok'])
        self.assertEqual((budget.spent,c.summary()['grounding_sent_repairs'],c.summary()['grounding_repairs']),(1,1,0))
        self.assertEqual(c.entries[0]['outcome'],'raised');self.assertFalse(c.monitor.backup)

    def test_returned_without_public_success_confirmation_does_not_count_as_repair(self):
        ch,c,raw,bridge,budget=channel(message='Unrecognized outcome')
        self.assertTrue(dispatch(ch,c)[0]['ok'])
        self.assertEqual(c.summary()['repaired_write_returns'],1)
        self.assertEqual(c.summary()['grounding_repairs'],0)

    def test_unknown_dispatch_stops_budget_preserves_real_paid_attempt(self):
        ch,c,raw,bridge,budget=channel(status='unknown')
        reply,row,_,_=dispatch(ch,c)
        self.assertFalse(reply['ok']);self.assertTrue(row['effects_unknown'])
        self.assertTrue(budget.stopped and bridge.fatal)
        self.assertEqual((budget.spent,c.entries[0]['outcome'],c.summary()['grounding_repairs']),(1,'unknown',0))
        with self.assertRaises(RuntimeError):ch.exchange(dict(kind='api',id=2,app='file_system',api='create_file',arguments=Fixture().arguments()))
        self.assertEqual(len(raw.commands),1)

    def test_delete_remains_unintervened_even_without_backup(self):
        for mode in ('off','feedback','repair'):
            ch,c,raw,bridge,budget=channel(mode,message='Account terminated.')
            dispatch(ch,c,{'access_token':'spotify-one'},app='spotify',api='delete_account')
            self.assertEqual(c.entries,[]);self.assertEqual(budget.spent,1)
            self.assertIsNone(c.take_notice())

    def test_malformed_replacement_is_fatal_before_any_dispatch(self):
        ch,c,raw,bridge,budget=channel();args=Fixture().arguments()
        assessment=c.monitor.propose('file_system__create_file',args,mode='repair')
        assessment['replacement_args']['access_token']='changed'
        with patch.object(c.monitor,'propose',return_value=assessment),self.assertRaises(ValueError):
            ch.exchange(dict(kind='api',id=1,app='file_system',api='create_file',arguments=args))
        self.assertTrue(c.failed);self.assertFalse(raw.commands)
        self.assertEqual((budget.spent,budget.pending),(0,0))

    def test_event_binding_tamper_is_fatal_and_cannot_be_retried(self):
        ch,c,raw,bridge,budget=channel();args=Fixture().arguments()
        ch.exchange(dict(kind='api',id=1,app='file_system',api='create_file',arguments=args))
        row=ch.rows[-1]
        event=dict(call='call_001',span_id='wrong',stage='python_api',api_request_sent=True)
        with self.assertRaises(ValueError):
            c.observe(event,dict(id='different',action=row['action'],observation=row['observation']),entry_index=0)
        self.assertTrue(c.failed)
        with self.assertRaises(ValueError):c.ready()


if __name__=='__main__':unittest.main()
