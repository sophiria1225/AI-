"""Independent corruption controls for the research result auditor."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from audit_p2 import audit_run


class FrozenRunAudit(unittest.TestCase):
    def setUp(self):
        (ROOT / '.runtime').mkdir(exist_ok=True)
        self.directory = tempfile.TemporaryDirectory(prefix='audit_fixture_', dir=ROOT / '.runtime')
        self.addCleanup(self.directory.cleanup)
        self.run = Path(self.directory.name)
        self.call = self.run / 'call_001_single'
        self.call.mkdir()
        self.config = dict(instance_id='fixture', model='fixture-model', temperature=1.0,
                           top_p=0.95, top_k=0, min_p=0.0, repeat_penalty=1.0, seed=7,
                           thinking_mode='enabled', num_predict=64, num_ctx=512,
                           max_total_tokens=1000, max_calls=4)
        self.write(self.run / 'config.json', self.config)
        (self.run / 'fixture.py').write_text('fixture = True\n')
        (self.run / 'final.patch').write_text('fixture artifact\n')
        digest = hashlib.sha256((self.run / 'final.patch').read_bytes()).hexdigest()
        self.summary = {'calls': [{'path': self.call.name, 'input_tokens': 100, 'output_tokens': 10,
                                  'precall_input_bound': 100, 'done_reason': 'stop'}],
                        'tools': [], 'total_recorded_tokens': 110, 'usage_complete': True,
                        'source_hashes': {'fixture.py': hashlib.sha256((self.run / 'fixture.py').read_bytes()).hexdigest()},
                        'artifact_frozen_at': '2026-10-20T00:00:00Z', 'artifact_sha256': digest,
                        'artifact_bytes': 17, 'stop_reason': 'submitted', 'wall_seconds': 1}
        self.write(self.run / 'summary.json', self.summary)
        self.write(self.run / 'final_evaluation_summary.json', {'artifact_sha256': digest, 'resolved': False})
        self.write(self.call / 'response.json', {'status': 'ok', 'input_tokens': 100, 'output_tokens': 10})
        self.write(self.call / 'raw_response.json', {'usage': {'prompt_tokens': 100, 'completion_tokens': 10,
                   'total_tokens': 110, 'prompt_tokens_details': {'cached_tokens': 90}},
                   'choices': [{'finish_reason': 'stop'}]})
        self.write(self.call / 'preflight.json', {'input_tokens': 100})
        self.request = {k: self.config[k] for k in ['model','temperature','top_p','top_k','min_p','repeat_penalty','seed']}
        self.request.update(max_tokens=64, chat_template_kwargs={'thinking_mode': 'enabled'})
        self.write(self.call / 'request.json', self.request)

    def write(self, path, value):
        path.write_text(json.dumps(value))

    def test_valid_measurement_can_have_failed_task(self):
        result = audit_run(self.run)
        self.assertEqual(result['errors'], [])
        self.assertEqual(result['known_total_tokens'], 110)
        self.assertEqual(result['cached_input_tokens'], 90)
        self.assertFalse(result['evaluation']['resolved'])

    def test_changed_final_artifact_is_detected(self):
        (self.run / 'final.patch').write_text('changed after evaluation\n')
        self.assertIn('frozen artifact hash mismatch', audit_run(self.run)['errors'])

    def test_changed_thinking_setting_is_detected(self):
        self.request['chat_template_kwargs']['thinking_mode'] = 'disabled'
        self.write(self.call / 'request.json', self.request)
        self.assertTrue(any('thinking setting differs' in e for e in audit_run(self.run)['errors']))

    def test_matching_summaries_cannot_override_raw_usage(self):
        self.summary['calls'][0]['output_tokens'] = 9
        self.summary['total_recorded_tokens'] = 109
        self.write(self.run / 'summary.json', self.summary)
        self.write(self.call / 'response.json', {'status': 'ok', 'input_tokens': 100, 'output_tokens': 9})
        result = audit_run(self.run)
        self.assertEqual(result['known_total_tokens'], 110)
        self.assertTrue(any('raw usage disagrees' in e for e in result['errors']))


if __name__ == '__main__':
    unittest.main()
