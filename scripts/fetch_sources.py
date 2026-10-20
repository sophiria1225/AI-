"""Download small official sources with hashes and an audit manifest."""
import concurrent.futures
import datetime
import hashlib
import json
import pathlib
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / 'records' / 'sources'
SOURCES = {
 'swebench_readme': 'https://raw.githubusercontent.com/SWE-bench/SWE-bench/main/README.md',
 'swebench_pyproject': 'https://raw.githubusercontent.com/SWE-bench/SWE-bench/main/pyproject.toml',
 'mini_readme': 'https://raw.githubusercontent.com/SWE-agent/mini-swe-agent/main/README.md',
 'mini_pyproject': 'https://raw.githubusercontent.com/SWE-agent/mini-swe-agent/main/pyproject.toml',
 'verified_metadata': 'https://huggingface.co/api/datasets/princeton-nlp/SWE-bench_Verified',
 'verified_files': 'https://huggingface.co/api/datasets/princeton-nlp/SWE-bench_Verified/tree/main?recursive=true',
 'colima_readme': 'https://raw.githubusercontent.com/abiosoft/colima/main/README.md',
 'qwen_existing_readme': 'https://huggingface.co/Qwen/Qwen3.8-Flash-Next/raw/main/README.md',
 'qwen_27b_readme': 'https://huggingface.co/Qwen/Qwen3.8-27B/raw/main/README.md',
 'maas_proceedings': 'https://proceedings.mlr.press/v267/zhang25bi.html',
}

def fetch(item):
    name, url = item
    record = {'name': name, 'url': url, 'retrieved_at': datetime.datetime.now(datetime.timezone.utc).isoformat()}
    try:
        request = urllib.request.Request(url, headers={'User-Agent':'HarnessResearchFeasibility/0.1'})
        with urllib.request.urlopen(request, timeout=30) as response:
            content = response.read(2_000_001)
            if len(content) > 2_000_000:
                raise ValueError('source exceeds 2MB limit')
            record.update(http_status=response.status, final_url=response.url, content_type=response.headers.get('Content-Type'))
        path = OUT / (name + '_full.txt')
        path.write_bytes(content)
        record.update(path=str(path.relative_to(ROOT)), bytes=len(content), sha256=hashlib.sha256(content).hexdigest(), status='saved')
    except Exception as error:
        record.update(status='error', error=repr(error))
    return record

OUT.mkdir(parents=True, exist_ok=True)
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
    records = list(pool.map(fetch, SOURCES.items()))
(OUT / 'manifest.json').write_text(json.dumps(records, ensure_ascii=False, indent=2) + '\n')
for record in records:
    print(json.dumps(record, ensure_ascii=False))
