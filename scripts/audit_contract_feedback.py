"""Reconstruct feedback from program-start schemas and ordered public receipts.

No saved generated code, model request, environment API or evaluator is run.
"""
from collections import Counter
import copy
import json
import math

from appworld_native_tools import NativeCatalog
from contract_comparison import CONDITIONS
from contract_feedback import canonical, make_feedback
from native_data_compute import selected_receipts
from recorded_python_replay import reply_from_receipt
from run_handoff_factors import read, sha


def validate_feedback(span, event, exposed, mode):
    base = copy.deepcopy(span)
    observed = base['observation'].pop('contract_feedback', None)
    expected = make_feedback({'action': base['action'], 'observation': base['observation'],
        'api_request_sent': event['api_request_sent'], 'effects_unknown': event['effects_unknown']},
        exposed, mode, 16000)
    if observed != expected:
        raise ValueError('feedback differs from the exact already-exposed contract or fixed policy')
    return base, expected


def feedback_summary(feedback):
    return {key: feedback[key] for key in ('api', 'mode', 'schema_sha256')} | {
        'characters': len(canonical(feedback))}


def audit_feedback_cell(trial, item, arm, tools, schemas):
    mode = CONDITIONS[arm][1]
    summary, events, spans, usage = (read(trial / n) for n in (
        'summary.json', 'events.json', 'spans.json', 'usage.json'))
    if 'contract_feedback' not in summary:
        if summary['stop_reason'] != 'setup_failure' or usage:
            raise ValueError('feedback runtime missing after setup')
        return {'programs_checked': 0, 'requests_checked': 0, 'feedback_events': [],
                'control_wall_seconds': 0, 'runtime_installed': False, 'source_sha256': {}}
    runtime = summary['contract_feedback']
    by_id = {event['span_id']: event for event in events}
    call_index = {call['id']: index for index, call in enumerate(usage)}
    catalog = NativeCatalog(tools)
    for event in item['prefix']['events']:
        catalog.visible.update(event['new_tools'])
    programs = requests = 0
    indices = Counter(); feedback_events = []; measured = []; hashes = {}
    checked_ids = []
    for event in events:
        if event['stage'] != 'model_tool':
            continue
        cid = event['call']; indices[cid] += 1
        outer = spans[event['span_id']]
        folder = trial / 'programs' / f'{cid}_{indices[cid]:02d}'
        if not folder.exists():
            if outer['action'] and outer['action']['name'] == 'run_python' and 'status' in outer['observation']:
                raise ValueError('executed program files missing')
            continue
        source, result = (read(folder / n) for n in ('input_private.json', 'result_private.json'))
        programs += 1
        number = len(item['programs']) + programs
        args = json.loads(outer['action']['arguments'])
        earlier = {**item['prefix']['spans'], **{e['span_id']: spans[e['span_id']] for e in events
                    if call_index[e['call']] < call_index[cid]}}
        prior = selected_receipts(args['span_ids'], earlier)
        if (source['code'] != args['code'] or source['observations'] != prior
                or source['program_index'] != number or result['program_index'] != number
                or source['api_schemas'] != {name: schemas[name] for name in catalog.visible}):
            raise ValueError('program source, prior receipts, boundary or exposed schema set differs')
        wire = [json.loads(line) for line in (folder / 'wire_private.jsonl').read_text().splitlines()]
        packets = [row for row in wire if row['kind'] == 'api']
        refs = outer['observation']['api_receipts']
        if len(packets) != len(refs):
            raise ValueError('recorded RPC/receipt correspondence differs')
        completed = bool(wire and wire[-1]['kind'] == 'done')
        if completed:
            if (len(wire) != len(packets) + 1 or wire[-1]['program_index'] != number
                    or any(wire[-1][k] != result[k] for k in ('stdout', 'stdout_truncated', 'error'))):
                raise ValueError('program wire completion differs from its stored result')
        elif result['status'] == 'ok' or result.get('session_usable'):
            raise ValueError('usable or successful program without a completion packet')
        for key in ('status', 'stdout', 'stdout_truncated', 'api_requests', 'declared_complete', 'unknown_effects'):
            if result[key] != outer['observation'][key]:
                raise ValueError('model-visible result differs from original program result')
        if outer['observation']['error'] != result.get('error', result.get('error_type')):
            raise ValueError('model-visible error differs from original program result')
        if result['api_requests'] != sum(by_id[ref['span_id']]['api_request_sent'] for ref in refs):
            raise ValueError('program API count differs from its receipts')
        for packet, ref in zip(packets, refs, strict=True):
            sid = ref['span_id']; inner = by_id[sid]; span = spans[sid]
            if (packet['program_index'] != number or inner['call'] != cid or inner['stage'] != 'python_api'
                    or ref['api'] != span['action']['name'] or ref['api_request_sent'] != inner['api_request_sent']):
                raise ValueError('program request identity or linkage differs')
            base, feedback = validate_feedback(span, inner, {name: schemas[name] for name in catalog.visible}, mode)
            if inner['effects_unknown']:
                if (base['action']['name'] != packet['app'] + '__' + packet['api']
                        or json.loads(base['action']['arguments']) != packet['arguments'] or feedback is not None):
                    raise ValueError('unknown-effect receipt or feedback differs')
            else:
                reply_from_receipt(packet, base, inner, schemas)
            requests += 1; checked_ids.append(sid)
            if feedback is not None:
                measured.append(feedback_summary(feedback))
                next_index = call_index[cid] + 1
                following = usage[next_index]['id'] if next_index < len(usage) else None
                visible = None
                if following:
                    messages = read(trial / following / 'request.json')['messages']
                    raw = canonical(feedback)
                    encoded = json.dumps(raw, ensure_ascii=False)[1:-1]
                    visible = any(raw in (m.get('content') or '') or encoded in (m.get('content') or '') for m in messages)
                feedback_events.append({**feedback_summary(feedback), 'call_id': cid, 'span_id': sid,
                    'next_call_id': following, 'canonical_feedback_in_immediate_next_input': visible,
                    'transmission_is_inferred_from_frozen_code_and_receipts': True,
                    'new_model_call_for_feedback': False})
            catalog.visible.update(inner['new_tools'])
        for name in ('input_private.json', 'result_private.json', 'wire_private.jsonl'):
            hashes[str((folder / name).relative_to(trial))] = sha(folder / name)
    if checked_ids != [e['span_id'] for e in events if e['stage'] == 'python_api']:
        raise ValueError('not every recorded inner request was checked exactly once')
    if (runtime['mode'] != mode or runtime['checked_requests'] != requests
            or runtime['feedback_events'] != measured
            or any(runtime[k] != 0 for k in ('automatic_retries', 'extra_model_calls', 'extra_environment_requests'))
            or type(runtime['control_wall_seconds']) not in (int, float)
            or not math.isfinite(runtime['control_wall_seconds']) or runtime['control_wall_seconds'] < 0):
        raise ValueError('feedback counters or charged controller time differ')
    return {'programs_checked': programs, 'requests_checked': requests, 'feedback_events': feedback_events,
            'control_wall_seconds': runtime['control_wall_seconds'], 'runtime_installed': True,
            'source_sha256': hashes, 'code_programs_reexecuted': 0, 'environment_api_requests': 0}
