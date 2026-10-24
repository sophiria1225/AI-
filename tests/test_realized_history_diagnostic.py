from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from receipt_history_worker_fixture import ROOT, audit_fixture, fixture
from realized_history_diagnostic import prepared_views, collect_renderings, summarize_cell, accounting_decompositions
from receipt_reasoning_history import POLICIES, strip_reasoning


class RealizedHistoryTests(unittest.TestCase):
    def saved(self, policy='recent', actions=('echo', 'echo', 'finish'), **options):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        result = fixture(folder=temporary.name, policy=policy, actions=actions, **options)
        source = audit_fixture(temporary.name, result, policy)
        trial = Path(temporary.name)/'records/context_pilot/BOC_P111_fixture'
        def read(name):
            path = trial/(name+'.json')
            return json.loads(path.read_text()) if path.exists() else None
        usage = read('usage')
        values = dict(original=json.loads((ROOT/'configs/P29_stateful_code_v01.json').read_text()),
            public_task=read('public_task'), config=read('plan'), usage=usage,
            events=read('events'), spans=read('spans'), signals=read('budget_observations'),
            execution_records=read('reasoning_execution_records'), history_views=read('reasoning_history_views'),
            requests={c['id']: read(c['id']+'/request') for c in usage},
            responses={c['id']: read(c['id']+'/response') for c in usage})
        return values, source

    def test_full_archive_is_reconstructed_behind_already_compacted_input(self):
        values, _ = self.saved()
        before = deepcopy(values)
        views, evidence = prepared_views(**values)
        self.assertEqual(values, before)
        full, recent, gated = views[-3:]
        self.assertEqual(full['projection']['removed_reasoning_turns'], [])
        self.assertEqual(recent['projection']['removed_reasoning_turns'], [1])
        self.assertEqual(gated['projection']['removed_reasoning_turns'], [1])
        full_assistants = [m for m in full['payload']['messages'] if m['role'] == 'assistant']
        self.assertEqual([m['reasoning_content'] for m in full_assistants], ['synthetic test text']*2)
        self.assertEqual(recent['payload'], values['requests']['call_003'])
        self.assertEqual(len(evidence), 3)

    def test_all_three_actual_policies_reproduce_recorded_requests_and_public_history(self):
        for policy in POLICIES:
            values, _ = self.saved(policy)
            views, _ = prepared_views(**values)
            for offset in range(0, len(views), 3):
                triplet = views[offset:offset+3]
                actual = next(v for v in triplet if v['policy'] == policy)
                self.assertEqual(actual['payload'], values['requests'][actual['call_id']])
                self.assertEqual(strip_reasoning(triplet[0]['payload']['messages']),
                                 strip_reasoning(triplet[1]['payload']['messages']))
                self.assertEqual(strip_reasoning(triplet[1]['payload']['messages']),
                                 strip_reasoning(triplet[2]['payload']['messages']))

    def test_failure_redisplay_and_later_retention_are_causal(self):
        values, _ = self.saved('execution_gated', ('echo', 'echo', 'fail', 'echo', 'finish'))
        views, _ = prepared_views(**values)
        selected = [v for v in views if v['policy'] == 'execution_gated']
        self.assertEqual([v['projection']['prior_turns'] for v in selected], [0, 1, 2, 3, 4])
        self.assertEqual(selected[2]['projection']['removed_reasoning_turns'], [1])
        self.assertEqual(selected[3]['projection']['redisplayed_reasoning_turns'], [1])
        self.assertEqual(selected[4]['projection']['removed_reasoning_turns'], [1, 2])

    def test_changed_actual_request_is_rejected(self):
        values, _ = self.saved()
        values['requests']['call_003']['messages'][0]['content'] = 'tampered'
        with self.assertRaisesRegex(ValueError, 'actual_request_messages_changed'):
            prepared_views(**values)

    def test_changed_trusted_execution_link_is_rejected(self):
        values, _ = self.saved()
        values['execution_records'][0]['evidence']['trusted_record_sha256'] = '0'*64
        with self.assertRaisesRegex(ValueError, 'trusted_execution_record_changed'):
            prepared_views(**values)

    def test_unknown_usage_and_absent_request_remain_distinct(self):
        values, _ = self.saved(actions=('echo', 'unknown'))
        views, _ = prepared_views(**values)
        for view in views[-3:]:
            self.assertTrue(view['actual_request_available'])
            self.assertIsNone(view['actual_measured_input_tokens'])
            self.assertIsNone(view['actual_measured_output_tokens'])
        values['requests']['call_002'] = None
        views, _ = prepared_views(**values)
        self.assertTrue(all(v['payload'] is None and not v['actual_request_available'] for v in views[-3:]))

    def test_terminal_unattempted_projection_adds_no_model_cost_slots(self):
        values, _ = self.saved(token_limit=50)
        views, _ = prepared_views(**values)
        self.assertEqual(len(values['history_views']), 2)
        self.assertEqual(len(values['usage']), 1)
        self.assertEqual(len(views), 3)

    def test_saved_actions_are_never_executed_during_reconstruction(self):
        values, _ = self.saved()
        with patch('subprocess.Popen', side_effect=AssertionError('no child execution')):
            views, _ = prepared_views(**values)
        self.assertEqual(len(views), 9)

    def rendered(self, *, unknown=False, absent=False):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        folder = Path(temporary.name)
        views = []
        for policy in POLICIES:
            key = 'call_001_'+policy
            tokens = [1, 2, 3] if policy == 'full' else [1, 3]
            views.append(dict(call_id='call_001', case_id=key, policy=policy, actual_policy='recent',
                actual_request_available=not absent, actual_usage_status='error' if unknown else 'ok',
                actual_measured_input_tokens=None if unknown else 2))
            if not absent:
                (folder/(key+'_rendered_private.json')).write_text(json.dumps(dict(
                    id=key, tokens=tokens, input_tokens=len(tokens), prompt='synthetic', media_files=0,
                    session_controls={'fixed': True}, parsed_non_message_parameters={'seed': 57})))
        return folder, views

    def test_count_matches_actual_recent_not_hypothetical_full(self):
        folder, views = self.rendered()
        rows = collect_renderings(folder, views)
        self.assertEqual([r['delta_from_full'] for r in rows], [0, -1, -1])
        self.assertEqual([r['delta_from_actual'] for r in rows], [1, 0, 0])
        views[0]['actual_measured_input_tokens'] = 3
        with self.assertRaisesRegex(ValueError, 'actual_measured_input_count_differs'):
            collect_renderings(folder, views)

    def test_decoder_controls_cannot_change_with_display(self):
        folder, views = self.rendered()
        path = folder/'call_001_full_rendered_private.json'
        value = json.loads(path.read_text())
        value['parsed_non_message_parameters']['seed'] = 99
        path.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError, 'only_history_may_change_decoder_controls'):
            collect_renderings(folder, views)

    def test_unknown_usage_is_not_recovered_from_offline_input_count(self):
        folder, views = self.rendered(unknown=True)
        rows = collect_renderings(folder, views)
        source = dict(run_id='fixture', task_id='task', reasoning_display_policy='recent',
            record_status='evaluated', success=False, model_calls=1, known_total_tokens=0, unknown_usage_calls=1)
        summary = summarize_cell(source, rows)
        self.assertEqual(summary['actual_policy_input_omission_on_realized_path'], 1)
        self.assertIsNone(summary['actual_full_logical_tokens'])
        self.assertIsNone(summary['hypothetical_full_display_cost_on_same_outputs'])
        self.assertTrue(summary['actual_unknown_usage_not_imputed'])

    def test_absent_request_keeps_three_uncounted_slots(self):
        folder, views = self.rendered(unknown=True, absent=True)
        rows = collect_renderings(folder, views)
        self.assertEqual(len(rows), 3)
        self.assertTrue(all(r['status'] == 'missing_recorded_request' for r in rows))
        self.assertTrue(all(r['input_tokens'] is None for r in rows))

    def test_accounting_identity_does_not_turn_shorter_input_into_savings(self):
        cells = [dict(task_id='task', actual_policy=p, actual_full_logical_tokens=cost,
            actual_policy_input_omission_on_realized_path=omission, actual_success=True)
            for p, cost, omission in [('full', 100, 0), ('recent', 110, 30), ('execution_gated', 95, 20)]]
        results = accounting_decompositions(cells)
        self.assertEqual(results[0]['observed_cost_difference_from_full'], 10)
        self.assertEqual(results[0]['remainder_after_adding_back_local_omission'], 40)
        self.assertFalse(results[0]['quality_preservation_or_savings_claim'])
        self.assertEqual(results[1]['observed_cost_difference_from_full'], -5)
        cells[1]['actual_full_logical_tokens'] = None
        result = accounting_decompositions(cells)[0]
        self.assertIsNone(result['observed_cost_difference_from_full'])
        self.assertIsNone(result['remainder_after_adding_back_local_omission'])


if __name__ == '__main__':
    unittest.main()
