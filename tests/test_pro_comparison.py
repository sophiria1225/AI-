import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from contextlib import redirect_stdout

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from run_pro_pilot import trial_units, require_same_conditions, run_schedule
from experiment_state import SharedBudget, CompletionState, ProtocolStop
from run_pro_comparison_batch import validate_batch


class ProComparisonTests(unittest.TestCase):
    def test_batch_rejects_different_conditions_before_either_trial(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            trials=[]
            for strategy in ('fixed_pair','single'):
                path=root/(strategy+'.json')
                path.write_text('{}')
                trials.append({'strategy':strategy,'trial_id':'P5_'+strategy,'plan':path.name,
                               'plan_sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
            batch=root/'batch.json'
            batch.write_text(json.dumps({'trial_count':2,'trials':trials,'source_sha256':{}}))
            expected=hashlib.sha256(batch.read_bytes()).hexdigest()
            def prepared(path,storage):
                strategy=path.stem
                detail={'strategy':strategy,'trial_id':'P5_'+strategy}
                return detail,{'budget':100 if strategy=='single' else 200},None,None
            with patch('run_pro_comparison_batch.ROOT',root), patch('run_pro_comparison_batch.prepare',side_effect=prepared):
                with self.assertRaisesRegex(ValueError,'exactly the same'):
                    validate_batch(batch,expected,root)
                with self.assertRaisesRegex(ValueError,'Batch plan changed'):
                    validate_batch(batch,'0'*64,root)

    def test_phase_cannot_enable_unplanned_strategy_or_extra_trials(self):
        self.assertEqual(trial_units({'trial_count': 1, 'strategy': 'single'}), ('single',))
        self.assertEqual(trial_units({'phase': 'P5', 'trial_count': 1, 'strategy': 'fixed_pair'}),
                         ('implementation', 'validation'))
        self.assertEqual(trial_units({'phase': 'P5', 'trial_count': 1, 'strategy': 'single'}), ('single',))
        for plan in ({'phase': 'P4', 'strategy': 'fixed_pair', 'trial_count': 1},
                     {'phase': 'P5', 'strategy': 'dynamic', 'trial_count': 1},
                     {'phase': 'P5', 'strategy': 'fixed_pair', 'trial_count': 2}):
            with self.assertRaises(ValueError):
                trial_units(plan)

    def test_pair_cannot_silently_change_baseline_budget_model_or_public_input(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            baseline = {'phase': 'P4', 'scope': 'single', 'model': 'pinned',
                        'seed': 7, 'max_total_tokens': 600000,
                        'public_inputs_sha256': 'digest', 'visible_checks': ['public-check'],
                        'max_wall_seconds': 3600}
            path = root/'baseline.json'
            path.write_text(json.dumps(baseline))
            plan = {'phase': 'P5', 'comparison_baseline': {
                'config': path.name, 'config_sha256': hashlib.sha256(path.read_bytes()).hexdigest()}}
            pair = baseline | {'phase': 'P5', 'scope': 'pair', 'max_wall_seconds': 7200}
            with patch('run_pro_pilot.ROOT', root):
                require_same_conditions(plan, pair)
                for key,value in [('model', 'changed'), ('seed', 8), ('max_total_tokens', 1200000),
                                  ('public_inputs_sha256', 'other'), ('visible_checks', [])]:
                    with self.subTest(key=key), self.assertRaisesRegex(ValueError, 'substantive'):
                        require_same_conditions(plan, pair | {key: value})
                with self.assertRaisesRegex(ValueError, 'ceiling'):
                    require_same_conditions(plan, pair | {'max_wall_seconds': 10000})
                path.write_text('{}')
                with self.assertRaisesRegex(ValueError, 'Baseline'):
                    require_same_conditions(plan, pair)

    def test_scheduler_shares_budget_propagates_observations_and_invalidates_stale_vote(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            class Agent:
                def __init__(self, name):
                    self.name, self.messages = name, []
                    self.config = SimpleNamespace(output_path=root/(name+'.json'), max_consecutive_format_errors=3)
                    self.n_consecutive_format_errors = 0
                def add_messages(self, *messages):
                    self.messages.extend(messages)
                def save(self, path):
                    path.write_text(json.dumps(self.messages))
            agents = {name: Agent(name) for name in ('implementation','validation')}
            budget = SharedBudget(4, 1000, 1000, 50, 60)
            state = CompletionState(tuple(agents), '0'*64)
            model, env = SimpleNamespace(), SimpleNamespace()
            summary = {'turns': []}
            observed = []
            def synthetic_turn(agent, env, completion, out, base, turn, *, artifact_options):
                observed.append((agent.name, model.unit, env.unit, artifact_options))
                budget.begin_request(100, 0)
                budget.finish_request({'status':'ok','input_tokens':100,'output_tokens':10,'done_reason':'stop'})
                # First worker votes on v0; the second changes v0 -> v1, removing that vote.
                changed = completion.observe_artifact(('1' if turn >= 2 else '0')*64)
                completion.vote(env.unit, completion.artifact_sha256)
                return {'turn':turn,'unit':env.unit,'artifact_changed':changed,
                        'artifact':completion.snapshot(),'visible_content':['public observation'],
                        'operations':[]}
            with patch('run_pro_pilot.run_turn', side_effect=synthetic_turn), redirect_stdout(io.StringIO()):
                run_schedule(agents, model, env, state, root, 'base', summary, budget,
                             'synthetic_control', artifact_options={'workdir':'/app'})
            self.assertTrue(state.complete)
            self.assertEqual(budget.calls, 3)
            self.assertEqual(budget.total_tokens, 330)
            self.assertEqual([r[0] for r in observed], ['implementation','validation','implementation'])
            self.assertTrue(all(name == mu == eu for name,mu,eu,_ in observed))
            self.assertTrue(all(options == {'workdir':'/app'} for *_,options in observed))
            self.assertFalse(summary['turns'][1]['artifact']['complete'])
            self.assertEqual(len(agents['validation'].messages), 2)
            self.assertEqual(len(agents['implementation'].messages), 1)
            self.assertNotIn('operations', summary['turns'][0])

    def test_exhausted_shared_budget_stops_pair_before_second_call(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            class Agent:
                config=SimpleNamespace(output_path=root/'agent.json', max_consecutive_format_errors=3)
                n_consecutive_format_errors=0
                def add_messages(self,*messages): pass
                def save(self,path): pass
            budget=SharedBudget(1,1000,1000,50,60)
            state=CompletionState(('implementation','validation'),'0'*64)
            def synthetic_turn(*args, **kwargs):
                budget.begin_request(100,0)
                budget.finish_request({'status':'ok','input_tokens':100,'output_tokens':10,'done_reason':'stop'})
                return {'visible_content':[],'operations':[]}
            with patch('run_pro_pilot.run_turn',side_effect=synthetic_turn), redirect_stdout(io.StringIO()):
                with self.assertRaisesRegex(ProtocolStop,'call_limit'):
                    run_schedule({'implementation':Agent(),'validation':Agent()},SimpleNamespace(),SimpleNamespace(),
                                 state,root,'base',{'turns':[]},budget,'synthetic_control',artifact_options={})
            self.assertEqual(budget.calls,1)
            self.assertEqual(budget.total_tokens,110)


if __name__=='__main__':
    unittest.main()
