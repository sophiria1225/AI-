import copy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from review_memory_probe import export_review, template


class SemanticReviewControls(unittest.TestCase):
    def fixture(self):
        packet = dict(probe_id='P7_01', terminal_status='complete', source_request_sha256='source',
                      prefix_spans={'s1': {'observation': 'PRIVATE_BODY'}}, task='PRIVATE_TASK',
                      known_total_tokens=100, unknown_usage_calls=0, calls=[dict(
                          call_id='call_001', variant='raw', seed=43, schema_valid=True,
                          known_tokens=100, request_sha256='request', response_sha256='response',
                          done_items=[dict(index=0, item_sha256='item', item='PRIVATE_CLAIM')])])
        annotations = template(packet)
        annotations['claims'][0].update(category='operation_done', family='authentication',
                                        state_support='unsupported', cited_source_support='unsupported',
                                        reason='no_execution', evidence_span_ids=['s1'])
        return packet, annotations

    def test_unreviewed_claim_is_not_automatically_a_truth_label(self):
        packet, _ = self.fixture()
        with self.assertRaises(ValueError):
            export_review(packet, template(packet))

    def test_review_rejects_later_evidence_duplicate_or_changed_item(self):
        packet, annotations = self.fixture()
        for change in ('future', 'duplicate', 'hash'):
            candidate = copy.deepcopy(annotations)
            if change == 'future':
                candidate['claims'][0]['evidence_span_ids'] = ['s2']
            elif change == 'duplicate':
                candidate['claims'].append(candidate['claims'][0])
            else:
                candidate['claims'][0]['item_sha256'] = 'wrong'
            with self.assertRaises(ValueError):
                export_review(packet, candidate)

    def test_private_text_and_invalid_schema_never_become_zero_error_success(self):
        packet, annotations = self.fixture()
        packet['calls'].append(dict(call_id='call_002', variant='execution_tag', seed=43,
                                    schema_valid=False, known_tokens=40, request_sha256='q',
                                    response_sha256='r', done_items=[]))
        annotations['claims'][0]['free_text'] = 'PRIVATE_EXTRA'
        report = export_review(packet, annotations)
        self.assertNotIn('PRIVATE_', json.dumps(report))
        self.assertEqual(report['calls'][0]['unsupported_operation_done'], 1)
        self.assertFalse(report['calls'][1]['semantic_measurement_available'])


if __name__ == '__main__':
    unittest.main()
