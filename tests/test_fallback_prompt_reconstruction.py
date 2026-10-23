import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from api_error_comparison import initial_conversation,task_snapshot
from budget_observation import notification
from budget_visibility_comparison import canonical_messages
from fallback_prompt_reconstruction import IDS,SOURCE_RUNS,SUFFIX,controls,interpret,reconstruct,validate_plan
from run_handoff_factors import sha

ROOT=Path(__file__).resolve().parents[1]


def output_fixture():
    def entry(prompt,tokens):return {'prompt':prompt,'tokens':tokens,'input_tokens':len(tokens),
        'session_controls':{'format':'same'},'parsed_non_message_parameters':{'seed':70}}
    values=[entry('original-a',[1,2]),entry('original-b',[1,3]),entry('normal',[1,4]),
        entry('normal',[1,4]),entry('original-a',[1,2]),entry('content-control',[1,2,5])]
    return dict(zip(IDS,values)),[{'known_input_tokens':2}]*2


def history_fixture(storage,identifier):
    folder=storage/'records/context_pilot'/identifier;folder.mkdir(parents=True)
    original=json.loads((ROOT/'configs/P29_stateful_code_v01.json').read_text())
    public={'instruction':'synthetic task','ground_truth_loaded':False}
    config={'model':{'num_ctx':1024},'max_wall_seconds':60,'max_api_requests':8,'max_calls':4,
        'max_total_tokens':200,'max_output_tokens':40,'observation_page_characters':24000}
    call={'id':identifier+'-random','type':'function','function':{'name':'run_python','arguments':'[]'}}
    message={'role':'assistant','content':'synthetic','reasoning_content':'opaque synthetic','tool_calls':[call]}
    span={'id':'s1','assistant':'synthetic','action':call['function'],'observation':{'format_error':'non-object arguments'}}
    conversation=initial_conversation(original,public);checks=[];usage=[];notices=[]
    for i in (1,2):
        cid=f'call_{i:03d}';out=folder/cid;out.mkdir()
        state=task_snapshot(config,usage,0,0)
        rendered,_=conversation.for_model()
        request={'messages':notification(canonical_messages(rendered),state,'not_exposed')[0],'seed':57+i-1}
        response={'status':'ok','input_tokens':20,'output_tokens':5,'message':message}
        for kind,v in [('request',request),('response',response)]:
            (out/(kind+'.json')).write_text(json.dumps(v))
        checks.append({'call_id':cid,'request_sha256':sha(out/'request.json'),'response_sha256':sha(out/'response.json')})
        usage.append({'id':cid,'status':'ok','input_tokens':20,'output_tokens':5})
        notices.append({'next_call_id':cid,'model_attempted':True,'measured_state':state})
        if i==1:conversation.append(message,[span])
    for name,v in [('plan',config),('public_task',public),('events',[{'call':'call_001','span_id':'s1','stage':'model_tool'}]),
        ('spans',{'s1':span}),('usage',usage),('budget_observations',notices)]:
        (folder/(name+'.json')).write_text(json.dumps(v))
    return {'run_id':identifier,'request_checks':checks},original


