"""Synthetic transport/control tests: no live model, tokenizer, task API or evaluator."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'tests')]
import test_state_update_p144 as fixture
import checkpoint_indexed_update_p147 as core
from test_checkpoint_indexed_update_p147 import keep_all
import indexed_update_transport_p147 as transport
from indexed_update_inference_p147 import IndexedUpdateInference
from checkpoint_state_update_inference_p144 import StateUpdateInference
from fixed_budget_local_llama import payload_for as old_focus_payload
from checkpoint_attempt_usage import attempt_usage
from receipt_reasoning_history import digest
from run_context_comparison import BudgetStop
import indexed_update_config_p147 as config
from whole_task_state_update_p144 import worker_config as old_worker_config,cell_id as old_cell_id


def model_config():
    return dict(model='synthetic',base_url='http://127.0.0.1:8011',temperature=.7,seed=257,
        num_predict=4096,num_ctx=65536,reasoning_budget_tokens=-1,thinking_mode='enabled',
        tool_choice='auto',cache_prompt=True,call_timeout_seconds=600)


def indexed_edited(old):
    result=keep_all(old)
    result['completed']['by_index']={'0':{'action':'update','text':'replacement'},'1':{'action':'delete'}}
    result['completed']['add']=['new item']
    return result


def raw_response(value=None):
    return dict(usage=dict(prompt_tokens=200,completion_tokens=31,total_tokens=231),
        choices=[dict(finish_reason='stop',message=fixture.message(
            indexed_edited(fixture.state()) if value is None else value))])


def infer_fixture(folder,mode=config.MODES[1]):
    old=fixture.InferenceBoundaryTests().fake_inference(folder,mode=mode)
    old.__class__=IndexedUpdateInference
    old.checkpoint=core.IndexedStateUpdateCheckpoint(mode)
    old.checkpoint.begin(fixture.history(6),8192)
    old.checkpoint.close_separate(fixture.history(6),fixture.message(fixture.state()),'stop',usage_known=True)
    old.checkpoint.decide(8192,4000)
    old.config.update(max_wall_seconds=1800,seed=257,draft_temperature=.7,agent_temperature=1.,
        model=model_config())
    old.started=time.monotonic();old.policy='residual';old.input_counts=[]
    def resolve(normalized,tools):
        if old.checkpoint.pending:
            decision=old.checkpoint.decide(2000,1000)
            old.controls.append(dict(status='checkpoint_decided',after_model_calls=len(old.calls),**decision))
    old._resolve=resolve
    return old


class TransportTests(unittest.TestCase):
    def setUp(self):
        self.old=fixture.state()
        self.messages=fixture.installed().begin(fixture.history(9),8192)['summary_messages']

    def test_payload_changes_only_three_predeclared_fields(self):
        cfg=model_config();before=deepcopy((cfg,self.messages,self.old))
        expected=old_focus_payload(cfg,self.messages,[])
        result=transport.payload_for(cfg,self.messages,[],self.old)
        self.assertEqual(result['reasoning_budget_tokens'],2048)
        self.assertTrue(result['response_format']['json_schema']['strict'])
        self.assertEqual(result['messages'][0]['content'],core.INDEXED_UPDATE_PROMPT)
        result['messages'][0]=expected['messages'][0]
        result.pop('response_format');result['reasoning_budget_tokens']=-1
        self.assertEqual(result,expected)
        self.assertEqual((cfg,self.messages,self.old),before)

    def test_count_and_generation_have_identical_payload_and_saved_request(self):
        seen=[]
        def post(cfg,endpoint,payload,timeout):
            seen.append((endpoint,deepcopy(payload)))
            return {'input_tokens':200} if endpoint.endswith('input_tokens') else raw_response()
        with tempfile.TemporaryDirectory() as tmp,patch.object(transport,'post',post),patch.object(transport.signal,'alarm'):
            count=transport.count_input(model_config(),self.messages,[],self.old)
            response=transport.model_call(model_config(),self.messages,tmp,900,[],self.old,
                expected_request_sha256=count['request_sha256'])
            self.assertEqual(response['status'],'ok')
            self.assertEqual(seen[0][1],seen[1][1])
            self.assertEqual(json.loads((Path(tmp)/'request.json').read_text()),seen[1][1])

    def test_changed_payload_is_rejected_before_model_dispatch(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(transport,'post') as post:
            with self.assertRaisesRegex(ValueError,'payload_mismatch'):
                transport.model_call(model_config(),self.messages,tmp,900,[],self.old,
                    expected_request_sha256='0'*64)
            post.assert_not_called()
            self.assertFalse((Path(tmp)/'request.json').exists())

    def test_timeout_remains_unknown_and_persists_response(self):
        payload=transport.payload_for(model_config(),self.messages,[],self.old)
        with tempfile.TemporaryDirectory() as tmp,patch.object(transport,'post',side_effect=TimeoutError()),patch.object(transport.signal,'alarm'):
            result=transport.model_call(model_config(),self.messages,tmp,100,[],self.old,
                expected_request_sha256=digest(payload))
            self.assertEqual(result['status'],'error');self.assertIsNone(result['input_tokens'])
            self.assertIsNone(result['output_tokens']);self.assertEqual(result['timeout_scope'],'run_wall')
            self.assertEqual(json.loads((Path(tmp)/'response.json').read_text()),result)

    def test_tools_wrong_cap_or_old_state_mismatch_cannot_use_transport(self):
        for cfg,tools,old in [(model_config(),[{}],self.old),
                ({**model_config(),'num_predict':2048},[],self.old),
                (model_config(),[],{f:[] for f in self.old})]:
            with self.subTest(cfg=cfg,tools=tools),self.assertRaises(ValueError):
                transport.payload_for(cfg,self.messages,tools,old)


class UpdateBranchTests(unittest.TestCase):
    def test_first_checkpoint_and_both_recursive_views_are_identical_to_frozen_controller(self):
        for mode in config.MODES:
            old=fixture.core.StateUpdateCheckpoint(mode)
            new=core.IndexedStateUpdateCheckpoint(mode)
            rounds=(6,9) if mode==config.MODES[0] else (6,)
            for n in rounds:
                archive=fixture.history(n)
                self.assertEqual(old.begin(archive,8192),new.begin(archive,8192))
                self.assertEqual(old.close_separate(archive,fixture.message(fixture.state()),'stop',usage_known=True),
                                 new.close_separate(archive,fixture.message(fixture.state()),'stop',usage_known=True))
                self.assertEqual(old.decide(8192,4000),new.decide(8192,4000))
                self.assertEqual(old.view(archive),new.view(archive))
                self.assertEqual(old.events,new.events)
            self.assertEqual(new.indexed_conversions,[])

    def test_actor_counter_resolver_and_first_focus_are_frozen_delegations(self):
        self.assertIs(IndexedUpdateInference.call,StateUpdateInference.call)
        self.assertIs(IndexedUpdateInference._count,StateUpdateInference._count)
        self.assertIs(IndexedUpdateInference._count_without_raw,StateUpdateInference._count_without_raw)
        self.assertIs(IndexedUpdateInference._resolve,StateUpdateInference._resolve)
        for mode,index in [(config.MODES[0],1),(config.MODES[0],2),(config.MODES[1],1)]:
            with tempfile.TemporaryDirectory() as tmp:
                infer=infer_fixture(tmp,mode)
                offered=dict(opportunity_index=index,update_requested=False)
                with (patch.object(StateUpdateInference,'_summarize_separately',return_value='old') as old,
                     patch.object(transport,'post',side_effect=AssertionError('new transport must not run'))):
                    self.assertEqual(infer._summarize_separately(['same'],['same'],offered),'old')
                    old.assert_called_once_with(['same'],['same'],offered)

    def test_second_update_valid_paid_usage_and_frozen_state_application(self):
        requests=[]
        def post(cfg,endpoint,payload,timeout):
            requests.append((endpoint,deepcopy(payload)))
            return {'input_tokens':200} if endpoint.endswith('input_tokens') else raw_response()
        with tempfile.TemporaryDirectory() as tmp,patch.object(transport,'post',post),patch.object(transport.signal,'alarm'):
            infer=infer_fixture(tmp);offered=infer.checkpoint.begin(fixture.history(9),8192)
            infer.offers=[dict(after_model_calls=0,offer=offered)]
            infer._summarize_separately(fixture.history(9),[],offered)
            self.assertEqual(len(requests),3)
            self.assertEqual([r[1] for r in requests],[requests[0][1]]*3)
            self.assertEqual(infer.tokens,231);self.assertEqual(infer.exposure.previous_focus_cost,231)
            self.assertTrue(infer.checkpoint.update_applied)
            self.assertGreater(infer.checkpoint.installed_update_counts['changed_old_items'],0)
            self.assertEqual(infer.schema_transport_summary()['update_dispatched'],1)
            self.assertEqual(infer.checkpoint._values[0]['completed'],['replacement','new item'])
            conversion=infer.checkpoint.indexed_conversions[0]
            self.assertEqual(conversion['status'],'converted_and_strictly_validated')
            self.assertEqual(conversion['raw_response_sha256'],digest(raw_response()['choices'][0]['message']))
            self.assertNotEqual(conversion['raw_response_sha256'],conversion['converted_message_sha256'])
            self.assertTrue(conversion['unchanged_P144_parser_reapplied'])
            self.assertFalse(conversion['repair_applied'])
            saved=json.loads((Path(tmp)/'call_001/request.json').read_text())
            self.assertEqual(saved['messages'][0]['content'],core.INDEXED_UPDATE_PROMPT)
            self.assertEqual(saved['messages'][1],offered['summary_messages'][1])
            self.assertNotEqual(saved['messages'][0],offered['summary_messages'][0])

    def test_known_invalid_patch_keeps_paid_usage_without_installation(self):
        def post(cfg,endpoint,payload,timeout):
            return {'input_tokens':200} if endpoint.endswith('input_tokens') else raw_response({'invalid':True})
        with tempfile.TemporaryDirectory() as tmp,patch.object(transport,'post',post),patch.object(transport.signal,'alarm'):
            infer=infer_fixture(tmp);offered=infer.checkpoint.begin(fixture.history(9),8192)
            infer._summarize_separately(fixture.history(9),[],offered)
            self.assertEqual(infer.tokens,231);self.assertFalse(infer.checkpoint.update_applied)
            self.assertEqual(infer.exposure.events[-1]['status'],'known_paid_focus')
            terminal=[e for e in infer.controls if e['status']=='checkpoint_terminal_without_counted_decision']
            self.assertEqual(len(terminal),1);self.assertFalse(terminal[0]['accepted'])

    def test_valid_old_operation_lists_are_rejected_as_wrong_representation_with_paid_usage(self):
        legacy=fixture.edited(fixture.state())
        fixture.core.parse_update_patch(fixture.message(legacy),'stop',fixture.state())
        def post(cfg,endpoint,payload,timeout):
            return {'input_tokens':200} if endpoint.endswith('input_tokens') else raw_response(legacy)
        with tempfile.TemporaryDirectory() as tmp,patch.object(transport,'post',post),patch.object(transport.signal,'alarm'):
            infer=infer_fixture(tmp);before=infer.checkpoint.view(fixture.history(9))
            offered=infer.checkpoint.begin(fixture.history(9),8192)
            infer._summarize_separately(fixture.history(9),[],offered)
            self.assertEqual(infer.tokens,231);self.assertFalse(infer.checkpoint.update_applied)
            self.assertEqual(infer.checkpoint.view(fixture.history(9)),before)
            self.assertEqual(infer.checkpoint.events[-1]['reason'],'invalid_update_patch')
            self.assertEqual(infer.checkpoint.indexed_conversions[0]['status'],'rejected')
            self.assertFalse(infer.exposure.blocked)
            self.assertIsNone(infer.checkpoint.pending)

    def test_unknown_and_stale_checkpoint_close_never_apply_host_conversion(self):
        for usage_known,stale in [(False,False),(True,True)]:
            with tempfile.TemporaryDirectory() as tmp:
                infer=infer_fixture(tmp);c=infer.checkpoint
                c.begin(fixture.history(9),8192)
                if stale:c._values[0]['completed'][0]='externally altered'
                with patch.object(core,'to_legacy_patch',side_effect=AssertionError('conversion forbidden')):
                    if not usage_known:
                        with self.assertRaisesRegex(ValueError,'unknown_usage'):
                            c.close_separate(fixture.history(9),fixture.message(indexed_edited(fixture.state())),
                                'stop',usage_known=False)
                        self.assertTrue(c._blocked)
                    else:
                        c.close_separate(fixture.history(9),fixture.message(indexed_edited(fixture.state())),
                            'stop',usage_known=True)
                        self.assertEqual(c.events[-1]['reason'],'stale_update_state')
                self.assertFalse(c.update_applied)

    def test_unknown_response_stops_and_remains_an_unknown_attempt(self):
        def post(cfg,endpoint,payload,timeout):
            if endpoint.endswith('input_tokens'):return {'input_tokens':200}
            raise TimeoutError('synthetic timeout')
        with tempfile.TemporaryDirectory() as tmp,patch.object(transport,'post',post),patch.object(transport.signal,'alarm'):
            infer=infer_fixture(tmp);offered=infer.checkpoint.begin(fixture.history(9),8192)
            with self.assertRaisesRegex(RuntimeError,'usage unknown'):
                infer._summarize_separately(fixture.history(9),[],offered)
            usage=attempt_usage(infer)
            self.assertEqual(len(usage),1);self.assertEqual(usage[0]['status'],'error')
            self.assertIsNone(usage[0]['input_tokens']);self.assertEqual(infer.tokens,0)
            self.assertTrue(infer.exposure.blocked);self.assertFalse(infer.checkpoint.update_applied)

    def test_dispatch_without_terminal_record_is_retained_as_unknown(self):
        with tempfile.TemporaryDirectory() as tmp:
            infer=infer_fixture(tmp);offered=infer.checkpoint.begin(fixture.history(9),8192)
            def lost(*args,**kwargs):
                infer.admissions.append(dict(next_call_id='call_001',role='focus',model_request_started=True))
                raise RuntimeError('lost terminal write')
            with patch.object(infer,'_count_update_focus',return_value={'input_tokens':200}),patch.object(infer,'_call_update_focus',lost):
                with self.assertRaisesRegex(RuntimeError,'lost terminal'):
                    infer._summarize_separately(fixture.history(9),[],offered)
            usage=attempt_usage(infer)
            self.assertEqual(len(usage),1)
            self.assertEqual(usage[0]['error_kind'],'dispatched_without_terminal_usage')
            self.assertIsNone(usage[0]['input_tokens'])
            self.assertEqual(infer.controls[-1]['unknown_usage_calls'],1)

    def test_unstarted_summary_is_not_charged_or_dispatched(self):
        with tempfile.TemporaryDirectory() as tmp:
            infer=infer_fixture(tmp);infer.config['max_calls']=1
            offered=infer.checkpoint.begin(fixture.history(9),8192)
            with patch.object(infer,'_count_update_focus',return_value={'input_tokens':200}),patch.object(infer,'_call_update_focus') as call:
                infer._summarize_separately(fixture.history(9),[],offered)
                call.assert_not_called()
            self.assertEqual(attempt_usage(infer),[]);self.assertEqual(infer.tokens,0)
            self.assertEqual(infer.exposure.previous_focus_cost,100)

    def test_screening_and_admission_count_mismatch_blocks_generation(self):
        with tempfile.TemporaryDirectory() as tmp:
            infer=infer_fixture(tmp);offered=infer.checkpoint.begin(fixture.history(9),8192)
            old=infer.checkpoint.pending['update_prior_state']
            payload=transport.payload_for(infer._focus_config(),offered['summary_messages'],[],old)
            native=dict(input_tokens=200,wall_seconds=0,request_sha256=digest(payload))
            with patch.object(transport,'count_input',return_value=native),patch.object(transport,'model_call') as model:
                with self.assertRaisesRegex(ValueError,'screen_admission'):
                    infer._call_update_focus(offered['summary_messages'],old,
                        screened_count={**native,'input_tokens':201})
                model.assert_not_called()
            self.assertEqual(attempt_usage(infer),[])
            self.assertFalse(infer.admissions[-1]['model_attempted'])

    def test_forged_update_flag_cannot_apply_schema_to_first_or_recursive_focus(self):
        for mode in config.MODES:
            with tempfile.TemporaryDirectory() as tmp:
                infer=infer_fixture(tmp,mode);offered=infer.checkpoint.begin(fixture.history(9),8192)
                offered['update_requested']=True
                offered['opportunity_index']=1
                with patch.object(transport,'post') as post:
                    with self.assertRaisesRegex(ValueError,'only_bound_second_UPDATE'):
                        infer._summarize_separately(fixture.history(9),[],offered)
                    post.assert_not_called()

    def test_known_usage_mismatch_is_retained_before_error(self):
        def post(cfg,endpoint,payload,timeout):
            if endpoint.endswith('input_tokens'):return {'input_tokens':200}
            raw=raw_response();raw['usage'].update(prompt_tokens=201,total_tokens=232)
            return raw
        with tempfile.TemporaryDirectory() as tmp,patch.object(transport,'post',post),patch.object(transport.signal,'alarm'):
            infer=infer_fixture(tmp);offered=infer.checkpoint.begin(fixture.history(9),8192)
            with self.assertRaisesRegex(RuntimeError,'terminal input counts differ'):
                infer._summarize_separately(fixture.history(9),[],offered)
            self.assertEqual(infer.tokens,232)
            self.assertEqual(attempt_usage(infer)[0]['status'],'ok')
            self.assertEqual(infer.exposure.previous_focus_cost,232)
            self.assertFalse(infer.checkpoint.update_applied)


class ConfigurationTests(unittest.TestCase):
    def plan(self):
        p=json.loads((ROOT/'configs/P144_state_update_v01.json').read_text())
        p.update(config.fixed_fields());p.pop('deadline_jst');p.pop('reporting_deadline_jst')
        return p

    def test_all_eight_fresh_ids_balanced_order_and_same_scientific_configuration(self):
        p=self.plan();original=json.loads((ROOT/'configs/P29_stateful_code_v01.json').read_text())
        config.validate_plan(p)
        order=config.run_order();self.assertEqual(len(order),8)
        self.assertEqual([m for _,m in order],[config.MODES[0],config.MODES[1],config.MODES[1],config.MODES[0]]*2)
        metadata={'phase','experiment','comparison_arm','update_transport','actor_reasoning_budget_tokens',
            'first_focus_reasoning_budget_tokens','update_focus_reasoning_budget_tokens'}
        for number,mode in order:
            tid=config.TASKS[number-1]
            new=config.worker_config(original,p,tid,config.ERROR_POLICY,config.cell_id(number,mode),mode)
            prior=old_worker_config(original,p,tid,config.ERROR_POLICY,old_cell_id(number,mode),mode)
            self.assertEqual({k:v for k,v in new.items() if k not in metadata},
                             {k:v for k,v in prior.items() if k not in metadata})
            self.assertEqual(config.ARM_LABELS[config.MODES[1]],'UPDATE_INDEXED')
            self.assertEqual(new['phase'],'P147');self.assertEqual(new['model']['reasoning_budget_tokens'],-1)
            self.assertIn('P147',config.cell_id(number,mode));self.assertNotIn('P144',config.cell_id(number,mode))

    def test_old_identity_stale_deadline_seed_or_budget_changes_are_rejected(self):
        p=self.plan();original=json.loads((ROOT/'configs/P29_stateful_code_v01.json').read_text())
        for key,value in [('deadline_jst','past'),('model_seed',357),('max_cells',12),('max_wall_seconds',2400),
                          ('candidate_selection_from_results',True)]:
            changed=deepcopy(p);changed[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):config.validate_plan(changed)
        with self.assertRaises(ValueError):
            config.worker_config(original,p,config.TASKS[0],config.ERROR_POLICY,'BOC_P144_01_THRESHOLD_RECURSIVE',config.MODES[0])


if __name__=='__main__':unittest.main()
