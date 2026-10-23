import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from audit_fallback_output import audit
from fallback_output_replay import CASES, COUNTS, digest, equality_summary, output_fingerprints, schedule
from inference_cache_control import cache_measurement
from local_llama import parse_response
from run_context_comparison import write_json
from run_handoff_factors import sha


def fixture(base, unknown=False, bad_total=False):
    root, storage = base / 'repo', base / 'storage'
    (root / 'reports').mkdir(parents=True)
    pipeline = storage / 'records/context_pilot/P84_pipeline_v01'
    batch_dir = storage / 'records/context_pilot/P84_fallback_output_v01'
    server_dir = storage / 'server'
    for path in (pipeline, batch_dir, server_dir):
        path.mkdir(parents=True)
    requests = {case: {'messages': [{'role': 'user', 'content': case}], 'cache_prompt': False}
                for case in CASES}
    cases = [dict(id=case, expected_input_tokens=count, source_request_sha256=digest(requests[case]))
             for case, count in zip(CASES, COUNTS)]
    plan = dict(batch_id='P84_fallback_output_v01', cases=cases, max_output_tokens=4096)
    server = dict(status='stopped', stop_reason='test', started_at='synthetic', wall_seconds=20,
        load_wall_seconds=1, sampled_peak_rss_bytes=10, peak_system_swap_bytes=0, exit_code=0,
        model_revision='synthetic', runtime={}, ctx_size=65536, cache_type_k='q8_0',
        cache_type_v='q8_0', memory_note='synthetic', pid=999998, supervisor_pid=999997,
        record_directory=str(server_dir))
    write_json(server_dir / 'summary.json', server)
    (server_dir / 'memory.jsonl').write_text(json.dumps({'swap_used_bytes': 0}) + '\n')
    write_json(pipeline / 'server_final.json', server)
    write_json(pipeline / 'status.json', dict(status='stopped' if unknown else 'complete',
        server_stopped=True, server_supervisor_pid=999997, wall_seconds=20, stages=[]))
    write_json(root / 'reports/P84_initial_checks.json', {'source_sha256': {'synthetic': 'hash'}})
    values = dict(zip(CASES, ('A', 'B', 'C', 'C', 'A', 'D')))
    rows, total = [], 0
    for i, item in enumerate(schedule()):
        call = batch_dir / item['id']; call.mkdir()
        payload = requests[item['case']]
        write_json(call / 'request.json', payload)
        row = {**item, 'status': 'error', 'input_tokens': None, 'output_tokens': None,
               'payload_sha256': digest(payload), 'request_sha256': sha(call / 'request.json'),
               **output_fingerprints({'status': 'error'})}
        if unknown and i == 17:
            response = dict(status='error', input_tokens=None, output_tokens=None, wall_seconds=.1)
        else:
            count = COUNTS[CASES.index(item['case'])]
            raw = dict(choices=[{'finish_reason': 'stop', 'message': {'role': 'assistant', 'content': values[item['case']]}}],
                usage={'prompt_tokens': count, 'completion_tokens': 4, 'total_tokens': count+4,
                       'prompt_tokens_details': {'cached_tokens': 0}},
                timings={'cache_n': 0, 'prompt_n': count, 'predicted_n': 4, 'prompt_ms': 10, 'predicted_ms': 20})
            write_json(call / 'raw_response.json', raw)
            response = {**parse_response(raw), 'wall_seconds': .1}
            row.update({k: response[k] for k in ('status', 'input_tokens', 'output_tokens', 'done_reason')})
            row.update(output_fingerprints(response))
            row['cache'] = cache_measurement('cold_1', response, count)
            row['idle'] = {'one_slot_idle': True}
            total += count+4
        write_json(call / 'response.json', response)
        row['response_sha256'] = sha(call / 'response.json'); rows.append(row)
    write_json(batch_dir / 'status.json', dict(status='stopped' if unknown else 'complete', rows=rows,
        known_total_tokens=total + int(bad_total), unknown_usage_calls=int(unknown), model_calls_attempted=18,
        environment_api_requests=0, generated_programs_executed=0, evaluations=0, reserved_scenarios_read=0,
        equality_summary=equality_summary(rows)))
    return root, storage, plan, requests, total


class FallbackOutputAuditTests(unittest.TestCase):
    def check(self, unknown=False, bad_total=False):
        with tempfile.TemporaryDirectory() as temp:
            root, storage, plan, requests, total = fixture(Path(temp), unknown, bad_total)
            with patch('audit_fallback_output.sources', return_value=(plan, {}, requests)), \
                 patch('audit_fallback_output.frozen_hashes', return_value={'synthetic': 'hash'}), \
                 patch('audit_fallback_output.subprocess.run') as process, \
                 contextlib.redirect_stdout(io.StringIO()):
                process.return_value.returncode = 1; process.return_value.stdout = ''
                result = audit(storage, root)
            self.assertEqual(len(result['rows']), 18)
            self.assertEqual(result['known_total_tokens'], total)
            return result

    def test_complete_source_bound_accounting_and_all_output_controls(self):
        result = self.check()
        self.assertTrue(result['all_eighteen_audited'])
        self.assertTrue(result['diagnostic_usable'])
        self.assertTrue(result['local_public_output_difference_identified'])
        self.assertEqual(result['known_total_tokens'], 408015)
        self.assertFalse(result['task_quality_or_savings_measured'])

    def test_retains_unknown_terminal_attempt_in_complete_planned_table(self):
        result = self.check(unknown=True)
        self.assertEqual(result['unknown_usage_calls'], 1)
        self.assertEqual(result['rows'][-1]['record_status'], 'unknown_usage')
        self.assertIsNone(result['rows'][-1]['output_tokens'])
        self.assertFalse(result['all_eighteen_audited'])
        self.assertIsNone(result['local_public_output_difference_identified'])

    def test_matching_output_pattern_cannot_override_accounting_audit_failure(self):
        result = self.check(bad_total=True)
        self.assertIn('batch_known_total_mismatch', result['audit_errors'])
        self.assertTrue(result['equality_summary']['original_fallback_ID_pair_public_outputs_differ'])
        self.assertFalse(result['diagnostic_usable'])
        self.assertIsNone(result['local_public_output_difference_identified'])


if __name__ == '__main__':
    unittest.main()
