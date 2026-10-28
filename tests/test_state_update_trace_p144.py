"""Independent UPDATE replay boundaries; only handwritten fake transports."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
from audit_state_update_trace_p144 import (audit_apply_update, audit_parse_update,
    AuditRepresentationCheckpoint, audit_trace)
from checkpoint_state_update_p144 import MODES, StateUpdateCheckpoint
from receipt_reasoning_history import digest
from single_checkpoint_history import FIELDS
from test_checkpoint_representation_p139 import history, message


UPDATE = MODES[2]


def state(items=('old A','old B','old C')):
    return {field:list(items) for field in FIELDS}


def edits():
    return {field:dict(keep=[2],update=[dict(index=0,text='changed A')],delete=[1],add=['new D'])
            for field in FIELDS}


def keep_patch(old):
    return {field:dict(keep=list(range(len(old[field]))),update=[],delete=[],add=[])
            for field in FIELDS}


def first(cls=AuditRepresentationCheckpoint, mode=UPDATE, old=None):
    control=cls(mode); raw=history(6)
    control.begin(raw,8192)
    control.close_separate(raw,message(old or state()),'stop',usage_known=True)
    control.decide(8192,4000)
    return control


def replay(tmp, result):
    from state_update_worker_fixture_p144 import write_wire_fixture
    from whole_task_state_update_p144 import initial_conversation
    trial=write_wire_fixture(tmp,result)
    config=json.loads((trial/'plan.json').read_text())
    public=json.loads((trial/'public_task.json').read_text())
    original=json.loads((ROOT/'configs/P29_stateful_code_v01.json').read_text())
    return trial,config,lambda:audit_trace(trial,config,initial_conversation(original,public))


class StateUpdateReplayTests(unittest.TestCase):
    def test_independent_simultaneous_order_and_counts(self):
        old,patch=state(),edits();before=deepcopy((old,patch))
        new,counts=audit_apply_update(old,patch)
        self.assertEqual(new,state(('changed A','old C','new D')))
        self.assertEqual(counts,dict(kept_old_items=4,update_operations=4,
            unchanged_update_operations=0,updated_old_items=4,deleted_old_items=4,
            added_items=4,changed_old_items=8,final_items=12))
        self.assertEqual((old,patch),before)

    def test_unchanged_update_and_add_are_not_changed_old(self):
        old=state(('unchanged',));patch=keep_patch(old)
        for field in FIELDS:patch[field].update(keep=[],update=[dict(index=0,text='unchanged')],add=['new'])
        _,counts=audit_apply_update(old,patch)
        self.assertEqual(counts['changed_old_items'],0)
        self.assertEqual(counts['unchanged_update_operations'],4)
        self.assertEqual(counts['added_items'],4)

    def test_invalid_coverage_types_ranges_and_duplicate_atomic(self):
        old=state();original=deepcopy(old)
        for kind in ('missing','duplicate','bool','negative','range','extra','bad_text','string_list'):
            patch=edits();one=patch[FIELDS[0]]
            if kind=='missing':one['keep']=[]
            elif kind=='duplicate':one['keep']=[2,0]
            elif kind=='bool':one['keep']=[True]
            elif kind=='negative':one['keep']=[-1]
            elif kind=='range':one['keep']=[3]
            elif kind=='extra':one['unused']=[]
            elif kind=='bad_text':one['update'][0]['text']=None
            else:one['delete']='1'
            saved=deepcopy(patch)
            with self.subTest(kind=kind),self.assertRaises(ValueError):audit_apply_update(old,patch)
            self.assertEqual((old,patch),(original,saved))

    def test_output_merged_item_and_character_caps(self):
        old=state(('a',));patch=keep_patch(old)
        for kind in ('item','field','merged','output'):
            value=deepcopy(patch)
            if kind=='item':value[FIELDS[0]]['add']=['x'*2049]
            elif kind=='field':value[FIELDS[0]]['add']=['x']*32
            elif kind=='merged':
                for f in FIELDS:value[f]['add']=['x'*2048]
            else:
                text=json.dumps(patch)+' '*8192
                with self.assertRaises(ValueError):audit_parse_update({'role':'assistant','content':text},'stop',old)
                continue
            with self.subTest(kind=kind),self.assertRaises(ValueError):audit_apply_update(old,value)

    def test_json_duplicate_fields_finish_tools_and_nonobject_fail(self):
        old=state();text=json.dumps(edits())
        for msg,finish in [({'role':'assistant','content':text},'length'),
            ({'role':'assistant','content':text,'tool_calls':[{}]},'stop'),
            ({'role':'assistant','content':'['+text+']'},'stop'),
            ({'role':'assistant','content':text[:-1]+',"completed":{}}'},'stop')]:
            with self.assertRaises((ValueError,TypeError)):audit_parse_update(msg,finish,old)

    def test_controller_live_independent_transitions_all_modes(self):
        for mode in MODES:
            a,b=StateUpdateCheckpoint(mode),AuditRepresentationCheckpoint(mode)
            for i in (0,1):
                raw=history(6+3*i);body=edits() if mode==UPDATE and i else state()
                self.assertEqual(a.begin(raw,8192),b.begin(raw,8192))
                self.assertEqual(a.close_separate(raw,message(body),'stop',usage_known=True),
                                 b.close_separate(raw,message(body),'stop',usage_known=True))
                self.assertEqual(a.decide(8192,4000),b.decide(8192,4000))
                self.assertEqual(a.view(raw),b.view(raw))
            self.assertEqual(b.fragment_count,2 if mode==MODES[1] else 1)
            self.assertIsNone(b.begin(history(12),50000))

    def test_stale_old_state_and_note_bindings_at_close_and_decide(self):
        for cls in (StateUpdateCheckpoint,AuditRepresentationCheckpoint):
            for boundary in ('close','decide'):
                for changed in ('state','notes'):
                    c=first(cls);raw=history(9);c.begin(raw,8192)
                    if boundary=='decide':c.close_separate(raw,message(edits()),'stop',usage_known=True)
                    if changed=='state':c._values[0][FIELDS[0]][0]='changed outside offer'
                    else:c._notes[0]['content']+='changed outside offer'
                    if boundary=='close':c.close_separate(raw,message(edits()),'stop',usage_known=True)
                    else:c.decide(8192,4000)
                    self.assertEqual(c.events[-1]['reason'],'stale_update_state')
                    self.assertEqual(c.revision,1);self.assertFalse(c.update_applied)

    def test_invalid_nonshrinking_unknown_and_unstarted_do_not_install(self):
        for kind in ('invalid','nonshrinking','unknown','unstarted'):
            c=first();old=deepcopy(c.summary_notes);raw=history(9);c.begin(raw,8192)
            if kind=='unknown':
                with self.assertRaises(ValueError):c.close_separate(raw,message(edits()),'stop',usage_known=False)
                with self.assertRaises(ValueError):c.view(raw)
            elif kind=='unstarted':c.skip_unstarted_summary(raw,'insufficient_shared_call_budget')
            else:
                c.close_separate(raw,message({} if kind=='invalid' else edits()),'stop',usage_known=True)
                if kind=='nonshrinking':c.decide(8192,8192)
            self.assertEqual(c.summary_notes,old);self.assertFalse(c.update_applied)

    def test_fake_worker_all_three_modes_complete_wire_replay(self):
        from state_update_worker_fixture_p144 import fixture
        results=[]
        for mode in MODES:
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as tmp:
                result=fixture(mode=mode,folder=tmp,actions=('echo',)*12+('finish',),max_calls=30)
                _,_,run=replay(tmp,result);audited=run();results.append(audited)
                self.assertEqual(audited['state_update_control'],result['result']['state_update_control'])
                self.assertEqual(audited['known_total_tokens'],result['result']['known_total_tokens'])
                self.assertEqual(audited['usage_by_role'],result['result']['usage_by_role'])
                self.assertEqual(audited['unknown_usage_calls'],0)
                self.assertEqual(audited['update_installations'],int(mode==UPDATE))
                self.assertEqual(audited['actual_delta_actor_calls']>0,mode==MODES[1])
                if mode==UPDATE:
                    self.assertEqual(audited['changed_old_items'],4)
                    self.assertGreater(audited['actual_changed_old_known_actor_calls'],0)
                    self.assertEqual(audited['fragment_count'],1)
        from checkpoint_prefix_identity_p140 import representation_prefix_comparison
        for control in results[:2]:
            self.assertIs(representation_prefix_comparison(control,results[2])['canonical_match'],True)

    def test_fake_worker_invalid_paid_and_unknown_focus_are_retained(self):
        from state_update_worker_fixture_p144 import fixture
        for second in ('invalid','unknown','transport_error'):
            with self.subTest(second=second),tempfile.TemporaryDirectory() as tmp:
                result=fixture(mode=UPDATE,folder=tmp,actions=('echo',)*12+('finish',),max_calls=30,
                               summary_mode=['valid',second])
                _,_,run=replay(tmp,result);a=run()
                self.assertEqual(a['update_installations'],0)
                self.assertEqual(a['update_prompt_dispatched_focus_calls'],1)
                self.assertEqual(a['update_prompt_known_focus_calls'],int(second=='invalid'))
                self.assertEqual(a['unknown_usage_calls'],int(second!='invalid'))
                if second=='invalid':
                    decision=result['result']['checkpoint_control']['decisions'][-1]
                    self.assertEqual(decision['reason'],'invalid_update_patch')
                    self.assertEqual(a['usage_by_role']['focus']['calls'],2)
                else:self.assertEqual(result['captured'][-1]['role'],'focus')

    def test_fake_worker_update_view_without_semantic_old_change_is_separate(self):
        from state_update_worker_fixture_p144 import fixture
        old=state(('fixture',));patch=keep_patch(old)
        with tempfile.TemporaryDirectory() as tmp:
            result=fixture(mode=UPDATE,folder=tmp,actions=('echo',)*12+('finish',),max_calls=30,
                           summary_payloads=[old,patch])
            _,_,run=replay(tmp,result);a=run()
            self.assertEqual(a['update_installations'],1)
            self.assertGreater(a['actual_update_known_actor_calls'],0)
            self.assertEqual(a['actual_changed_old_actor_calls'],0)
            self.assertEqual(a['changed_old_items'],0)

    def test_delete_then_readd_identical_text_is_not_changed_state_activity(self):
        from state_update_worker_fixture_p144 import fixture
        old=state(('fixture',));patch=keep_patch(old)
        for field in FIELDS:patch[field].update(keep=[],delete=[0],add=['fixture'])
        with tempfile.TemporaryDirectory() as tmp:
            result=fixture(mode=UPDATE,folder=tmp,actions=('echo',)*12+('finish',),max_calls=30,
                           summary_payloads=[old,patch])
            _,_,run=replay(tmp,result);a=run()
            self.assertEqual(a['deleted_old_items'],4)
            self.assertEqual(a['changed_old_items'],4)
            self.assertEqual(a['update_installations'],1)
            self.assertGreater(a['actual_update_known_actor_calls'],0)
            self.assertEqual(a['actual_changed_old_actor_calls'],0)
            self.assertEqual(a['state_changed_installations'],0)
            self.assertEqual(a['old_items_changed_installations'],0)

    def test_saved_input_count_and_update_disclosure_tamper_rejected(self):
        from state_update_worker_fixture_p144 import fixture
        with tempfile.TemporaryDirectory() as tmp:
            result=fixture(mode=UPDATE,folder=tmp,actions=('echo',)*12+('finish',),max_calls=30)
            trial,_,run=replay(tmp,result);run()
            for filename,key in [('rolling_input_counts.json','messages_sha256'),
                                 ('state_update_views.json','summary_notes_sha256')]:
                path=trial/filename;data=json.loads(path.read_text());before=path.read_bytes()
                data[-1][key]='0'*64;path.write_text(json.dumps(data))
                with self.assertRaises(ValueError):run()
                path.write_bytes(before)
            path=trial/'summary.json';data=json.loads(path.read_text())
            data['state_update_control']['changed_old_items']+=1
            path.write_text(json.dumps(data))
            with self.assertRaises(ValueError):run()

    def test_accepted_update_without_dispatch_is_not_actual_exposure(self):
        from state_update_worker_fixture_p144 import fixture
        from tool_choice_residual import ToolChoiceResidualInference
        from run_context_comparison import BudgetStop
        ordinary_call=ToolChoiceResidualInference.call
        def stop_after_install(infer,role,messages,tools):
            if infer.checkpoint.update_applied:raise BudgetStop('wall_limit')
            return ordinary_call(infer,role,messages,tools)
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(ToolChoiceResidualInference,'call',stop_after_install):
                result=fixture(mode=UPDATE,folder=tmp,actions=('echo',)*12,max_calls=30)
            _,_,run=replay(tmp,result);a=run()
            self.assertEqual(a['update_installations'],1)
            self.assertEqual(a['actual_update_actor_calls'],0)
            self.assertEqual(a['actual_changed_old_known_actor_calls'],0)
            self.assertTrue(result['saved']['state_update_views'][-1]['update_view'])
            self.assertFalse(result['saved']['state_update_views'][-1]['model_attempted'])

    def test_unknown_and_lost_terminal_actor_with_update_are_not_known(self):
        from state_update_worker_fixture_p144 import fixture
        for action in ('unknown','transport_error'):
            with self.subTest(action=action),tempfile.TemporaryDirectory() as tmp:
                result=fixture(mode=UPDATE,folder=tmp,actions=('echo',)*8+(action,),max_calls=30)
                _,_,run=replay(tmp,result);a=run()
                self.assertEqual(a['unknown_usage_calls'],1)
                self.assertEqual(a['actual_update_unknown_actor_calls'],1)
                self.assertEqual(a['actual_changed_old_unknown_actor_calls'],1)
                self.assertFalse(a['state_update_accounting_complete'])
                self.assertEqual(a['known_total_tokens'],result['result']['known_total_tokens'])

    def test_paid_actor_measurement_failure_retains_cost_and_withholds_action(self):
        from state_update_worker_fixture_p144 import fixture
        from checkpoint_representation_inference_p139 import CheckpointRepresentationInference
        from run_context_comparison import BudgetStop
        normal=CheckpointRepresentationInference._count_without_raw
        for exception in (ValueError('synthetic count failure'),BudgetStop('wall_limit_before_prefix_exposure_count')):
            def stop_measurement(infer,*args):
                if infer.checkpoint.update_applied:raise exception
                return normal(infer,*args)
            with self.subTest(exception=type(exception).__name__),tempfile.TemporaryDirectory() as tmp:
                with patch.object(CheckpointRepresentationInference,'_count_without_raw',stop_measurement):
                    result=fixture(mode=UPDATE,folder=tmp,actions=('echo',)*12,max_calls=30)
                _,_,run=replay(tmp,result);a=run()
                self.assertEqual(a['unknown_usage_calls'],0)
                self.assertFalse(a['state_update_accounting_complete'])
                self.assertEqual(a['prefix_exposure_control']['incomplete_paid_actor_measurements'],1)
                self.assertEqual(a['known_total_tokens'],result['result']['known_total_tokens'])
                actors=sum(c['role']=='agent' for c in result['captured'])
                self.assertEqual(len(result['programs']),actors-1)

    def test_new_cohort_accepts_all_modes_without_fake_success(self):
        from state_update_worker_fixture_p144 import fixture,configuration
        from audit_whole_task_state_update_p144 import audit_cell
        from whole_task_state_update_p144 import initial_conversation
        for mode in MODES:
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as tmp:
                result=fixture(mode=mode,folder=tmp,actions=('finish',))
                trial,_,_=replay(tmp,result)
                plan=json.loads((trial/'comparison_plan.json').read_text())
                original,_,item=configuration();original['api_budget_by_task']['6104387_1']=80
                archive,_=initial_conversation(original,item['public_task']).for_model()
                row=audit_cell(trial,ROOT,plan,original,item,mode,
                               {'base_messages_sha256':digest(archive)},False)
                self.assertEqual(row['record_status'],'unevaluated')
                self.assertIsNone(row['success'])
                self.assertEqual(row['model_seed'],257)
                self.assertFalse(row['state_update_contract_failed'])


if __name__=='__main__':unittest.main()
