import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from event_review_results import aggregate, seal, sha, validate_annotations, write_new
from prepare_event_review import digest


class ReviewResultsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.review = self.root/'review'
        self.review.mkdir()
        rubric = json.loads((Path(__file__).resolve().parents[1]/'configs/P16_semantic_review_v01.json').read_text())
        write_new(self.review/'rubric.json', rubric)
        items = [{'status': 'done', 'requirement': 'PRIVATE simulated operation'},
                 {'status': 'pending', 'requirement': 'PRIVATE next action'}]
        packet = {'packet_id': 'review_001', 'schema_valid': True, 'spans': {'s1': {}},
                  'items': [{'item_index': i, 'item_sha256': digest(v), 'item': v} for i, v in enumerate(items)]}
        write_new(self.review/'review_001.json', packet)
        write_new(self.review/'review_002.json', {'packet_id': 'review_002', 'schema_valid': False, 'spans': {}, 'items': []})
        manifest = {'counts': {'outputs': 2, 'valid_outputs': 1, 'items': 2, 'done_items': 1},
                    'prepared_rubric_sha256': sha(self.review/'rubric.json'), 'results_sha256': 'result-digest',
                    'packets_sha256': {p.name: sha(p) for p in self.review.glob('review_*.json')}}
        write_new(self.review/'manifest.json', manifest)
        mapping = [{'packet_id': 'review_001', 'case_id': 'case_01', 'variant': 'raw', 'call_id': 'call_001'},
                   {'packet_id': 'review_002', 'case_id': 'case_01', 'variant': 'execution_tag', 'call_id': 'call_002'}]
        write_new(self.review/'mapping_private.json', mapping)
        self.annotations = [{'packet_id': 'review_001', 'item_index': i, 'item_sha256': digest(items[i]),
                             'label': label, 'evidence_span_ids': ['s1'],
                             'rationale_category': 'rejected_request_not_execution_evidence', 'uncertainty': 'low'}
                            for i, label in enumerate(('unsupported_action_completion', 'not_a_completion_claim'))]
        self.annotation_path, self.lock, self.audit = [self.root/name for name in ('labels.json', 'seal.json', 'audit.json')]
        write_new(self.annotation_path, self.annotations)
        rows = [{**m, 'condition': 'rejected_before_dispatch', 'schema_valid': i == 0} for i, m in enumerate(mapping)]
        groups = [{'condition': r['condition'], 'variant': r['variant'], 'calls': 1, 'schema_valid': int(r['schema_valid'])} for r in rows]
        write_new(self.audit, {'run_id': 'P16_01', 'audit_errors': [], 'source_hashes': {'results.json': 'result-digest'},
                              'rows': rows, 'groups': groups, 'calls': 2, 'known_total_tokens': 20, 'unknown_usage_calls': 0})

    def test_counts_do_not_treat_invalid_as_zero_error_success(self):
        seal(self.review, self.annotation_path, self.lock)
        result = aggregate(self.review, self.annotation_path, self.lock, self.audit)
        self.assertEqual(result['groups'][0]['outputs_with_unsupported_done_action'], 1)
        self.assertEqual(result['groups'][1]['valid_reviewed_outputs'], 0)
        self.assertEqual(result['known_total_tokens'], 20)
        self.assertNotIn('PRIVATE', json.dumps(result))

    def test_missing_duplicate_or_wrong_item_rejected(self):
        bad_hash = copy.deepcopy(self.annotations)
        bad_hash[0]['item_sha256'] = 'wrong'
        for annotations in (self.annotations[:1], self.annotations + self.annotations[:1], bad_hash):
            with self.subTest(annotations=annotations), self.assertRaises(ValueError):
                validate_annotations(self.review, annotations)

    def test_future_evidence_rejected(self):
        self.annotations[0]['evidence_span_ids'] = ['future_or_evaluation']
        with self.assertRaises(ValueError):
            validate_annotations(self.review, self.annotations)

    def test_post_seal_edits_rejected(self):
        seal(self.review, self.annotation_path, self.lock)
        self.annotations[0]['label'] = 'supported_action_completion'
        self.annotation_path.write_text(json.dumps(self.annotations))
        with self.assertRaises(ValueError):
            aggregate(self.review, self.annotation_path, self.lock, self.audit)

    def replace_packet(self, packet):
        path = self.review/'review_001.json'
        path.write_text(json.dumps(packet))
        manifest = json.loads((self.review/'manifest.json').read_text())
        manifest['packets_sha256'][path.name] = sha(path)
        (self.review/'manifest.json').write_text(json.dumps(manifest))

    def test_task_source_is_allowed_only_as_the_actual_supplied_requirement(self):
        packet = json.loads((self.review/'review_001.json').read_text())
        packet['task'] = {'instruction': 'perform the requested work'}
        packet['additional_sources'] = {'task': {'kind': 'user_requirement', 'value': packet['task']}}
        self.replace_packet(packet)
        self.annotations[1]['evidence_span_ids'] = ['task']
        validate_annotations(self.review, self.annotations)
        packet['additional_sources']['task']['kind'] = 'successful_operation'
        self.replace_packet(packet)
        with self.assertRaisesRegex(ValueError, 'requirement source'):
            validate_annotations(self.review, self.annotations)

    def test_audited_seed_must_match_the_sealed_mapping(self):
        path = self.review/'mapping_private.json'
        mapping = json.loads(path.read_text())
        mapping[0]['seed'] = 47
        path.write_text(json.dumps(mapping))
        seal(self.review, self.annotation_path, self.lock)
        with self.assertRaisesRegex(ValueError, 'seed differ'):
            aggregate(self.review, self.annotation_path, self.lock, self.audit)


if __name__ == '__main__':
    unittest.main()
