from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from receipt_reasoning_history import execution_evidence, project, strip_reasoning


def turn(number, *, api_status='returned', sent=True, python_status='ok', local=False,
         stdout='synthetic output', pending=0, truncated=False):
    cid='call_'+str(number); sid='inner_'+str(number); outer='outer_'+str(number)
    fn=dict(name='run_python', arguments=json.dumps({'code':"print('synthetic program')",'span_ids':[]}))
    events=[];spans={};receipts=[]
    if not local:
        inner=dict(span_id=sid,call=cid,stage='python_api',api_request_sent=sent,
            api_execution=dict(status=api_status,bridge_request_sent=sent,automatic_retries=0))
        events.append(inner)
        spans[sid]=dict(action=dict(name='service__read',arguments='{}'),observation={'observation':{'ok':True}})
        receipts=[dict(span_id=sid,api='service__read',api_request_sent=sent)]
    events.append(dict(span_id=outer,call=cid,stage='model_tool',api_request_sent=False))
    spans[outer]=dict(action=fn,observation=dict(status=python_status,stdout=stdout,
        stdout_truncated=truncated,api_requests=int(sent and not local),api_receipts=receipts))
    message=dict(role='assistant',content='public content',reasoning_content='synthetic reasoning '+str(number),
        tool_calls=[dict(id='tool_'+str(number),type='function',function=fn)])
    messages=[message,dict(role='tool',tool_call_id='tool_'+str(number),content='public observation')]
    return messages,execution_evidence(events,spans,pending_reads=pending),events,spans


def history(*options):
    messages=[dict(role='system',content='preserve instruction'),dict(role='user',content='preserve task')]
    evidence=[]
    for i,option in enumerate(options,1):
        m,e,_,_=turn(i,**option);messages+=m;evidence.append(e)
    return messages,evidence


