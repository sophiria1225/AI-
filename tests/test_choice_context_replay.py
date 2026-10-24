import copy
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from choice_context_replay import (CASES, COUNTS, CHOICES, FIXED, condition, conditions,
    digest, equality_summary, input_comparisons, output_summary, request_for,
    reserve_tokens, schedule, validate_plan)
from audit_choice_context import audit_known_record
from inference_cache_control import cache_measurement
from local_llama import parse_response
import probe_choice_context as worker
from run_context_comparison import write_json


def original():
    return dict(model='minimax-m3-iq4xs',seed=70,max_tokens=4096,cache_prompt=False,
        stream=False,temperature=1.0,tool_choice='auto',tools=[{'type':'function'}],
        messages=[{'role':'user','content':'synthetic input'}])


def plan():
    return {**FIXED,'conditions':conditions(),'schedule':schedule(),
            'cases':[dict(id=case,expected_input_tokens=count) for case,count in zip(CASES,COUNTS)]}


def counts():
    return {condition(case,choice):count+int(choice=='required')
            for case,count in zip(CASES,COUNTS) for choice in CHOICES}


def response(*, submitted=True, truncated=False):
    message={'role':'assistant','content':'' if submitted else 'synthetic text'}
    if submitted:
        message['tool_calls']=[{'id':'synthetic','type':'function','function':{
            'name':'run_python','arguments':json.dumps({'code':'print(1)','span_ids':[]})}}]
    return {'status':'ok','message':message,'done_reason':'length' if truncated else 'stop'}


def rows():
    return [{**item,'status':'ok',**output_summary(response(submitted=item['tool_choice']=='required'))}
            for item in schedule()]


def raw(count, *, cached=0):
    return dict(choices=[{'finish_reason':'stop','message':response()['message']}],
        usage={'prompt_tokens':count,'completion_tokens':4,'total_tokens':count+4,
               'prompt_tokens_details':{'cached_tokens':cached}},
        timings={'cache_n':cached,'prompt_n':count-cached,'predicted_n':4,'prompt_ms':10,'predicted_ms':20})


def worker_fixture(base, fail_at=None, bad_count=False):
    root=base/'repo';storage=base/'storage';(root/'reports').mkdir(parents=True)
    storage.mkdir();fixed=plan();keys=conditions()
    requests={key:{**original(),'tool_choice':key.rsplit('__',1)[1],
                  'messages':[{'role':'user','content':key}]} for key in keys}
    identity={'synthetic':True};closure={'closed':True};measured=counts()
    pre=dict(status='complete',git_commit='synthetic',source_sha256={},model_identity=identity,P99_closure=closure,
             counts=measured,rows=[dict(condition=k,payload_sha256=digest(requests[k])) for k in keys])
    write_json(root/worker.PREFLIGHT,pre);sent=[]
    def post(config,endpoint,payload,timeout):
        sent.append(copy.deepcopy(payload))
        if fail_at and len(sent)==fail_at: raise TimeoutError('synthetic timeout')
        key=payload['messages'][0]['content']
        return raw(measured[key]+int(bad_count))
    with contextlib.ExitStack() as stack:
        stack.enter_context(patch.object(worker,'sources',return_value=(fixed,{},requests)))
        stack.enter_context(patch.object(worker,'previous_session_closed',return_value=closure))
        stack.enter_context(patch.object(worker,'frozen_hashes',return_value={}))
        stack.enter_context(patch.object(worker,'live_identity',return_value=(identity,'synthetic lease')))
        stack.enter_context(patch.object(worker,'wait_idle',return_value={'one_slot_idle':True}))
        stack.enter_context(patch.object(worker,'post',side_effect=post))
        stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
        code=worker.run(storage,root)
    state=json.loads((storage/'records/context_pilot'/fixed['batch_id']/'status.json').read_text())
    return code,state,sent


