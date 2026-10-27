"""Synthetic finite P136 specification and saved preflight checks; no live I/O."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import whole_task_late_obligations_p136 as helper
import run_whole_task_late_obligations_p136 as driver


def fixture():
    prior = json.loads((ROOT/'configs/P123_whole_task_rolling_checkpoint_v01.json').read_text())
    plan = {**prior, **helper.fixed_fields()}
    plan['known_tasks'] = [t for t in prior['known_tasks'] if t['source_run']=='P29_04_CODE']
    plan['source_sha256'] = {name:'a'*64 for name in helper.REQUIRED_SOURCES}
    return plan


def preflight_fixture(test):
    temporary=tempfile.TemporaryDirectory();test.addCleanup(temporary.cleanup)
    root=Path(temporary.name)/'repo';storage=Path(temporary.name)/'storage'
    (root/'reports').mkdir(parents=True);storage.mkdir()
    plan=fixture();original=json.loads((ROOT/'configs/P29_stateful_code_v01.json').read_text())
    prepared=[{**t,'public_task':{'instruction':'Handwritten synthetic task.'}} for t in plan['known_tasks']]
    captured=[]
    def count(config,messages,tools,timeout):
        captured.append((deepcopy(config),deepcopy(messages),deepcopy(tools)))
        return {'input_tokens':5000,'wall_seconds':0}
    patches=[patch.object(driver,'sources',return_value=(plan,original,[],prepared)),
        patch.object(driver,'launch_predecessor_closed',return_value={'synthetic':'closed'}),
        patch.object(driver,'frozen_hashes',return_value={'synthetic':'a'*64}),
        patch.object(driver,'frozen_sources',return_value='b'*40),
        patch.object(driver,'live_identity',return_value=({'synthetic':True},'synthetic-end')),
        patch.object(driver,'check_resume',return_value={'synthetic':'resume'}),
        patch.object(driver,'count_input',side_effect=count),
        patch.object(driver,'count_summary_input',side_effect=count)]
    for p in patches:p.start();test.addCleanup(p.stop)
    pre=driver.preflight(storage,root)
    return storage,root,plan,original,prepared,captured,pre


class ObservedObligationPlanTests(unittest.TestCase):
    def test_six_slots_fixed_order_seeds_budget_and_deadline(self):
        plan=fixture();helper.validate_plan(plan)
        self.assertEqual(helper.run_order(),[(1,1,'raw_anchor'),(1,1,'ids_only'),(1,1,'entity_fields'),
            (2,1,'entity_fields'),(2,1,'ids_only'),(2,1,'raw_anchor')])
        expected={'max_cells':6,'model_seeds':[57,157],'max_calls':80,'max_total_tokens':450000,
            'max_wall_seconds':1800,'api_budget_by_task_slot':[80],'max_model_calls':480,
            'max_reserved_tokens':2700000,'max_reserved_environment_api_requests':480,
            'max_evaluator_calls':6,'server_max_lifetime_seconds':21600,'deadline_jst':'2026-10-27T18:00:00+09:00'}
        for k,v in expected.items():self.assertEqual(plan[k],v,k)
        for k,v in [('model_seeds',[157]),('max_cells',4),('max_calls',81),('max_total_tokens',450001),
                    ('api_budget_by_task_slot',[120]),('server_max_lifetime_seconds',21601),
                    ('deadline_jst','2026-10-27T19:00:00+09:00'),('max_evaluator_calls',True)]:
            with self.subTest(key=k),self.assertRaises(ValueError):helper.validate_plan({**plan,k:v})
        for args in [(True,1,'ids_only'),(3,1,'ids_only'),(1,2,'ids_only'),(1,1,'other')]:
            with self.subTest(args=args),self.assertRaises(ValueError):helper.cell_id(*args)

    def test_late_only_design_has_no_initial_guide_query_handle_or_new_clock_control(self):
        plan=helper.fixed_fields()
        for key in ('initial_guide_added','query_interface_exposed','run_scoped_handle_exposed',
                    'server_predict_time_limit_added','client_terminal_grace_added','payback_enabled'):
            self.assertIs(plan[key],False,key)
        self.assertEqual(plan['primary_comparison'],['ids_only','entity_fields'])
        self.assertIs(plan['require_P135_closed_collection_before_launch'],True)
        self.assertIs(plan['same_ID_selector_and_row_count'],True)

    def test_bound_new_sources_cannot_be_missing_or_malformed(self):
        plan=fixture()
        for name in helper.REQUIRED_SOURCES:
            changed=deepcopy(plan);changed['source_sha256'].pop(name)
            with self.subTest(source=name),self.assertRaises(ValueError):helper.validate_plan(changed)
        name=helper.REQUIRED_SOURCES[0]
        for value in ('', 'g'*64, True):
            changed=deepcopy(plan);changed['source_sha256'][name]=value
            with self.subTest(value=value),self.assertRaises(ValueError):helper.validate_plan(changed)

    def test_adoption_requires_known_cost_quality_against_both_controls_and_paid_exposure(self):
        def rows():
            return [dict(task_id='synthetic',run_id=helper.cell_id(rep,1,mode),replication=rep,
                model_seed=helper.SEEDS[rep-1],obligation_mode=mode,record_status='evaluated',success=True,
                known_total_tokens=80 if mode=='entity_fields' else 100,unknown_usage_calls=0,
                obligation_field_rows_exposed=1 if mode=='entity_fields' else 0,
                obligation_contract_failed=False,obligation_accounting_complete=True)
                for rep,_,mode in helper.run_order()]
        self.assertTrue(helper.summarize(rows(),[])['development_gate_met'])
        for key,value in [('success',False),('unknown_usage_calls',1),('known_total_tokens',201),
                          ('obligation_contract_failed',True),('obligation_accounting_complete',None)]:
            sample=rows();sample[2][key]=value
            with self.subTest(key=key):self.assertFalse(helper.summarize(sample,[])['development_gate_met'])
        sample=rows()
        for row in sample:row['obligation_field_rows_exposed']=0
        self.assertFalse(helper.summarize(sample,[])['development_gate_met'])
        sample=rows()
        for row in sample:
            row['obligation_field_rows_exposed']=0
            row['obligation_entity_rows_exposed']=10
        self.assertFalse(helper.summarize(sample,[])['development_gate_met'])
        sample=rows();sample[0].update(known_total_tokens=None,unknown_usage_calls=None,record_status='not_run',success=None)
        self.assertFalse(helper.summarize(sample,[])['development_gate_met'])
        self.assertIsNone(helper.summarize(sample,[])['raw_anchor_comparison']['candidate_minus_baseline_whole_task_tokens'])
        self.assertFalse(helper.summarize(rows(),['synthetic audit failure'])['development_gate_met'])
        sample=rows();sample[1]['success']=False
        report=helper.summarize(sample,[])
        self.assertEqual(report['primary_comparison']['paired_results'][0]['quality_transition'],'quality_gain')
        self.assertEqual(report['primary_comparison']['costs_by_quality_transition']['quality_gain']['pairs'],1)
        sample=rows()
        for row in sample:
            if row['obligation_mode']=='raw_anchor':row['known_total_tokens']=50
        self.assertFalse(helper.summarize(sample,[])['development_gate_met'])

    def test_six_actor_two_summary_counts_primary_inputs_match_and_activate_once(self):
        storage,root,plan,original,prepared,captured,pre=preflight_fixture(self)
        self.assertEqual((pre['input_count_requests'],pre['summary_input_count_requests']),(6,2))
        self.assertEqual(len(captured),8)
        self.assertEqual(captured[1],captured[2]);self.assertEqual(captured[4],captured[5])
        self.assertEqual(captured[0],captured[1]);self.assertEqual(captured[3],captured[4])
        driver.validate_preflight(storage,root,pre,plan,original,prepared)
        driver.activate(storage,root)
        frozen=json.loads((root/driver.ACTIVATION).read_text())
        self.assertIs(frozen['all_six_conditions_frozen_before_generation'],True)
        driver.validate_activation(storage,root,frozen)
        with self.assertRaises(FileExistsError):driver.preflight(storage,root)
        with self.assertRaises(FileExistsError):driver.activate(storage,root)

    def test_preflight_wrong_phase_missing_slot_paid_call_seed_and_hash_rejected(self):
        storage,root,plan,original,prepared,captured,pre=preflight_fixture(self)
        changes=[lambda x:x.update(phase='P133_preflight'),lambda x:x.update(rows=x['rows'][:1]),
            lambda x:x.update(model_generations=1),lambda x:x.update(environment_api_requests=1),
            lambda x:x.update(input_count_requests=True),lambda x:x.update(source_hashes={}),
            lambda x:x['rows'][0].update(model_seed=157),
            lambda x:x['rows'][0]['conditions'].pop('ids_only'),
            lambda x:x['rows'][0]['conditions']['entity_fields'].update(count_request_sha256='0'*64)]
        for mutate in changes:
            changed=deepcopy(pre);mutate(changed)
            with self.assertRaises(ValueError):driver.validate_preflight(storage,root,changed,plan,original,prepared)
        self.assertFalse((root/driver.ACTIVATION).exists())

    def test_source_or_resume_drift_invalidates_frozen_activation(self):
        storage,root,plan,original,prepared,captured,pre=preflight_fixture(self);driver.activate(storage,root)
        frozen=json.loads((root/driver.ACTIVATION).read_text())
        for key,value in [('phase','P133'),('source_hashes',{}),('preflight_sha256','0'*64),
                          ('all_six_conditions_frozen_before_generation',False),('research_resume',{})]:
            with self.subTest(key=key),self.assertRaises(ValueError):driver.validate_activation(storage,root,{**frozen,key:value})

if __name__=='__main__':unittest.main()