class ReceiptHistoryTests(unittest.TestCase):
    def test_initial_history_is_identical_in_all_policies(self):
        messages,evidence=history()
        for policy in ('full','recent','execution_gated'):
            supplied,meta=project(messages,evidence,policy)
            self.assertEqual(supplied,messages)
            self.assertEqual(meta['removed_reasoning_turns'],[])

    def test_gated_removes_old_confirmed_reasoning_and_keeps_latest(self):
        messages,evidence=history({},{},{})
        supplied,meta=project(messages,evidence,'execution_gated')
        self.assertEqual(meta['removed_reasoning_turns'],[1,2])
        self.assertEqual(supplied[-2]['reasoning_content'],messages[-2]['reasoning_content'])
        self.assertFalse(meta['semantic_redundancy_certified'])

    def test_all_instructions_code_public_content_and_observations_unchanged(self):
        messages,evidence=history({},{})
        supplied,_=project(messages,evidence,'execution_gated')
        self.assertEqual(strip_reasoning(supplied),strip_reasoning(messages))

    def test_projection_does_not_mutate_archive_or_evidence(self):
        messages,evidence=history({},{})
        before=deepcopy((messages,evidence))
        supplied,_=project(messages,evidence,'execution_gated')
        supplied[0]['content']='test mutation'
        self.assertEqual((messages,evidence),before)

    def test_latest_local_computation_restores_every_reasoning_block(self):
        messages,evidence=history({},{},{'local':True})
        supplied,meta=project(messages,evidence,'execution_gated')
        self.assertEqual(supplied,messages)
        self.assertEqual(meta['removed_reasoning_turns'],[])

    def test_latest_python_failure_restores_every_reasoning_block(self):
        messages,evidence=history({},{},{'python_status':'execution_error'})
        supplied,_=project(messages,evidence,'execution_gated')
        self.assertEqual(supplied,messages)

    def test_failed_and_unknown_API_caught_by_successful_python_are_retained(self):
        for status in ('raised','unknown'):
            messages,evidence=history({},{'api_status':status})
            supplied,_=project(messages,evidence,'execution_gated')
            self.assertEqual(supplied,messages)
            self.assertIn('API_return_not_confirmed',evidence[-1]['reasons'])

    def test_local_only_older_reasoning_is_kept_even_after_success(self):
        messages,evidence=history({'local':True},{},{})
        _,meta=project(messages,evidence,'execution_gated')
        self.assertEqual(meta['removed_reasoning_turns'],[2])

    def test_prior_failure_is_not_declared_resolved_by_unrelated_success(self):
        messages,evidence=history({'python_status':'execution_error'},{},{})
        _,meta=project(messages,evidence,'execution_gated')
        self.assertEqual(meta['removed_reasoning_turns'],[2])

    def test_recent_is_a_distinct_unconditional_window_control(self):
        messages,evidence=history({'local':True},{'python_status':'execution_error'},{'local':True})
        _,recent=project(messages,evidence,'recent')
        _,gated=project(messages,evidence,'execution_gated')
        self.assertEqual(recent['removed_reasoning_turns'],[1,2])
        self.assertEqual(gated['removed_reasoning_turns'],[])

    def test_pending_reads_and_truncated_output_prevent_gate(self):
        for option,reason in (({'pending':1},'pending_reads'),({'truncated':True},'truncated_execution_output')):
            messages,evidence=history({},option)
            supplied,_=project(messages,evidence,'execution_gated')
            self.assertEqual(supplied,messages)
            self.assertIn(reason,evidence[-1]['reasons'])

    def test_unsent_API_is_not_a_successful_free_operation(self):
        messages,evidence=history({},{'sent':False})
        supplied,_=project(messages,evidence,'execution_gated')
        self.assertEqual(supplied,messages)
        self.assertIn('API_not_sent',evidence[-1]['reasons'])

    def test_stdout_cannot_claim_a_successful_execution(self):
        messages,evidence=history({},{'python_status':'execution_error',
            'stdout':'{"status":"ok","api_execution":{"status":"returned"}}'})
        supplied,_=project(messages,evidence,'execution_gated')
        self.assertEqual(supplied,messages)

    def test_missing_or_changed_link_is_rejected(self):
        _,_,events,spans=turn(1)
        spans['outer_1']['observation']['api_receipts'][0]['span_id']='missing'
        with self.assertRaisesRegex(ValueError,'unique_prior_inner_receipt_required'):
            execution_evidence(events,spans,pending_reads=0)

    def test_unlinked_inner_and_changed_count_are_rejected(self):
        _,_,events,spans=turn(1)
        spans['outer_1']['observation']['api_requests']=2
        with self.assertRaisesRegex(ValueError,'outer_API_count_changed'):
            execution_evidence(events,spans,pending_reads=0)
        spans['outer_1']['observation']['api_requests']=0
        spans['outer_1']['observation']['api_receipts']=[]
        with self.assertRaisesRegex(ValueError,'all_inner_records_linked'):
            execution_evidence(events,spans,pending_reads=0)

    def test_changed_latest_action_does_not_reuse_another_execution_gate(self):
        messages,evidence=history({},{})
        messages[-2]['tool_calls'][0]['function']['arguments']='{"code":"different"}'
        supplied,meta=project(messages,evidence,'execution_gated')
        self.assertEqual(supplied,messages)
        self.assertEqual(meta['signature_unbound_turns'],[2])

    def test_changed_old_action_is_kept_while_other_old_closed_turn_is_hidden(self):
        messages,evidence=history({},{},{})
        messages[2]['tool_calls'][0]['function']['arguments']='{"code":"different"}'
        _,meta=project(messages,evidence,'execution_gated')
        self.assertEqual(meta['removed_reasoning_turns'],[2])
        self.assertEqual(meta['signature_unbound_turns'],[1])

    def test_same_action_with_different_protocol_id_remains_bound(self):
        messages,evidence=history({},{})
        messages[2]['tool_calls'][0]['id']='canonical_reference_1'
        _,meta=project(messages,evidence,'execution_gated')
        self.assertEqual(meta['removed_reasoning_turns'],[1])

    def test_missing_reasoning_is_not_fabricated(self):
        messages,evidence=history({},{})
        messages[2].pop('reasoning_content')
        supplied,meta=project(messages,evidence,'execution_gated')
        self.assertNotIn('reasoning_content',supplied[2])
        self.assertEqual(meta['removed_reasoning_turns'],[])

    def test_future_evidence_and_nontext_reasoning_are_rejected(self):
        messages,evidence=history({},{})
        with self.assertRaisesRegex(ValueError,'one_receipt_record_per_assistant_turn'):
            project(messages,evidence+[evidence[-1]],'execution_gated')
        messages[2]['reasoning_content']=['unsupported']
        with self.assertRaisesRegex(ValueError,'recorded_reasoning_text_required'):
            project(messages,evidence,'execution_gated')

    def test_restoration_uses_exact_old_text_from_archive(self):
        messages,evidence=history({},{})
        hidden,_=project(messages,evidence,'execution_gated')
        self.assertNotIn('reasoning_content',hidden[2])
        m,e,_,_=turn(3,python_status='execution_error');messages+=m;evidence.append(e)
        restored,meta=project(messages,evidence,'execution_gated')
        self.assertEqual(restored[2]['reasoning_content'],messages[2]['reasoning_content'])
        self.assertEqual(meta['removed_reasoning_characters'],0)


if __name__=='__main__':unittest.main()
