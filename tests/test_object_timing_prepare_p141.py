"""P141 binding/selection tests on a tiny handwritten filesystem only."""
from contextlib import ExitStack
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import prepare_whole_task_object_timing_p141 as prep


def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value))


class PrepareTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name)/'repo';self.storage=Path(tmp.name)/'storage';self.root.mkdir();self.storage.mkdir()
        self.old=self.root/'scripts/old.py';self.old.parent.mkdir();self.old.write_text('# synthetic old\n')
        self.prior=self.root/'configs/P140_whole_task_checkpoint_delta_envelope_v01.json'
        write(self.prior,{'source_sha256':{'scripts/old.py':prep.sha(self.old)}})
        self.audit=self.root/'reports/P140_comparison.json';write(self.audit,{'plan_sha256':prep.sha(self.prior)})
        write(self.storage/'records/context_pilot/P140_pipeline_v01/status.json',{'git_commit':'a'*40})
        self.publication=self.root/'reports/P140_results_provenance_20261028.json'
        write(self.publication,{'fixed_plan_sha256':prep.sha(self.prior),'fixed_execution_head':'a'*40,
                               'source_sha256':{'reports/P140_comparison.json':prep.sha(self.audit)}})
        self.task={'task_id':'6104387_1','source_run':'P29_04_CODE'}
        source=({'known_tasks':[self.task]}, {'api_budget_by_task':{'6104387_1':80}},[],[self.task])
        stack=ExitStack();self.addCleanup(stack.close)
        stack.enter_context(patch.object(prep,'ROOT',self.root));stack.enter_context(patch.object(prep,'REQUIRED_SOURCES',()))
        self.sources=stack.enter_context(patch.object(prep,'original_sources',return_value=source))
        stack.enter_context(patch.object(prep,'fixed_fields',return_value={}))
        self.validate=stack.enter_context(patch.object(prep,'validate_plan'))
        stack.enter_context(patch.object(prep,'predecessor_closed',return_value={'synthetic':True}))

    def test_one_fixed_Task4_new_namespace_once_and_old_bytes_preserved(self):
        old=self.old.read_bytes();value=prep.prepare(self.storage,self.root)
        self.assertEqual(value['known_tasks'],[self.task]);self.assertEqual(self.old.read_bytes(),old)
        self.assertFalse(value['scientific_adoption_evaluated']);self.assertFalse(value['development_gate_met'])
        self.validate.assert_called_once()
        with self.assertRaises(ValueError):prep.prepare(self.storage,self.root)

    def test_source_or_publication_or_head_changes_are_not_rebound(self):
        changes=[(self.old,b'# changed\n'),(self.prior,b'{}'),
                 (self.audit,b'{"plan_sha256":"wrong"}'),
                 (self.storage/'records/context_pilot/P140_pipeline_v01/status.json',b'{"git_commit":"wrong"}')]
        for path,content in changes:
            with self.subTest(path=path.name):
                original=path.read_bytes();path.write_bytes(content)
                with self.assertRaises((ValueError,KeyError)):prep.prepare(self.storage,self.root)
                path.write_bytes(original)
                self.assertFalse((self.root/prep.PLAN).exists())

    def test_no_substitution_or_extra_selected_task(self):
        for items in ([],[self.task,self.task],[dict(self.task,source_run='wrong')]):
            self.sources.return_value=({'known_tasks':[self.task]}, {'api_budget_by_task':{'6104387_1':80}},[],items)
            with self.assertRaises(ValueError):prep.prepare(self.storage,self.root)
        self.assertFalse((self.root/prep.PLAN).exists())

if __name__=='__main__':unittest.main()
