from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from checkpoint_realized_inputs import prepared_views, collect_renderings, summarize_cell, DISPLAYS
from whole_task_single_checkpoint import initial_conversation
from single_checkpoint_worker_fixture import fixture as separate_fixture, audit_fixture as audit_separate
from inline_checkpoint_worker_fixture import fixture as optional_fixture, audit_fixture as audit_optional
from required_inline_checkpoint_worker_fixture import fixture as required_fixture, audit_fixture as audit_required

ROOT = Path(__file__).resolve().parents[1]


def inputs(folder, phase):
    trial = Path(folder) / 'records/context_pilot' / f'BOC_{phase}_fixture'
    def get(name, default=None):
        p = trial / (name + '.json')
        return json.loads(p.read_text()) if p.exists() else default
    config, usage = get('plan'), get('usage')
    inline = config['checkpoint_policy'] == 'inline_checkpoint'
    original = json.loads((ROOT / 'configs/P29_stateful_code_v01.json').read_text())
    return {'conversation': initial_conversation(original, get('public_task')), 'config': config,
        'usage': usage, 'events': get('events'), 'spans': get('spans'),
        'signals': get('budget_observations', []),
        'history_views': get('inline_history_views' if inline else 'checkpoint_history_views', []),
        'controls': get('inline_controls' if inline else 'checkpoint_controls', []),
        'checkpoint': get('checkpoint_private'),
        'requests': {c['id']: get(c['id'] + '/request') for c in usage},
        'responses': {c['id']: get(c['id'] + '/response') for c in usage}, 'phase': phase}


