"""Bounded corpus-only tools. No QA file, answer label, shell or evaluator access."""
import hashlib
import math
import re


TOOLS = [
    {'type': 'function', 'function': {
        'name': 'search',
        'description': 'Search the entire fixed document corpus using BM25. Returns ranked '
                       'document IDs, scores and initial excerpts. Use get_document for more text.',
        'parameters': {'type': 'object', 'properties': {
            'query': {'type': 'string', 'maxLength': 1000},
            'top_k': {'type': 'integer', 'minimum': 1, 'maximum': 10}},
            'required': ['query'], 'additionalProperties': False}}},
    {'type': 'function', 'function': {
        'name': 'get_document',
        'description': 'Read a document page by corpus ID. Offsets and lengths are Unicode '
                       'characters. Responses state the total length and next offset; more pages '
                       'remain available. This tool cannot open paths, URLs or evaluation files.',
        'parameters': {'type': 'object', 'properties': {
            'docid': {'type': 'string', 'pattern': '^[0-9]{1,20}$'},
            'offset': {'type': 'integer', 'minimum': 0},
            'length': {'type': 'integer', 'minimum': 1, 'maximum': 8000}},
            'required': ['docid'], 'additionalProperties': False}}},
]


def integer(value, lower, upper):
    if type(value) is not int or not lower <= value <= upper:
        raise ValueError('integer is outside the supported range')
    return value


def document_id(value):
    if not isinstance(value, str) or re.fullmatch(r'[0-9]{1,20}', value) is None:
        raise ValueError('docid must be a numeric corpus identifier')
    return value


def page(docid, contents, offset, length):
    document_id(docid)
    if not isinstance(contents, str):
        raise TypeError('backend returned non-text contents')
    if offset > len(contents):
        return {'status': 'offset_out_of_range', 'docid': docid, 'total_characters': len(contents)}
    end = min(len(contents), offset + length)
    return {'status': 'ok', 'docid': docid, 'text': contents[offset:end], 'start': offset,
            'end': end, 'total_characters': len(contents),
            'next_offset': end if end < len(contents) else None,
            'full_content_sha256': hashlib.sha256(contents.encode()).hexdigest()}


class CorpusTools:
    """Backend injection permits boundary tests without a JVM or benchmark text."""
    def __init__(self, backend, snippet_characters=2048):
        integer(snippet_characters, 1, 8000)
        self.backend = backend
        self.snippet_characters = snippet_characters
        self.requests = 0

    def dispatch(self, name, args):
        self.requests += 1  # Invalid requests also consume the request budget.
        try:
            if not isinstance(args, dict):
                raise ValueError('arguments must be an object')
            if name == 'search':
                if set(args) - {'query', 'top_k'} or 'query' not in args:
                    raise ValueError('unexpected or missing search arguments')
                query = args['query']
                if not isinstance(query, str) or not query.strip() or len(query) > 1000:
                    raise ValueError('query must contain 1 to 1000 characters')
                k = integer(args.get('top_k', 5), 1, 10)
            elif name == 'get_document':
                if set(args) - {'docid', 'offset', 'length'} or 'docid' not in args:
                    raise ValueError('unexpected or missing document arguments')
                docid = document_id(args['docid'])
                offset = integer(args.get('offset', 0), 0, 2**31-1)
                length = integer(args.get('length', 8000), 1, 8000)
            else:
                return {'status': 'unsupported_tool'}
        except ValueError as error:
            return {'status': 'invalid_arguments', 'error': str(error)}
        # Backend failures, including ValueError, must remain infrastructure errors.
        # They are not invalid model arguments or successful empty searches.
        if name == 'search':
            raw = self.backend.search(query, k)
            if not isinstance(raw, list) or len(raw) > k:
                raise RuntimeError('backend result count is invalid')
            results = []
            for row in raw:
                if type(row['score']) not in (int, float) or not math.isfinite(row['score']):
                    raise RuntimeError('backend score is invalid')
                item = page(row['docid'], row['contents'], 0, self.snippet_characters)
                results.append({**item, 'score': row['score']})
            return {'status': 'ok', 'results': results, 'returned_documents': len(results),
                    'corpus_documents': self.backend.num_docs}
        contents = self.backend.get_document(docid)
        if contents is None:
            return {'status': 'not_found', 'docid': docid}
        return page(docid, contents, offset, length)


class LuceneBackend:
    def __init__(self, index_path, expected_documents=100195):
        # The caller configures its isolated Java environment before this import.
        import json
        from pyserini.search.lucene import LuceneSearcher
        self.json = json
        self.searcher = LuceneSearcher(str(index_path))
        self.num_docs = self.searcher.num_docs
        if self.num_docs != expected_documents:
            raise ValueError('full corpus size differs from the frozen distribution')

    def search(self, query, k):
        return [{'docid': str(hit.docid), 'score': hit.score,
                 'contents': self.json.loads(hit.lucene_document.get('raw'))['contents']}
                for hit in self.searcher.search(query, k)]

    def get_document(self, docid):
        doc = self.searcher.doc(docid)
        return None if doc is None else self.json.loads(doc.raw())['contents']
