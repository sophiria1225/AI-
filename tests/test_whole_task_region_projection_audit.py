"""Closed synthetic P127 records only; no live model/API, Docker, or task data.

The worker fixture executes trusted handwritten programs in its local test
interpreter and substitutes model/API replies. Tamper cases reuse copies of
those records and never rerun saved generated code.
"""
from copy import deepcopy
from contextlib import ExitStack
import hashlib
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
import audit_whole_task_region_projection as auditor
from budget_signal import digest
from joined_public_read_views import JOINED_CONTRACT_ID
from test_public_name_catalog import tool
from test_public_read_views_live_probe import catalog
from test_whole_task_region_projection_worker import fixture
from whole_task_region_projection import initial_conversation
from test_whole_task_region_projection_worker import PROGRAMS
from region_field_projection import plan_region_projection
from test_region_projection_runtime import TrustedRegionSession


ROOT = Path(__file__).resolve().parents[1]
POLICIES = ('explicit_joined_fields', 'automatic_region_joined_fields')


def read(path):
    return json.loads(path.read_text())


def write(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tools():
    return list(catalog().catalog.values()) + [tool('supervisor__complete_task')]


class WholeTaskProjectionAuditTests(unittest.TestCase):
    def setUp(self):
        for name in ('region_projection_runtime.verify_joined_implementation',
                     'demand_joined_read_adapter.verify_joined_implementation'):
            verifier = patch(name, return_value=JOINED_CONTRACT_ID)
            verifier.start()
            self.addCleanup(verifier.stop)

    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temporary.cleanup)
        base = Path(cls.temporary.name)
        cls.records = {}
        for name, policy, options in (
                ('eager', POLICIES[0], {}), ('projection', POLICIES[1], {}),
                ('contract_stop', POLICIES[1], {'contract_failure': True}),
                ('unknown_api', POLICIES[1], {'unknown_api': True}),
                ('unknown_model', POLICIES[1], {'unknown': True}),
                ('ordinary_error', POLICIES[1], {'programs': (PROGRAMS[0], '1/0', PROGRAMS[1], PROGRAMS[-1])}),
                ('explicit_control', POLICIES[0], {'programs': (PROGRAMS[0],
                    "print(read_fields('spotify', 'show_song', ['title'], song_id=10))", PROGRAMS[-1])}),
                ('explicit_automatic', POLICIES[1], {'programs': (PROGRAMS[0],
                    "print(read_fields('spotify', 'show_song', ['title'], song_id=10))", PROGRAMS[-1])})):
            storage = base / name
            storage.mkdir()
            cls.records[name] = fixture(storage, policy, **options)['folder']
        ordinary_run = TrustedRegionSession.run
        def bounded_timeout(session, source, *args, **kwargs):
            if source.endswith('while True:\n    pass\n'):
                kwargs['timeout'] = 0.1
            return ordinary_run(session, source, *args, **kwargs)
        storage = base / 'hard_timeout'
        storage.mkdir()
        with patch.object(TrustedRegionSession, 'run', bounded_timeout):
            cls.records['hard_timeout'] = fixture(storage, POLICIES[1], programs=(
                PROGRAMS[0], PROGRAMS[1] + '\nwhile True:\n    pass\n', PROGRAMS[-1]))['folder']

    def copied(self, destination, name='projection'):
        original = self.records[name]
        folder = Path(destination) / 'records/context_pilot' / original.name
        shutil.copytree(original, folder)
        return folder

    def audited(self, folder):
        return auditor.audit_runtime(folder, read(folder / 'plan.json'), tools())

    def cell_arguments(self, folder):
        config = read(folder / 'plan.json')
        plan = read(folder / 'comparison_plan.json')
        original = read(ROOT / 'configs/P29_stateful_code_v01.json')
        identity = read(folder / 'source_identity.json')
        item = {**identity, 'public_task': read(folder / 'public_task.json')}
        conversation = initial_conversation(original, item['public_task'])
        messages, _ = conversation.for_model(config['observation_page_characters'])
        pre = {'base_messages_sha256': digest(messages)}
        return folder, ROOT, plan, original, item, config['projection_policy'], pre

    def trace_result(self, folder):
        summary = read(folder / 'summary.json')
        return {key: deepcopy(summary[key]) for key in (
            'known_total_tokens', 'unknown_usage_calls', 'model_calls', 'usage_by_role')}

    def synthetic_evaluation(self, folder, success):
        summary = read(folder / 'summary.json')
        dbs = (folder.parents[2] / '.runtime/appworld/r18_probe_01/experiments/outputs'
               / folder.name / 'tasks' / summary['task_id'] / 'dbs')
        dbs.mkdir(parents=True)
        database = dbs / 'handwritten_fixture.db'
        database.write_bytes(b'synthetic test bytes; no task database')
        evaluation = {'execution_summary_sha256': sha(folder / 'summary.json'),
            'evaluation_returned_to_model': False, 'official_success': success,
            'evaluation_script_sha256': sha(ROOT / 'scripts/evaluate_context_trial.py'),
            'frozen_database_hashes': {database.name: sha(database)}}
        write(folder / 'evaluation.json', evaluation)
        return database

    def test_normal_arms_reconcile_independent_cache_lookup_and_receipt_records(self):
        for name, hits, complete in (('eager', 0, 3), ('projection', 4, 1)):
            with self.subTest(name=name):
                folder = self.records[name]
                checked = self.audited(folder)
                self.assertEqual(checked['projection_hits'], hits)
                self.assertFalse(checked['projection_contract_failed'])
                self.assertEqual(checked['projection_runtime']['ordinary_complete_cache_hits'], complete)
                self.assertEqual(checked['compact_receipts'], read(folder / 'summary.json')['compact_receipts'])
                self.assertEqual(len(checked['program_costs']), 4)
                self.assertTrue(checked['runtime_audit_hashes'])

    def test_known_contract_stop_is_a_retained_failure_not_missing_data(self):
        folder = self.records['contract_stop']
        before = (folder / 'summary.json').read_bytes()
        checked = self.audited(folder)
        self.assertTrue(checked['projection_contract_failed'])
        self.assertTrue(checked['projection_runtime']['projection_failed'])
        self.assertEqual(checked['projection_hits'], 2)
        summary = read(folder / 'summary.json')
        self.assertEqual(summary['stop_reason'], 'projection_contract_stopped')
        self.assertEqual(summary['model_calls'], 2)
        self.assertEqual(summary['known_total_tokens'], 100)
        self.assertEqual((summary['unknown_usage_calls'], summary['unknown_effect_requests']), (0, 0))
        self.assertEqual((folder / 'summary.json').read_bytes(), before)

    def test_unknown_model_has_only_its_completed_program_and_no_imputed_cost(self):
        folder = self.records['unknown_model']
        checked = self.audited(folder)
        summary = read(folder / 'summary.json')
        self.assertEqual(checked['projection_hits'], 0)
        self.assertEqual(len(checked['program_costs']), 1)
        self.assertEqual(summary['known_total_tokens'], 50)
        self.assertEqual(summary['unknown_usage_calls'], 1)
        self.assertEqual(summary['model_calls'], 2)

    def test_unknown_api_effect_retains_sent_cost_and_prohibits_evaluation(self):
        folder = self.records['unknown_api']
        checked = self.audited(folder)
        summary = read(folder / 'summary.json')
        self.assertEqual(summary['unknown_effect_requests'], 1)
        self.assertTrue(checked['projection_contract_failed'])
        self.assertEqual(summary['api_requests'], summary['request_budget']['spent'])
        self.assertEqual(sum(r['bridge_request_sent'] for r in summary['api_execution_receipts']),
                         summary['api_requests'])
        with patch.object(auditor, 'audit_trace', return_value=self.trace_result(folder)):
            with self.assertRaisesRegex(ValueError, 'evaluation_after_invalid_cell'):
                auditor.audit_cell(*self.cell_arguments(folder), evaluated=True, tools=tools())

    def test_partial_then_hard_timeout_has_incomplete_trace_and_keeps_known_cost(self):
        folder = self.records['hard_timeout']
        checked = self.audited(folder)
        summary = read(folder / 'summary.json')
        self.assertTrue(checked['projection_contract_failed'])
        self.assertEqual(checked['projection_hits'], 2)
        self.assertFalse(checked['projection_runtime']['execution_trace_accounting_complete'])
        self.assertFalse(checked['projection_runtime']['control_accounting_complete'])
        self.assertTrue(summary['request_budget']['stopped'])
        self.assertEqual(summary['model_calls'], 2)
        self.assertEqual(summary['known_total_tokens'], 100)
        self.assertEqual(summary['unknown_usage_calls'], 0)
        evidence = read(folder / 'programs/call_002_01/projection_program_private.json')
        self.assertEqual(evidence['execution_transform_report'], [])
        self.assertEqual(evidence['result']['contract_stop_reason'],
                         'region_execution_report_missing_after_partial')
        self.assertEqual(evidence['result']['status'], 'harness_error')
        self.assertNotEqual(evidence['result']['underlying_execution_status'], 'ok')

    def test_shared_explicit_fields_do_not_count_as_automatic_projection(self):
        for name in ('explicit_control', 'explicit_automatic'):
            checked = self.audited(self.records[name])
            self.assertEqual(checked['explicit_field_requests'], 1)
            self.assertEqual(checked['explicit_field_partial_hits'], 1)
            self.assertEqual(checked['automatic_region_partial_hits'], 0)
            self.assertEqual(checked['projection_hits'], 0)
            self.assertFalse(checked['projection_contract_failed'])
            self.assertIn('joined_field_events_private.json', checked['runtime_audit_hashes'])

    def test_ordinary_error_report_is_present_and_later_program_can_continue(self):
        folder = self.records['ordinary_error']
        checked = self.audited(folder)
        self.assertEqual(len(checked['program_costs']), 4)
        self.assertFalse(checked['projection_contract_failed'])
        evidence = read(folder / 'programs/call_002_01/projection_program_private.json')
        self.assertEqual(evidence['result']['status'], 'execution_error')
        self.assertEqual(len(evidence['execution_transform_report']), 1)
        self.assertEqual(evidence['execution_transform_report'][0]['execution_status'], 'execution_error')

    def test_segment_selection_and_hit_interval_tampering_is_rejected_independently(self):
        directory = self.records['projection'] / 'programs/call_002_01'
        plan = plan_region_projection(read(directory / 'input_private.json')['code'])
        original = read(directory / 'projection_program_private.json')['execution_transform_report'][0]
        auditor.audit_segment_report(plan, original)
        changes = (
            lambda r: r.update(plan_sha256='0'*64),
            lambda r: r['segments'][0].update(segment_index=False),
            lambda r: r['segments'][0].update(completed=False),
            lambda r: r['segments'][1].update(selected_sha256='0'*64),
            lambda r: r['regions'][0].update(site_index=False),
            lambda r: r['regions'][0].update(hits_before=1, hits_after=3),
            lambda r: r['regions'][0].update(hits_before=False),
            lambda r: r['regions'][0].update(admitted=False),
            lambda r: r.update(hits=3),
        )
        for number, change in enumerate(changes):
            with self.subTest(number=number):
                report = deepcopy(original)
                change(report)
                with self.assertRaises(ValueError):
                    auditor.audit_segment_report(plan, report)

    def test_error_report_can_end_at_incomplete_last_segment_only(self):
        directory = self.records['contract_stop'] / 'programs/call_002_01'
        plan = plan_region_projection(read(directory / 'input_private.json')['code'])
        report = read(directory / 'projection_program_private.json')['execution_transform_report'][0]
        auditor.audit_segment_report(plan, report)
        self.assertEqual(report['execution_status'], 'execution_error')
        self.assertFalse(report['segments'][-1]['completed'])
        self.assertTrue(all(s['completed'] for s in report['segments'][:-1]))
        report['segments'][0]['completed'] = False
        with self.assertRaises(ValueError):
            auditor.audit_segment_report(plan, report)

    def test_real_rolling_trace_and_region_runtime_share_one_audited_cost_ledger(self):
        from fixed_budget_local_llama import payload_for as summary_payload
        from tool_choice_local_llama import payload_for as agent_payload
        from public_display import CODE_TOOLS
        with tempfile.TemporaryDirectory() as temporary:
            data = fixture(Path(temporary), POLICIES[1], checkpoint=True,
                programs=(PROGRAMS[0],) + (PROGRAMS[1],) * 7 + (PROGRAMS[-1],), max_calls=12)
            folder = data['folder']
            # Populate only handwritten synthetic transport evidence. No saved
            # generated source is rerun by this test or by the auditor.
            for ordinal, capture in enumerate(data['captured'], 1):
                call = folder / f'call_{ordinal:03d}'
                agent = capture['role'] == 'agent'
                payload = agent_payload if agent else summary_payload
                write(call / 'request.json', payload(capture['config'], capture['messages'],
                                                    CODE_TOOLS if agent else []))
                response = read(call / 'response.json')
                usage = dict(prompt_tokens=response['input_tokens'], completion_tokens=response['output_tokens'],
                    total_tokens=response['input_tokens'] + response['output_tokens'],
                    prompt_tokens_details={'cached_tokens': response['cached_input_tokens']})
                response['usage_details'] = usage
                write(call / 'response.json', response)
                write(call / 'raw_response.json', dict(usage=usage, timings=response['timings'],
                    choices=[dict(message=response['message'], finish_reason=response['done_reason'])]))
            config, plan = read(folder / 'plan.json'), read(folder / 'comparison_plan.json')
            item = {**read(folder / 'source_identity.json'), 'public_task': data['public']}
            conversation = initial_conversation(data['original'], data['public'])
            initial, _ = conversation.for_model(config['observation_page_characters'])
            row = auditor.audit_cell(folder, ROOT, plan, data['original'], item, POLICIES[1],
                {'base_messages_sha256': digest(initial)}, False, tools=tools())
            self.assertGreaterEqual(row['checkpoint_installations'], 2)
            self.assertEqual(row['known_total_tokens'], data['result']['known_total_tokens'])
            self.assertEqual(row['usage_by_role'], data['result']['usage_by_role'])
            self.assertEqual(row['projection_hits'], data['result']['projection_runtime']['automatic_region_partial_hits'])
            self.assertGreater(row['usage_by_role']['focus']['calls'], 0)
            self.assertEqual(row['record_status'], 'unevaluated')
            self.assertIsNone(row['success'])

    def test_source_and_execution_evidence_hash_tamper_are_rejected(self):
        for kind in ('submitted_source', 'execution_evidence', 'model_response'):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as temporary:
                folder = self.copied(temporary)
                program = folder / 'programs/call_002_01'
                if kind == 'submitted_source':
                    path = program / 'input_private.json'
                    value = read(path)
                    value['code'] += '\n# synthetic unauthorized source change\n'
                elif kind == 'execution_evidence':
                    path = program / 'projection_program_private.json'
                    value = read(path)
                    value['control_request_bytes'] += 1
                else:
                    path = folder / 'call_002/response.json'
                    value = read(path)
                    function = value['message']['tool_calls'][0]['function']
                    arguments = json.loads(function['arguments'])
                    arguments['code'] += '\n# synthetic changed model-origin code\n'
                    function['arguments'] = json.dumps(arguments)
                write(path, value)
                expected = 'executed_tool_differs_from_model_response' if kind == 'model_response' else ''
                with self.assertRaisesRegex(ValueError, expected):
                    self.audited(folder)

    def test_duplicate_dispatch_nonce_is_rejected_even_with_matching_summary_receipts(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = self.copied(temporary)
            events = read(folder / 'events.json')
            sent = [event['api_execution'] for event in events if event['api_request_sent']]
            self.assertGreaterEqual(len(sent), 2)
            self.assertNotEqual(sent[0]['nonce'], sent[1]['nonce'])
            sent[1]['nonce'] = sent[0]['nonce']
            write(folder / 'events.json', events)
            summary = read(folder / 'summary.json')
            summary['api_execution_receipts'][1]['nonce'] = sent[0]['nonce']
            write(folder / 'summary.json', summary)
            with self.assertRaisesRegex(ValueError, 'missing_or_reused_invocation_nonce'):
                self.audited(folder)

    def test_cache_lookup_and_shared_budget_tamper_are_rejected(self):
        for name, change in (
                ('ordinary_cache_events_private.json', lambda rows: rows.pop()),
                ('projection_lookup_events_private.json',
                 lambda rows: next(row for row in rows if row['kind'] == 'partial').update(kind='miss')),
                ('request_budget_events_private.json',
                 lambda rows: rows.remove(next(row for row in rows if row['kind'] == 'sent'))),
                ('joined_field_events_private.json', lambda rows: rows.pop())):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temporary:
                folder = self.copied(temporary)
                path = folder / name
                value = read(path)
                change(value)
                write(path, value)
                with self.assertRaises(ValueError):
                    self.audited(folder)

    def test_compact_receipt_sent_flag_cannot_hide_an_actual_dispatch(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = self.copied(temporary)
            path = folder / 'spans.json'
            value = read(path)
            observation = next(span['observation'] for span in value.values()
                if span['action'] and span['action'].get('name') == 'run_python'
                and span['observation'].get('api_receipts', {}).get('rows'))
            observation['api_receipts']['rows'][0][2] = False
            write(path, value)
            with self.assertRaises(ValueError):
                self.audited(folder)

    def test_missing_program_evidence_and_invented_partial_savings_are_rejected(self):
        for kind in ('missing_program', 'inflated_hits'):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as temporary:
                folder = self.copied(temporary)
                if kind == 'missing_program':
                    (folder / 'programs/call_002_01/projection_program_private.json').unlink()
                else:
                    path = folder / 'summary.json'
                    value = read(path)
                    value['projection_runtime']['projection_partial_hits'] += 1
                    write(path, value)
                with self.assertRaises(ValueError):
                    self.audited(folder)

    def test_unknown_cell_remains_unevaluated_without_imputed_success_or_usage(self):
        folder = self.records['unknown_model']
        with patch.object(auditor, 'audit_trace', return_value=self.trace_result(folder)) as trace:
            row = auditor.audit_cell(*self.cell_arguments(folder), evaluated=False, tools=tools())
        trace.assert_called_once()
        self.assertEqual(row['record_status'], 'unevaluated')
        self.assertIsNone(row['success'])
        self.assertEqual(row['known_total_tokens'], 50)
        self.assertEqual(row['unknown_usage_calls'], 1)
        self.assertEqual(row['projection_hits'], 0)
        self.assertIsNone(row['evaluation_sha256'])

    def test_contract_stop_keeps_synthetic_official_success_and_known_cost(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = self.copied(temporary, 'contract_stop')
            self.synthetic_evaluation(folder, True)
            with patch.object(auditor, 'audit_trace', return_value=self.trace_result(folder)):
                row = auditor.audit_cell(*self.cell_arguments(folder), evaluated=True, tools=tools())
            self.assertEqual(row['record_status'], 'evaluated')
            self.assertTrue(row['success'])
            self.assertTrue(row['projection_contract_failed'])
            self.assertEqual(row['stop_reason'], 'projection_contract_stopped')
            self.assertEqual(row['known_total_tokens'], 100)
            self.assertEqual(row['unknown_usage_calls'], 0)

    def test_success_cannot_bypass_evaluation_source_database_or_model_separation(self):
        for kind in ('summary_binding', 'database_hash', 'evaluation_leaked'):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as temporary:
                folder = self.copied(temporary)
                database = self.synthetic_evaluation(folder, True)
                if kind == 'database_hash':
                    database.write_bytes(b'different synthetic bytes after evaluation')
                else:
                    path = folder / 'evaluation.json'
                    value = read(path)
                    if kind == 'summary_binding':
                        value['execution_summary_sha256'] = '0' * 64
                    else:
                        value['evaluation_returned_to_model'] = True
                    write(path, value)
                with patch.object(auditor, 'audit_trace', return_value=self.trace_result(folder)):
                    with self.assertRaises(ValueError):
                        auditor.audit_cell(*self.cell_arguments(folder), evaluated=True, tools=tools())


class ProjectionCohortAuditTests(unittest.TestCase):
    """Exercise run() against in-memory records and temporary presence markers.

    All source discovery, file reads/hashes, process probes, cell audits and
    output writes are patched. Neither predecessor nor experiment data is read.
    """
    def cohort(self, temporary, *, statuses=None, row_change=None, closed=True, active_index=None):
        storage, root = Path(temporary) / 'storage', Path(temporary) / 'repo'
        root.mkdir()
        order = auditor.run_order()
        statuses = ['evaluated'] * 8 if statuses is None else statuses
        prepared = [{'task_id': f'synthetic-task-{i}'} for i in range(1, 5)]
        plan = {'batch_id': 'synthetic_P127_batch'}
        frozen = {'scripts/only_a_synthetic_source.py': 'f' * 64}
        pipeline_dir = storage / 'records/context_pilot/P127_pipeline_v01'
        pipeline = {'status': 'complete' if closed else 'running',
                    'server_stopped': closed, 'server_supervisor_pid': 10002}
        server = {'status': 'stopped' if closed else 'running', 'pid': 10001,
                  'supervisor_pid': 10002}
        pre = {'rows': [{'conditions': {policy: {} for policy in POLICIES}} for _ in range(4)]}
        fake_sha = lambda path: hashlib.sha256(str(Path(path)).encode()).hexdigest()
        reads = {
            pipeline_dir / 'status.json': pipeline,
            pipeline_dir / 'server_final.json': server,
            root / auditor.ACTIVATION: {'source_hashes': frozen,
                                      'preflight_sha256': fake_sha(root / auditor.PREFLIGHT)},
            root / auditor.PREFLIGHT: pre,
        }
        public_rows, completed = {}, []
        for index, ((number, policy), status) in enumerate(zip(order, statuses)):
            rid = auditor.cell_id(number, policy)
            folder = storage / 'records/context_pilot' / rid
            if status != 'not_run':
                folder.mkdir(parents=True)
                if status != 'incomplete_worker':
                    (folder / 'summary.json').touch()
                    reads[folder / 'summary.json'] = {'phase': 'P127'}
            if status in ('evaluated', 'audit_error'):
                completed.append(rid)
            row = {'run_id': rid, 'task_id': prepared[number - 1]['task_id'],
                'time_visibility': 'not_exposed', 'checkpoint_policy': 'rolling_separate',
                'projection_policy': policy, 'record_status': status,
                'success': True if status == 'evaluated' else None,
                'known_total_tokens': (100 if policy == POLICIES[0] else 90),
                'unknown_usage_calls': 0, 'projection_hits': int(policy == POLICIES[1]),
                'projection_contract_failed': False, 'stop_reason': 'agent_declared_complete'}
            if status == 'unevaluated':
                row.update(known_total_tokens=50, unknown_usage_calls=1,
                           stop_reason='model_usage_unknown', projection_hits=0)
            if row_change is not None:
                row_change(index, row)
            public_rows[rid] = row
        reads[storage / 'records/context_pilot' / plan['batch_id'] / 'status.json'] = {
            'status': 'complete' if all(s == 'evaluated' for s in statuses) else 'stopped',
            'completed': completed,
            'active': auditor.cell_id(*order[active_index]) if active_index is not None else None}

        def read_only_synthetic(path):
            path = Path(path)
            if path not in reads:
                raise AssertionError('unexpected read outside synthetic record map')
            return deepcopy(reads[path])

        def audit_only_synthetic(folder, passed_root, passed_plan, original, item,
                                 policy, preflight, evaluated, *, tools=None):
            self.assertEqual(passed_root, root)
            self.assertEqual(passed_plan, plan)
            self.assertEqual(original, {})
            self.assertEqual(tools, [])
            self.assertEqual(policy, public_rows[folder.name]['projection_policy'])
            self.assertEqual(evaluated, folder.name in completed)
            if public_rows[folder.name]['record_status'] == 'audit_error':
                raise ValueError('synthetic evidence mismatch')
            return deepcopy(public_rows[folder.name])

        stack = ExitStack()
        self.addCleanup(stack.close)
        mocked = {
            'sources': stack.enter_context(patch.object(auditor, 'sources',
                return_value=(plan, {}, [], prepared))),
            'frozen': stack.enter_context(patch.object(auditor, 'frozen_hashes', return_value=frozen)),
            'read': stack.enter_context(patch.object(auditor, 'read', side_effect=read_only_synthetic)),
            'sha': stack.enter_context(patch.object(auditor, 'sha', side_effect=fake_sha)),
            'ps': stack.enter_context(patch.object(auditor.subprocess, 'run',
                return_value=SimpleNamespace(returncode=1, stdout=''))),
            'cell': stack.enter_context(patch.object(auditor, 'audit_cell', side_effect=audit_only_synthetic)),
            'write': stack.enter_context(patch.object(auditor, 'write_json')),
        }
        stack.enter_context(patch('builtins.print'))
        return storage, root, order, mocked, stack

    def test_all_eight_slots_preserve_missing_states_and_known_contract_stop(self):
        statuses = ['evaluated', 'evaluated', 'unevaluated', 'not_run',
                    'incomplete_worker', 'audit_error', 'evaluated', 'evaluated']
        def change(index, row):
            if index == 1:
                row.update(projection_contract_failed=True, stop_reason='projection_contract_stopped',
                           known_total_tokens=50)
        with tempfile.TemporaryDirectory() as temporary:
            storage, root, order, mocked, stack = self.cohort(temporary, statuses=statuses, row_change=change)
            with stack:
                result = auditor.run(storage, root)
                mocked['sources'].assert_called_once_with(storage, root)
                self.assertEqual(mocked['ps'].call_count, 2)
                mocked['write'].assert_called_once_with(root / 'reports/P127_comparison.json', result)
        self.assertEqual([row['run_id'] for row in result['rows']],
                         [auditor.cell_id(number, policy) for number, policy in order])
        self.assertEqual([row['record_status'] for row in result['rows']], statuses)
        self.assertEqual(len(result['rows']), 8)
        for index in (3, 4, 5):
            for field in ('success', 'known_total_tokens', 'unknown_usage_calls',
                          'projection_hits', 'projection_contract_failed'):
                self.assertIsNone(result['rows'][index][field], (index, field))
        self.assertIsNone(result['rows'][2]['success'])
        self.assertEqual(result['rows'][2]['known_total_tokens'], 50)
        self.assertEqual(result['rows'][2]['unknown_usage_calls'], 1)
        stopped = result['rows'][1]
        self.assertTrue(stopped['success'])
        self.assertTrue(stopped['projection_contract_failed'])
        self.assertEqual(stopped['known_total_tokens'], 50)
        self.assertEqual(stopped['stop_reason'], 'projection_contract_stopped')
        self.assertEqual(len(result['audit_errors']), 1)
        self.assertEqual(result['audit_errors'][0]['run_id'], result['rows'][5]['run_id'])
        self.assertFalse(result['all_eight_complete_with_known_usage'])
        self.assertFalse(result['development_gate_met'])

    def test_unclosed_pipeline_prevents_source_discovery_and_process_checks(self):
        with tempfile.TemporaryDirectory() as temporary:
            storage, root, _, mocked, stack = self.cohort(temporary, closed=False)
            with stack:
                with self.assertRaisesRegex(ValueError, 'pipeline_must_be_closed'):
                    auditor.run(storage, root)
                mocked['sources'].assert_not_called()
                mocked['frozen'].assert_not_called()
                mocked['ps'].assert_not_called()
                mocked['cell'].assert_not_called()
                mocked['write'].assert_not_called()

    def test_active_worker_without_trial_directory_is_incomplete_with_unknown_cost(self):
        from inspect_whole_task_region_projection_session import cell_time_totals
        with tempfile.TemporaryDirectory() as temporary:
            storage, root, order, mocked, stack = self.cohort(
                temporary, statuses=['not_run'] * 8, active_index=0)
            self.assertFalse((storage / 'records/context_pilot' / auditor.cell_id(*order[0])).exists())
            with stack:
                result = auditor.run(storage, root)
                mocked['cell'].assert_not_called()
        self.assertEqual(result['rows'][0]['record_status'], 'incomplete_worker')
        self.assertTrue(all(row['record_status'] == 'not_run' for row in result['rows'][1:]))
        for key in ('success', 'known_total_tokens', 'unknown_usage_calls',
                    'projection_hits', 'projection_contract_failed'):
            self.assertIsNone(result['rows'][0][key])
        timing = cell_time_totals(result['rows'])
        self.assertEqual(timing['unknown_cell_full_wall_count'], 1)
        self.assertIsNone(timing['cell_full_wall_seconds'])
        self.assertFalse(result['development_gate_met'])

    def test_cohort_gate_requires_explicit_intact_contracts_and_rejects_cheap_failures(self):
        for mode in ('intact', 'missing_flag', 'contract_stop', 'cheap_failures'):
            def change(index, row):
                if mode == 'missing_flag' and index == 1:
                    row.pop('projection_contract_failed')
                elif mode == 'contract_stop' and index == 1:
                    row.update(projection_contract_failed=True, stop_reason='projection_contract_stopped')
                elif mode == 'cheap_failures' and row['projection_policy'] == POLICIES[1]:
                    row.update(success=False, known_total_tokens=1)
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as temporary:
                storage, root, _, _, stack = self.cohort(temporary, row_change=change)
                with stack:
                    result = auditor.run(storage, root)
                self.assertEqual(len(result['rows']), 8)
                self.assertEqual(result['audit_errors'], [])
                self.assertEqual(result['development_gate_met'], mode == 'intact')
                if mode == 'missing_flag':
                    self.assertFalse(result['mechanism_contracts_intact'])
                    self.assertIsNone(result['projection_contract_failure_cells'])
                elif mode == 'contract_stop':
                    self.assertEqual(result['paired_successful_tasks'], 4)
                    self.assertEqual(result['projection_contract_failure_cells'], 1)
                    self.assertTrue(result['rows'][1]['success'])
                elif mode == 'cheap_failures':
                    self.assertLess(result['automatic_region_joined_fields_minus_explicit_joined_fields_whole_task_tokens'], 0)
                    self.assertEqual(result['paired_success_losses'], 4)


if __name__ == '__main__':
    unittest.main()
