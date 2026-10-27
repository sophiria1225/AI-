"""Handwritten P140 gate counterexamples; no actual cohort records or execution."""
from copy import deepcopy
import unittest

from test_checkpoint_prefix_identity_p140 import fixture as identity_fixture
from whole_task_checkpoint_delta_envelope_p140 import MODES, TASKS, summarize


def rows():
    result = []
    for task in TASKS:
        for mode, cost in zip(MODES, (1000, 900, 800)):
            prefix = identity_fixture('candidate' if mode == MODES[-1] else 'control')[2]
            result.append(dict(task_id=task, checkpoint_representation_mode=mode,
                record_status='evaluated', success=True, unknown_usage_calls=0,
                known_total_tokens=cost, **prefix,
                prefix_exposure_contract_failed=False, prefix_exposure_accounting_complete=True,
                checkpoint_representation_contract_failed=False,
                checkpoint_representation_accounting_complete=True,
                delta_envelope_contract_failed=False, delta_envelope_accounting_complete=True,
                object_prompt_known_focus_calls=int(mode == MODES[-1]),
                actual_delta_known_actor_calls=int(mode != MODES[0])))
    return result


class EnvelopeGateTests(unittest.TestCase):
    def test_both_independent_controls_and_validated_id_difference(self):
        result = summarize(rows(), [])
        self.assertEqual(result['planned_rows'], 12)
        self.assertEqual(len(result['comparisons']), 2)
        self.assertEqual([c['all_task_token_difference'] for c in result['comparisons']], [-800, -400])
        self.assertTrue(result['both_control_development_gate_met'])
        self.assertTrue(all(p['canonical_representation_prefix_match'] is True
                            and p['representation_prefix_match'] is False
                            for p in result['comparisons'][1]['pairs']))
        self.assertFalse(result['novel_method_claim'])
        self.assertFalse(result['independent_replication_claim'])

    def test_primary_pass_cannot_hide_unchanged_delta_control_failure(self):
        data=rows()
        for r in data:
            if r['checkpoint_representation_mode'] == 'exposure_delta': r['known_total_tokens']=700
        result=summarize(data, [])
        self.assertTrue(result['primary_utility_gate_met'])
        self.assertFalse(result['unchanged_delta_control_gate_met'])
        self.assertFalse(result['development_gate_met'])

    def test_every_slot_and_error_list_retained(self):
        for data in (rows()[:-1], rows()[:-1]+[rows()[0]], rows()+[rows()[0]]):
            with self.assertRaises(ValueError): summarize(data, [])
        for bad in (False, None, 0, ''):
            with self.assertRaises(ValueError): summarize(rows(), bad)
        self.assertFalse(summarize(rows(), ['synthetic'])['development_gate_met'])

    def test_unstarted_and_unknown_costs_are_not_zero(self):
        data=rows()
        for r in data:
            r.update(record_status='not_run',success=None,unknown_usage_calls=None,
                     known_total_tokens=None,representation_second_opportunity=None,
                     object_prompt_known_focus_calls=None,actual_delta_known_actor_calls=None)
        result=summarize(data, [])
        self.assertEqual(result['usage_count_missing_conditions'], 12)
        self.assertEqual(result['recorded_unknown_usage_calls'], 0)
        self.assertTrue(all(x is None for x in result['total_tokens_by_mode'].values()))
        self.assertTrue(all(c['common_success_token_difference'] is None for c in result['comparisons']))
        data=rows();data[-1]['unknown_usage_calls']=1
        result=summarize(data, [])
        self.assertEqual(result['recorded_unknown_usage_calls'], 1)
        self.assertEqual(result['known_token_subtotals_by_mode'][MODES[-1]], 3200)
        self.assertTrue(all(c['all_task_token_difference'] is None for c in result['comparisons']))
        self.assertFalse(result['development_gate_met'])

    def test_cheap_failure_and_equal_success_swap_do_not_pass(self):
        data=rows();data[-1].update(success=False,known_total_tokens=1)
        self.assertFalse(summarize(data, [])['primary_utility_gate_met'])
        data[0]['success']=False
        result=summarize(data, [])
        self.assertEqual(result['success_counts'][MODES[0]], result['success_counts'][MODES[-1]])
        self.assertFalse(result['primary_utility_gate_met'])

    def test_empty_common_and_failed_only_savings_do_not_pass(self):
        data=rows()
        for r in data:r['success']=False
        result=summarize(data, [])
        self.assertTrue(all(c['common_success_token_difference'] is None for c in result['comparisons']))
        self.assertFalse(result['development_gate_met'])
        data=rows()
        for r in data:
            r['known_total_tokens']=1000
            if r['task_id']==TASKS[-1]:
                r['success']=False
                if r['checkpoint_representation_mode']==MODES[-1]:r['known_total_tokens']=1
        result=summarize(data, [])
        self.assertEqual(result['comparisons'][0]['common_success_token_difference'], 0)
        self.assertFalse(result['development_gate_met'])

    def test_prompt_offer_installation_or_unknown_is_not_known_exposure(self):
        for key in ('object_prompt_known_focus_calls','actual_delta_known_actor_calls'):
            for value in (0,None,True):
                data=rows()
                for r in data:
                    r[key]=value;r['object_prompt_offers']=1;r['delta_installations']=1
                self.assertFalse(summarize(data, [])['development_gate_met'])

    def test_prefix_invalid_absent_or_other_values_differ_is_fail_closed(self):
        for change in ('missing','invalid','count','request','archive'):
            data=rows();s=data[-1]['representation_second_opportunity']
            if change=='missing':data[-1]['representation_second_opportunity']=None
            elif change=='invalid':s['protocol_prefix_identity']={'status':'invalid'}
            elif change=='count':s['candidate_cutoff']+=2
            elif change=='request':s['prior_request_output_sequence'][0]['request_sha256']='f'*64
            else:s['protocol_prefix_identity']['canonical_archive_sha256']='f'*64
            result=summarize(data, [])
            self.assertTrue(result['primary_utility_gate_met'])
            self.assertFalse(result['unchanged_delta_control_gate_met'])

    def test_failed_activated_mismatch_not_discarded_by_common_filter(self):
        data=rows()
        for r in data:
            if r['task_id']==TASKS[-1]:r['success']=False
        data[-1]['representation_second_opportunity']['accumulated_exposure']+=1
        result=summarize(data, [])
        self.assertFalse(result['comparisons'][1]['all_activated_canonical_prefixes_match'])
        self.assertFalse(result['unchanged_delta_control_gate_met'])

    def test_boolean_counts_and_contract_flags_are_not_evidence(self):
        for key,bad in [('success',1),('unknown_usage_calls',False),('known_total_tokens',True),
            ('prefix_exposure_contract_failed',0),('checkpoint_representation_accounting_complete',1),
            ('delta_envelope_contract_failed',0),('delta_envelope_accounting_complete',1)]:
            data=rows();data[-1][key]=bad
            self.assertFalse(summarize(data, [])['development_gate_met'])


if __name__=='__main__':unittest.main()
