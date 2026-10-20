"""Provenance controls for keeping different quantizations and attempts separate."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from model_provenance import check_live_model, load_selection, stable_manifest, verified_model


class ModelProvenanceControls(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.name = 'configs/models/fixture_selection.json'
        self.config = {'repo_id': 'fixture/model', 'revision': 'a' * 40,
                       'quantization': 'IQ4_XS', 'subdirectory': 'model-IQ4_XS',
                       'total_bytes': 4, 'model_alias': 'fixture-iq4',
                       'file_manifest': 'configs/models/fixture_files.json',
                       'download_record': 'records/models/fixture_download.json'}
        self.config['runtime'] = {'binary_tag': 'b1', 'commit': 'd' * 40}
        self.entry = {'path': 'model-IQ4_XS/part-00001-of-00001.gguf', 'bytes': 4, 'sha256': 'b' * 64}
        self.manifest = {'repo_id': 'fixture/model', 'revision': 'a' * 40,
                         'total_bytes': 4, 'files': [self.entry], 'retrieved_at': 'first retrieval'}
        self.write(self.name, self.config)
        stable_manifest(self.config, self.manifest, self.root)
        self.record = {'status': 'verified', 'manifest': self.manifest,
                       'destination': 'models/fixture/' + 'a' * 40,
                       'files': {self.entry['path']: {'status': 'verified', 'bytes': 4, 'sha256': 'b' * 64}}}
        self.write(self.config['download_record'], self.record)
        weight = self.root / self.record['destination'] / self.entry['path']
        weight.parent.mkdir(parents=True)
        weight.write_bytes(b'test')

    def write(self, relative, value):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value))

    def test_requery_preserves_original_manifest_bytes(self):
        path = self.root / self.config['file_manifest']
        before = path.read_bytes()
        later = self.manifest | {'retrieved_at': 'later retrieval'}
        result = stable_manifest(self.config, later, self.root)
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(result['retrieved_at'], 'first retrieval')

    def test_changed_remote_checksum_cannot_replace_fixed_manifest(self):
        path = self.root / self.config['file_manifest']
        before = path.read_bytes()
        changed = copy.deepcopy(self.manifest)
        changed['files'][0]['sha256'] = 'c' * 64
        with self.assertRaisesRegex(ValueError, 'differs'):
            stable_manifest(self.config, changed, self.root)
        self.assertEqual(path.read_bytes(), before)

    def test_other_quantization_record_cannot_authorize_loading(self):
        self.record['manifest'] = copy.deepcopy(self.manifest)
        self.record['manifest']['files'][0]['path'] = 'model-Q3_K_L/part.gguf'
        self.write(self.config['download_record'], self.record)
        with self.assertRaisesRegex(ValueError, 'outside selected'):
            verified_model(self.name, self.root)

    def test_summary_verified_does_not_override_failed_individual_file(self):
        self.record['files'][self.entry['path']]['status'] = 'failed'
        self.write(self.config['download_record'], self.record)
        with self.assertRaisesRegex(ValueError, 'incomplete'):
            verified_model(self.name, self.root)

    def test_valid_record_and_size_change(self):
        config, _, weight = verified_model(self.name, self.root)
        self.assertEqual(config['model_alias'], 'fixture-iq4')
        weight.write_bytes(b'changed size')
        with self.assertRaisesRegex(ValueError, 'size changed'):
            verified_model(self.name, self.root)

    def test_external_record_path_is_rejected(self):
        self.config['download_record'] = '../outside.json'
        self.write(self.name, self.config)
        with self.assertRaisesRegex(ValueError, 'within this repository'):
            load_selection(self.name, self.root)

    def test_live_server_for_other_quantization_is_rejected(self):
        _, _, model = verified_model(self.name, self.root)
        runtime = {'status': 'ready', 'runtime': self.config['runtime'],
                   'model_revision': 'a' * 40, 'ctx_size': 8192}
        props = {'default_generation_settings': {'n_ctx': 8192}, 'total_slots': 1,
                 'model_alias': 'fixture-iq4', 'build_info': 'b1-' + 'd' * 9,
                 'model_path': str(model)}
        check_live_model(self.name, runtime, props, 8192, self.root)
        props['model_alias'] = 'fixture-q3'
        with self.assertRaisesRegex(ValueError, 'live model settings'):
            check_live_model(self.name, runtime, props, 8192, self.root)


if __name__ == '__main__':
    unittest.main()
