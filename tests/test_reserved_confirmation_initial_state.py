"""Synthetic typed-bridge receipts only; no world/model/API/evaluator calls."""
import ast
from copy import deepcopy
import inspect
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import reserved_confirmation_initial_state as initial
from reserved_confirmation_schedule import build_schedule
from protocol_stable_history import StableReferenceConversation


def fixture():
    reservation = dict(status='frozen', source_sha256='a'*64,
        task_ids=[f'synthetic-{i:02d}_1' for i in [8,2,12,1,5,3,10,4,11,7,6,9]])
    args = dict(baseline='ordinary', candidate='chosen_method', seed=57,
        budgets=dict(max_calls=80, max_total_tokens=450000, max_api_requests=80,
                     max_wall_seconds=1800, max_setup_seconds=120, max_cleanup_seconds=180,
                     max_idle_wait_seconds=60, max_evaluation_seconds=180))
    plan = build_schedule(reservation, **args)
    args.update(namespace='HANDWRITTEN_ONLY', world_seed=42)
    requests = initial.initialization_requests(plan, reservation, **args)
    refs = []
    for i,command in enumerate(requests['reference']):
        public = dict(instruction=f'Invented task {i}; no real requirements',
            supervisor={'name':'synthetic person'}, app_descriptions={'synthetic':'invented'},
            helper_docs={'api_docs':{}, 'supervisor':{}}, ground_truth_loaded=False)
        refs.append(dict(initialization=receipt(command, public),
            cleanup={'process_stopped':True, 'graceful':True, 'transport_failed':False}))
    return plan, reservation, args, requests, refs


def receipt(command, public):
    return dict(command=deepcopy(command), raw_request_started=True, wall_seconds=0.25,
                response={'ok':True,'result':deepcopy(public) | {'api_result_protocol':initial.PROTOCOL}})


