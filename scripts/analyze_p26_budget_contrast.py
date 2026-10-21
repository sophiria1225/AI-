"""Post-hoc one-case budget contrast; export aggregates, never private payloads."""
import argparse
import hashlib
import json
from pathlib import Path

from diagnose_p25_public_traces import sent_rows, photos
from analyze_p18_public_evidence import sha, recorded_operations


def common_prefix(left, right):
    n = 0
    for a, b in zip(left, right):
        if a != b:
            break
        n += 1
    return n


def public_message(response):
    message = response['message']
    return {k: message.get(k) for k in ('role', 'content', 'tool_calls')}


def analyze(storage, output):
    base = storage/'records/context_pilot'
    if json.loads((base/'P26_batch_v01/status.json').read_text())['status'] != 'complete':
        raise ValueError('wait for the complete batch')
    if output.exists():
        raise FileExistsError('preserve the previous diagnosis')
    records = []
    requests, messages, operations = [], [], []
    for rid in ('P25_01_GUIDED', 'P26_01_GUIDED'):
        p = base/rid
        spans = json.loads((p/'spans.json').read_text())
        events = json.loads((p/'events.json').read_text())
        summary = json.loads((p/'summary.json').read_text())
        rows = sent_rows(spans, events)
        calls = sorted(p.glob('call_*'))
        requests.append([json.loads((c/'request.json').read_text()) for c in calls])
        messages.append([public_message(json.loads((c/'response.json').read_text())) for c in calls])
        operations.append([{k: row[k] for k in ('name', 'args', 'data')} for row in rows])
        records.append(dict(run_id=rid, **recorded_operations(spans, events),
            photo_counts=photos(rows), model_calls=summary['model_calls'],
            known_total_tokens=summary['known_total_tokens'], wall_seconds=summary['wall_seconds'],
            official_success=json.loads((p/'evaluation.json').read_text())['official_success'],
            source_sha256={f: sha(p/f) for f in ('spans.json','events.json','summary.json','evaluation.json')},
            call_file_sha256={str(c.relative_to(p)/f):sha(c/f) for c in calls
                              for f in ('request.json','response.json')}))
    result = dict(phase='P26', all_one_reviewed=True, trials=records,
        identical_prefix=dict(model_requests=common_prefix(*requests),
                              public_model_messages=common_prefix(*messages),
                              sent_api_action_and_observation=common_prefix(*operations)),
        model_calls=0, environment_requests=0, evaluator_contents_read=False,
        script_sha256=sha(Path(__file__)),
        scope='One previously observed case and seed. Same seed does not guarantee the same path. '
              'Increasing the cap is not a proposed method or evidence of improved success at equal cost. '
              'Only public content/tool calls are compared; no model reasoning is exported.')
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ('phase','identical_prefix','all_one_reviewed')}))


if __name__ == '__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--storage-root',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();analyze(a.storage_root,a.output)
