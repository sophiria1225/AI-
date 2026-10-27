"""P139 preparation lineage: tiny handwritten filesystem, no real preparation.

The cohort schema and prior source loader are stubbed here. These tests isolate
the old-source/plan/head/publication binding before any new plan is written.
"""
from contextlib import ExitStack
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import prepare_whole_task_checkpoint_representation_p139 as prep


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True) + '\n')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class PrepareLineageTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / 'repo'
        self.storage = Path(temporary.name) / 'storage'
        self.root.mkdir(); self.storage.mkdir()
        self.old = self.root / 'scripts/old_frozen.py'
        self.old.parent.mkdir()
        self.old.write_text('# Handwritten frozen source\n')
        self.prior_path = self.root / 'configs/P138_whole_task_prefix_exposure_v01.json'
        write(self.prior_path, {'source_sha256': {'scripts/old_frozen.py': sha(self.old)}})
        self.audit_path = self.root / 'reports/P138_comparison.json'
        write(self.audit_path, {'plan_sha256': sha(self.prior_path)})
        write(self.root / 'reports/P138_server_session.json', {'synthetic': True})
        write(self.root / 'configs/P123_whole_task_rolling_checkpoint_v01.json', {'synthetic': True})
        write(self.root / 'reports/P138_task4_API_progress_metadata_20261027.json', {
            'status': 'complete', 'additional_model_API_evaluator_tokenizer_calls': 0,
            'original_results_modified': False})
        write(self.root / 'docs/experiments/P139_checkpoint_representation_draft_20261027.md',
              {'synthetic_document': True})
        self.pipeline_path = self.storage / 'records/context_pilot/P138_pipeline_v01/status.json'
        write(self.pipeline_path, {'git_commit': 'a' * 40})
        self.publication_path = self.root / 'reports/P138_results_provenance_20261027.json'
        write(self.publication_path, {
            'fixed_plan_sha256': sha(self.prior_path), 'fixed_execution_head': 'a' * 40,
            'source_sha256': {'reports/P138_comparison.json': sha(self.audit_path)}})
        tasks = [{'task_id': f'synthetic_{n}'} for n in range(4)]
        previous = {'known_tasks': tasks, 'source_runs': ['synthetic-prior']}
        original = {'api_budget_by_task': {x['task_id']: n
                    for x, n in zip(tasks, (160, 80, 80, 80), strict=True)}}
        stack = ExitStack(); self.addCleanup(stack.close)
        stack.enter_context(patch.object(prep, 'ROOT', self.root))
        stack.enter_context(patch.object(prep, 'original_sources',
                                         return_value=(previous, original, [], [])))
        stack.enter_context(patch.object(prep, 'fixed_fields',
            side_effect=lambda: {'source_runs': deepcopy(previous['source_runs'])}))
        self.schema = stack.enter_context(patch.object(prep, 'validate_plan'))
        self.closure = stack.enter_context(patch.object(prep, 'predecessor_closed',
                                                       return_value={'synthetic_closed': True}))

    def assert_rejected_without_plan(self, label):
        with self.assertRaisesRegex(ValueError, label):
            prep.prepare(self.storage, self.root)
        self.assertFalse((self.root / prep.PLAN).exists())
        self.schema.assert_not_called()
        self.closure.assert_not_called()

    def test_success_binds_old_and_new_files_without_rewriting_old(self):
        original_bytes = self.old.read_bytes()
        new = self.root / 'scripts/new_p139.py'
        new.write_text('# Handwritten new source\n')
        result = prep.prepare(self.storage, self.root)
        self.assertEqual(result['source_sha256']['scripts/old_frozen.py'], sha(self.old))
        self.assertEqual(result['source_sha256']['scripts/new_p139.py'], sha(new))
        self.assertEqual(result['predecessor_closure'], {'synthetic_closed': True})
        self.assertFalse(result['model_generations_started'])
        self.assertEqual(self.old.read_bytes(), original_bytes)
        self.schema.assert_called_once(); self.closure.assert_called_once()
        with self.assertRaisesRegex(ValueError, 'unused_P139_namespace'):
            prep.prepare(self.storage, self.root)

    def test_changed_old_source_cannot_be_rehashed_into_new_plan(self):
        self.old.write_text('# Changed after old freeze\n')
        self.assert_rejected_without_plan('fixed_P138_sources_changed')

    def test_prior_plan_bytes_must_match_public_fixed_digest(self):
        value = json.loads(self.prior_path.read_text()); value['altered'] = True
        write(self.prior_path, value)
        self.assert_rejected_without_plan('closed_P138_fixed_plan_or_head_changed')

    def test_audit_plan_and_execution_head_must_match_publication(self):
        for target, key, value in (
            (self.audit_path, 'plan_sha256', 'b' * 64),
            (self.pipeline_path, 'git_commit', 'b' * 40),
            (self.publication_path, 'fixed_execution_head', 'b' * 40),
        ):
            with self.subTest(key=key):
                original = target.read_bytes()
                record = json.loads(original); record[key] = value; write(target, record)
                self.assert_rejected_without_plan('closed_P138_fixed_plan_or_head_changed')
                target.write_bytes(original)

    def test_publication_artifact_bytes_cannot_be_silently_rebound(self):
        record = json.loads(self.audit_path.read_text()); record['altered_metadata'] = True
        write(self.audit_path, record)
        self.assert_rejected_without_plan('closed_P138_publication_changed')


if __name__ == '__main__':
    unittest.main()
