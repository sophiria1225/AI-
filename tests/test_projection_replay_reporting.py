"""Synthetic closed-record publication tests; no replay, models, or APIs."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from build_projection_replay_report import build_report, CHECKS, POLICIES


def put(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fixture(base):
    root = base / 'replay'
    root.mkdir()
    manifest = {'phase': 'P124', 'kind': 'fixed_saved_response_prefix_replay',
        'policies': list(POLICIES), 'programs': [str(i) for i in range(10)],
        'total_generated_programs': 20, 'total_seconds': 600, 'program_seconds': 30,
        'private_files': {'PRIVATE_VALUE_SENTINEL': 'a' * 64},
        'schema_files': {'schema': 'b' * 64}, 'implementation_files': {'source': 'c' * 64},
        'environment_API_requests': 0, 'model_calls': 0, 'tokenizer_calls': 0, 'evaluator_calls': 0}
    manifest_path = base / 'manifest.json'
    digest = put(manifest_path, manifest)
    put(root / 'input_manifest_private.json', manifest)
    rows = []
    for policy in POLICIES:
        session_rows = []
        for i, logical in enumerate((3, 7, 1, 4, 2, 1, 1, 1, 12, 48), 1):
            partial = 11 if policy == POLICIES[1] and i in (9, 10) else 0
            ordinary = (12 if policy == POLICIES[0] else 1) if i == 10 else 0
            row = {'policy': policy, 'program_number': i,
                'checks': {k: True for k in CHECKS}, 'logical_requests': logical,
                'saved_backend_responses': logical - partial - ordinary,
                'ordinary_complete_cache_hits': ordinary, 'projection_hits': partial,
                'boundary_sha256': 'd' * 64, 'stdout_sha256': 'e' * 64, 'error_sha256': 'f' * 64,
                'control_requests': logical + 2, 'control_request_bytes': 100,
                'control_reply_bytes': 200, 'snapshot_controls': 1, 'wall_seconds': .01,
                'private_namespace': 'PRIVATE_VALUE_SENTINEL'}
            if policy == POLICIES[1]:
                row['checks'].update(paired_boundary=True, paired_stdout_error=True)
            rows.append(row)
            session_rows.append({'program_index': i, 'status': 'ok', 'session_usable': True,
                                 'api_requests': row['saved_backend_responses'], 'wall_seconds': .009})
        put(root / policy / 'session/session_private.json', {'status': 'closed',
            'container_removed': True, 'oom_killed': False, 'container_exit_code': 0,
            'projection_policy': policy, 'controls': {'network_none': True},
            'trusted_bootstrap_sha256': '1' * 64, 'cleanup_wall_seconds': .02,
            'programs': session_rows, 'namespace_scope': 'PRIVATE_VALUE_SENTINEL'})
    summary = {'phase': 'P124', 'kind': 'fixed_saved_response_prefix_replay',
        'all_20_programs_match': True, 'implementation_unchanged_at_end': True,
        'attempted_generated_programs': 20, 'completed_generated_programs': 20,
        'compared_generated_programs': 20, 'programs': rows, 'wall_seconds': 1,
        'input_manifest_sha256': digest, 'environment_API_requests': 0, 'model_calls': 0,
        'tokenizer_calls': 0, 'evaluator_calls': 0, 'live_environment_counterfactual_proved': False,
        'task_quality_or_total_token_savings_established': False,
        'private_result_api_requests_meaning': 'simulated_saved_backend_responses_only',
        'private_prompt': 'PRIVATE_VALUE_SENTINEL'}
    summary_hash = put(root / 'summary.json', summary)
    start_path, end_path, preparation_path = (base / f'{name}.json' for name in ('start', 'end', 'prepare'))
    put(start_path, {'source_head': '2' * 40, 'wrapper_sha256': '3' * 64,
        'manifest_sha256': digest, 'maximum_generated_programs': 20, 'maximum_seconds': 600,
        'started_at': '2026-10-26T00:00:00+00:00', 'ci': [
            {'event': event, 'head_sha': '2' * 40, 'status': 'completed', 'conclusion': 'success'}
            for event in ('push', 'pull_request')]})
    put(end_path, {'source_head': '2' * 40, 'status': 'complete', 'all_20_programs_match': True,
                   'summary_sha256': summary_hash, 'finished_at': '2026-10-26T00:00:02+00:00'})
    put(preparation_path, {'command_kind': 'prepare-only', 'status': 'failed',
        'manifest_created': False, 'historical_records_changed': False, 'source_head': '4' * 40,
        'generated_programs': 0, 'model_calls': 0, 'environment_API_requests': 0})
    return root, start_path, end_path, manifest_path, preparation_path


def change_summary(args, mutate):
    path = args[0] / 'summary.json'
    value = json.loads(path.read_text())
    mutate(value)
    digest = put(path, value)
    end = json.loads(args[2].read_text())
    end['summary_sha256'] = digest
    put(args[2], end)


class ProjectionReplayReportingTests(unittest.TestCase):
    def test_net_reduction_and_public_allowlist_preserve_scope(self):
        with tempfile.TemporaryDirectory() as directory:
            result = build_report(*fixture(Path(directory)))
        self.assertEqual(result['arms'][POLICIES[0]]['saved_backend_responses'], 68)
        self.assertEqual(result['arms'][POLICIES[1]]['saved_backend_responses'], 57)
        self.assertEqual(result['arms'][POLICIES[1]]['projection_hits'], 22)
        self.assertEqual(result['saved_backend_response_reduction']['net_count'], 11)
        self.assertAlmostEqual(result['saved_backend_response_reduction']['percent'], 100 * 11 / 68)
        self.assertEqual(result['paired_boundaries_matched'], 10)
        self.assertEqual(len(result['source_sha256']), 8)
        self.assertNotIn('PRIVATE_VALUE_SENTINEL', json.dumps(result))
        self.assertFalse(result['task_quality_or_total_token_savings_established'])
        self.assertEqual(result['earlier_preparation_failure']['count'], 1)
        self.assertEqual(result['replay_execution_count'], 1)

    def test_binding_tamper_is_not_accepted(self):
        with tempfile.TemporaryDirectory() as directory:
            args = fixture(Path(directory))
            value = json.loads((args[0] / 'summary.json').read_text())
            value['wall_seconds'] = 2
            put(args[0] / 'summary.json', value)
            with self.assertRaisesRegex(ValueError, 'hash_binding'):
                build_report(*args)

    def test_asserted_match_cannot_hide_boundary_or_action_mismatch(self):
        for field, replacement, expected in (
                ('boundary_sha256', '0' * 64, 'paired_boundary'),
                ('projection_hits', 23, 'conservation'),
                ('checks', {k: False for k in CHECKS}, 'observable_checks')):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as directory:
                args = fixture(Path(directory))
                change_summary(args, lambda s: s['programs'][-1].update({field: replacement}))
                with self.assertRaisesRegex(ValueError, expected):
                    build_report(*args)

    def test_missing_program_or_unclosed_session_is_not_success(self):
        with tempfile.TemporaryDirectory() as directory:
            args = fixture(Path(directory))
            change_summary(args, lambda s: s['programs'].pop())
            with self.assertRaisesRegex(ValueError, 'all_program_rows'):
                build_report(*args)
        with tempfile.TemporaryDirectory() as directory:
            args = fixture(Path(directory))
            path = args[0] / POLICIES[1] / 'session/session_private.json'
            value = json.loads(path.read_text())
            value['container_removed'] = False
            put(path, value)
            with self.assertRaisesRegex(ValueError, 'clean_closed'):
                build_report(*args)

    def test_nonzero_work_or_live_quality_claim_is_rejected(self):
        for key, value in (('model_calls', 1), ('environment_API_requests', 1),
                           ('task_quality_or_total_token_savings_established', True)):
            with self.subTest(key=key), tempfile.TemporaryDirectory() as directory:
                args = fixture(Path(directory))
                change_summary(args, lambda s: s.update({key: value}))
                with self.assertRaises(ValueError):
                    build_report(*args)


if __name__ == '__main__':
    unittest.main()
