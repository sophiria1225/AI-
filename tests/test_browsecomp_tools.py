import hashlib
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from browsecomp_tools import CorpusTools


class FakeCorpus:
    num_docs = 100195
    def __init__(self):
        self.calls = []
        self.text = 'A\u3042\U0001f642BCDEF'
    def search(self, query, k):
        self.calls.append(('search', query, k))
        return [{'docid': '7', 'score': 1.5, 'contents': self.text,
                 'answer': 'MUST_NOT_CROSS', 'gold_docs': ['secret']}]
    def get_document(self, docid):
        self.calls.append(('document', docid))
        return self.text if docid == '7' else None


class BoundedCorpusTests(unittest.TestCase):
    def test_unicode_pages_reconstruct_the_entire_document(self):
        backend = FakeCorpus(); tools = CorpusTools(backend)
        offset, parts = 0, []
        while offset is not None:
            result = tools.dispatch('get_document', {'docid': '7', 'offset': offset, 'length': 2})
            self.assertEqual(result['status'], 'ok')
            self.assertEqual(result['full_content_sha256'], hashlib.sha256(backend.text.encode()).hexdigest())
            parts.append(result['text']); offset = result['next_offset']
        self.assertEqual(''.join(parts), backend.text)

    def test_search_does_not_export_unrequested_backend_fields(self):
        tools = CorpusTools(FakeCorpus(), snippet_characters=2)
        result = tools.dispatch('search', {'query': 'generic control'})
        self.assertEqual(result['results'][0]['text'], 'A\u3042')
        self.assertEqual(result['results'][0]['next_offset'], 2)
        self.assertNotIn('MUST_NOT_CROSS', repr(result))
        self.assertNotIn('gold_docs', repr(result))
        self.assertEqual(result['corpus_documents'], 100195)

    def test_paths_urls_extra_fields_and_bad_ranges_never_reach_backend(self):
        backend = FakeCorpus(); tools = CorpusTools(backend)
        bad = [('get_document', {'docid': '../qa/answers'}),
               ('get_document', {'docid': 'https://example.invalid'}),
               ('get_document', {'docid': '7', 'length': 8001}),
               ('get_document', {'docid': '7', 'offset': True}),
               ('search', {'query': 'x', 'top_k': True}),
               ('search', {'query': 'x', 'ground_truth': 'secret'}),
               ('search', {'query': 'x'*1001})]
        for name, args in bad:
            self.assertEqual(tools.dispatch(name, args)['status'], 'invalid_arguments')
        self.assertEqual(backend.calls, [])
        self.assertEqual(tools.requests, len(bad))

    def test_absence_and_end_of_document_are_distinct(self):
        backend = FakeCorpus(); tools = CorpusTools(backend)
        self.assertEqual(tools.dispatch('get_document', {'docid': '8'})['status'], 'not_found')
        end = tools.dispatch('get_document', {'docid': '7', 'offset': len(backend.text)})
        self.assertEqual(end['status'], 'ok'); self.assertEqual(end['text'], '')
        self.assertIsNone(end['next_offset'])
        self.assertEqual(tools.dispatch('get_document', {'docid': '7', 'offset': 99})['status'],
                         'offset_out_of_range')


if __name__ == '__main__':
    unittest.main()
