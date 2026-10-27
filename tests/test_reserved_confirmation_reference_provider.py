"""Provider orchestration with fake bridge/process and handwritten tasks only."""
from copy import deepcopy
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import reserved_confirmation_reference_provider as provider
from reserved_confirmation_schedule import build_schedule
from public_api_envelope import PROTOCOL


class Clock:
    def __init__(self):self.now=0.0
    def __call__(self):return self.now


class FakeProcess:
    def __init__(self, env):
        self.env=env;self.pid=7000+len(env.bridges);self.returncode=None
        self.stdin=io.BytesIO();self.stdout=io.BytesIO();self.action=None;self.waits=[]
    def poll(self):return self.returncode
    def terminate(self):self.action='terminate';self.env.operations.append(('terminate',self.pid))
    def kill(self):self.action='kill';self.env.operations.append(('kill',self.pid))
    def wait(self,timeout):
        self.waits.append(timeout)
        if self.action=='close':
            self.env.clock.now+=min(.1,timeout);self.returncode=0;self.env.closed+=1
        elif self.action=='terminate' and self.env.mode not in ('terminate_timeout','kill_timeout'):
            self.env.clock.now+=min(.1,timeout);self.returncode=-15
        elif self.action=='kill' and self.env.mode!='kill_timeout':
            self.env.clock.now+=min(.1,timeout);self.returncode=-9
        else:
            self.env.clock.now+=timeout
            raise subprocess.TimeoutExpired('FAKE_OWNED_CHILD',timeout)
        return self.returncode


class Environment:
    def __init__(self,clock,mode='normal'):
        self.clock=clock;self.mode=mode;self.bridges=[];self.operations=[];self.commands=[];self.closed=0
    def bridge_class(self):
        env=self
        class FakeBridge:
            def __init__(self,python,root,output,*,timeout_seconds):
                self.timeout_seconds=timeout_seconds;self.failed=False;self.closed=False
                self.errors=io.BytesIO();self.selector=io.BytesIO();env.bridges.append(self)
                if env.mode=='resource_close_error':
                    class BadClose:
                        def close(self):raise OSError('FAKE_RESOURCE_CLOSE_FAILED')
                    self.errors=BadClose()
                self.process=FakeProcess(env)
                if env.mode=='partial_constructor':
                    self.failed=True
                    raise RuntimeError('FAKE_CONSTRUCTOR_AFTER_CHILD')
                if env.mode=='constructor_overrun':env.clock.now+=3700
            def request(self,command):
                env.commands.append(deepcopy(command))
                if command['op']=='init':
                    if env.mode=='init_timeout':
                        env.clock.now+=self.timeout_seconds;self.failed=True
                        raise TimeoutError('FAKE_INIT_NO_TERMINAL')
                    env.clock.now+=.2
                    public=dict(instruction='Invented public task '+command['task_id'],supervisor={},
                        app_descriptions={},helper_docs={'api_docs':{},'supervisor':{}},
                        ground_truth_loaded=False,api_result_protocol=PROTOCOL)
                    if env.mode=='invalid_response':public['ground_truth_loaded']=True
                    return {'ok':True,'result':public}
                if command['op']=='close':
                    if env.mode in ('hung_close','terminate_timeout','kill_timeout'):
                        env.clock.now+=self.timeout_seconds;self.failed=True
                        raise TimeoutError('FAKE_HUNG_CLOSE')
                    env.clock.now+=.1;self.process.action='close'
                    return {'ok':True,'result':{'closed':True}}
                raise AssertionError('Only init/close may be invoked')
        return FakeBridge


def inputs(root):
    reservation={'status':'frozen','source_sha256':'a'*64,
        'task_ids':[f'invented-{n:02d}_1' for n in [8,2,12,1,5,3,10,4,11,7,6,9]]}
    args=dict(baseline='ordinary',candidate='fixed_candidate',seed=57,
        budgets=dict(max_calls=80,max_total_tokens=450000,max_api_requests=80,max_wall_seconds=1800,
            max_setup_seconds=120,max_cleanup_seconds=180,max_idle_wait_seconds=60,max_evaluation_seconds=180))
    schedule=build_schedule(reservation,**args)
    args.update(namespace='FAKE_REFERENCE_TEST',world_seed=42,setup_seconds=120,
                cleanup_seconds=180,total_lease_seconds=3660)
    auth_input=provider.authorization_inputs(schedule,**{k:args[k] for k in
        ('namespace','world_seed','setup_seconds','cleanup_seconds','total_lease_seconds')})
    args['authorization']=dict(authorized=True,frozen_protocol_sha256='b'*64,
        frozen_source_manifest_sha256='c'*64,inputs_sha256=provider.digest(auth_input))
    world=root/'fake_world';(world/'experiments/outputs').mkdir(parents=True)
    args.update(python='NO_REAL_PYTHON_ALLOWED',appworld_root=world,output_dir=root/'private_attempt')
    return schedule,reservation,args