class CheckpointRealizedInputTests(unittest.TestCase):
    def test_all_three_phases_reconstruct_actual_inputs_and_restore_only_active_replacements(self):
        for phase, fixture, audit in (('P118', separate_fixture, audit_separate),
                                      ('P119', optional_fixture, audit_optional),
                                      ('P120', required_fixture, audit_required)):
            policies = ('full', 'single_checkpoint') if phase == 'P118' else ('single_checkpoint', 'inline_checkpoint')
            for policy in policies:
                with self.subTest(phase=phase, policy=policy), tempfile.TemporaryDirectory() as folder:
                    result = fixture(policy=policy, actions=('echo', 'echo', 'echo', 'echo', 'finish'), folder=folder)
                    audit(folder, result)
                    values = inputs(folder, phase)
                    rows = prepared_views(**values)
                    self.assertEqual(len(rows), 2 * len(values['usage']))
                    active = [r for r in rows if r['display'] == 'actual' and r['checkpoint_active']]
                    self.assertEqual(len(active), 0 if policy == 'full' else 1 if policy == 'inline_checkpoint' else 2)
                    for actual, restored in zip(rows[::2], rows[1::2], strict=True):
                        self.assertEqual(actual['payload'], values['requests'][actual['call_id']])
                        if actual['checkpoint_active']:
                            self.assertNotEqual(actual['payload']['messages'], restored['payload']['messages'])
                            for key in actual['payload']:
                                if key != 'messages': self.assertEqual(actual['payload'][key], restored['payload'][key])
                            if policy == 'inline_checkpoint':
                                args = [m['tool_calls'][0]['function']['arguments'] for m in restored['payload']['messages']
                                        if m.get('tool_calls')]
                                self.assertTrue(all('checkpoint' not in json.loads(a) for a in args))
                        else:
                            self.assertEqual(actual['payload'], restored['payload'])

    def test_absent_invalid_truncated_and_terminal_only_checkpoints_do_not_restore_anything(self):
        cases = [{'summary_mode': m} for m in ('missing', 'invalid', 'truncated')]
        cases += [{'actions': ('echo', 'echo', 'echo', 'finish')}]
        for options in cases:
            with self.subTest(options=options), tempfile.TemporaryDirectory() as folder:
                result = required_fixture(folder=folder, **{'actions': ('echo', 'echo', 'echo', 'echo', 'finish'), **options})
                audit_required(folder, result)
                rows = prepared_views(**inputs(folder, 'P120'))
                self.assertFalse(any(r['checkpoint_active'] for r in rows))
                for a, b in zip(rows[::2], rows[1::2], strict=True): self.assertEqual(a['payload'], b['payload'])

    def test_unknown_usage_and_missing_request_remain_missing_without_executing_saved_actions(self):
        for action in ('unknown', 'transport_error'):
            with self.subTest(action=action), tempfile.TemporaryDirectory() as folder:
                result = required_fixture(actions=('echo', 'echo', 'echo', action), folder=folder)
                audit_required(folder, result)
                values = inputs(folder, 'P120')
                values['requests'][values['usage'][-1]['id']] = None
                rows = prepared_views(**values)
                self.assertEqual(len(rows), 8)
                for row in rows[-2:]:
                    self.assertIsNone(row['payload'])
                    self.assertIsNone(row['actual_measured_input_tokens'])
                    self.assertFalse(row['actual_request_available'])

    def test_changed_archive_reference_or_actual_request_is_rejected(self):
        for mode in ('history', 'request', 'schema'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as folder:
                result = required_fixture(actions=('echo', 'echo', 'echo', 'echo', 'finish'), folder=folder)
                audit_required(folder, result)
                values = inputs(folder, 'P120')
                if mode == 'history': values['history_views'][-1]['original_history_sha256'] = '0' * 64
                elif mode == 'request': values['requests']['call_005']['messages'][-1]['content'] += ' changed'
                else: values['requests']['call_004']['tools'][0]['function']['parameters']['required'].remove('checkpoint')
                with self.assertRaises(ValueError): prepared_views(**values)

    def test_native_count_of_unknown_attempt_does_not_impute_terminal_usage(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            views = []
            for display, count in zip(DISPLAYS, (100, 140), strict=True):
                cid = 'call_001_' + display
                views.append({'call_id': 'call_001', 'case_id': cid, 'role': 'agent', 'display': display,
                    'actual_request_available': True, 'checkpoint_active': True,
                    'actual_measured_input_tokens': None, 'actual_output_cap': 4096, 'actual_usage_status': 'error'})
                (folder / (cid + '_rendered_private.json')).write_text(json.dumps({
                    'id': cid, 'input_tokens': count, 'tokens': [1] * count, 'media_files': 0,
                    'session_controls': {}, 'parsed_non_message_parameters': {}, 'prompt': 'synthetic'}))
            rows = collect_renderings(folder, views)
            source = {'run_id': 'synthetic', 'task_id': 'fixture', 'checkpoint_policy': 'inline_checkpoint',
                'record_status': 'evaluated', 'success': False, 'model_calls': 1, 'known_total_tokens': 0,
                'unknown_usage_calls': 1, 'usage_by_role': {'focus': {'input_tokens': 0, 'output_tokens': 0, 'unknown_usage': 0}}}
            summary = summarize_cell(source, rows)
            self.assertEqual(summary['direct_input_difference_on_realized_path'], 40)
            self.assertIsNone(summary['hypothetical_restore_cost_on_same_outputs'])
            self.assertTrue(summary['actual_unknown_usage_not_imputed'])
            self.assertFalse(summary['actual_success'])
            self.assertIsNone(summary['active_replacement_input_timeline'][0]['minus_separate_summary_cost'])
            altered = deepcopy(views)
            altered[0]['actual_measured_input_tokens'] = 101
            with self.assertRaises(ValueError): collect_renderings(folder, altered)

    def test_amortization_uses_all_later_inputs_and_keeps_budget_overflow_and_missing_slots(self):
        rows = [{'call_id': f'call_{i}', 'display': 'actual', 'status': 'counted',
                 'checkpoint_active': True, 'actual_usage_status': 'ok', 'restoration_input_difference': d}
                for i, d in enumerate((100, 300), 1)]
        source = {'run_id': 'synthetic', 'task_id': 'fixture', 'checkpoint_policy': 'single_checkpoint',
            'record_status': 'evaluated', 'success': False, 'model_calls': 2, 'known_total_tokens': 449900,
            'unknown_usage_calls': 0, 'usage_by_role': {'focus': {'input_tokens': 300, 'output_tokens': 50, 'unknown_usage': 0}}}
        summary = summarize_cell(source, rows)
        self.assertEqual([r['minus_separate_summary_cost'] for r in summary['active_replacement_input_timeline']], [-250, 50])
        self.assertEqual(summary['direct_input_difference_minus_separate_summary_cost'], 50)
        self.assertTrue(summary['hypothetical_restore_cost_exceeds_task_token_budget'])
        self.assertFalse(summary['actual_success'])
        self.assertFalse(summary['whole_task_savings_claim'])
        rows[-1]['status'] = 'missing_recorded_request'
        self.assertIsNone(summarize_cell(source, rows)['direct_input_difference_on_realized_path'])


if __name__ == '__main__':
    unittest.main()
