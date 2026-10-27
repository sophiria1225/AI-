"""Real new worker and independent replay with handwritten external stubs."""
import json
from pathlib import Path
import tempfile
import unittest
from object_timing_worker_fixture_p141 import fixture, write_wire_fixture, ROOT
from checkpoint_object_timing_p141 import MODES, OBJECT_DELTA_SUMMARY_PROMPT
from audit_object_timing_trace_p141 import audit_trace
from whole_task_object_timing_p141 import initial_conversation, summarize
from object_timing_prefix_p141 import timing_prefix_comparison


def run_fixture(mode, **options):
    with tempfile.TemporaryDirectory() as tmp:
        result=fixture(mode=mode,folder=tmp,**options)
        trial=write_wire_fixture(tmp,result)
        config=json.loads((trial/'plan.json').read_text())
        public=json.loads((trial/'public_task.json').read_text())
        original=json.loads((ROOT/'configs/P29_stateful_code_v01.json').read_text())
        audited=audit_trace(trial,config,initial_conversation(original,public))
        return result,audited


class ObjectTimingWorkerTests(unittest.TestCase):
    def test_three_real_paths_honest_axes_full_count_send_and_cost(self):
        for mode in MODES:
            with self.subTest(mode=mode):
                result,audit=run_fixture(mode,actions=('echo',)*12+('finish',),max_calls=30)
                self.assertEqual(audit['known_total_tokens'],result['result']['known_total_tokens'])
                self.assertEqual(audit['delta_envelope_control'],result['result']['delta_envelope_control'])
                self.assertEqual(result['result']['object_timing_mode'],mode)
                self.assertLessEqual(audit['checkpoint_opportunity'],2)
                for view in result['saved']['checkpoint_representation_views']:
                    if view['model_attempted']:
                        self.assertTrue(any(view['model_messages_sha256']==__import__('receipt_reasoning_history').digest(x['messages'])
                                            for x in result['captured']))
                if mode != MODES[0]:
                    self.assertEqual(audit['object_prompt_known_focus_calls'],1)
                    self.assertGreater(audit['actual_delta_known_actor_calls'],0)
                    self.assertTrue(any(c['messages'][0]['content']==OBJECT_DELTA_SUMMARY_PROMPT
                                        for c in result['captured'] if c['role']=='focus'))
                else:self.assertEqual(audit['object_prompt_known_focus_calls'],0)

    def test_real_predecision_prefix_until_timing_divergence(self):
        rows=[]
        for mode in MODES[1:]:
            result,audit=run_fixture(mode,actions=('echo',)*12+('finish',),max_calls=30,focus_input_tokens=1000,post_checkpoint_step=2000)
            rows.append({**audit,'checkpoint_representation_mode':mode})
        comparison=timing_prefix_comparison(*rows)
        self.assertTrue(comparison['boundary_present'])
        self.assertTrue(comparison['canonical_match'])
        self.assertTrue(comparison['actual_dispatch_diverged'])
        self.assertTrue(comparison['both_dispatches_known'])
        self.assertNotEqual(rows[0]['representation_second_opportunity']['after_model_calls'],
                            rows[1]['representation_second_opportunity']['after_model_calls'])

    def test_unknown_focus_and_invalid_delta_preserve_failure_accounting(self):
        for mode in MODES[1:]:
            result,audit=run_fixture(mode,actions=('echo',)*12+('finish',),max_calls=30,
                                      summary_mode=['valid','unknown'])
            self.assertEqual(audit['unknown_usage_calls'],1)
            self.assertEqual(audit['object_prompt_unknown_focus_calls'],1)
            self.assertEqual(result['captured'][-1]['role'],'focus')
            result,audit=run_fixture(mode,actions=('echo',)*12+('finish',),max_calls=30,
                                      summary_mode=['valid','invalid'])
            self.assertEqual(audit['checkpoint_installations'],1)
            self.assertEqual(audit['actual_delta_actor_calls'],0)
            self.assertEqual(audit['object_prompt_known_focus_calls'],1)

    def test_new_cohort_audit_cell_accepts_all_three_exact_worker_modes(self):
        from audit_whole_task_object_timing_p141 import audit_cell
        from object_timing_worker_fixture_p141 import configuration
        from receipt_reasoning_history import digest
        for mode in MODES:
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as tmp:
                result=fixture(mode=mode,folder=tmp,actions=('finish',))
                trial=write_wire_fixture(tmp,result)
                plan=json.loads((trial/'comparison_plan.json').read_text())
                original,_,item=configuration();original['api_budget_by_task']['6104387_1']=80
                archive,_=initial_conversation(original,item['public_task']).for_model()
                row=audit_cell(trial,ROOT,plan,original,item,mode,
                               {'base_messages_sha256':digest(archive)},False)
                self.assertEqual(row['object_timing_mode'],mode)
                self.assertEqual(row['record_status'],'unevaluated')
                self.assertIsNone(row['success'])
                self.assertEqual(row['known_total_tokens'],result['result']['known_total_tokens'])

    def test_short_task_has_no_fabricated_boundary_or_intervention(self):
        rows=[]
        for mode in MODES[1:]:
            result,audit=run_fixture(mode,actions=('finish',))
            self.assertEqual(audit['object_prompt_offers'],0)
            rows.append({**audit,'checkpoint_representation_mode':mode})
        out=timing_prefix_comparison(*rows)
        self.assertFalse(out['boundary_present']);self.assertIsNone(out['canonical_match'])

if __name__=='__main__':unittest.main()
