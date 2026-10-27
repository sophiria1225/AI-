"""Handwritten synthetic IDs only; no actual reservation/runtime records."""
import ast
from copy import deepcopy
import inspect
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import reserved_confirmation_schedule as schedule


def inputs():
    reservation = dict(status='frozen', source_sha256='a'*64,
                       task_ids=[f'synthetic-{i:02d}_1' for i in range(1, 13)])
    choices = dict(baseline='ordinary_control', candidate='candidate_method', seed=57,
        budgets=dict(max_calls=80, max_total_tokens=450000, max_api_requests=80,
                     max_wall_seconds=1800, max_setup_seconds=120, max_cleanup_seconds=180,
                     max_idle_wait_seconds=60, max_evaluation_seconds=180))
    return reservation, choices


class ReservedConfirmationScheduleTests(unittest.TestCase):
    def test_original_full_order_variant_pairing_and_rotation(self):
        reservation, choices = inputs()
        plan = schedule.build_schedule(reservation, **choices)
        self.assertEqual(plan['planned_cells'], 24)
        self.assertEqual(plan['reserved_task_ids'], reservation['task_ids'])
        self.assertEqual([c['slot'] for c in plan['cells']], list(range(1, 25)))
        for n in range(12):
            pair = plan['cells'][2*n:2*n+2]
            self.assertEqual([c['task_id'] for c in pair], [f'synthetic-{n+1:02d}_1']*2)
            self.assertEqual([c['scenario_id'] for c in pair], [f'synthetic-{n+1:02d}']*2)
            self.assertEqual([c['arm_role'] for c in pair],
                             ['baseline', 'candidate'] if n % 2 == 0 else ['candidate', 'baseline'])
            for c in pair:
                self.assertEqual(c['method'], choices[c['arm_role']])
                self.assertEqual((c['variant'], c['seed'], c['budgets']), (1, 57, choices['budgets']))
                self.assertNotIn('success', c)
                self.assertNotIn('source_run', c)
        self.assertTrue(schedule.validate_schedule(plan, reservation, **choices))
        self.assertEqual(plan, schedule.build_schedule(reservation, **choices))

    def test_inputs_and_cells_have_no_mutable_aliases(self):
        reservation, choices = inputs(); before = deepcopy((reservation, choices))
        plan = schedule.build_schedule(reservation, **choices)
        plan['cells'][0]['budgets']['max_calls'] = 1
        plan['reserved_task_ids'][0] = 'replacement_1'
        self.assertEqual((reservation, choices), before)
        self.assertEqual(plan['cells'][1]['budgets']['max_calls'], 80)
        self.assertEqual(plan['budgets']['max_calls'], 80)

    def test_subset_duplicates_sibling_variants_and_unfrozen_metadata_rejected(self):
        mutations = [lambda r: r.update(task_ids=r['task_ids'][:4]),
                     lambda r: r['task_ids'].__setitem__(1, r['task_ids'][0]),
                     lambda r: r['task_ids'].__setitem__(1, 'synthetic-01_2'),
                     lambda r: r['task_ids'].__setitem__(0, 'synthetic-01_01'),
                     lambda r: r.update(status='draft'),
                     lambda r: r.update(source_sha256='not-a-hash'),
                     lambda r: r.update(selected_task_ids=r['task_ids'][:4])]
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                reservation, choices = inputs(); mutate(reservation)
                with self.assertRaises(ValueError): schedule.build_schedule(reservation, **choices)

    def test_method_and_seed_ambiguity_rejected(self):
        for changes in ({'candidate':'ordinary_control'}, {'candidate':'ORDINARY_CONTROL'},
                        {'baseline':'candidate'}, {'candidate':'baseline'}, {'baseline':' bad '},
                        {'candidate':''}, {'seed':True}, {'seed':-1}, {'seed':[57,157]}, {'seed':57.0}):
            reservation, choices = inputs(); choices.update(changes)
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                schedule.build_schedule(reservation, **choices)

    def test_invalid_nonfinite_or_incomplete_budget_rejected(self):
        for key, values in [('max_calls', [0,-1,True,80.0,None]),
                            ('max_wall_seconds', [0,-1,True,float('inf'),float('-inf'),float('nan'),1e308])]:
            for value in values:
                reservation, choices = inputs(); choices['budgets'][key] = value
                with self.subTest(key=key,value=value), self.assertRaises(ValueError):
                    schedule.build_schedule(reservation, **choices)
        for key in schedule.COUNT_BUDGETS + schedule.TIME_BUDGETS:
            reservation, choices = inputs(); choices['budgets'].pop(key)
            with self.assertRaises(ValueError): schedule.build_schedule(reservation, **choices)
        reservation, choices = inputs(); choices['budgets']['candidate_override'] = 1
        with self.assertRaises(ValueError): schedule.build_schedule(reservation, **choices)
        reservation, choices = inputs()
        choices['budgets'].update({key: 5e306 for key in schedule.TIME_BUDGETS})
        with self.assertRaises(ValueError): schedule.build_schedule(reservation, **choices)

    def test_tampered_membership_order_budgets_and_role_are_rejected(self):
        mutations = [lambda p: p.update(cells=p['cells'][:8]),
                     lambda p: p['cells'][0].update(task_id='unreserved_1'),
                     lambda p: p['reserved_task_ids'].__setitem__(0, 'replacement_1'),
                     lambda p: p['cells'].reverse(),
                     lambda p: p['cells'][1].update(arm_role='baseline'),
                     lambda p: p['cells'][0].update(method='different_method'),
                     lambda p: p['cells'][0]['budgets'].update(max_calls=79),
                     lambda p: p['cells'][0].update(variant=True),
                     lambda p: p.update(seed=58),
                     lambda p: p.update(reservation_source_sha256='b'*64),
                     lambda p: p.update(eligibility_override=True)]
        for mutate in mutations:
            reservation, choices = inputs(); plan=schedule.build_schedule(reservation, **choices); mutate(plan)
            with self.subTest(mutate=mutate), self.assertRaises(ValueError):
                schedule.validate_schedule(plan, reservation, **choices)

    def test_caller_authority_cannot_be_replaced_by_schedule(self):
        reservation, choices = inputs(); plan=schedule.build_schedule(reservation, **choices)
        other=deepcopy(reservation); other['task_ids'][0]='other-synthetic_1'
        with self.assertRaises(ValueError): schedule.validate_schedule(plan, other, **choices)
        altered=deepcopy(choices); altered['candidate']='other_candidate'
        with self.assertRaises(ValueError): schedule.validate_schedule(plan, reservation, **altered)

    def test_fractional_finite_time_budget_and_zero_seed_are_explicit(self):
        reservation, choices=inputs(); choices['seed']=0; choices['budgets']['max_wall_seconds']=10.5
        plan=schedule.build_schedule(reservation, **choices)
        self.assertEqual(plan['cells'][-1]['budgets']['max_wall_seconds'],10.5)
        self.assertTrue(schedule.validate_schedule(plan,reservation,**choices))

    def test_module_imports_are_pure_and_no_action_entrypoint(self):
        tree=ast.parse(inspect.getsource(schedule))
        imports={node.module if isinstance(node,ast.ImportFrom) else name.name
                 for node in ast.walk(tree) if isinstance(node,(ast.Import,ast.ImportFrom))
                 for name in node.names}
        self.assertEqual(imports, {'copy','math','re'})
        forbidden={'open','exec','eval','compile','__import__','main'}
        self.assertFalse(any(isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id in forbidden
                             for n in ast.walk(tree)))
        self.assertFalse(hasattr(schedule,'main'))


if __name__ == '__main__':
    unittest.main()
