import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from native_boundary_record import snapshot_boundary, verify_boundary


class BoundaryRecordControls(unittest.TestCase):
    def test_later_source_mutation_cannot_change_the_saved_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); source = root / 'db.jsonl'; store = root / 'snapshots'
            source.write_text('first private state')
            first = snapshot_boundary(store, 'initial', {'dbs/db.jsonl': source}, {'calls': 0})
            unchanged = snapshot_boundary(store, 'call_001', {'dbs/db.jsonl': source}, {'calls': 1})
            self.assertEqual(unchanged['new_object_bytes'], 0)
            source.write_text('later changed state')
            snapshot_boundary(store, 'call_002', {'dbs/db.jsonl': source}, {'calls': 2})
            result = verify_boundary(store, 'initial')
            self.assertEqual(result['captured_file_bytes'], len('first private state'))
            self.assertNotIn('private state', json.dumps(first))
            with self.assertRaises(FileExistsError):
                snapshot_boundary(store, 'initial', {'dbs/db.jsonl': source}, {})

    def test_missing_symlink_and_oversize_sources_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); source = root / 'db'; source.write_bytes(b'1234')
            link = root / 'link'; link.symlink_to(source)
            for index, candidate in enumerate([root / 'missing', link]):
                with self.assertRaises(ValueError):
                    snapshot_boundary(root / str(index), 'initial', {'db': candidate}, {})
            with self.assertRaises(ValueError):
                snapshot_boundary(root / 'large', 'initial', {'db': source}, {}, max_new_bytes=3)
            with self.assertRaises(ValueError):
                snapshot_boundary(root / 'bad', '../outside', {'db': source}, {})

    def test_saved_corruption_is_detected_without_running_an_environment(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); source = root / 'db'; source.write_bytes(b'1234')
            store = root / 'snapshots'
            snapshot_boundary(store, 'initial', {'db': source}, {})
            next((store / 'objects').iterdir()).write_bytes(b'4321')
            with self.assertRaises(ValueError):
                verify_boundary(store, 'initial')
            with self.assertRaises(ValueError):
                snapshot_boundary(store, 'call_001', {'db': source}, {})


if __name__ == '__main__':
    unittest.main()
