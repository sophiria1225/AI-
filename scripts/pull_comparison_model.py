"""Download the explicitly selected local model; retain terminal status and metadata."""
import datetime
import json
import pathlib
import time
import urllib.request

root = pathlib.Path(__file__).resolve().parents[1]
out = root / 'records/models' / datetime.datetime.now().strftime('%Y%m%d_%H%M%S_qwen27b')
out.mkdir(parents=True)
model = 'qwen3.8:27b-mlx'
started = time.monotonic()
summary = {'model': model, 'started_at': datetime.datetime.now(datetime.timezone.utc).isoformat()}
def request(path, data=None):
    return urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:11434/api/' + path,
        data=None if data is None else json.dumps(data).encode(),
        headers={'Content-Type': 'application/json'}), timeout=120)
try:
    last_print = 0
    terminal = None
    with request('pull', {'model': model, 'stream': True}) as response, (out / 'pull_events.jsonl').open('wb') as events:
        for line in response:
            events.write(line)
            event = json.loads(line)
            if 'error' in event:
                raise RuntimeError(event['error'])
            if time.monotonic() - last_print >= 20:
                print(json.dumps({'elapsed': round(time.monotonic()-started), **event}), flush=True)
                last_print = time.monotonic()
            terminal = event
    if not terminal or terminal.get('status') != 'success':
        raise RuntimeError('pull did not end successfully')
    with request('tags') as response:
        summary['installed_model'] = next(m for m in json.load(response)['models'] if m['name'] == model)
    with request('show', {'model': model}) as response:
        metadata = json.load(response)
    (out / 'show.json').write_text(json.dumps(metadata, indent=2) + '\n')
    summary['status'] = 'success'
except Exception as error:
    summary.update(status='error', error=repr(error))
finally:
    summary['elapsed_seconds'] = time.monotonic() - started
    (out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(summary), flush=True)
raise SystemExit(0 if summary['status'] == 'success' else 1)
