"""Synthetic closed records only; no model, external API, evaluator or Docker.

Worker fixtures execute handwritten test programs with fake transports. The
auditor itself only reads/hash/parses their saved records; it never reruns code.
"""
from copy import deepcopy
from contextlib import ExitStack
import json
from pathlib import Path
from types import SimpleNamespace
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import audit_whole_task_receipt_disclosure as auditor
from audit_receipt_checkpoint_trace import audit_archive_reads, audit_trace
from budget_signal import digest
from context_preservation import compact, page_span
from fixed_budget_local_llama import payload_for as focus_payload
from joined_public_read_views import JOINED_CONTRACT_ID
from public_display import CODE_TOOLS
from test_public_name_catalog import tool
from test_public_read_views_live_probe import catalog
from test_whole_task_receipt_disclosure_worker import fixture, PROGRAMS
from tool_choice_local_llama import payload_for as agent_payload
from whole_task_receipt_disclosure import initial_conversation, cell_id, run_order

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return json.loads(path.read_text())


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def transport_records(data):
    """Finish fake transport evidence, without executing any saved program."""
    for number, capture in enumerate(data['captured'], 1):
        call = data['folder'] / f'call_{number:03d}'
        actor = capture['role'] == 'agent'
        payload = agent_payload if actor else focus_payload
        write(call / 'request.json', payload(capture['config'], capture['messages'], CODE_TOOLS if actor else []))
        response_path = call / 'response.json'
        if not response_path.exists():
            continue
        response = read(response_path)
        if response['status'] != 'ok':
            continue
        usage = dict(prompt_tokens=response['input_tokens'], completion_tokens=response['output_tokens'],
            total_tokens=response['input_tokens'] + response['output_tokens'],
            prompt_tokens_details={'cached_tokens': response['cached_input_tokens']})
        response['usage_details'] = usage
        write(response_path, response)
        write(call / 'raw_response.json', dict(usage=usage, timings=response['timings'],
            choices=[dict(message=response['message'], finish_reason=response['done_reason'])]))


class ReceiptDisclosureAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.records = {}
        specs = [(f'{mode}{rep}', mode, dict(replication=rep))
                 for rep in (1, 2) for mode in ('full', 'disclose')]
        specs += [('rolling_' + mode, mode, dict(checkpoint=True,
            programs=(PROGRAMS[0],) + (PROGRAMS[1],) * 7 + (PROGRAMS[-1],), max_calls=12))
            for mode in ('full', 'disclose')]
        expansion = {'name': 'read_span', 'arguments': json.dumps({'span_id': 's2', 'offset': 7})}
        specs += [('archive', 'disclose', dict(programs=(PROGRAMS[0], PROGRAMS[1], expansion, PROGRAMS[-1]))),
                  ('terminal_only', 'disclose', dict(programs=('\n'.join((PROGRAMS[0], PROGRAMS[1], PROGRAMS[-1])),))),
                  ('unknown_model', 'disclose', dict(unknown=True)),
                  ('unknown_api', 'disclose', dict(unknown_api=True)),
                  ('known_api_error', 'disclose', dict(contract_failure=True)),
                  ('ordinary_error', 'disclose', dict(programs=(PROGRAMS[0], '1/0', PROGRAMS[1], PROGRAMS[-1])))]
        for name, mode, options in specs:
            storage = Path(cls.temporary.name) / name
            storage.mkdir()
            data = fixture(storage, mode, **options)
            transport_records(data)
            cls.records[name] = data

    def setUp(self):
        for name in ('region_projection_runtime.verify_joined_implementation',
                     'demand_joined_read_adapter.verify_joined_implementation'):
            verifier = patch(name, return_value=JOINED_CONTRACT_ID)
            verifier.start()
            self.addCleanup(verifier.stop)

    def copied(self, destination, name='disclose1'):
        data = self.records[name]
        folder = Path(destination) / 'records/context_pilot' / data['folder'].name
        shutil.copytree(data['folder'], folder)
        return {**data, 'folder': folder}

    def audit(self, data, evaluated=False):
        folder = data['folder']
        config, plan = read(folder / 'plan.json'), read(folder / 'comparison_plan.json')
        item = {**read(folder / 'source_identity.json'), 'public_task': data['public']}
        mode, rep = config['receipt_disclosure_policy'], config['replication']
        conversation = initial_conversation(data['original'], data['public'], mode, execution_scope=folder.name)
        pre = {'base_messages_sha256': digest(conversation.for_model(config['observation_page_characters'])[0])}
        return auditor.audit_cell(folder, ROOT, plan, data['original'], item, mode, rep, pre,
            evaluated, tools=list(catalog().catalog.values()) + [tool('supervisor__complete_task')])

    def trace(self, data):
        config = read(data['folder'] / 'plan.json')
        conversation = initial_conversation(data['original'], data['public'],
            config['receipt_disclosure_policy'], execution_scope=data['folder'].name)
        return audit_trace(data['folder'], config, conversation)

    def test_both_modes_both_fixed_seeds_reconstruct_source_and_shared_runtime(self):
        for rep, seed in enumerate((57, 157), 1):
            for mode in ('full', 'disclose'):
                with self.subTest(mode=mode, rep=rep):
                    checked = self.audit(self.records[f'{mode}{rep}'])
                    self.assertEqual((checked['replication'], checked['model_seed'], checked['receipt_mode']),
                                     (rep, seed, mode))
                    self.assertEqual((checked['model_calls'], checked['known_total_tokens'], checked['api_requests']), (4, 200, 5))
                    self.assertEqual(checked['projection_hits'], 0)
                    self.assertEqual(checked['projection_runtime']['ordinary_complete_cache_hits'], 3)
                    self.assertEqual(checked['receipt_disclosures'] > 0, mode == 'disclose')
                    self.assertFalse(checked['receipt_disclosure_contract_failed'])
                    self.assertTrue(checked['disclosure_decisions_reconstructed_from_original_records'])
                    decisions = read(self.records[f'{mode}{rep}']['folder'] /
                                     'receipt_disclosure_sidecar_private.json')['decisions']
                    self.assertEqual(decisions[2]['receipt_rows'], 0)
                    self.assertFalse(decisions[2]['disclosed'])

    def test_rolling_actor_and_focus_requests_use_reconstructed_view_and_one_cost_ledger(self):
        for mode in ('full', 'disclose'):
            checked = self.audit(self.records['rolling_' + mode])
            self.assertGreaterEqual(checked['checkpoint_installations'], 2)
            self.assertGreater(checked['usage_by_role']['focus']['calls'], 0)
            self.assertEqual(checked['model_calls'], sum(v['calls'] for v in checked['usage_by_role'].values()))
            self.assertEqual(checked['known_total_tokens'], sum(v['input_tokens'] + v['output_tokens']
                for v in checked['usage_by_role'].values()))
            if mode == 'disclose':
                self.assertTrue(any(row['role'] == 'focus' and row['disclosed_outer_count'] > 0
                                    for row in checked['receipt_disclosure_paid_input_exposures']))

    def test_terminal_disclosure_never_seen_by_another_paid_request_is_not_gate_activity(self):
        checked = self.audit(self.records['terminal_only'])
        self.assertEqual(checked['model_calls'], 1)
        self.assertGreater(checked['receipt_disclosed_turns'], 0)
        self.assertEqual(checked['receipt_disclosures'], 0)
        self.assertEqual(sum(row['disclosed_outer_count']
            for row in checked['receipt_disclosure_paid_input_exposures']), 0)

    def test_paid_archive_expansion_reconstructs_original_character_page(self):
        checked = self.audit(self.records['archive'])
        self.assertEqual(checked['receipt_read_span_actions'], 1)
        self.assertGreater(checked['receipt_read_span_checks'][0]['returned_characters'], 0)
        self.assertEqual(checked['known_total_tokens'], 200)
        self.assertEqual(checked['api_requests'], 5)

    def test_unknown_usage_and_API_effect_are_retained_without_zero_imputation(self):
        for name in ('unknown_model', 'unknown_api'):
            checked = self.audit(self.records[name])
            self.assertGreater(checked['known_total_tokens'], 0)
            self.assertIsNone(checked['success'])
            self.assertEqual(checked['record_status'], 'unevaluated')
        self.assertEqual(self.audit(self.records['unknown_model'])['unknown_usage_calls'], 1)
        with self.assertRaisesRegex(ValueError, 'evaluation_after_invalid_cell'):
            self.audit(self.records['unknown_api'], evaluated=True)

    def test_ordinary_python_error_keeps_full_display_and_following_work(self):
        checked = self.audit(self.records['ordinary_error'])
        self.assertEqual(checked['model_calls'], 4)
        self.assertFalse(checked['projection_contract_failed'])
        decisions = read(self.records['ordinary_error']['folder'] / 'receipt_disclosure_sidecar_private.json')['decisions']
        self.assertFalse(decisions[1]['eligible'])
        self.assertFalse(decisions[1]['disclosed'])

    def test_known_typed_API_exception_is_charged_kept_full_and_recoverable(self):
        checked = self.audit(self.records['known_api_error'])
        self.assertEqual(checked['model_calls'], 4)
        self.assertFalse(checked['projection_contract_failed'])
        self.assertGreater(checked['invocation_status_counts']['raised'], 0)
        decisions = read(self.records['known_api_error']['folder'] /
                         'receipt_disclosure_sidecar_private.json')['decisions']
        self.assertFalse(decisions[1]['eligible'])
        self.assertFalse(decisions[1]['disclosed'])

    def test_actual_actor_and_focus_request_tampering_cannot_match_sidecar_only(self):
        for role in ('agent', 'focus'):
            with self.subTest(role=role), tempfile.TemporaryDirectory() as temp:
                data = self.copied(temp, 'rolling_disclose')
                usage = read(data['folder'] / 'usage.json')
                call = next(c for c in usage if c['role'] == role)
                path = data['folder'] / call['id'] / 'request.json'
                request = read(path)
                request['messages'][-1]['content'] += 'tampered paid input'
                write(path, request)
                with self.assertRaisesRegex(ValueError, 'actual_rolling_request_differs'):
                    self.trace(data)

    def test_sidecar_decision_is_not_a_trusted_input(self):
        for field, value in (('disclosed_turns', 0), ('normalized_history_sha256', '0' * 64)):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as temp:
                data = self.copied(temp)
                path = data['folder'] / 'receipt_disclosure_sidecar_private.json'
                sidecar = read(path); sidecar[field] = value; write(path, sidecar)
                with self.assertRaisesRegex(ValueError, 'saved_receipt_disclosure_snapshot_differs'):
                    self.trace(data)

    def test_future_snapshot_or_missing_view_is_rejected(self):
        for mutation in ('future', 'missing'):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as temp:
                data = self.copied(temp)
                path = data['folder'] / 'receipt_disclosure_inference_views.json'
                views = read(path)
                if mutation == 'future':
                    views[0]['receipt_snapshot_sha256'] = views[-1]['receipt_snapshot_sha256']
                else:
                    views.pop()
                write(path, views)
                with self.assertRaisesRegex(ValueError, 'receipt_inference_view_not_bound'):
                    self.trace(data)

    def test_raw_archive_order_and_added_tail_cannot_hide_behind_canonical_json(self):
        for mutation in ('order', 'tail'):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as temp:
                data = self.copied(temp)
                path = data['folder'] / 'spans.json'; spans = read(path)
                if mutation == 'order':
                    sid = next(iter(spans)); spans[sid] = dict(reversed(list(spans[sid].items())))
                else:
                    spans['unrecorded'] = {'id': 'unrecorded'}
                write(path, spans)
                with self.assertRaises(ValueError):
                    self.trace(data)

    def test_raw_page_unicode_offsets_future_read_and_tamper(self):
        first = dict(id='s1', action=None, observation={'text': '日本語' * 30})
        fn = {'name': 'read_span', 'arguments': compact({'span_id': 's1', 'offset': 7})}
        page = dict(id='s2', action=fn, observation=page_span({'s1': first}, 's1', 7, 31))
        events = [dict(call='call_001', span_id=sid, stage='model_tool', api_request_sent=False,
                       new_tools=[]) for sid in ('s1', 's2')]
        spans = {'s1': first, 's2': page}
        self.assertEqual(audit_archive_reads(events, spans, 31)[0]['returned_characters'], 31)
        page['observation']['text'] += '!'
        with self.assertRaisesRegex(ValueError, 'raw_archive_character_page_changed'):
            audit_archive_reads(events, spans, 31)
        page['observation'] = page_span({'s1': first}, 's1', 7, 31)
        with self.assertRaisesRegex(ValueError, 'raw_archive_character_page_changed'):
            audit_archive_reads(events[::-1], spans, 31)

    def test_replication_seed_and_mode_must_match_executed_condition(self):
        for field, value in (('replication', True), ('model_seed', 157),
                             ('receipt_disclosure_policy', 'full'), ('phase', 'P127'),
                             ('projection_policy', 'automatic_region_joined_fields')):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as temp:
                data = self.copied(temp); path = data['folder'] / 'summary.json'
                summary = read(path); summary[field] = value; write(path, summary)
                with self.assertRaisesRegex(ValueError, 'executed_P128_condition_changed'):
                    self.audit(data)

    def test_preflight_requires_all_eight_task_seed_rows_and_both_modes(self):
        tasks = [{'task_id': f'synthetic_{i}'} for i in range(4)]
        rows = [dict(replication=rep, model_seed=seed, task_id=item['task_id'], conditions={'full': {}, 'disclose': {}})
                for rep, seed in enumerate((57, 157), 1) for item in tasks]
        self.assertEqual(len(auditor.preflight_conditions(rows, tasks)), 8)
        variants = [rows[:-1], rows[:-1] + [rows[0]], deepcopy(rows), deepcopy(rows)]
        variants[2][0]['model_seed'] = 157
        variants[3][0]['conditions'].pop('disclose')
        for variant in variants:
            with self.assertRaises(ValueError):
                auditor.preflight_conditions(variant, tasks)

    def test_closed_batch_rejects_old_phase_extra_or_duplicate_and_incomplete_complete(self):
        ids = [cell_id(*entry) for entry in run_order()]
        valid = dict(phase='P128', status='complete', completed=ids,
                     rows=[{'run_id': rid} for rid in ids], active=None)
        self.assertEqual(auditor.validate_closed_batch(valid), set(ids))
        for field, value in (('phase', 'P127'), ('completed', ids[:-1]),
                             ('completed', ids + ids[:1]), ('active', ids[0]),
                             ('rows', valid['rows'] + [{'run_id': 'unplanned'}])):
            changed = {**valid, field: value}
            with self.assertRaises(ValueError):
                auditor.validate_closed_batch(changed)

    def test_stopped_batch_keeps_all_sixteen_slots_and_audit_failure_unknown(self):
        import run_whole_task_receipt_disclosure as driver
        with tempfile.TemporaryDirectory() as temp, ExitStack() as stack:
            storage, root = Path(temp) / 'storage', Path(temp) / 'repo'
            tasks = [{'task_id': f'synthetic_{i}'} for i in range(4)]
            pre = {'rows': [dict(replication=rep, model_seed=seed, task_id=item['task_id'],
                    conditions={'full': {}, 'disclose': {}})
                for rep, seed in enumerate((57, 157), 1) for item in tasks]}
            write(root / auditor.PREFLIGHT, pre)
            hashes = {'synthetic.py': '0' * 64}
            write(root / auditor.ACTIVATION, dict(source_hashes=hashes,
                  preflight_sha256=auditor.sha(root / auditor.PREFLIGHT)))
            plan = {'batch_id': 'P128_batch_v01'}
            write(root / auditor.PLAN, plan)
            pipeline = storage / 'records/context_pilot/P128_pipeline_v01'
            write(pipeline / 'status.json', dict(status='stopped', server_stopped=True, server_supervisor_pid=12345))
            write(pipeline / 'server_final.json', dict(status='stopped', pid=12344, supervisor_pid=12345))
            ids = [cell_id(*entry) for entry in run_order()]
            write(storage / 'records/context_pilot/P128_batch_v01/status.json',
                  dict(phase='P128', status='stopped', rows=[], completed=[], active=ids[0]))
            write(storage / 'records/context_pilot' / ids[0] / 'summary.json', {'synthetic': True})
            (storage / 'records/context_pilot' / ids[1]).mkdir()
            stack.enter_context(patch.object(driver, 'sources', return_value=(plan, {}, [], tasks)))
            stack.enter_context(patch.object(driver, 'frozen_hashes', return_value=hashes))
            stack.enter_context(patch.object(auditor.subprocess, 'run',
                return_value=SimpleNamespace(returncode=1, stdout='')))
            stack.enter_context(patch.object(auditor, 'audit_cell', side_effect=ValueError('synthetic_receipt_contract_failure')))
            stack.enter_context(patch('builtins.print'))
            result = auditor.run(storage, root)
            self.assertEqual(len(result['rows']), 16)
            self.assertEqual([r['run_id'] for r in result['rows']], ids)
            self.assertEqual(result['rows'][0]['record_status'], 'audit_error')
            self.assertEqual(result['rows'][1]['record_status'], 'incomplete_worker')
            self.assertTrue(all(r['record_status'] == 'not_run' for r in result['rows'][2:]))
            self.assertTrue(all(r['known_total_tokens'] is None for r in result['rows']))
            self.assertFalse(result['development_gate_met'])
            self.assertEqual(len(result['audit_errors']), 1)
            with self.assertRaises(FileExistsError):
                auditor.run(storage, root)


if __name__ == '__main__':
    unittest.main()
