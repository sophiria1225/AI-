"""Small synthetic source-freeze boundaries; no real prepare/task/model calls."""
from pathlib import Path
import json
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import prepare_whole_task_threshold_object_p143 as prepare


def write(root, name, data):
    path=root/name
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(data) if not isinstance(data,str) else data)
    return path


class PreparationTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name)/'repo';self.root.mkdir()
        self.storage=Path(tmp.name)/'storage';self.storage.mkdir()
        source=write(self.root,'scripts/historical.py','historical fixed source')
        publication=write(self.root,'reports/synthetic_public_result.json',{'complete':True})
        self.prior={'source_sha256':{'scripts/historical.py':prepare.sha(source)}}
        write(self.root,prepare.PRIOR_PLAN,self.prior)
        self.public={'fixed_plan_sha256':prepare.sha(self.root/prepare.PRIOR_PLAN),
            'fixed_execution_head':'a'*40,
            'source_sha256':{'reports/synthetic_public_result.json':prepare.sha(publication)}}
        write(self.root,prepare.PRIOR_PUBLICATION,self.public)
        write(self.root,prepare.PRIOR_AUDIT,{'plan_sha256':self.public['fixed_plan_sha256']})
        write(self.storage,'records/context_pilot/P142_pipeline_v01/status.json',{'git_commit':'a'*40})

    def test_previous_plan_head_sources_and_publication_are_all_required(self):
        self.assertEqual(prepare.verify_predecessor_sources(self.storage,self.root),(self.prior,self.public))
        cases=[('scripts/historical.py','changed'),
               ('reports/synthetic_public_result.json','changed'),
               (prepare.PRIOR_AUDIT,{'plan_sha256':'b'*64}),
               (prepare.PRIOR_PUBLICATION,self.public|{'fixed_plan_sha256':'b'*64}),
               (prepare.PRIOR_PUBLICATION,self.public|{'fixed_execution_head':'b'*40})]
        for name, value in cases:
            path=self.root/name;old=path.read_bytes()
            write(self.root,name,value)
            with self.subTest(name=name,value=value),self.assertRaises(ValueError):
                prepare.verify_predecessor_sources(self.storage,self.root)
            path.write_bytes(old)

    def test_only_bound_prior_publication_tracked_and_explicit_new_sources(self):
        tracked=['scripts/historical.py','tests/tracked_test.py']
        required=('scripts/new_p143.py','tests/test_new_p143.py')
        drafts=['scripts/reserved_confirmation_worker_inputs.py','tests/test_reserved_confirmation_worker_inputs.py']
        for name in [*tracked,*required,*drafts]:
            if not (self.root/name).exists():write(self.root,name,'synthetic only')
        with patch.object(prepare.subprocess,'check_output',side_effect=[
                ('\0'.join(tracked)+'\0').encode(), ('\0'.join([*required,*drafts])+'\0').encode()]):
            result=prepare.source_paths(self.root,self.prior,self.public,required)
        names={str(path.relative_to(self.root)) for path in result}
        self.assertTrue(set(required)|set(tracked)<=names)
        self.assertTrue(set(self.prior['source_sha256'])|set(self.public['source_sha256'])<=names)
        self.assertTrue({prepare.PRIOR_PLAN,prepare.PRIOR_PUBLICATION,prepare.PRIOR_AUDIT}<=names)
        self.assertTrue(set(drafts).isdisjoint(names))

    def test_unlisted_new_phase_source_cannot_escape_freeze(self):
        with patch.object(prepare.subprocess,'check_output',side_effect=[b'',b'scripts/unlisted_p143.py\0']):
            with self.assertRaisesRegex(ValueError,'unlisted_new_P143'):
                prepare.source_paths(self.root,self.prior,self.public,())

    def test_explicit_accidental_reserved_draft_inclusion_is_rejected(self):
        name='scripts/reserved_confirmation_worker_inputs.py'
        write(self.root,name,'unfinished draft')
        with patch.object(prepare.subprocess,'check_output',side_effect=[b'',(name+'\0').encode()]):
            with self.assertRaisesRegex(ValueError,'untracked_reserved_confirmation'):
                prepare.source_paths(self.root,self.prior,self.public,(name,))

    def test_source_traversal_and_symbolic_links_cannot_be_frozen(self):
        for name in ('../outside.py','/synthetic/absolute.py'):
            with self.subTest(name=name),self.assertRaises(ValueError):prepare._path(self.root,name)
        target=write(self.root,'scripts/target.py','local')
        link=self.root/'scripts/link.py';link.symlink_to(target)
        with self.assertRaises(ValueError):prepare._path(self.root,'scripts/link.py')


if __name__=='__main__':unittest.main()
