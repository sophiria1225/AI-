"""Finite path regression and original accounting semantics; handwritten data only."""
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import build_p133_report_recovery_v01 as recovery
from build_p132_report import public_path as original_public_path


class RecoveryTests(unittest.TestCase):
    def test_only_seven_original_extra_paths_are_fixed(self):
        self.assertEqual(len(recovery.EXTRA_PUBLIC_SOURCES),7)
        self.assertEqual(sum(n.startswith('materials/') for n in recovery.EXTRA_PUBLIC_SOURCES),6)
        self.assertEqual(sum(n.startswith('papers/') for n in recovery.EXTRA_PUBLIC_SOURCES),1)
        for n,h in recovery.EXTRA_PUBLIC_SOURCES.items():
            self.assertFalse(Path(n).is_absolute());self.assertNotIn('..',Path(n).parts)
            self.assertEqual(len(h),64)

    def test_old_report_rejects_but_exact_bound_new_path_passes(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td).resolve();name=next(iter(recovery.EXTRA_PUBLIC_SOURCES));p=root/name
            p.parent.mkdir(parents=True);p.write_bytes(b'handwritten-public-fixture')
            with self.assertRaisesRegex(ValueError,'repository_public_source_path_required'):original_public_path(root,name)
            h=hashlib.sha256(p.read_bytes()).hexdigest()
            with patch.dict(recovery.EXTRA_PUBLIC_SOURCES,{name:h}):
                self.assertEqual(recovery.public_path(root,name),p)
                p.write_bytes(b'changed')
                with self.assertRaisesRegex(ValueError,'additional_frozen_source_changed'):recovery.public_path(root,name)

    def test_arbitrary_materials_papers_absolute_and_traversal_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td).resolve()
            for name in ('materials/unplanned.json','papers/unplanned.tex','/tmp/file','scripts/../private.json','reports/../../private.json'):
                with self.subTest(name=name),self.assertRaises(ValueError):recovery.public_path(root,name)

    def test_symlink_is_not_regular_bound_extra_source(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td).resolve();name=next(iter(recovery.EXTRA_PUBLIC_SOURCES));p=root/name
            p.parent.mkdir(parents=True);target=root/'fixture';target.write_bytes(b'x');p.symlink_to(target)
            with patch.dict(recovery.EXTRA_PUBLIC_SOURCES,{name:hashlib.sha256(b'x').hexdigest()}),self.assertRaisesRegex(ValueError,'bounded_regular_public_source_required'):
                recovery.public_path(root,name)

    def test_unknown_component_totals_remain_null_and_subtotals_remain_known(self):
        row={'record_status':'evaluated','success':False,'known_total_tokens':30,'unknown_usage_calls':1,'input_tokens':20,'output_tokens':10,'cached_input_tokens':3}
        value=recovery.aggregate([row]);self.assertEqual(value['known_token_subtotal'],30);self.assertIsNone(value['exact_total_tokens'])
        for k in ('input_tokens','output_tokens','cached_input_tokens'):
            self.assertEqual(value['measures'][k]['known_subtotal'],row[k]);self.assertIsNone(value['measures'][k]['exact_all_condition_total'])

    def test_all_four_missing_slots_are_not_free(self):
        rows=[{'record_status':'not_run','success':None,'known_total_tokens':None,'unknown_usage_calls':None}for _ in range(4)]
        value=recovery.aggregate(rows)
        self.assertEqual(value['planned_conditions'],4);self.assertEqual(value['unknown_usage_count_missing_conditions'],4)
        self.assertIsNone(value['exact_total_tokens']);self.assertFalse(value['all_condition_usage_known'])

if __name__=='__main__':unittest.main()