class InitialStateTests(unittest.TestCase):
    def test_full12_reference_and_all24_worker_inputs_use_real_pure_formatter(self):
        plan,reservation,args,commands,refs=fixture()
        before=deepcopy((plan,reservation,args,refs))
        bundle=initial.bind_reference_initial_states(plan,reservation,refs,**args)
        bound=initial.digest(bundle); payloads=[]
        self.assertEqual(len({c['experiment'] for v in commands.values() for c in v}),36)
        self.assertEqual([c['task_id'] for c in commands['reference']],reservation['task_ids'])
        for cell,command in zip(plan['cells'],commands['cells']):
            public=bundle['references'][cell['scenario_ordinal']-1]['public_task']
            value=initial.confirm_cell_initial_state(plan,reservation,bundle,cell['slot'],
                receipt(command,public),expected_bundle_sha256=bound,**args)
            messages,stats=StableReferenceConversation('synthetic fixed system',value).for_model()
            self.assertEqual(stats,{'text_fallback_turns':0,'paged_spans':0})
            payloads.append(messages)
            self.assertNotIn('source_run',bundle['references'][cell['scenario_ordinal']-1])
            value['instruction']='mutated after return'
        for i in range(12):self.assertEqual(payloads[i*2],payloads[i*2+1])
        self.assertEqual((plan,reservation,args,refs),before)
        self.assertEqual(initial.digest(bundle),bound)
        self.assertNotIn('reserved_scenarios_read',bundle)

    def test_partial_reference_selection_and_reordered_or_reused_init_rejected(self):
        for variant in ['subset','reordered','duplicate','wrong_task','old_namespace','wrong_seed']:
            plan,r,args,commands,refs=fixture()
            if variant=='subset':refs=refs[:4]
            elif variant=='reordered':refs.reverse()
            elif variant=='duplicate':refs[1]=deepcopy(refs[0])
            elif variant=='wrong_task':refs[0]['initialization']['command']['task_id']='unreserved_1'
            elif variant=='old_namespace':refs[0]['initialization']['command']['experiment']='old_run'
            else:refs[0]['initialization']['command']['seed']=True
            with self.subTest(variant=variant),self.assertRaises(ValueError):
                initial.bind_reference_initial_states(plan,r,refs,**args)

    def test_failed_unknown_unclosed_overbudget_or_ground_truth_reference_rejected(self):
        for variant in ['not_sent','error','missing','unclosed','cleanup_unknown','protocol','truth','extra','wall','nan']:
            plan,r,args,commands,refs=fixture();row=refs[0]['initialization']
            if variant=='not_sent':row['raw_request_started']=False
            elif variant=='error':row['response']={'ok':False,'error':'PRIVATE_SENTINEL'}
            elif variant=='missing':row.pop('response')
            elif variant=='unclosed':refs[0]['cleanup']['process_stopped']=False
            elif variant=='cleanup_unknown':refs[0]['cleanup']['transport_failed']=True
            elif variant=='protocol':row['response']['result']['api_result_protocol']='other'
            elif variant=='truth':row['response']['result']['ground_truth_loaded']=True
            elif variant=='extra':row['response']['result']['gold']='PRIVATE_SENTINEL'
            elif variant=='wall':row['wall_seconds']=121
            else:row['wall_seconds']=float('nan')
            with self.subTest(variant=variant),self.assertRaises(ValueError) as caught:
                initial.bind_reference_initial_states(plan,r,refs,**args)
            self.assertNotIn('PRIVATE_SENTINEL',str(caught.exception))

    def test_cell_reset_must_match_bound_initial_projection_and_own_command(self):
        for variant in ['different_body','swapped_task','reference_namespace','different_seed','protocol','slot','boolean_slot']:
            plan,r,args,commands,refs=fixture()
            bundle=initial.bind_reference_initial_states(plan,r,refs,**args)
            row=receipt(commands['cells'][0],bundle['references'][0]['public_task']);slot=1
            if variant=='different_body':row['response']['result']['instruction']='different PRIVATE_SENTINEL'
            elif variant=='swapped_task':row['command']=commands['cells'][2]
            elif variant=='reference_namespace':row['command']=commands['reference'][0]
            elif variant=='different_seed':row['command']['seed']=43
            elif variant=='protocol':row['response']['result']['api_result_protocol']='other'
            elif variant=='slot':slot=25
            else:slot=True
            with self.subTest(variant=variant),self.assertRaises(ValueError) as caught:
                initial.confirm_cell_initial_state(plan,r,bundle,slot,row,
                    expected_bundle_sha256=initial.digest(bundle),**args)
            self.assertNotIn('PRIVATE_SENTINEL',str(caught.exception))

    def test_external_bundle_hash_and_schedule_authority_cannot_be_replaced(self):
        plan,r,args,commands,refs=fixture()
        bundle=initial.bind_reference_initial_states(plan,r,refs,**args);bound=initial.digest(bundle)
        row=receipt(commands['cells'][0],bundle['references'][0]['public_task'])
        bundle['references'][0]['public_task']['instruction']='tampered'
        with self.assertRaises(ValueError):initial.confirm_cell_initial_state(plan,r,bundle,1,row,
            expected_bundle_sha256=bound,**args)
        bundle=initial.bind_reference_initial_states(plan,r,refs,**args)
        plan['cells'][0]['method']='replacement'
        with self.assertRaises(ValueError):initial.confirm_cell_initial_state(plan,r,bundle,1,row,
            expected_bundle_sha256=initial.digest(bundle),**args)

    def test_every_reference_not_only_selected_cell_is_bound(self):
        plan,r,args,commands,refs=fixture()
        bundle=initial.bind_reference_initial_states(plan,r,refs,**args)
        row=receipt(commands['cells'][0],bundle['references'][0]['public_task'])
        bundle['references'][-1]['task_id']='replacement_1'
        with self.assertRaises(ValueError):initial.confirm_cell_initial_state(plan,r,bundle,1,row,
            expected_bundle_sha256=initial.digest(bundle),**args)

    def test_typed_boolean_and_number_in_public_state_are_not_equal(self):
        plan,r,args,commands,refs=fixture();refs[0]['initialization']['response']['result']['supervisor']['test']=1
        bundle=initial.bind_reference_initial_states(plan,r,refs,**args)
        row=receipt(commands['cells'][0],bundle['references'][0]['public_task'])
        row['response']['result']['supervisor']['test']=True
        with self.assertRaises(ValueError):initial.confirm_cell_initial_state(plan,r,bundle,1,row,
            expected_bundle_sha256=initial.digest(bundle),**args)

    def test_typed_bridge_helper_documents_must_be_objects(self):
        for key in ['api_docs','supervisor']:
            for malformed in [None,[],True]:
                plan,r,args,_,refs=fixture()
                refs[0]['initialization']['response']['result']['helper_docs'][key]=malformed
                with self.subTest(key=key,value=malformed),self.assertRaises(ValueError):
                    initial.bind_reference_initial_states(plan,r,refs,**args)

    def test_invalid_namespace_seed_and_no_action_entrypoint(self):
        for changes in [{'namespace':'../escape'},{'namespace':''},{'world_seed':True},{'world_seed':-1}]:
            plan,r,args,_,_=fixture();args.update(changes)
            with self.assertRaises(ValueError):initial.initialization_requests(plan,r,**args)
        tree=ast.parse(inspect.getsource(initial))
        imports={n.module if isinstance(n,ast.ImportFrom) else x.name
            for n in ast.walk(tree) if isinstance(n,(ast.Import,ast.ImportFrom)) for x in n.names}
        self.assertEqual(imports,{'copy','hashlib','json','math','re','public_api_envelope','reserved_confirmation_schedule'})
        forbidden={'open','exec','eval','compile','__import__','main'}
        self.assertFalse(any(isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id in forbidden for n in ast.walk(tree)))
        self.assertFalse(hasattr(initial,'main'))


if __name__=='__main__':unittest.main()