class ChoiceContextReplayTests(unittest.TestCase):
    def test_only_tool_choice_changes_and_archive_is_not_mutated(self):
        before=original();saved=copy.deepcopy(before)
        for choice in CHOICES:
            changed=request_for(before,choice)
            self.assertEqual(changed,{**saved,'tool_choice':choice})
            changed['messages'][0]['content']='edited'
        self.assertEqual(before,saved)
        for key,value in [('seed',71),('cache_prompt',True),('max_tokens',1024),
                          ('tool_choice','required'),('grammar','different')]:
            with self.assertRaises(ValueError):request_for({**saved,key:value},'auto')

    def test_all_six_by_two_by_three_slots_and_frozen_limits(self):
        validate_plan(plan());self.assertEqual(len(schedule()),36)
        for key in conditions():
            self.assertEqual([r['repetition'] for r in schedule() if r['condition']==key],[1,2,3])
        for key,value in [('max_calls',35),('seed',71),('automatic_retries',1)]:
            with self.assertRaises(ValueError):validate_plan({**plan(),key:value})

    def test_required_has_own_input_count_without_assumed_equality(self):
        self.assertEqual(reserve_tokens(counts()),963360)
        changed=counts();changed[conditions()[0]]+=1
        with self.assertRaisesRegex(ValueError,'archived_auto'):reserve_tokens(changed)
        changed=counts();changed[conditions()[1]]=24577
        with self.assertRaisesRegex(ValueError,'bounded_input'):reserve_tokens(changed)
        changed=counts();changed.pop(conditions()[-1])
        with self.assertRaises(ValueError):reserve_tokens(changed)

    def test_equal_text_without_submission_is_not_a_static_action(self):
        result=equality_summary(rows())
        self.assertEqual(len(result['groups']),12)
        self.assertEqual(len(result['structural_comparisons']['cross']),66)
        for group in result['groups']:
            self.assertTrue(group['all_three_public_outputs_equal'])
            self.assertEqual(group['all_three_complete_static_submissions'],group['tool_choice']=='required')
        self.assertTrue(result['static_submission_is_not_execution'])
        self.assertFalse(result['task_quality_measured'])

    def test_truncation_and_invalid_json_cannot_be_promoted_to_valid_submission(self):
        self.assertFalse(output_summary(response(truncated=True))['complete_static_submission'])
        bad=response();bad['message']['tool_calls'][0]['function']['arguments']='{"code":'
        self.assertFalse(output_summary(bad)['complete_static_submission'])
        good=output_summary(response())
        self.assertTrue(good['complete_static_submission']);self.assertFalse(good['actual_execution_confirmed'])

    def test_missing_and_unknown_slots_are_retained_without_retry(self):
        sample=rows()[:4];sample[-1].update(status='error',**output_summary({'status':'error'}))
        result=equality_summary(sample)
        self.assertEqual(result['all_planned_slots_preserved'],36)
        self.assertEqual(result['unknown_usage_calls'],1)
        self.assertEqual(sum(x['unattempted'] for x in result['groups']),32)
        self.assertFalse(result['all_36_terminal_usages_known'])
        with self.assertRaises(ValueError):equality_summary(sample[:2]+sample[:1])

    def test_input_identity_and_decoder_controls_are_separate(self):
        rendered={key:dict(prompt_sha256='same',tokens_sha256='same',
            session_controls_sha256=key.rsplit('__',1)[1],parsed_non_message_parameters_sha256=key)
            for key in conditions()}
        comparisons=input_comparisons(rendered);self.assertEqual(len(comparisons),66)
        self.assertTrue(comparisons[0]['tokens_equal'])
        self.assertFalse(comparisons[0]['session_controls_equal'])

    def test_worker_dispatches_every_fixed_slot_once_with_own_count(self):
        with tempfile.TemporaryDirectory() as t:code,state,sent=worker_fixture(Path(t))
        self.assertEqual(code,0);self.assertEqual(len(sent),36)
        self.assertEqual([p['tool_choice'] for p in sent],[x['tool_choice'] for x in schedule()])
        self.assertEqual(state['unknown_usage_calls'],0)
        self.assertEqual(state['equality_summary']['all_planned_slots_preserved'],36)
        self.assertEqual(state['known_total_tokens'],3*sum(v+4 for v in counts().values()))
        self.assertEqual(state['generated_programs_executed'],0)

    def test_worker_stops_on_unknown_usage_and_does_not_fill_remaining_slots(self):
        with tempfile.TemporaryDirectory() as t:code,state,sent=worker_fixture(Path(t),fail_at=4)
        self.assertEqual(code,1);self.assertEqual(len(sent),4)
        self.assertEqual(state['unknown_usage_calls'],1)
        self.assertIsNone(state['rows'][-1]['input_tokens'])
        self.assertEqual(sum(g['unattempted'] for g in state['equality_summary']['groups']),32)

    def test_worker_stops_on_terminal_input_mismatch(self):
        with tempfile.TemporaryDirectory() as t:code,state,sent=worker_fixture(Path(t),bad_count=True)
        self.assertEqual(code,1);self.assertEqual(len(sent),1)
        self.assertEqual(state['status'],'stopped')

    def test_running_predecessor_rejects_before_final_record_or_new_server(self):
        with tempfile.TemporaryDirectory() as t:
            storage=Path(t);folder=storage/FIXED['required_closed_pipeline'];folder.mkdir(parents=True)
            write_json(folder/'status.json',{'status':'batch','server_stopped':False})
            with self.assertRaisesRegex(ValueError,'must_be_closed'):
                worker.previous_session_closed(storage,plan())
            self.assertFalse((folder/'server_final.json').exists())

    def test_audit_rejects_promoted_structure_and_cache_reuse(self):
        value=raw(22669);parsed=parse_response(value)
        row={**parsed,**output_summary(parsed),'cache':cache_measurement('cold_1',parsed,22669),
             'idle':{'one_slot_idle':True}}
        self.assertTrue(audit_known_record(value,parsed,row,22669,4096)['complete_static_submission'])
        changed=copy.deepcopy(row);changed['complete_static_submission']=False
        with self.assertRaisesRegex(ValueError,'fingerprint_mismatch'):
            audit_known_record(value,parsed,changed,22669,4096)
        with self.assertRaisesRegex(ValueError,'input/cache'):
            audit_known_record(value,parsed,row,22670,4096)

    def test_preflight_counts_all_twelve_exact_renderings_once(self):
        for mismatch in (False,True):
            with tempfile.TemporaryDirectory() as t, contextlib.ExitStack() as stack:
                base=Path(t);root=base/'repo';storage=base/'storage'
                (root/'reports').mkdir(parents=True);(storage/'.runtime').mkdir(parents=True)
                write_json(storage/'.runtime/model_server.json',{})
                measured=counts();requests={k:{'synthetic':k} for k in conditions()}
                rendered={k:dict(input_tokens=measured[k],prompt_sha256=k,tokens_sha256=k,
                    session_controls_sha256=k,parsed_non_message_parameters_sha256=k)
                    for k in conditions()}
                calls=[]
                def post(cfg,endpoint,payload,timeout):
                    calls.append(payload['synthetic'])
                    return {'input_tokens':measured[payload['synthetic']]+int(mismatch and len(calls)==2)}
                for name,value in [('sources',(plan(),{},requests)),('previous_session_closed',{}),
                                   ('frozen_hashes',{}),('frozen_sources','synthetic'),
                                   ('live_identity',({},'lease')),('check_resume',{}),('render_inputs',rendered)]:
                    stack.enter_context(patch.object(worker,name,return_value=value))
                stack.enter_context(patch.object(worker,'post',side_effect=post))
                stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
                code=worker.preflight(storage,root)
                result=json.loads((root/worker.PREFLIGHT).read_text())
                self.assertEqual(code,int(mismatch));self.assertEqual(len(calls),2 if mismatch else 12)
                self.assertEqual(result['model_generations'],0)
                if not mismatch:self.assertEqual(result['counts'],measured)


if __name__=='__main__':unittest.main()
