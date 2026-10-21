"""Read every stored document and check BM25 I/O without any QA labels or LLM."""
import argparse
import datetime
import hashlib
import importlib.metadata
import json
import math
import resource
import time
from pathlib import Path

from download_browsecomp_assets import verify


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--index-root', type=Path, required=True)
    parser.add_argument('--download-report', type=Path, required=True)
    parser.add_argument('--expected-documents', type=int, default=100195)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError('keep prior verification attempts')
    start = time.monotonic()
    downloaded = json.loads(args.download_report.read_text())
    if downloaded['status'] != 'complete' or downloaded['kind'] != 'bm25':
        raise ValueError('complete pinned BM25 download required')
    result = {'status': 'running', 'started_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'index_revision': downloaded['revision'], 'model_calls': 0,
              'questions_loaded': 0, 'answer_or_label_columns_read': False,
              'source_download_report_sha256': hashlib.sha256(args.download_report.read_bytes()).hexdigest(),
              'script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    try:
        for asset in downloaded['files']:
            verify(args.index_root / asset['path'], asset)
        result['all_downloaded_assets_verified'] = True
        from pyserini.search.lucene import LuceneSearcher
        searcher = LuceneSearcher(str(args.index_root / 'bm25'))
        result['index_documents'] = searcher.num_docs
        if searcher.num_docs != args.expected_documents:
            raise ValueError('unexpected full-corpus document count')
        ids, total_bytes, total_characters, nonempty = set(), 0, 0, 0
        corpus_hash = hashlib.sha256()
        for ordinal in range(searcher.num_docs):
            doc = searcher.doc(ordinal)
            if doc is None:
                raise ValueError('missing stored document')
            raw = doc.raw()
            row = json.loads(raw)
            if not isinstance(row.get('id'), str) or not isinstance(row.get('contents'), str):
                raise ValueError('stored document schema mismatch')
            if row['id'] in ids:
                raise ValueError('duplicate external document id')
            ids.add(row['id'])
            data = row['contents'].encode('utf-8')
            total_bytes += len(data)
            total_characters += len(row['contents'])
            nonempty += bool(row['contents'].strip())
            corpus_hash.update(json.dumps([row['id'], hashlib.sha256(raw.encode()).hexdigest()],
                                          separators=(',', ':')).encode() + b'\n')
        if nonempty != searcher.num_docs:
            raise ValueError('empty stored documents require investigation')
        query = 'theory of evolution'
        hits = searcher.search(query, k=3)
        if not 0 < len(hits) <= 3:
            raise ValueError('positive search control returned no results')
        controls = []
        for hit in hits:
            raw = hit.lucene_document.get('raw')
            fetched = searcher.doc(str(hit.docid))
            if (str(hit.docid) not in ids or not math.isfinite(hit.score) or fetched is None
                    or json.loads(raw)['contents'] != json.loads(fetched.raw())['contents']):
                raise ValueError('search result and external-ID lookup disagree')
            controls.append({'docid': str(hit.docid), 'score': hit.score,
                             'raw_sha256': hashlib.sha256(raw.encode()).hexdigest()})
        absent = '__ai_harness_absent_document_20261021_953b01d6__'
        if searcher.doc(absent) is not None or searcher.search(absent, k=3):
            raise ValueError('negative control unexpectedly present')
        result.update(status='complete', unique_document_ids=len(ids), stored_documents_read=len(ids),
                      nonempty_documents=nonempty, content_utf8_bytes=total_bytes,
                      content_characters=total_characters, ordered_stored_content_sha256=corpus_hash.hexdigest(),
                      similarity=str(searcher.get_similarity()), control_query=query,
                      positive_control=controls, absent_id_and_query_controls=True,
                      package_versions={n: importlib.metadata.version(n) for n in ('pyserini', 'pyjnius', 'pyarrow')},
                      scope='Full stored-text integrity and generic retrieval I/O, not task relevance, '
                            'answer quality, original-paper ranking reproduction or a main experiment.')
    except Exception as error:
        result.update(status='failed', error_type=type(error).__name__)
        private = args.output.with_suffix('.private_error.txt')
        private.write_text(str(error))
        private.chmod(0o600)
    finally:
        result.update(finished_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                      wall_seconds=time.monotonic()-start,
                      process_maxrss_platform_units=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
        args.output.write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result))
    return 0 if result['status'] == 'complete' else 1


if __name__ == '__main__':
    raise SystemExit(main())
