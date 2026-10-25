from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from public_only_history_worker_fixture import ROOT, audit_fixture, fixture
from public_only_realized_history import (
    POLICIES, prepared_views, collect_renderings, summarize_cell, accounting_decompositions,
)
from receipt_reasoning_history import strip_reasoning


class PublicOnlyRealizedHistoryTests(unittest.TestCase):
    def saved(self, actions=('echo', 'echo', 'finish'), **options):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        result = fixture(folder=temporary.name, actions=actions, **options)
        source = audit_fixture(temporary.name, result, 'public_only')
        trial = Path(temporary.name)/'records/context_pilot/BOC_P114_fixture'
        def read(name):
            path = trial/(name+'.json')
            return json.loads(path.read_text()) if path.exists() else None
        usage = read('usage')
        return dict(original=json.loads((ROOT/'configs/P29_stateful_code_v01.json').read_text()),
            public_task=read('public_task'), config=read('plan'), usage=usage,
            events=read('events'), spans=read('spans'), signals=read('budget_observations'),
            execution_records=read('reasoning_execution_records'), history_views=read('reasoning_history_views'),
            requests={c['id']: read(c['id']+'/request') for c in usage},
            responses={c['id']: read(c['id']+'/response') for c in usage}), source

    def test_rebuilds_full_archive_behind_omitted_latest_and_failed_reasoning(self):
        values, _ = self.saved(('echo', 'fail', 'echo', 'finish'))
        before = deepcopy(values)
        with patch('subprocess.Popen', side_effect=AssertionError('saved actions must not execute')):
            views, evidence = prepared_views(**values)
        self.assertEqual(values, before)
        self.assertEqual(len(evidence), 4)
        full, recent, gated, public = views[8:12]
        self.assertEqual(full['projection']['removed_reasoning_turns'], [])
        self.assertEqual(recent['projection']['removed_reasoning_turns'], [1])
        self.assertEqual(gated['projection']['removed_reasoning_turns'], [])
        self.assertEqual(public['projection']['removed_reasoning_turns'], [1, 2])
        self.assertEqual(public['payload'], values['requests']['call_003'])
        for view in (full, recent, gated):
            self.assertEqual(strip_reasoning(view['payload']['messages']), public['payload']['messages'])
        self.assertFalse(public['projection']['receipt_eligibility_used_for_selection'])

    def test_changed_actual_request_and_future_execution_evidence_are_rejected(self):
        values, _ = self.saved()
        changed = deepcopy(values)
        changed['requests']['call_002']['messages'][0]['content'] = 'tampered'
        with self.assertRaisesRegex(ValueError, 'actual_request_messages_changed'):
            prepared_views(**changed)
        changed = deepcopy(values)
        changed['execution_records'][0]['evidence']['trusted_record_sha256'] = '0'*64
        with self.assertRaisesRegex(ValueError, 'trusted_execution_record_changed'):
            prepared_views(**changed)

    def test_actual_policy_cannot_be_relabelled_as_a_hypothetical_run(self):
        values, _ = self.saved()
        values['config']['reasoning_display_policy'] = 'full'
        with self.assertRaisesRegex(ValueError, 'recorded_P114_public_only_policy_required'):
            prepared_views(**values)

    def test_unknown_and_missing_request_keep_all_four_slots(self):
        values, _ = self.saved(('echo', 'unknown'))
        views, _ = prepared_views(**values)
        self.assertTrue(all(v['actual_measured_input_tokens'] is None for v in views[-4:]))
        self.assertTrue(all(v['actual_measured_output_tokens'] is None for v in views[-4:]))
        values['requests']['call_002'] = None
        views, _ = prepared_views(**values)
        self.assertTrue(all(v['payload'] is None and not v['actual_request_available'] for v in views[-4:]))

    def test_unattempted_terminal_view_is_not_charged(self):
        values, _ = self.saved(token_limit=50)
        views, _ = prepared_views(**values)
        self.assertEqual(len(values['history_views']), 2)
        self.assertEqual(len(values['usage']), 1)
        self.assertEqual(len(views), 4)

    def rendered(self, unknown=False, absent=False, overflow=False):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        folder = Path(temporary.name)
        views = []
        for index, policy in enumerate(POLICIES):
            key = 'call_001_'+policy
            tokens = list(range(5-index))
            if overflow and policy == 'full':
                tokens = [1]*61441
            views.append(dict(call_id='call_001', case_id=key, policy=policy, actual_policy='public_only',
                actual_request_available=not absent, actual_usage_status='error' if unknown else 'ok',
                actual_measured_input_tokens=None if unknown else 2))
            if not absent:
                (folder/(key+'_rendered_private.json')).write_text(json.dumps(dict(
                    id=key, tokens=tokens, input_tokens=len(tokens), prompt='synthetic', media_files=0,
                    session_controls={'fixed': True}, parsed_non_message_parameters={'seed': 57})))
        return folder, views

    def test_native_count_must_match_actual_public_only_and_keep_decoder_controls(self):
        folder, views = self.rendered()
        rows = collect_renderings(folder, views)
        self.assertEqual([r['delta_from_actual'] for r in rows], [3, 2, 1, 0])
        views[0]['actual_measured_input_tokens'] = 5
        with self.assertRaisesRegex(ValueError, 'actual_measured_input_count_differs'):
            collect_renderings(folder, views)
        views[0]['actual_measured_input_tokens'] = 2
        path = folder/'call_001_full_rendered_private.json'
        value = json.loads(path.read_text())
        value['parsed_non_message_parameters']['seed'] = 99
        path.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError, 'only_history_may_change_decoder_controls'):
            collect_renderings(folder, views)

    def test_hypothetical_context_overflow_is_labelled_not_hidden(self):
        folder, views = self.rendered(overflow=True)
        rows = collect_renderings(folder, views)
        self.assertFalse(rows[0]['input_and_max_output_fit_context'])
        self.assertTrue(rows[-1]['input_and_max_output_fit_context'])
        self.assertTrue(rows[0]['context_fit_is_not_total_budget_admission'])

    def test_native_count_does_not_impute_unknown_usage(self):
        folder, views = self.rendered(unknown=True)
        rows = collect_renderings(folder, views)
        source = dict(run_id='fixture', task_id='task', reasoning_display_policy='public_only',
            record_status='evaluated', success=False, model_calls=1, known_total_tokens=0, unknown_usage_calls=1)
        cell = summarize_cell(source, rows)
        self.assertEqual(cell['actual_policy_input_omission_on_realized_path'], 3)
        self.assertIsNone(cell['actual_full_logical_tokens'])
        self.assertIsNone(cell['hypothetical_full_display_cost_on_same_outputs'])

    def test_missing_request_has_four_uncounted_rows(self):
        folder, views = self.rendered(unknown=True, absent=True)
        rows = collect_renderings(folder, views)
        self.assertEqual(len(rows), 4)
        self.assertTrue(all(r['status'] == 'missing_recorded_request' and r['input_tokens'] is None for r in rows))
        self.assertTrue(all(r['input_and_max_output_fit_context'] is None for r in rows))

    def comparison(self):
        cells = [dict(run_id='new'+str(i), task_id=str(i), actual_policy='public_only',
            actual_full_logical_tokens=110, actual_policy_input_omission_on_realized_path=30,
            actual_success=True) for i in range(4)]
        historical = [dict(run_id='old'+str(i)+p, task_id=str(i), reasoning_display_policy=p,
            record_status='evaluated', known_total_tokens=100, unknown_usage_calls=0,
            success=True) for i in range(4) for p in POLICIES[:3]]
        return cells, historical

    def test_accounting_uses_all_historical_rows_and_does_not_claim_causality(self):
        cells, historical = self.comparison()
        rows = accounting_decompositions(cells, historical)
        self.assertEqual(len(rows), 4)
        self.assertEqual(rows[0]['observed_cost_difference_from_full'], 10)
        self.assertEqual(rows[0]['remainder_after_adding_back_local_omission'], 40)
        self.assertFalse(rows[0]['contemporaneous_comparison'])
        self.assertTrue(rows[0]['remainder_is_not_a_causal_effect'])
        with self.assertRaisesRegex(ValueError, 'all_four_new_and_twelve_historical_conditions_required'):
            accounting_decompositions(cells, historical[:-1])

    def test_historical_unknown_or_missing_new_input_cannot_create_exact_residual(self):
        cells, historical = self.comparison()
        historical[0]['unknown_usage_calls'] = 1
        row = accounting_decompositions(cells, historical)[0]
        self.assertIsNone(row['observed_cost_difference_from_full'])
        self.assertIsNone(row['remainder_after_adding_back_local_omission'])
        historical[0]['unknown_usage_calls'] = 0
        cells[0]['actual_policy_input_omission_on_realized_path'] = None
        row = accounting_decompositions(cells, historical)[0]
        self.assertEqual(row['observed_cost_difference_from_full'], 10)
        self.assertIsNone(row['remainder_after_adding_back_local_omission'])


if __name__ == '__main__':
    unittest.main()
