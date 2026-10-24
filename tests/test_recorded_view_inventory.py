import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from inspect_recorded_view_compatibility import PLAN, RUNS, ZERO, inspect


class RecordedViewInventoryTests(unittest.TestCase):
    def fixture(self, root, storage, *, wrong_parent=False, missing_program=False):
        def save(path, obj, lines=False):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(('\n'.join(json.dumps(x) for x in obj) if lines else json.dumps(obj))+'\n')
            return hashlib.sha256(path.read_bytes()).hexdigest()
        rows = []; files = {}
        for rid in RUNS:
            folder = storage/'records/context_pilot'/rid
            events = []; spans = {}; files[rid] = {}
            if rid == 'P29_04_CODE':
                code = "v=call_api('spotify','show_song',song_id=1)"
                events = [dict(span_id='a', stage='python_api', call='call_001', api_request_sent=True),
                          dict(span_id='b', stage='model_tool', call='call_001', api_request_sent=False)]
                spans = {'a': {'action': {'name': 'spotify__show_song', 'arguments': '{"song_id":1}'}},
                         'b': {'action': {'name': 'run_python', 'arguments': json.dumps({'code': 'pass' if wrong_parent else code})},
                               'observation': {'api_receipts': [{'span_id': 'a'}]}}}
                program = folder/'programs/call_001_01'
                result = dict(program_index=1, status='execution_error', session_usable=True,
                              api_requests=1, stdout='', error='stopped', stdout_truncated=False)
                wire = [dict(kind='api', id=1, program_index=1, app='spotify', api='show_song', arguments={'song_id':1}),
                        dict(kind='done', program_index=1, stdout='', error='stopped', stdout_truncated=False)]
                if not missing_program:
                    files[rid]['call_001_01'] = {
                        'input_private.json': save(program/'input_private.json', dict(program_index=1, code=code, observations=[], api_schemas={})),
                        'result_private.json': save(program/'result_private.json', result),
                        'wire_private.jsonl': save(program/'wire_private.jsonl', wire, True)}
            sources = {'events.json': save(folder/'events.json', events), 'spans.json': save(folder/'spans.json', spans)}
            rows.append(dict(run_id=rid, original_official_success=rid=='P25_04_GUIDED', show_song_requests=1,
                             task_fields_preknown_requests=0, same_request_response_preknown_requests=0, source_sha256=sources))
        report = 'reports/P69_export_acquisition_scope.json'
        digest = save(root/report, {'rows': rows})
        save(root/PLAN, dict(phase='P92', run_ids=RUNS, max_wall_seconds=120, max_file_bytes=16777216,
            max_programs_per_record=80, max_source_characters=20000, max_ast_nodes=5000,
            max_events_per_record=4000, measured_savings=None, novel_method_claim=False,
            source_sha256={report:digest}, program_files=files, selection='synthetic fixture', **{k:0 for k in ZERO}))

    def test_all_five_formats_and_original_failure_are_kept(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)/'repo';storage=Path(d)/'storage';self.fixture(root,storage)
            with patch('inspect_recorded_view_compatibility.subprocess.check_output', return_value='a'*40):
                result=inspect(storage,root)
            self.assertEqual([r['run_id'] for r in result['rows']], RUNS)
            self.assertEqual(result['inspected_programs'],1)
            self.assertTrue(result['rows'][1]['original_official_success'])
            self.assertFalse(result['rows'][2]['original_official_success'])
            self.assertEqual(result['rows'][2]['programs'][0]['boundary']['status'],'execution_error')
            self.assertEqual(result['saved_code_executions'],0)

    def test_parent_code_mismatch_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)/'repo';storage=Path(d)/'storage';self.fixture(root,storage,wrong_parent=True)
            with self.assertRaisesRegex(ValueError,'parent_code_differs'):inspect(storage,root)

    def test_a_missing_program_is_not_converted_to_a_native_record(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)/'repo';storage=Path(d)/'storage';self.fixture(root,storage,missing_program=True)
            with self.assertRaisesRegex(ValueError,'saved_program_count'):inspect(storage,root)

    def test_additional_program_artifact_is_not_ignored(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)/'repo';storage=Path(d)/'storage';self.fixture(root,storage)
            p=storage/'records/context_pilot/P29_04_CODE/programs/call_002_01/input_private.json'
            p.parent.mkdir();p.write_text('{}')
            with self.assertRaisesRegex(ValueError,'file_inventory_changed'):inspect(storage,root)


if __name__=='__main__':unittest.main()
