from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from measure_receipt_history import collect_renderings, prepared_views
from test_receipt_reasoning_history import turn


def fixture(last_unknown=False):
    messages=[dict(role='system',content='fixed instructions'),dict(role='user',content='synthetic task')]
    usage=[];events=[];spans={};requests={}
    for i in range(1,4):
        cid='call_'+str(i)
        requests[cid]=dict(messages=deepcopy(messages),temperature=1,seed=i,tool_choice='auto')
        u=dict(id=cid,status='ok',input_tokens=10,output_tokens=2,cached_input_tokens=0)
        usage.append(u)
        if last_unknown and i==3:
            u.update(status='error',input_tokens=None,output_tokens=None,cached_input_tokens=None)
        else:
            m,_,e,s=turn(i);messages+=m;events+=e;spans.update(s)
    return usage,events,spans,requests


class ReceiptMeasurementTests(unittest.TestCase):
    def test_all_policies_see_only_preceding_evidence(self):
        rows,evidence=prepared_views(*fixture())
        self.assertEqual(len(rows),9)
        self.assertEqual([r['projection']['prior_turns'] for r in rows],[0]*3+[1]*3+[2]*3)
        self.assertEqual(rows[-1]['projection']['removed_reasoning_turns'],[1])
        self.assertEqual(len(evidence),3)

    def test_requests_are_unchanged_except_reasoning_display(self):
        inputs=fixture();before=deepcopy(inputs)
        rows,_=prepared_views(*inputs)
        self.assertEqual(inputs,before)
        for r in rows:
            p=deepcopy(r['payload']);p['messages']=inputs[3][r['call_id']]['messages']
            self.assertEqual(p,inputs[3][r['call_id']])

    def test_missing_usage_is_retained_for_all_three_hypothetical_inputs(self):
        rows,_=prepared_views(*fixture(last_unknown=True))
        for r in rows[-3:]:
            self.assertEqual(r['original_usage_status'],'error')
            self.assertIsNone(r['original_measured_input_tokens'])
            self.assertIsNone(r['original_measured_output_tokens'])

    def test_unknown_response_cannot_have_execution(self):
        inputs=list(fixture());inputs[0][-1]['status']='error'
        with self.assertRaisesRegex(ValueError,'unknown_generation_cannot_have_later_execution'):
            prepared_views(*inputs)

    def test_no_subprocess_or_generated_code_is_used_to_select_views(self):
        inputs=fixture()
        with patch('subprocess.Popen',side_effect=AssertionError('no execution')):
            rows,_=prepared_views(*inputs)
        self.assertEqual(len(rows),9)

    def fake_renderings(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);folder=Path(temp.name)
        views=[]
        for cid,status in [('call_1','ok'),('call_2','error')]:
            for policy in ('full','recent','execution_gated'):
                case=cid+'_'+policy;tokens=[1,2,3] if policy=='full' else [1,4]
                value=dict(id=case,input_tokens=len(tokens),tokens=tokens,prompt='synthetic',media_files=0,
                    session_controls={'fixed':True},parsed_non_message_parameters={'seed':1})
                (folder/(case+'_rendered_private.json')).write_text(json.dumps(value))
                views.append(dict(case_id=case,call_id=cid,policy=policy,original_usage_status=status,
                    original_measured_input_tokens=3 if status=='ok' else None))
        return folder,views

    def test_exact_count_validation_preserves_unknown_and_names_prefix_measurement(self):
        folder,views=self.fake_renderings();rows=collect_renderings(folder,views)
        self.assertEqual([r['delta_from_full'] for r in rows],[0,-1,-1,0,-1,-1])
        self.assertTrue(rows[-1]['original_unknown_usage_not_imputed'])
        self.assertEqual(rows[-1]['adjacent_input_common_prefix_tokens'],2)
        self.assertTrue(rows[-1]['common_prefix_is_not_measured_cache_usage'])

    def test_measured_baseline_count_mismatch_is_rejected(self):
        folder,views=self.fake_renderings();views[0]['original_measured_input_tokens']=9
        with self.assertRaisesRegex(ValueError,'original_measured_input_count_differs'):
            collect_renderings(folder,views)

    def test_projection_cannot_silently_change_decoder_controls(self):
        folder,views=self.fake_renderings();path=folder/'call_1_recent_rendered_private.json'
        value=json.loads(path.read_text());value['session_controls']['fixed']=False
        path.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError,'only_history_may_change_decoder_controls'):
            collect_renderings(folder,views)


if __name__=='__main__':unittest.main()
