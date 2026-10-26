"""Public aggregates and handwritten arithmetic; no raw/runtime/online reads."""
import unittest
from scripts.build_closed_results_index_20261027 import ROOT, build, compare, totals


def row(arm, seed=57, *, success=True, known=100, unknown=0, task='synthetic'):
    return dict(arm=arm,model_seed=seed,task=task,success=success,evaluated=True,
                known_input_tokens=known-10,known_output_tokens=10,unknown_usage_calls=unknown,
                model_calls=1,environment_api_requests=0)


class ArithmeticTests(unittest.TestCase):
    def test_unknown_does_not_erase_known_or_become_zero(self):
        r=totals([row('b',unknown=1)])
        self.assertEqual(r['known_token_subtotal'],100)
        self.assertEqual(r['unknown_usage_calls'],1)
        self.assertIsNone(r['exact_total_tokens'])

    def test_empty_common_success_is_not_zero_savings(self):
        c=compare([row('b',success=False),row('a',success=False)],'b','a')
        self.assertEqual(c['common_success_pairs'],0)
        self.assertIsNone(c['common_baseline_exact_tokens'])
        self.assertIsNone(c['descriptive_common_success_delta_tokens'])

    def test_equal_success_totals_do_not_hide_loss(self):
        rows=[row('b',57,success=True),row('a',57,success=False),
              row('b',157,success=False),row('a',157,success=True)]
        c=compare(rows,'b','a')
        self.assertEqual((c['success_losses'],c['success_gains']),(1,1))
        self.assertEqual(c['common_success_pairs'],0)

    def test_different_seeds_cannot_be_paired(self):
        with self.assertRaisesRegex(ValueError,'coverage'):
            compare([row('b',57),row('a',157)],'b','a')


class PublicClosedIndexTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.summary,cls.conditions,cls.dependencies=build(ROOT)

    def test_all56_and_only_public_dependencies(self):
        self.assertEqual(len(self.conditions),56)
        self.assertEqual({r['phase']for r in self.conditions},{'P123','P125','P127','P128','P129','P132','P133'})
        self.assertTrue(all(p.startswith(('reports/','materials/','docs/','configs/'))for p in self.dependencies))
        self.assertFalse(any('records/'in p or '.runtime/'in p for p in self.dependencies))
        self.assertEqual([p for p in self.dependencies if 'P135' in p],
                         ['reports/P135_execution_start_20261027.json','docs/experiments/P135_execution_start_20261027.md'])

    def test_ordinary_P123_and_inline_distinction(self):
        rows={c['comparison']:c for c in self.summary['comparisons']if c['phase']=='P123'}
        self.assertEqual(rows['ordinary_anchor']['exact_total_delta_tokens'],-107873)
        self.assertEqual(rows['inline_vs_strong_ordinary']['exact_total_delta_tokens'],51266)
        self.assertFalse(self.summary['phases']['P123']['fixed_development_gate'])

    def test_known_subset_is_not_gate_replacement(self):
        for phase,expected in [('P128',-141841),('P129',0)]:
            c=next(c for c in self.summary['comparisons']if c['phase']==phase and c['scope']=='fixed_cohort' and c['comparison']=='primary')
            self.assertIsNone(c['exact_total_delta_tokens'])
            self.assertIsNone(c['fixed_gate_common_success_delta_tokens'])
            self.assertEqual(c['descriptive_common_success_delta_tokens'],expected)
        c=next(c for c in self.summary['comparisons']if c['phase']=='P132')
        self.assertIsNone(c['descriptive_common_success_delta_tokens'])

    def test_saved_replay_and_unstarted_are_separate(self):
        self.assertEqual([r['attempted_programs']for r in self.summary['saved_response_replays']],[20,48])
        p126=self.summary['saved_response_replays'][1]
        self.assertEqual((p126['regular_boundary_ok_programs'],p126['regular_boundary_known_error_programs'],p126['frontier_programs']),(40,4,4))
        for r in self.summary['saved_response_replays']:
            self.assertEqual(r['environment_api_requests'],0)
            self.assertIsNone(r['whole_job_token_effect'])
        ops={r['phase']:r for r in self.summary['operational_attempts']}
        self.assertEqual([ops[p]['evaluated_conditions']for p in ['P130','P131','P134']],[0,0,0])
        for r in ops.values():self.assertIsNone(r['exact_total_tokens'])
        self.assertIsNone(ops['P135']['successful_conditions'])
        self.assertIsNone(ops['P135']['model_calls'])


if __name__=='__main__':
    unittest.main()
