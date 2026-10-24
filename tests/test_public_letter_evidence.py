import copy
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from verify_public_letter_evidence import (ROOT, DEFAULT_FOLDER, action_comparisons,
                                          public_path, verify, whole_task)


class AccountingTest(unittest.TestCase):
    def rows(self):
        return [dict(run_id='ok', record_status='evaluated', success=True,
                     known_total_tokens=20, unknown_usage_calls=0, model_calls=2, api_requests=1),
                dict(run_id='failed', record_status='evaluated', success=False,
                     known_total_tokens=60, unknown_usage_calls=0, model_calls=4, api_requests=3)]

    def test_failed_work_is_included(self):
        out = whole_task(self.rows())
        self.assertEqual((out['full_logical_tokens'],out['model_calls'],out['failed']),(80,6,1))

    def test_unknown_terminal_usage_is_not_zero(self):
        rows=self.rows(); rows[1]['unknown_usage_calls']=1
        out=whole_task(rows)
        self.assertEqual(out['known_logical_tokens'],80)
        self.assertIsNone(out['full_logical_tokens'])
        self.assertEqual(out['unknown_usage_calls'],1)

    def test_unevaluated_missing_condition_remains_missing(self):
        rows=self.rows()+[dict(run_id='not_run',record_status='not_attempted')]
        out=whole_task(rows)
        self.assertEqual((out['planned_rows'],out['evaluated'],out['unevaluated']),(3,2,1))
        self.assertEqual(out['rows_without_usage_count'],1)
        self.assertIsNone(out['full_logical_tokens'])
        self.assertIsNone(out['api_requests'])

    def test_duplicate_condition_rejected(self):
        rows=self.rows(); rows.append(copy.deepcopy(rows[0]))
        with self.assertRaisesRegex(ValueError,'duplicate_condition'):
            whole_task(rows)

    def test_matching_empty_actions_are_not_valid_execution_agreement(self):
        rows=[dict(id=c,case=c,structured_submissions=0,suffix_saved_programs=0,
                   suffix_request_sequence_sha256='empty',suffix_execution_evidence_sha256='error')
              for c in ('C','D')]
        structures=[dict(id=c,structure=dict(public_output_sha256='same-text',
                    syntax_actions_sha256='empty')) for c in ('C','D')]
        out=action_comparisons(rows,structures)[0]
        self.assertEqual((out['public_output_equal'],out['comparable_executed_pairs'],
                          out['request_sequence_equal'],out['unavailable_pairs']),(1,0,0,1))
        self.assertFalse(out['independent_samples'])

    def test_different_code_can_have_same_request_sequence(self):
        rows=[dict(id=c,case=c,structured_submissions=1,suffix_saved_programs=1,
                   suffix_request_sequence_sha256='same-request',suffix_execution_evidence_sha256=c)
              for c in ('A','X')]
        structures=[dict(id=c,structure=dict(public_output_sha256=c,
                    syntax_actions_sha256=c)) for c in ('A','X')]
        out=action_comparisons(rows,structures)[0]
        self.assertEqual((out['syntax_equal'],out['request_sequence_equal'],
                          out['public_execution_result_equal']),(0,1,0))


class PublishedFilesTest(unittest.TestCase):
    def test_complete_published_cohorts_and_missing_usage(self):
        out=verify(ROOT)
        self.assertEqual((out['P82']['planned_rows'],out['P82']['model_calls'],
                          out['P82']['known_logical_tokens'],out['P82']['unknown_usage_calls'],
                          out['P82']['api_requests']),(24,426,4602713,4,1156))
        self.assertIsNone(out['P82']['full_logical_tokens'])
        self.assertEqual(out['independent_tasks'],4)
        self.assertEqual((out['P94']['conditions'],out['P94']['saved_contexts'],
                          out['P94']['total_api_requests'],out['P94']['total_program_executions']),
                         (18,1,546,228))
        self.assertEqual(len(out['P94']['all_15_cross_comparisons']),15)

    def copy_public_files(self,target):
        folder=ROOT/DEFAULT_FOLDER
        manifest=json.loads((folder/'build_manifest.json').read_text())
        names=set(manifest['source_sha256'])
        names.update(DEFAULT_FOLDER+'/'+n for n in manifest['generated_sha256'])
        names.update(DEFAULT_FOLDER+'/'+n for n in ('build_manifest.json','draft.pdf',
                                                   'visual_review.json','layout.json'))
        for name in names:
            out=target/name;out.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(ROOT/name,out)

    def test_changed_public_table_is_detected(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);self.copy_public_files(root)
            table=root/DEFAULT_FOLDER/'whole_task.tex'
            table.write_text(table.read_text().replace('128,796','128,795',1))
            with self.assertRaisesRegex(ValueError,'public_file_changed:.*whole_task.tex'):
                verify(root)

    def test_missing_source_is_detected(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);self.copy_public_files(root)
            (root/'reports/P93_public_action_structure.json').unlink()
            with self.assertRaisesRegex(ValueError,'missing_or_oversized_public_file'):
                verify(root)

    def test_paths_cannot_reach_private_or_external_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)/'repo';root.mkdir()
            outside=Path(directory)/'outside';outside.write_text('private')
            (root/'papers').mkdir();(root/'papers/link').symlink_to(outside)
            (root/'.runtime').mkdir();(root/'.runtime/secret').write_text('private')
            (root/'papers/private').symlink_to(root/'.runtime/secret')
            for name in ('.runtime/secret','records/private','papers/../../outside',
                         'papers/link','papers/private'):
                with self.subTest(name=name),self.assertRaises(ValueError):
                    public_path(root,name)


if __name__=='__main__':
    unittest.main()
