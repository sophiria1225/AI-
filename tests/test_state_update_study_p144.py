"""P144 three-way utility/accounting/publication counterexamples; synthetic only."""
from copy import deepcopy
import csv
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
import whole_task_state_update_p144 as study
from test_checkpoint_prefix_identity_p140 import fixture as identity_fixture

BUILDER = 'scripts/build_state_update_summary_p144.py'


def put(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rows():
    result = []
    for number, mode in study.run_order():
        prefix = identity_fixture('control' if mode==study.MODES[0] else 'candidate')[2]
        candidate = mode == study.MODES[2]
        row = dict(run_id=study.cell_id(number,mode),task_id=study.TASKS[number-1],
            object_timing_mode=mode,checkpoint_representation_mode=mode,model_seed=257,
            record_status='evaluated',success=True,
            known_total_tokens=dict(zip(study.MODES,(1000,950,900)))[mode],
            unknown_usage_calls=0,request_checks=[],**prefix,
            object_prompt_known_focus_calls=int(mode==study.MODES[1]),
            actual_delta_known_actor_calls=int(mode==study.MODES[1]),
            update_prompt_known_focus_calls=int(candidate),actual_update_known_actor_calls=int(candidate),
            actual_changed_old_known_actor_calls=int(candidate),changed_old_items=int(candidate))
        for name in ('prefix_exposure','checkpoint_representation','delta_envelope','state_update'):
            row[name+'_contract_failed']=False
            row[name+'_accounting_complete']=True
        result.append(row)
    return result


def plan():
    return dict(study.fixed_fields(),known_tasks=[dict(task_id=t,source_run=f'P29_{n:02d}_CODE')
        for n,t in enumerate(study.TASKS,1)],source_sha256={name:'a'*64 for name in study.REQUIRED_SOURCES})


def closed_fixture(root, data, errors=()):
    for name in study.REQUIRED_SOURCES:
        p=root/name;p.parent.mkdir(parents=True,exist_ok=True)
        p.write_bytes((ROOT/name).read_bytes() if name==BUILDER else b'handwritten synthetic source\n')
    p=plan();p['source_sha256']={name:sha(root/name) for name in study.REQUIRED_SOURCES}
    put(root/study.PLAN,p)
    audit=dict(phase='P144',batch_status='stopped',owned_processes_absent=True,
        rows=data,audit_errors=list(errors),plan_sha256=sha(root/study.PLAN),**study.summarize(data,list(errors)))
    put(root/'reports/P144_comparison.json',audit)
    put(root/'reports/P144_server_session.json',dict(phase='P144',status='stopped',
        owned_processes_absent=True,audit_source_sha256=sha(root/'reports/P144_comparison.json')))
    spec=importlib.util.spec_from_file_location('synthetic_P144_builder',root/BUILDER)
    builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)
    return builder


