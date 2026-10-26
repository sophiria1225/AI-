"""Synthetic P130 evidence audit; no saved generated source is executed."""
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
import audit_whole_task_checkpoint_inventory as auditor
from budget_signal import digest
from checkpoint_inventory_runtime import encoded
from joined_public_read_views import JOINED_CONTRACT_ID
from public_output_grounding import PUBLIC_CONTRACT_ID
from test_whole_task_output_grounding_audit import transport_records, read, write
from test_whole_task_checkpoint_inventory_worker import fixture
from whole_task_checkpoint_inventory import initial_conversation, cell_id, run_order

ROOT = Path(__file__).resolve().parents[1]


class CheckpointInventoryAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(); cls.addClassCleanup(cls.temporary.cleanup)
        cls.records = {}
        specs = [(mode + str(rep), mode, dict(replication=rep, checkpoint=True))
            for rep in (1, 2) for mode in ('off', 'checkpoint_inventory')]
        specs += [(name, 'checkpoint_inventory', options) for name, options in (
            ('none', {}), ('rejected', dict(checkpoint=True, reject_checkpoint=True)),
            ('unknown', dict(checkpoint=True, unknown_after_inventory=True)),
            ('capture_failed', dict(checkpoint=True, capture_fail=True)))]
        for name, mode, options in specs:
            storage = Path(cls.temporary.name) / name; storage.mkdir()
            data = fixture(storage, mode, **options); transport_records(data)
            cls.records[name] = data

    def setUp(self):
        for name, value in (
            ('region_projection_runtime.verify_joined_implementation', JOINED_CONTRACT_ID),
            ('demand_joined_read_adapter.verify_joined_implementation', JOINED_CONTRACT_ID),
            ('audit_output_grounding_runtime.verify_public_export_sources', PUBLIC_CONTRACT_ID),
            # The handwritten fixture uses this host Python; production checks
            # the source-bound container configuration instead.
            ('audit_checkpoint_inventory_trace.expected_inventory_python', sys.version.split()[0])):
            verifier = patch(name, return_value=value); verifier.start(); self.addCleanup(verifier.stop)

    def copied(self, destination, name='checkpoint_inventory1'):
        data = self.records[name]
        folder = Path(destination) / 'records/context_pilot' / data['folder'].name
        shutil.copytree(data['folder'], folder)
        return {**data, 'folder': folder}

    def audit(self, data):
        config = read(data['folder'] / 'plan.json')
        conv = initial_conversation(data['original'], data['public'])
        pre = dict(base_messages_sha256=digest(conv.for_model(config['observation_page_characters'])[0]))
        return auditor.audit_cell(data['folder'], ROOT, data['plan'], data['original'], data['item'],
            config['inventory_mode'], config['replication'], pre, False, tools=data['tools'])

    def test_all_four_conditions_reconstruct_both_captures_and_only_on_actor_exposure(self):
        for rep in (1, 2):
            for mode in ('off', 'checkpoint_inventory'):
                with self.subTest(rep=rep, mode=mode):
                    checked = self.audit(self.records[mode + str(rep)])
                    self.assertEqual((checked['replication'], checked['model_seed'], checked['inventory_mode']),
                        (rep, (57, 157)[rep-1], mode))
                    self.assertGreater(checked['inventory_captures'], 0)
                    self.assertEqual(checked['inventory_captures'], checked['checkpoint_installations'])
                    self.assertEqual(checked['inventory_notice_actor_calls'],
                        checked['inventory_captures'] if mode == 'checkpoint_inventory' else 0)
                    self.assertTrue(checked['inventory_accounting_complete'])
                    self.assertFalse(checked['inventory_contract_failed'])
                    self.assertEqual(checked['grounding_mode'], 'feedback')
                    self.assertTrue(checked['grounding_accounting_complete'])
                    self.assertFalse(checked['inventory_capture_metadata_recomputed_from_program_values'])

    def test_inventory_input_and_focus_cost_are_in_shared_total_without_bytes_as_tokens(self):
        for mode in ('off', 'checkpoint_inventory'):
            data = self.records[mode + '1']; checked = self.audit(data)
            usage = read(data['folder'] / 'usage.json')
            self.assertEqual(checked['known_total_tokens'], sum(c['input_tokens'] + c['output_tokens'] for c in usage))
            self.assertGreater(checked['usage_by_role']['focus']['calls'], 0)
            self.assertGreater(checked['inventory_response_bytes'], 0)
            self.assertEqual(checked['api_requests'], len(data['raw'].calls))

    def test_no_or_rejected_checkpoint_has_no_capture_no_notice_but_retains_focus_cost(self):
        for name in ('none', 'rejected'):
            checked = self.audit(self.records[name])
            self.assertEqual((checked['inventory_captures'], checked['inventory_notice_actor_calls']), (0, 0))
        self.assertGreater(self.audit(self.records['rejected'])['usage_by_role']['focus']['calls'], 0)

    def test_paid_unknown_actor_consumes_inventory_and_does_not_gain_known_usage(self):
        checked = self.audit(self.records['unknown'])
        self.assertEqual(checked['unknown_usage_calls'], 1)
        self.assertEqual(checked['inventory_notice_actor_calls'], 1)
        self.assertFalse(checked['inventory_runtime']['pending'])
        self.assertIsNone(checked['success'])

    def test_failed_capture_is_unverifiable_not_a_zero_cost_success(self):
        with self.assertRaises((ValueError, FileNotFoundError)):
            self.audit(self.records['capture_failed'])
        summary = read(self.records['capture_failed']['folder'] / 'summary.json')
        self.assertGreater(summary['known_total_tokens'], 0)
        self.assertEqual(summary['checkpoint_inventory']['actual_inventory_exposures'], 0)

    def test_capture_epoch_scope_program_and_request_bytes_are_bound(self):
        for field, value in (('checkpoint_revision', 2), ('program_index', 999),
                             ('execution_scope_sha256', '0' * 64), ('source_boundary_sha256', '0' * 64)):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as temp:
                data = self.copied(temp)
                path = data['folder'] / 'checkpoint_inventory/capture_001/request_private.json'
                packet = read(path); packet[field] = value; path.write_bytes(encoded(packet))
                with self.assertRaises(ValueError): self.audit(data)

    def test_saved_packet_or_capture_ledger_cannot_replace_trusted_response(self):
        for filename in ('checkpoint_inventory_packets_private.json', 'checkpoint_inventory_capture_private.json'):
            with self.subTest(filename=filename), tempfile.TemporaryDirectory() as temp:
                data = self.copied(temp); path = data['folder'] / filename; rows = read(path)
                inventory = rows[0]['inventory']; inventory['bindings'][0]['name'] = 'invented_binding'
                write(path, rows)
                with self.assertRaises(ValueError): self.audit(data)

    def test_capture_response_wire_and_extra_capture_directory_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            data = self.copied(temp)
            path = data['folder'] / 'checkpoint_inventory/capture_001/wire_private.jsonl'
            path.write_bytes(path.read_bytes() + b'{}\n')
            with self.assertRaises(ValueError): self.audit(data)
        with tempfile.TemporaryDirectory() as temp:
            data = self.copied(temp); (data['folder'] / 'checkpoint_inventory/capture_099').mkdir()
            with self.assertRaises(ValueError): self.audit(data)

    def test_actor_and_focus_actual_request_bytes_cannot_be_changed(self):
        for role in ('agent', 'focus'):
            with self.subTest(role=role), tempfile.TemporaryDirectory() as temp:
                data = self.copied(temp)
                number = next(i for i, capture in enumerate(data['captured_requests'], 1)
                    if capture['role'] == role and (role == 'focus'
                        or 'checkpoint_runtime_inventory_v1' in json.dumps(capture['messages'])))
                path = data['folder'] / f'call_{number:03d}/request.json'; request = read(path)
                request['messages'][0]['content'] += '\nnot the counted inventory view'; write(path, request)
                with self.assertRaises(ValueError): self.audit(data)

    def test_display_ledger_may_not_claim_an_extra_dispatched_notice(self):
        for field, value in (('inventory_included', False), ('packet_sha256', '0' * 64)):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as temp:
                data = self.copied(temp); path = data['folder'] / 'checkpoint_inventory_inference_views.json'
                views = read(path); next(v for v in views if v['inventory_included'])[field] = value
                write(path, views)
                with self.assertRaises(ValueError): self.audit(data)

    def test_condition_identity_preserves_common_feedback_and_fixed_seeds(self):
        for field, value in (('grounding_mode', 'repair'), ('inventory_mode', 'off'),
                             ('model_seed', 157), ('replication', True), ('phase', 'P129')):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as temp:
                data = self.copied(temp); path = data['folder'] / 'summary.json'
                summary = read(path); summary[field] = value; write(path, summary)
                with self.assertRaises(ValueError): self.audit(data)

    def test_stopped_batch_preserves_all_four_slots_unknown_costs_and_no_overwrite(self):
        import run_whole_task_checkpoint_inventory as driver
        with tempfile.TemporaryDirectory() as temp, ExitStack() as stack:
            storage, root = Path(temp) / 'storage', Path(temp) / 'repo'; tasks = [{'task_id': 'synthetic'}]
            pre = {'rows': [dict(replication=rep, model_seed=seed, task_id='synthetic',
                conditions={m: {} for m in ('off', 'checkpoint_inventory')}) for rep, seed in enumerate((57, 157), 1)]}
            write(root / auditor.PREFLIGHT, pre); hashes = {'synthetic.py': '0' * 64}
            write(root / auditor.ACTIVATION, dict(source_hashes=hashes,
                preflight_sha256=auditor.sha(root / auditor.PREFLIGHT)))
            plan = {'batch_id': 'P130_batch_v01'}; write(root / auditor.PLAN, plan)
            pipeline = storage / 'records/context_pilot/P130_pipeline_v01'
            write(pipeline / 'status.json', dict(status='stopped', server_stopped=True, server_supervisor_pid=12345))
            write(pipeline / 'server_final.json', dict(status='stopped', pid=12344, supervisor_pid=12345))
            ids = [cell_id(*entry) for entry in run_order()]
            write(storage / 'records/context_pilot/P130_batch_v01/status.json',
                dict(phase='P130', status='stopped', rows=[], completed=[], active=ids[0]))
            write(storage / 'records/context_pilot' / ids[0] / 'summary.json', {'synthetic': True})
            (storage / 'records/context_pilot' / ids[1]).mkdir()
            stack.enter_context(patch.object(driver, 'sources', return_value=(plan, {}, [], tasks)))
            stack.enter_context(patch.object(driver, 'frozen_hashes', return_value=hashes))
            stack.enter_context(patch.object(auditor.subprocess, 'run', return_value=SimpleNamespace(returncode=1, stdout='')))
            stack.enter_context(patch.object(auditor, 'audit_cell', side_effect=ValueError('synthetic_contract_failure')))
            stack.enter_context(patch('builtins.print'))
            result = auditor.run(storage, root)
            self.assertEqual([r['run_id'] for r in result['rows']], ids)
            self.assertEqual([r['record_status'] for r in result['rows']],
                ['audit_error', 'incomplete_worker', 'not_run', 'not_run'])
            self.assertTrue(all(r['known_total_tokens'] is None for r in result['rows']))
            self.assertFalse(result['development_gate_met'])
            with self.assertRaises(FileExistsError): auditor.run(storage, root)


if __name__ == '__main__':
    unittest.main()
