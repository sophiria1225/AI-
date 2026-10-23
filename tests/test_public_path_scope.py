import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from public_path_scope import inspect_cell, source_shape
from inspect_public_path_scope import validate_ci


def fixture(requests=('show_item','change_item','show_item'), changed=False):
    events=[];spans={};usage=[]
    for n,name in enumerate(requests,1):
        call=f'call_{n:03d}';sid=f'a{n}';pid=f'p{n}'
        usage.append({'id':call,'status':'ok','input_tokens':10,'output_tokens':2,
                      'cached_input_tokens':3,'wall_seconds':0.1})
        receipts=[]
        if name:
            events.append({'call':call,'span_id':sid,'stage':'python_api','api_request_sent':True,'effects_unknown':False})
            spans[sid]={'action':{'name':'app__'+name,'arguments':json.dumps({'id':1,'credential':'PRIVATE_LITERAL'})},
                        'observation':{'value':2 if changed and n==3 else 1}}
            receipts.append({'span_id':sid,'api':'app__'+name,'api_request_sent':True})
        events.append({'call':call,'span_id':pid,'stage':'model_tool','api_request_sent':False,'effects_unknown':False})
        spans[pid]={'action':{'name':'run_python','arguments':json.dumps({'code':"print('PRIVATE_LITERAL')",'span_ids':[]})},
                    'observation':{'status':'ok','stdout':'PRIVATE_LITERAL\n','stdout_truncated':False,
                                   'api_receipts':receipts,'api_requests':int(bool(name)),'error':None}}
    expected={'run_id':'fixture','task_id':'known','arm':'public','success':False,'stop_reason':'limit',
              'model_calls':len(usage),'known_total_tokens':len(usage)*12,'unknown_usage_calls':0,
              'api_requests':sum(bool(n) for n in requests),'program_status_counts':{'ok':len(usage)},
              'repeat_identical_request_excess':sum(bool(n) for n in requests)-len({n for n in requests if n})}
    return events,spans,usage,expected


class PublicPathScopeTests(unittest.TestCase):
    def test_describes_but_never_executes_source_or_exports_literals(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'must_not_exist'
            result=source_shape(f"open({str(p)!r}, 'w').write('PRIVATE_LITERAL')\n")
            self.assertFalse(p.exists())
            self.assertNotIn('PRIVATE_LITERAL',json.dumps(result))
            self.assertFalse(result['executed_by_inspector'])

    def test_repeated_returns_do_not_become_cache_safety(self):
        result=inspect_cell(*fixture())
        repeated=result['repeated_requests'][0]
        self.assertTrue(repeated['same_observation'])
        self.assertEqual(repeated['intervening_sent_api_names'],{'app__change_item':1})
        self.assertIsNone(repeated['safe_to_cache_or_omit'])
        self.assertIsNone(result['measured_savings'])
        self.assertNotIn('PRIVATE_LITERAL',json.dumps(result))

    def test_changed_reply_is_not_equal_even_with_identical_arguments(self):
        result=inspect_cell(*fixture(changed=True))
        self.assertFalse(result['repeated_requests'][0]['same_observation'])

    def test_known_local_work_and_unknown_unexecuted_generation_stay_separate(self):
        events,spans,usage,expected=fixture((None,))
        usage.append({'id':'call_002','status':'timeout','input_tokens':None,'output_tokens':None,
                      'cached_input_tokens':None,'wall_seconds':5})
        expected.update(model_calls=2,unknown_usage_calls=1)
        result=inspect_cell(events,spans,usage,expected)
        self.assertEqual(result['partition']['known_without_sent_api']['known_total_tokens'],12)
        self.assertEqual(result['partition']['unknown_usage_unexecuted']['unknown_usage_calls'],1)
        self.assertIsNone(result['calls'][1]['known_total_tokens'])

    def test_unknown_cost_cannot_be_imputed(self):
        e,s,u,x=fixture((None,));u[0]['status']='timeout'
        with self.assertRaisesRegex(ValueError,'unknown_usage'):inspect_cell(e,s,u,x)

    def test_duplicate_event_rejected(self):
        e,s,u,x=fixture();e.append(e[0])
        with self.assertRaisesRegex(ValueError,'duplicate'):inspect_cell(e,s,u,x)

    def test_receipt_from_another_generation_rejected(self):
        e,s,u,x=fixture();s['p2']['observation']['api_receipts'][0]['span_id']='a3'
        with self.assertRaisesRegex(ValueError,'receipt_link'):inspect_cell(e,s,u,x)

    def test_reused_receipt_cannot_double_assign_inner_api(self):
        e,s,u,x=fixture();s['p1']['observation']['api_receipts']*=2
        with self.assertRaisesRegex(ValueError,'receipt_link'):inspect_cell(e,s,u,x)

    def test_unassigned_api_is_not_dropped(self):
        e,s,u,x=fixture();s['p1']['observation']['api_receipts']=[];s['p1']['observation']['api_requests']=0
        with self.assertRaisesRegex(ValueError,'unassigned'):inspect_cell(e,s,u,x)

    def test_original_audit_total_must_match(self):
        e,s,u,x=fixture();x['known_total_tokens']+=1
        with self.assertRaisesRegex(ValueError,'total_disagrees'):inspect_cell(e,s,u,x)

    def test_dynamic_calls_and_syntax_errors_are_not_safety_proofs(self):
        result=source_shape("alias = call_api\nalias(*args)\nprint(globals())")
        self.assertIn('alias',result['call_syntax'])
        self.assertTrue(result['no_semantic_safety_or_liveness_inference'])
        self.assertEqual(source_shape('for :')['status'],'syntax_error')
        with self.assertRaisesRegex(ValueError,'source_size'):source_shape('x'*20001)

    def test_ci_must_match_both_events_and_job_commits(self):
        sha='a'*40
        ci=[{'event':e,'id':i,'job_id':i+10,'head_sha':sha,'job_head_sha':sha,
             'status':'completed','conclusion':'success','job_name':'accounting-and-syntax',
             'job_conclusion':'success'} for i,e in enumerate(['push','pull_request'],1)]
        validate_ci(ci,sha)
        bad=copy.deepcopy(ci);bad[1]['job_head_sha']='b'*40
        with self.assertRaisesRegex(ValueError,'exact_commit'):validate_ci(bad,sha)


if __name__=='__main__':unittest.main()
