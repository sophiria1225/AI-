import contextlib
import csv
import io
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import build_choice_context_report as report
from run_context_comparison import write_json
from test_choice_context_audit import fixture as audit_fixture
from test_choice_context_replay import plan

ROOT=Path(__file__).resolve().parents[1]


def fixture(base,fail_at=None):
    audit_fixture(base,fail_at=fail_at);root=base/'repo'
    (root/'configs').mkdir();(root/'scripts').mkdir()
    fixed=plan()
    for case in fixed['cases']:case['source_request_sha256']='synthetic-source'
    write_json(root/report.FILES[0],fixed)
    shutil.copyfile(ROOT/'scripts/audit_choice_context.py',root/'scripts/audit_choice_context.py')
    return root


class ChoiceContextReportingTests(unittest.TestCase):
    def test_all_slots_groups_and_contrasts_are_written(self):
        with tempfile.TemporaryDirectory() as t:
            base=Path(t);root=fixture(base);out=base/'report'
            value=report.build(out,root)
            self.assertEqual(value['pages'],7);self.assertFalse(value['visual_reviewed'])
            for name,count in [('all_36_generations.csv',36),('all_12_groups.csv',12),
                               ('all_66_input_pairs.csv',66),('all_66_output_pairs.csv',66)]:
                with (out/name).open() as stream:self.assertEqual(len(list(csv.DictReader(stream))),count)
            self.assertTrue(value['static_submission_is_not_execution'])
            self.assertEqual(value['report_build_model_calls'],0)

    def test_unknown_and_unattempted_slots_do_not_become_zero_usage(self):
        with tempfile.TemporaryDirectory() as t:
            base=Path(t);root=fixture(base,fail_at=4);out=base/'report';value=report.build(out,root)
            self.assertEqual(value['unknown_usage_calls'],1);self.assertEqual(value['unattempted_slots'],32)
            with (out/'all_36_generations.csv').open() as stream:rows=list(csv.DictReader(stream))
            self.assertEqual(rows[3]['input_tokens'],'');self.assertEqual(rows[4]['output_tokens'],'')
            self.assertIn('使用量不明',(out/'index.html').read_text())
            self.assertIn('未実行',(out/'index.html').read_text())

    def test_missing_slot_or_cross_contrast_cannot_be_hidden(self):
        for kind in ('row','pair'):
            with tempfile.TemporaryDirectory() as t:
                root=fixture(Path(t));path=root/report.FILES[2];value=json.loads(path.read_text())
                if kind=='row':value['rows'].pop()
                else:value['equality_summary']['structural_comparisons']['cross'].pop()
                write_json(path,value)
                with self.assertRaises(ValueError):report.validated(root)

    def test_open_server_or_claimed_task_success_rejected(self):
        for kind in ('server','quality'):
            with tempfile.TemporaryDirectory() as t:
                root=fixture(Path(t));path=root/report.FILES[2];value=json.loads(path.read_text())
                if kind=='server':value['server']['status']='ready'
                else:value['task_quality_or_savings_measured']=True
                write_json(path,value)
                with self.assertRaises(ValueError):report.validated(root)

    def test_tampered_known_totals_are_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            root=fixture(Path(t));path=root/report.FILES[2];value=json.loads(path.read_text())
            value['known_total_tokens']+=1;write_json(path,value)
            with self.assertRaisesRegex(ValueError,'aggregation_mismatch'):report.validated(root)

    def test_existing_output_is_preserved(self):
        with tempfile.TemporaryDirectory() as t:
            base=Path(t);root=fixture(base);out=base/'report';out.mkdir();(out/'failure.txt').write_text('keep')
            with self.assertRaises(FileExistsError):report.build(out,root)
            self.assertEqual((out/'failure.txt').read_text(),'keep')


if __name__=='__main__':unittest.main()
