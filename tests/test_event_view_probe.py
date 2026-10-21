import copy
import datetime as dt
import json
import signal
import sys
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from run_event_view_probe import inference_deadline, lease_remaining, messages_for, schedule, structural_outcome
from run_context_comparison import Inference


class ProbeTests(unittest.TestCase):
    def test_deadline_preserves_unknown_usage_and_stops_without_retry(self):
        config = {'model': {'model': 'test', 'temperature': 1, 'seed': 46,
                            'num_predict': 100, 'num_ctx': 1000, 'call_timeout_seconds': 600},
                  'seed': 46, 'agent_temperature': 1, 'draft_temperature': .7,
                  'max_calls': 2, 'max_wall_seconds': 21600, 'max_output_tokens': 100,
                  'max_total_tokens': 1000}
        old = signal.signal(signal.SIGALRM, inference_deadline)
        try:
            with tempfile.TemporaryDirectory() as directory:
                inference = Inference(config, Path(directory))
                def alarm(*args, **kwargs):
                    signal.raise_signal(signal.SIGALRM)
                with patch('run_context_comparison.count_input', return_value={'input_tokens': 10}), \
                        patch('local_llama.post', side_effect=alarm) as request:
                    with self.assertRaisesRegex(RuntimeError, 'usage unknown'):
                        inference.call('ledger', [{'role': 'user', 'content': 'test'}], [])
                    self.assertEqual(request.call_count, 1)
                usage = json.loads((Path(directory)/'usage.json').read_text())
                response = json.loads((Path(directory)/'call_001/response.json').read_text())
                self.assertIsNone(usage[0]['input_tokens'])
                self.assertIsNone(usage[0]['output_tokens'])
                self.assertEqual(response['error_kind'], 'timeout')
                self.assertEqual(response['timeout_scope'], 'call')
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, old)

    def test_normal_event_inputs_are_identical_across_views(self):
        case = {'task': {'instruction': 'finish'}, 'tools': [],
                'spans': {'s1': {'id': 's1', 'assistant': 'proposed',
                           'action': {'name': 'app__change', 'arguments': '{}'},
                           'observation': {'observation': 'returned'}}},
                'receipts': {'s1': {'span_id': 's1', 'api_request_sent': True, 'effects_unknown': False}}}
        raw = messages_for(case, 'raw', 24000)
        self.assertEqual(raw, messages_for(case, 'quarantine', 24000))
        self.assertEqual(raw, messages_for(case, 'execution_tag', 24000))
        rejected = copy.deepcopy(case)
        rejected['receipts']['s1']['api_request_sent'] = False
        rejected['spans']['s1']['observation'] = {'format_error': 'unknown API parameter'}
        self.assertNotEqual(messages_for(rejected, 'execution_tag', 24000), messages_for(rejected, 'quarantine', 24000))

    def test_structural_warning_is_not_named_semantic_error(self):
        case = {'spans': {'s1': {'id': 's1', 'action': {'name': 'app__change'},
                                  'observation': {'format_error': 'invalid'}}},
                'receipts': {'s1': {'span_id': 's1', 'api_request_sent': False, 'effects_unknown': False}}}
        value = {'items': [{'key': 'checked', 'requirement': 'Inspected rejection',
                           'status': 'done', 'source_ids': ['s1']}], 'constraints': [], 'unresolved': []}
        answer = {'tool_calls': [{'function': {'name': 'submit_ledger', 'arguments': json.dumps(value)}}]}
        result, ledger = structural_outcome(answer, case)
        self.assertEqual(result['done_only_rejected_sources'], 1)
        self.assertNotIn('semantic_error', result)
        self.assertEqual(ledger, value)
        value['items'][0]['source_ids'] = ['future_span']
        answer['tool_calls'][0]['function']['arguments'] = json.dumps(value)
        self.assertFalse(structural_outcome(answer, case)[0]['schema_valid'])

    def test_schedule_identity_and_real_supervisor_lease(self):
        plan = {'run_id': 'P16_01', 'variants': ['raw', 'execution_tag', 'quarantine'],
                'source_runs': ['run1'], 'conditions': ['recorded', 'rejected_before_dispatch'],
                'first_seed': 46, 'max_calls': 6}
        manifest = {'cases': [{'case_id': 'c1', 'source_run': 'run1', 'condition': 'recorded'},
                              {'case_id': 'c2', 'source_run': 'run1', 'condition': 'rejected_before_dispatch'}]}
        rows = schedule(plan, manifest)
        self.assertEqual(len(rows), 6)
        self.assertEqual({row['seed'] for row in rows}, {46})
        with self.assertRaises(ValueError):
            schedule(plan, {'cases': manifest['cases'][::-1]})
        runtime = {'started_at': '2026-10-21T00:00:00+00:00'}
        seconds, _ = lease_remaining(runtime, '/usr/bin/python /tmp/serve_research_model.py --max-seconds 7200',
                                      dt.datetime(2026, 10, 21, 1, tzinfo=dt.timezone.utc))
        self.assertEqual(seconds, 3600)
        with self.assertRaises(ValueError):
            lease_remaining(runtime, '/usr/bin/python unrelated.py --max-seconds 7200', dt.datetime.now(dt.timezone.utc))


if __name__ == '__main__':
    unittest.main()
