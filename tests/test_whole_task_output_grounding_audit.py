"""P129 closed synthetic wire/record reconstruction; no generated-code replay."""
from contextlib import ExitStack
from copy import deepcopy
import json
from pathlib import Path
import shutil
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import audit_whole_task_output_grounding as auditor
from audit_output_grounding_runtime import audit_runtime
from budget_signal import digest
from compact_api_receipts import ReceiptMetrics
from fixed_budget_local_llama import payload_for as focus_payload
from joined_public_read_views import JOINED_CONTRACT_ID
from public_display import CODE_TOOLS
from public_output_grounding import PUBLIC_CONTRACT_ID
from test_whole_task_output_grounding_worker import fixture
from tool_choice_local_llama import payload_for as agent_payload
from whole_task_output_grounding import initial_conversation, cell_id, run_order

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return json.loads(path.read_text())


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def transport_records(data):
    for number, capture in enumerate(data['captured_requests'], 1):
        folder = data['folder'] / f'call_{number:03d}'
        actor = capture['role'] == 'agent'
        payload = agent_payload if actor else focus_payload
        write(folder / 'request.json', payload(capture['config'], capture['messages'], CODE_TOOLS if actor else []))
        path = folder / 'response.json'
        if not path.exists(): continue
        response = read(path)
        if response['status'] != 'ok': continue
        usage = dict(prompt_tokens=response['input_tokens'], completion_tokens=response['output_tokens'],
            total_tokens=response['input_tokens'] + response['output_tokens'],
            prompt_tokens_details={'cached_tokens': response['cached_input_tokens']})
        response['usage_details'] = usage
        write(path, response)
        write(folder / 'raw_response.json', dict(usage=usage, timings=response['timings'],
            choices=[dict(message=response['message'], finish_reason=response['done_reason'])]))


class OutputGroundingAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.records = {}
        specs = [(mode + str(rep), mode, dict(replication=rep))
                 for rep in (1, 2) for mode in ('off', 'feedback', 'repair')]
        specs += [(name, 'repair', options) for name, options in (
            ('unknown_model', {'unknown_model': True}), ('unknown_write', {'unknown_write': True}),
            ('incomplete', {'incomplete': True}), ('raised', {'raised_write': True}),
            ('contract', {'corrupt_record': True}), ('checkpoint', {'checkpoint': True}))]
        for name, mode, options in specs:
            storage = Path(cls.temporary.name) / name; storage.mkdir()
            data = fixture(storage, mode, **options)
            transport_records(data)
            cls.records[name] = data

    def setUp(self):
        for name, value in (
            ('region_projection_runtime.verify_joined_implementation', JOINED_CONTRACT_ID),
            ('demand_joined_read_adapter.verify_joined_implementation', JOINED_CONTRACT_ID),
            ('audit_output_grounding_runtime.verify_public_export_sources', PUBLIC_CONTRACT_ID)):
            verifier = patch(name, return_value=value); verifier.start(); self.addCleanup(verifier.stop)

    def copied(self, destination, name='repair1'):
        data = self.records[name]
        folder = Path(destination) / 'records/context_pilot' / data['folder'].name
        shutil.copytree(data['folder'], folder)
        return {**data, 'folder': folder}

    def runtime(self, data):
        return audit_runtime(data['folder'], read(data['folder'] / 'plan.json'), data['tools'])

    def audit(self, data, *, evaluated=False):
        folder = data['folder']; config = read(folder / 'plan.json')
        conv = initial_conversation(data['original'], data['public'])
        pre = {'base_messages_sha256': digest(conv.for_model(config['observation_page_characters'])[0])}
        return auditor.audit_cell(folder, ROOT, data['plan'], data['original'], data['item'],
            config['grounding_mode'], config['replication'], pre, evaluated, tools=data['tools'])

    def test_all_six_fixed_conditions_reconstruct_actual_effective_payloads(self):
        for rep, seed in enumerate((57, 157), 1):
            for mode in ('off', 'feedback', 'repair'):
                with self.subTest(rep=rep, mode=mode):
                    checked = self.audit(self.records[mode + str(rep)])
                    self.assertEqual((checked['replication'], checked['model_seed'], checked['grounding_mode']),
                                     (rep, seed, mode))
                    self.assertEqual(checked['grounding_repairs'], int(mode == 'repair'))
                    self.assertEqual(checked['grounding_sent_repairs'], int(mode == 'repair'))
                    self.assertEqual(checked['grounding_feedback_blocks'], int(mode == 'feedback'))
                    self.assertTrue(checked['grounding_accounting_complete'])
                    self.assertFalse(checked['grounding_contract_failed'])
                    self.assertEqual(checked['projection_hits'], 0)
                    self.assertEqual(checked['known_total_tokens'], 250 if mode == 'feedback' else 200)
                    self.assertEqual(checked['api_requests'], len(self.records[mode + str(rep)]['raw'].calls))

    def test_feedback_is_unsent_but_paid_recovery_model_cost_is_included(self):
        data = self.records['feedback1']; checked = self.audit(data)
        ledger = read(data['folder'] / 'output_grounding_events_private.json')
        self.assertEqual(ledger[0]['decision'], 'feedback')
        self.assertEqual(ledger[0]['environment_API_requests'], 0)
        self.assertIsNone(ledger[0]['api_execution_nonce'])
        self.assertEqual(checked['model_calls'], 5)
        self.assertGreater(checked['known_total_tokens'], self.audit(self.records['repair1'])['known_total_tokens'])

    def test_real_rolling_checkpoint_reconstructs_notice_history_and_shared_focus_cost(self):
        data = self.records['checkpoint']; checked = self.audit(data)
        usage = read(data['folder'] / 'usage.json')
        self.assertGreater(checked['checkpoint_installations'], 0)
        self.assertTrue(any(capture['role'] == 'focus' for capture in data['captured_requests']))
        self.assertEqual(checked['known_total_tokens'], sum(
            call['input_tokens'] + call['output_tokens'] for call in usage))
        self.assertEqual(checked['model_calls'], len(data['captured_requests']))
        self.assertEqual(checked['grounding_repairs'], 1)
        self.assertTrue(any('output_grounding_notice' in json.dumps(capture['messages'])
                            for capture in data['captured_requests']))
        with tempfile.TemporaryDirectory() as temp:
            copied = self.copied(temp, 'checkpoint')
            focus_number = next(i for i, capture in enumerate(data['captured_requests'], 1)
                                if capture['role'] == 'focus')
            path = copied['folder'] / f'call_{focus_number:03d}' / 'request.json'
            request = read(path); request['messages'][-1]['content'] += '\nchanged source history'
            write(path, request)
            with self.assertRaises(ValueError): self.audit(copied)

    def test_incomplete_source_is_nonintervention_not_successful_repair(self):
        checked = self.audit(self.records['incomplete'])
        self.assertEqual((checked['grounding_repairs'], checked['grounding_repair_attempts']), (0, 0))
        self.assertTrue(checked['grounding_accounting_complete'])

    def test_raised_and_unknown_write_keep_actual_sent_cost_without_success_imputation(self):
        for name in ('raised', 'unknown_write'):
            checked = self.audit(self.records[name])
            self.assertEqual(checked['grounding_sent_repairs'], 1)
            self.assertEqual(checked['grounding_repairs'], 0)
            self.assertGreater(checked['known_total_tokens'], 0)
        with self.assertRaisesRegex(ValueError, 'evaluation_after_invalid_cell'):
            self.audit(self.records['unknown_write'], evaluated=True)

    def test_unknown_model_and_broken_controller_remain_unknown_or_unverifiable(self):
        checked = self.audit(self.records['unknown_model'])
        self.assertEqual(checked['unknown_usage_calls'], 1)
        self.assertEqual(checked['known_total_tokens'], 50)
        self.assertIsNone(checked['success'])
        with self.assertRaises(ValueError):
            self.audit(self.records['contract'])

    def test_uninitialized_runtime_has_unknown_accounting_not_an_incomplete_accounted_row(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            write(folder / 'summary.json', dict(projection_runtime=None,
                unknown_effect_requests=0, compact_receipts=ReceiptMetrics().summary()))
            write(folder / 'events.json', []); write(folder / 'spans.json', {})
            with self.assertRaisesRegex(ValueError, 'grounding_runtime_uninitialized_accounting_unknown'):
                audit_runtime(folder, {}, [])

    def test_decision_ledger_self_report_cannot_override_raw_reconstruction(self):
        for field, value in (('decision', 'pass'), ('effective_payload_sha256', '0' * 64),
                             ('supported_backup_confirmed', False), ('prior_record_count', 0)):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as temp:
                data = self.copied(temp); path = data['folder'] / 'output_grounding_events_private.json'
                rows = read(path); rows[0][field] = value; write(path, rows)
                with self.assertRaisesRegex(ValueError, 'grounding_decisions_or_payload_bindings_changed'):
                    self.runtime(data)

    def test_effective_inner_action_tampering_is_not_repaired_by_saved_proposal(self):
        with tempfile.TemporaryDirectory() as temp:
            data = self.copied(temp); path = data['folder'] / 'spans.json'; spans = read(path)
            target = next(s for s in spans.values() if (s.get('action') or {}).get('name') == 'file_system__create_file')
            args = json.loads(target['action']['arguments']); args['content'] = 'invented saved result'
            target['action']['arguments'] = json.dumps(args); write(path, spans)
            with self.assertRaises(ValueError): self.runtime(data)

    def test_original_wire_is_bound_and_effective_content_does_not_replace_archive(self):
        with tempfile.TemporaryDirectory() as temp:
            data = self.copied(temp)
            ledger = read(data['folder'] / 'output_grounding_events_private.json')
            program = data['folder'] / 'programs' / ledger[0]['program']
            original = read(program / 'input_private.json')['code']
            self.assertIn('Invented', original)
            lines = [json.loads(line) for line in (program / 'wire_private.jsonl').read_text().splitlines()]
            changed = False
            for packet in lines:
                if packet.get('kind') == 'api':
                    nested = packet.get('arguments', {}).get('packet', {})
                    action = nested.get('args', {})
                    if action.get('app') == 'file_system' and action.get('api') == 'create_file':
                        action['args']['content'] = 'changed original wire'; changed = True; break
            self.assertTrue(changed)
            (program / 'wire_private.jsonl').write_text(''.join(json.dumps(row) + '\n' for row in lines))
            with self.assertRaises(ValueError): self.runtime(data)

    def test_notice_ledger_and_displayed_notice_both_bind_actual_outcome(self):
        for target in ('ledger', 'display'):
            with self.subTest(target=target), tempfile.TemporaryDirectory() as temp:
                data = self.copied(temp)
                if target == 'ledger':
                    path = data['folder'] / 'output_grounding_notices_private.json'; value = read(path)
                    value[0]['notice']['interventions'][0]['outcome'] = 'raised'
                else:
                    path = data['folder'] / 'spans.json'; value = read(path)
                    span = next(s for s in value.values() if 'output_grounding_notice' in s['observation'])
                    span['observation']['output_grounding_notice']['interventions'][0]['outcome'] = 'raised'
                write(path, value)
                with self.assertRaises(ValueError): self.runtime(data)

    def test_public_source_contract_summary_and_reservation_tampering_are_rejected(self):
        for field, value in (('output_grounding_public_contract', 'wrong'),
                             ('output_grounding_summary_error_type', 'ValueError')):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as temp:
                data = self.copied(temp); path = data['folder'] / 'summary.json'
                summary = read(path); summary[field] = value; write(path, summary)
                with self.assertRaises(ValueError): self.runtime(data)

    def test_fixed_replication_mode_and_no_duplicate_preflight_condition(self):
        data = self.records['repair1']
        for field, value in (('grounding_mode', 'off'), ('model_seed', 157), ('replication', True), ('phase', 'P128')):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as temp:
                copied = self.copied(temp); path = copied['folder'] / 'summary.json'
                summary = read(path); summary[field] = value; write(path, summary)
                with self.assertRaisesRegex(ValueError, 'executed_P129_condition_changed'): self.audit(copied)
        tasks = [{'task_id': 'synthetic'}]
        rows = [dict(replication=rep, model_seed=seed, task_id='synthetic',
                     conditions={m: {} for m in ('off', 'feedback', 'repair')})
                for rep, seed in enumerate((57, 157), 1)]
        self.assertEqual(len(auditor.preflight_conditions(rows, tasks)), 2)
        with self.assertRaises(ValueError): auditor.preflight_conditions([rows[0], rows[0]], tasks)

    def test_stopped_batch_preserves_all_six_slots_without_overwrite(self):
        import run_whole_task_output_grounding as driver
        with tempfile.TemporaryDirectory() as temp, ExitStack() as stack:
            storage, root = Path(temp) / 'storage', Path(temp) / 'repo'
            tasks = [{'task_id': 'synthetic'}]
            pre = {'rows': [dict(replication=rep, model_seed=seed, task_id='synthetic',
                    conditions={m: {} for m in ('off', 'feedback', 'repair')})
                for rep, seed in enumerate((57, 157), 1)]}
            write(root / auditor.PREFLIGHT, pre)
            hashes = {'synthetic.py': '0' * 64}
            write(root / auditor.ACTIVATION, dict(source_hashes=hashes,
                  preflight_sha256=auditor.sha(root / auditor.PREFLIGHT)))
            plan = {'batch_id': 'P129_batch_v01'}; write(root / auditor.PLAN, plan)
            pipeline = storage / 'records/context_pilot/P129_pipeline_v01'
            write(pipeline / 'status.json', dict(status='stopped', server_stopped=True, server_supervisor_pid=12345))
            write(pipeline / 'server_final.json', dict(status='stopped', pid=12344, supervisor_pid=12345))
            ids = [cell_id(*entry) for entry in run_order()]
            write(storage / 'records/context_pilot/P129_batch_v01/status.json',
                  dict(phase='P129', status='stopped', rows=[], completed=[], active=ids[0]))
            write(storage / 'records/context_pilot' / ids[0] / 'summary.json', {'synthetic': True})
            (storage / 'records/context_pilot' / ids[1]).mkdir()
            stack.enter_context(patch.object(driver, 'sources', return_value=(plan, {}, [], tasks)))
            stack.enter_context(patch.object(driver, 'frozen_hashes', return_value=hashes))
            stack.enter_context(patch.object(auditor.subprocess, 'run', return_value=SimpleNamespace(returncode=1, stdout='')))
            stack.enter_context(patch.object(auditor, 'audit_cell', side_effect=ValueError('synthetic_contract_failure')))
            stack.enter_context(patch('builtins.print'))
            result = auditor.run(storage, root)
            self.assertEqual(len(result['rows']), 6)
            self.assertEqual([r['run_id'] for r in result['rows']], ids)
            self.assertEqual(result['rows'][0]['record_status'], 'audit_error')
            self.assertEqual(result['rows'][1]['record_status'], 'incomplete_worker')
            self.assertTrue(all(r['known_total_tokens'] is None for r in result['rows']))
            self.assertFalse(result['development_gate_met'])
            with self.assertRaises(FileExistsError): auditor.run(storage, root)


if __name__ == '__main__':
    unittest.main()