class ProviderTests(unittest.TestCase):
    def run_fake(self,mode='normal',stop_after_first=False):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);root=Path(temp.name)
        schedule,reservation,args=inputs(root);clock=Clock();env=Environment(clock,mode)
        with patch.object(provider,'TypedBridgeProcess',env.bridge_class()):
            result=provider.collect_references(schedule,reservation,clock=clock,
                stop=lambda:stop_after_first and env.closed>0,**args)
        return result,env,args,schedule,reservation

    def test_complete_all12_real_recorder_and_private_bundle_order(self):
        result,env,args,schedule,reservation=self.run_fake()
        self.assertEqual(result['status'],'complete');self.assertEqual(len(env.bridges),12)
        self.assertEqual([c['task_id'] for c in env.commands if c['op']=='init'],reservation['task_ids'])
        self.assertEqual([c['op'] for c in env.commands],['init','close']*12)
        self.assertTrue(result['all_owned_processes_stopped']);self.assertTrue(result['within_total_lease'])
        self.assertTrue(result['bundle_accepted'])
        self.assertEqual(result['model_API_native_evaluator_calls'],0)
        self.assertFalse(env.operations)
        bundle=json.loads((args['output_dir']/'initial_states_private.json').read_text())
        self.assertEqual(provider.digest(bundle),result['bundle_canonical_sha256'])
        self.assertEqual([r['task_id'] for r in bundle['references']],reservation['task_ids'])
        for n in range(1,13):
            folder=args['output_dir']/f'reference_{n:02d}'
            self.assertEqual(json.loads((folder/'bridge_01_private.json').read_text())['command']['op'],'init')
            self.assertEqual(json.loads((folder/'bridge_02_private.json').read_text())['command']['op'],'close')

    def test_hung_close_terminates_owned_child_and_stops_without_bundle(self):
        r,env,args,_,_=self.run_fake('hung_close')
        self.assertEqual(r['status'],'failed_no_retry');self.assertEqual(len(env.bridges),1)
        self.assertEqual(env.operations,[('terminate',env.bridges[0].process.pid)])
        self.assertTrue(r['rows'][0]['cleanup']['process_stopped']);self.assertFalse(r['rows'][0]['cleanup']['graceful'])
        self.assertEqual([x['status'] for x in r['rows'][1:]],['not_run']*11)
        self.assertFalse((args['output_dir']/'initial_states_private.json').exists())
        self.assertTrue((args['output_dir']/'reference_01/bridge_02_private.json').exists())

    def test_terminate_timeout_escalates_kill_only_owned_process(self):
        r,env,_,_,_=self.run_fake('terminate_timeout');pid=env.bridges[0].process.pid
        self.assertEqual(env.operations,[('terminate',pid),('kill',pid)])
        self.assertEqual(r['rows'][0]['cleanup_detail']['exit_code'],-9)
        self.assertTrue(r['all_owned_processes_stopped']);self.assertEqual(r['status'],'failed_no_retry')
        self.assertLessEqual(r['rows'][0]['cleanup_detail']['wall_seconds'],180)

    def test_kill_timeout_does_not_invent_absence_or_graceful_exit(self):
        r,env,_,_,_=self.run_fake('kill_timeout')
        self.assertFalse(r['all_owned_processes_stopped']);self.assertFalse(r['rows'][0]['cleanup']['process_stopped'])
        self.assertIsNone(r['rows'][0]['cleanup_detail']['exit_code']);self.assertEqual(len(env.bridges),1)
        self.assertTrue(r['rows'][0]['cleanup_detail']['within_deadline'])
        self.assertEqual(r['status'],'failed_no_retry');self.assertIsNone(r['bundle_canonical_sha256'])

    def test_partial_constructor_retains_and_cleans_owned_process(self):
        r,env,_,_,_=self.run_fake('partial_constructor')
        self.assertEqual(r['rows'][0]['initialization_status'],'not_dispatched')
        self.assertEqual(r['rows'][0]['owned_pid'],env.bridges[0].process.pid)
        self.assertEqual(env.operations,[('terminate',env.bridges[0].process.pid)])
        self.assertFalse(env.commands);self.assertTrue(r['all_owned_processes_stopped'])

    def test_init_timeout_preserves_unknown_attempt_and_does_not_retry(self):
        r,env,args,_,_=self.run_fake('init_timeout')
        self.assertEqual(r['rows'][0]['initialization_status'],'request_started_terminal_unknown')
        receipt=json.loads((args['output_dir']/'reference_01/bridge_01_private.json').read_text())
        self.assertTrue(receipt['raw_request_started']);self.assertNotIn('response',receipt)
        self.assertEqual(len(env.commands),1);self.assertEqual(r['automatic_init_retries'],0)
        self.assertTrue(r['all_owned_processes_stopped'])

    def test_stop_and_setup_overrun_preserve_all12_planned_rows(self):
        r,env,_,_,_=self.run_fake(stop_after_first=True)
        self.assertEqual([x['status'] for x in r['rows']],['complete']+['not_run']*11)
        self.assertEqual(r['status'],'failed_no_retry');self.assertEqual(len(env.bridges),1)
        r,env,_,_,_=self.run_fake('constructor_overrun')
        self.assertEqual(r['rows'][0]['initialization_status'],'not_dispatched')
        self.assertFalse(r['within_total_lease']);self.assertEqual(len(env.bridges),1)
        self.assertTrue(any(op[0]=='kill' for op in env.operations))
        self.assertFalse(r['all_owned_processes_stopped'])

    def test_invalid_init_reply_still_closes_and_preserves_failure(self):
        r,env,_,_,_=self.run_fake('invalid_response')
        self.assertEqual(r['rows'][0]['initialization_status'],'response_recorded')
        self.assertTrue(r['rows'][0]['cleanup']['graceful']);self.assertEqual(r['status'],'failed_no_retry')
        self.assertEqual(len(env.commands),2)

    def test_resource_close_error_cannot_create_successful_cleanup_or_bundle(self):
        r,env,args,_,_=self.run_fake('resource_close_error')
        self.assertEqual(r['status'],'failed_no_retry');self.assertEqual(len(env.bridges),1)
        self.assertTrue(r['all_owned_processes_stopped'])
        self.assertFalse(r['rows'][0]['cleanup']['graceful'])
        self.assertTrue(r['rows'][0]['cleanup']['transport_failed'])
        self.assertIn('resource_close_error:OSError',r['rows'][0]['cleanup_detail']['operations'])
        self.assertFalse((args['output_dir']/'initial_states_private.json').exists())

    def test_bundle_write_overrun_preserves_unaccepted_candidate_and_failure(self):
        with tempfile.TemporaryDirectory() as td:
            s,r,args=inputs(Path(td));clock=Clock();env=Environment(clock);writer=provider._write
            def delayed_write(path,value):
                writer(path,value)
                if path.name=='initial_states_private.json':clock.now+=4000
            with patch.object(provider,'TypedBridgeProcess',env.bridge_class()),patch.object(provider,'_write',delayed_write):
                result=provider.collect_references(s,r,clock=clock,**args)
            self.assertEqual(result['status'],'failed_no_retry')
            self.assertFalse(result['within_total_lease']);self.assertFalse(result['bundle_accepted'])
            self.assertTrue(result['all_owned_processes_stopped'])
            self.assertEqual(len(env.bridges),12)
            self.assertTrue((args['output_dir']/'initial_states_private.json').exists())
            self.assertEqual(json.loads((args['output_dir']/'provider_end_private.json').read_text())['status'],'failed_no_retry')

    def test_unexpected_cleanup_exception_does_not_invent_owned_absence(self):
        with tempfile.TemporaryDirectory() as td:
            s,r,args=inputs(Path(td));clock=Clock();env=Environment(clock)
            with patch.object(provider,'TypedBridgeProcess',env.bridge_class()),patch.object(provider,'_close_owned',side_effect=OSError('FAKE_POLL_ERROR')):
                result=provider.collect_references(s,r,clock=clock,**args)
            self.assertEqual(result['status'],'failed_no_retry');self.assertFalse(result['all_owned_processes_stopped'])
            self.assertIsNone(result['rows'][0]['cleanup']);self.assertEqual(result['rows'][0]['status'],'started')
            self.assertIsNone(env.bridges[0].process.poll());self.assertEqual(len(env.bridges),1)
            self.assertFalse(result['bundle_accepted']);self.assertEqual(len(result['rows']),12)

    def test_authority_lease_and_existing_namespaces_reject_before_bridge(self):
        for mutation in ('unauthorized','hash','source','lease','namespace','output'):
            with self.subTest(mutation=mutation),tempfile.TemporaryDirectory() as td:
                s,r,args=inputs(Path(td));clock=Clock();env=Environment(clock)
                if mutation=='unauthorized':args['authorization']['authorized']=False
                elif mutation=='hash':args['authorization']['inputs_sha256']='d'*64
                elif mutation=='source':args['authorization']['frozen_source_manifest_sha256']=None
                elif mutation=='lease':args['total_lease_seconds']=3599
                elif mutation=='namespace':
                    (args['appworld_root']/'experiments/outputs/FAKE_REFERENCE_TEST_CELL_24').mkdir()
                else:args['output_dir'].mkdir()
                with patch.object(provider,'TypedBridgeProcess',env.bridge_class()),self.assertRaises(ValueError):
                    provider.collect_references(s,r,clock=clock,**args)
                self.assertFalse(env.bridges)


if __name__=='__main__':unittest.main()
