"""Read and pin public metadata/code; never download task rows or execute upstream code."""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import urllib.request


DATASETS = ['Tevatron/browsecomp-plus', 'Tevatron/browsecomp-plus-corpus',
            'Tevatron/browsecomp-plus-indexes']
PUBLIC_CODE = ['README.md', 'pyproject.toml', 'scripts_build_index/download_indexes.sh',
               'scripts_build_index/decrypt_dataset.py', 'docs/llm_as_judge.md',
               'scripts_evaluation/evaluate_run.py']


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source-dir', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.source_dir.mkdir(parents=True, exist_ok=False)
    sources = []

    def get(url, name, as_json=False):
        request = urllib.request.Request(url, headers={'User-Agent': 'AI-harness-research-metadata'})
        with urllib.request.urlopen(request, timeout=30) as response:
            if 'rel="next"' in response.headers.get('Link', ''):
                raise ValueError('metadata pagination requires explicit handling')
            data = response.read(1048577)
            if len(data) > 1048576:
                raise ValueError('refusing unexpectedly large metadata/source')
        (args.source_dir / name).write_bytes(data)
        sources.append({'url': url, 'local_name': name, 'bytes': len(data), 'sha256': sha(data)})
        return json.loads(data) if as_json else data.decode('utf-8')

    datasets = []
    for identifier in DATASETS:
        prefix = identifier.rsplit('/', 1)[1]
        meta = get('https://huggingface.co/api/datasets/' + identifier, prefix + '_metadata.json', True)
        revision = meta['sha']
        tree = get(f'https://huggingface.co/api/datasets/{identifier}/tree/{revision}?recursive=true',
                   prefix + '_tree.json', True)
        files = [{k: row[k] for k in ('path', 'size', 'oid', 'lfs') if k in row}
                 for row in tree if row['type'] == 'file']
        datasets.append({'identifier': identifier, 'revision': revision,
                         'private': meta['private'], 'gated': meta['gated'],
                         'license_declared': meta.get('cardData', {}).get('license'),
                         'last_modified': meta.get('lastModified'), 'files': files,
                         'all_file_bytes': sum(row['size'] for row in files),
                         'parquet_bytes': sum(row['size'] for row in files if row['path'].endswith('.parquet'))})
    ref = get('https://api.github.com/repos/texttron/BrowseComp-Plus/git/ref/heads/main',
              'upstream_reference.json', True)
    revision = ref['object']['sha']
    for path in PUBLIC_CODE:
        get(f'https://raw.githubusercontent.com/texttron/BrowseComp-Plus/{revision}/{path}',
            path.replace('/', '__'))
    result = {'checked_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'datasets': datasets, 'upstream_code_commit': revision, 'sources': sources,
              'script_sha256': sha(Path(__file__).read_bytes()),
              'model_calls': 0, 'upstream_code_executed': False,
              'task_rows_downloaded': 0, 'corpus_shards_downloaded': 0,
              'scope': 'Metadata and listed public code/documentation only. Declared file bytes are '
                       'not expanded working-space, index or model requirements. No task selection, '
                       'accuracy, source-license clearance or runtime feasibility claim.'}
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'datasets': [{k: d[k] for k in ('identifier', 'revision', 'parquet_bytes', 'gated')}
                                  for d in datasets], 'source_files': len(sources), 'model_calls': 0}))


if __name__ == '__main__':
    main()