class FallbackPromptTests(unittest.TestCase):
    def test_source_bound_history_normalizes_fallback_and_preserves_original(self):
        with tempfile.TemporaryDirectory() as tmp:
            storage=Path(tmp);a,original=history_fixture(storage,'left');b,_=history_fixture(storage,'right')
            ar,an,proof=reconstruct(storage,a,original,'call_002');br,bn,_=reconstruct(storage,b,original,'call_002')
            self.assertNotEqual(ar,br);self.assertEqual(an,bn)
            self.assertEqual(proof['known_input_tokens'],20)
            self.assertEqual(ar['messages'][2]['reasoning_content'],an['messages'][2]['reasoning_content'])
            self.assertEqual(json.loads(ar['messages'][2]['content'])['tool_call_records'][0]['id'],'left-random')
            path=storage/'records/context_pilot/left/call_002/request.json'
            self.assertEqual(json.loads(path.read_text()),ar)

    def test_changed_archive_or_unbound_history_cannot_be_reconstructed(self):
        with tempfile.TemporaryDirectory() as tmp:
            storage=Path(tmp);row,original=history_fixture(storage,'test')
            path=storage/'records/context_pilot/test/call_001/request.json';v=json.loads(path.read_text())
            v['messages'][0]['content']='different';path.write_text(json.dumps(v))
            with self.assertRaisesRegex(ValueError,'audited_request'):reconstruct(storage,row,original,'call_002')
            row['request_checks'][0]['request_sha256']=sha(path)
            with self.assertRaisesRegex(ValueError,'original_history'):reconstruct(storage,row,original,'call_002')

    def test_native_control_changes_only_bound_fields_and_negative_control_changes_content(self):
        req={'messages':[{'role':'system','content':'system'},
            {'role':'assistant','content':'literal id-a', 'tool_calls':[{'id':'id-a','type':'function',
                'function':{'name':'f','arguments':'{}'}}]},
            {'role':'tool','tool_call_id':'id-a','content':'value'}]}
        old=copy.deepcopy(req);renamed,negative=controls(req)
        self.assertEqual(req,old);self.assertNotEqual(req,renamed)
        self.assertEqual(renamed['messages'][1]['content'],'literal id-a')
        self.assertEqual(negative['messages'][1:],req['messages'][1:])
        self.assertTrue(negative['messages'][0]['content'].endswith(SUFFIX))

    def test_rendered_results_distinguish_input_identity_from_output_effect(self):
        data,proof=output_fixture();result=interpret(data,proof)
        self.assertFalse(result['original_pair_equal']['tokens'])
        self.assertTrue(result['normalized_pair_equal']['tokens'])
        self.assertFalse(result['causal_output_effect_identified'])
        self.assertFalse(result['quality_or_savings_established'])
        data[IDS[1]]=copy.deepcopy(data[IDS[0]])
        self.assertTrue(interpret(data,proof)['original_pair_equal']['tokens'])

    def test_missing_renderings_counts_and_failed_controls_are_not_silently_accepted(self):
        for kind in ('missing','count','native','negative','normal'):
            data,proof=output_fixture()
            if kind=='missing':data.pop(IDS[-1])
            if kind=='count':data[IDS[1]]['input_tokens']=3
            if kind=='native':data[IDS[4]]['tokens']=[99]
            if kind=='negative':data[IDS[5]]=copy.deepcopy(data[IDS[0]])
            if kind=='normal':data[IDS[3]]['session_controls']={'format':'changed'}
            with self.assertRaises(ValueError):interpret(data,proof)

    def test_scope_changes_are_rejected(self):
        p={'phase':'P83','batch_id':'P83_fallback_prompt_v01','max_renderings':6,
            'max_wall_seconds':180,'max_sampled_rss_bytes':2**31,'max_input_file_bytes':2**21,
            'source_call':'call_014','source_runs':list(SOURCE_RUNS),'case_ids':list(IDS),
            'negative_control_suffix':SUFFIX,'model_generations':0,'evaluator_calls':0,
            'environment_api_requests':0,'reserved_scenarios_read':0,
            'runtime_commit':'620d2225cc436ab0b001e3200e590e3b286ef9ab',
            'source_plan':'configs/P29_stateful_code_v01.json',
            'required_closed_pipeline':'records/context_pilot/P81_pipeline_v01',
            'source_checkpoint':'.runtime/P81_checkpoint_08.json',
            'effective_template_sha256':'0'*64,'raw_template_sha256':'1'*64}
        validate_plan(p)
        for key,value in [('max_renderings',7),('model_generations',1),('source_call','call_015'),
            ('max_wall_seconds',True),('source_runs',list(SOURCE_RUNS[::-1]))]:
            with self.assertRaises(ValueError):validate_plan({**p,key:value})


if __name__=='__main__':unittest.main()