class StateUpdateStudyTests(unittest.TestCase):
    def test_both_required_controls_and_all_twelve_known(self):
        result=study.summarize(rows(),[])
        self.assertTrue(result['development_gate_met'])
        self.assertEqual((result['planned_rows'],result['independent_tasks'],result['model_seed']),(12,4,257))
        self.assertEqual([c['all_task_token_difference'] for c in result['comparisons']],[-400,-200,-200])
        self.assertTrue(all(len(c['pairs'])==4 and all(p['canonical_prefix_match'] for p in c['pairs'])
                            for c in result['comparisons']))
        self.assertFalse(result['novel_method_claim'])
        self.assertFalse(result['scientific_adoption_evaluated'])
        self.assertFalse(result['prior_results_pooled'])

    def test_beating_recursive_but_not_append_is_insufficient(self):
        data=rows()
        for r in data:
            if r['object_timing_mode']==study.MODES[1]:r['known_total_tokens']=800
        result=study.summarize(data,[])
        self.assertTrue(result['comparisons'][0]['comparison_gate_met'])
        self.assertFalse(result['comparisons'][1]['comparison_gate_met'])
        self.assertFalse(result['development_gate_met'])

    def test_equal_success_count_does_not_hide_paired_success_loss(self):
        data=rows()
        next(r for r in data if r['task_id']==study.TASKS[0] and r['object_timing_mode']==study.MODES[0])['success']=False
        next(r for r in data if r['task_id']==study.TASKS[1] and r['object_timing_mode']==study.MODES[2]).update(success=False,known_total_tokens=1)
        result=study.summarize(data,[])
        self.assertEqual(result['success_counts'][study.MODES[0]],result['success_counts'][study.MODES[2]])
        self.assertEqual(result['comparisons'][0]['success_loss_tasks'],[study.TASKS[1]])
        self.assertFalse(result['development_gate_met'])

    def test_unknown_affects_only_its_pairwise_totals_but_blocks_overall(self):
        data=rows()
        next(r for r in data if r['object_timing_mode']==study.MODES[1])['unknown_usage_calls']=1
        result=study.summarize(data,[])
        self.assertEqual(result['comparisons'][0]['all_task_token_difference'],-400)
        self.assertIsNone(result['comparisons'][1]['all_task_token_difference'])
        self.assertIsNone(result['comparisons'][2]['common_success_token_difference'])
        self.assertTrue(all(x is None for x in result['total_tokens_by_mode'].values()))
        self.assertFalse(result['development_gate_met'])
        self.assertEqual(result['recorded_unknown_usage_calls'],1)
        self.assertEqual(result['usage_count_missing_conditions'],0)
        for r in data:r.update(record_status='not_run',success=None,known_total_tokens=None,unknown_usage_calls=None)
        result=study.summarize(data,[])
        self.assertEqual((result['usage_count_missing_conditions'],result['recorded_unknown_usage_calls']),(12,0))

    def test_keep_add_or_net_unchanged_delete_add_cannot_establish_update(self):
        for key in ('update_prompt_known_focus_calls','actual_changed_old_known_actor_calls','changed_old_items'):
            for value in (0,None,True):
                data=rows()
                for r in data:
                    if r['object_timing_mode']==study.MODES[2]:r[key]=value
                with self.subTest(key=key,value=value):
                    self.assertFalse(study.summarize(data,[])['development_gate_met'])
        # changed_old_items and an update-bearing actor alone are insufficient.
        data=rows()
        for r in data:r['actual_changed_old_known_actor_calls']=0
        self.assertFalse(study.summarize(data,[])['comparisons'][0]['changed_intervention_on_common_success'])

    def test_activity_only_on_failed_task_does_not_establish_successful_saving(self):
        data=rows()
        for r in data:
            if r['task_id']==study.TASKS[0]:r['success']=False
            else:r['actual_changed_old_known_actor_calls']=0
        result=study.summarize(data,[])
        self.assertTrue(result['comparisons'][0]['observed_utility_criteria_met'])
        self.assertFalse(result['development_gate_met'])
        for r in data:r['success']=False
        self.assertIsNone(study.summarize(data,[])['comparisons'][0]['common_success_token_difference'])

    def test_invalid_prefix_contract_error_and_boolean_usage_fail(self):
        for kind in ('prefix','contract','unknown_bool','total_bool','success_int','audit_error'):
            data=rows();r=next(r for r in data if r['object_timing_mode']==study.MODES[2])
            if kind=='prefix':r['representation_second_opportunity']['candidate_cutoff']+=1
            elif kind=='contract':r['state_update_contract_failed']=True
            elif kind=='unknown_bool':r['unknown_usage_calls']=False
            elif kind=='total_bool':r['known_total_tokens']=True
            elif kind=='success_int':r['success']=1
            with self.subTest(kind=kind):
                self.assertFalse(study.summarize(data,['synthetic error'] if kind=='audit_error' else [])['development_gate_met'])

    def test_plan_and_exact_order_cannot_shrink_or_change_seed(self):
        good=plan();study.validate_plan(good)
        self.assertEqual(len(set(study.run_order())),12)
        for key,value in [('model_seed',57),('max_cells',8),('max_wall_seconds',1200),('server_max_lifetime_seconds',30000)]:
            with self.subTest(key=key),self.assertRaises(ValueError):study.validate_plan(good|{key:value})
        for data in (rows()[:-1],rows()[:-1]+[rows()[0]],list(reversed(rows()))):
            with self.assertRaises(ValueError):study.summarize(data,[])

    def test_closed_builder_preserves_all_twelve_and_all_three_pair_sets(self):
        data=rows();data[-1].update(record_status='audit_error',success=None,known_total_tokens=None,unknown_usage_calls=None)
        data[0]['request_checks']=[dict(call_id='call_001',role='focus',status='ok',input_tokens=900,output_tokens=100,cached_input_tokens=800)]
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);builder=closed_fixture(root,data,['synthetic error']);result=builder.build(root)
            self.assertEqual(len(result['conditions']),12)
            self.assertIsNone(result['conditions'][-1]['known_total_tokens'])
            with (root/study.MATERIAL/'pairs.csv').open() as f:pairs=list(csv.DictReader(f))
            self.assertEqual(len(pairs),12)
            self.assertTrue(any(p['candidate_minus_baseline_tokens']=='' for p in pairs))
            self.assertIn('candidate_changed_view_known_actor_calls',pairs[0])
            with (root/study.MATERIAL/'model_calls.csv').open() as f:calls=list(csv.DictReader(f))
            self.assertEqual((calls[0]['model_seed'],calls[0]['cached_input_tokens']),('257','800'))
            manifest=json.loads((root/study.MATERIAL/'build_manifest.json').read_text())
            self.assertTrue(all(sha(root/study.MATERIAL/n)==h for n,h in manifest['artifact_sha256'].items()))
            with self.assertRaises(FileExistsError):builder.build(root)

    def test_live_changed_sources_or_falsified_gate_cannot_publish(self):
        for kind in ('live','source','gate'):
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as td:
                root=Path(td);builder=closed_fixture(root,rows())
                if kind=='source':(root/study.REQUIRED_SOURCES[0]).write_text('changed')
                elif kind=='gate':
                    p=root/'reports/P144_comparison.json';v=json.loads(p.read_text());v['development_gate_met']=False;put(p,v)
                    p=root/'reports/P144_server_session.json';v=json.loads(p.read_text());v['audit_source_sha256']=sha(root/'reports/P144_comparison.json');put(p,v)
                else:
                    p=root/'reports/P144_server_session.json';v=json.loads(p.read_text());v['owned_processes_absent']=False;put(p,v)
                with self.assertRaises(ValueError):builder.build(root)
                self.assertFalse((root/study.MATERIAL).exists())


if __name__=='__main__':unittest.main()
