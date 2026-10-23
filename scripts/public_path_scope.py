"""Describe executed public code and API paths without executing or simplifying them.

Zero API calls can contain necessary local computation. Equal observed replies do
not establish a read contract, validity after mutations, or removable generation.
Only syntax, aggregate lengths and digests leave the recorded public trace.
"""
import ast
from collections import Counter
import hashlib
import json
import re

from inspect_terminal_cost_scope import cost


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     allow_nan=False).encode()).hexdigest()


def callable_name(node):
    if isinstance(node, ast.Name): return node.id
    if isinstance(node, ast.Attribute):
        base = callable_name(node.value)
        return base + '.' + node.attr if base else '<expression>.' + node.attr
    return '<expression>'


def source_shape(source):
    if type(source) is not str or not 0 < len(source) <= 20000:
        raise ValueError('source_size_or_type')
    result = {'source_sha256': hashlib.sha256(source.encode()).hexdigest(),
              'characters': len(source), 'executed_by_inspector': False}
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return {**result, 'status': 'syntax_error', 'line': exc.lineno, 'offset': exc.offset}
    nodes = list(ast.walk(tree))
    if len(nodes) > 5000: raise ValueError('ast_node_limit')
    calls = Counter(callable_name(n.func) for n in nodes if isinstance(n, ast.Call))
    return {**result, 'status': 'parsed', 'ast_nodes': len(nodes),
            'top_level_statements': [type(n).__name__ for n in tree.body],
            'call_syntax': dict(sorted(calls.items())),
            'load_name_counts': dict(sorted(Counter(n.id for n in nodes
                if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)).items())),
            'store_names': sorted({n.id for n in nodes if isinstance(n, ast.Name)
                                   and isinstance(n.ctx, ast.Store)}),
            'control_syntax': dict(sorted(Counter(type(n).__name__ for n in nodes
                if isinstance(n, (ast.For, ast.While, ast.If, ast.Try, ast.With,
                                  ast.FunctionDef, ast.Lambda, ast.comprehension))).items())),
            'no_semantic_safety_or_liveness_inference': True}


def exception_type(value):
    if value is None: return None
    if type(value) is not str: raise ValueError('unexpected_error_metadata')
    name = value.split(':', 1)[0]
    return name if re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]*', name) else 'unclassified'


def inspect_cell(events, spans, usage, expected):
    ids = [u['id'] for u in usage]
    event_ids = [e['span_id'] for e in events]
    if (len(ids) != len(set(ids)) or len(event_ids) != len(set(event_ids))
            or any(e['call'] not in ids or e['span_id'] not in spans or e.get('effects_unknown') for e in events)):
        raise ValueError('unlinked_duplicate_or_unknown_event')
    by_id = {e['span_id']: e for e in events}
    linked = set(); programs = []; calls = []; repeats = []; seen = {}; sent_order = []
    for event in events:
        span = spans[event['span_id']]
        if event['stage'] not in ('python_api', 'model_tool'):
            raise ValueError('unexpected_event_stage')
        if event['stage'] == 'python_api' and event['api_request_sent']:
            action = span['action']; key = (action['name'], digest(json.loads(action['arguments'])))
            observation_hash = digest(span['observation'])
            if key in seen:
                old = seen[key]
                repeats.append({'api': key[0], 'arguments_sha256': key[1],
                    'previous_span_id': old['span_id'], 'span_id': event['span_id'],
                    'previous_call_id': old['call_id'], 'call_id': event['call'],
                    'same_observation': old['observation_sha256'] == observation_hash,
                    'previous_observation_sha256': old['observation_sha256'],
                    'observation_sha256': observation_hash,
                    'intervening_sent_api_names': dict(sorted(Counter(sent_order[old['position'] + 1:]).items())),
                    'safe_to_cache_or_omit': None})
            seen[key] = {'span_id': event['span_id'], 'call_id': event['call'],
                         'position': len(sent_order), 'observation_sha256': observation_hash}
            sent_order.append(action['name'])
    for u in usage:
        entries = [e for e in events if e['call'] == u['id']]
        known = u['status'] == 'ok'
        if known:
            if (any(type(u[k]) is not int or u[k] < 0 for k in
                    ('input_tokens', 'output_tokens', 'cached_input_tokens'))
                    or u['cached_input_tokens'] > u['input_tokens']):
                raise ValueError('invalid_known_cost')
        elif entries or u['input_tokens'] is not None or u['output_tokens'] is not None:
            raise ValueError('unknown_usage_executed_or_imputed')
        sent = [e for e in entries if e['api_request_sent']]
        outer = [e for e in entries if e['stage'] == 'model_tool']
        for e in outer:
            span = spans[e['span_id']]; action = span['action']; observation = span['observation']
            if not action or action['name'] != 'run_python': continue
            args = json.loads(action['arguments'])
            p = {'call_id': u['id'], 'span_id': e['span_id'], 'shape': source_shape(args['code']),
                 'status': observation.get('status', 'not_executed_or_rejected'),
                 'selected_prior_receipts': len(args.get('span_ids', [])),
                 'stdout_characters': len(observation.get('stdout', '')),
                 'stdout_lines': len(observation.get('stdout', '').splitlines()),
                 'stdout_truncated': observation.get('stdout_truncated'),
                 'exception_type': exception_type(observation.get('error'))}
            api_events = []
            for receipt in observation.get('api_receipts', []):
                sid = receipt['span_id']; inner = by_id.get(sid)
                if (sid in linked or not inner or inner['stage'] != 'python_api'
                        or inner['call'] != u['id'] or event_ids.index(sid) >= event_ids.index(e['span_id'])
                        or receipt['api'] != spans[sid]['action']['name']
                        or receipt['api_request_sent'] != inner['api_request_sent']):
                    raise ValueError('invalid_program_receipt_link')
                linked.add(sid); api_events.append(inner)
            sent_inner = [a for a in api_events if a['api_request_sent']]
            if 'api_requests' in observation and observation['api_requests'] != len(sent_inner):
                raise ValueError('program_api_count_disagrees')
            p['sent_api_names'] = dict(sorted(Counter(spans[a['span_id']]['action']['name'] for a in sent_inner).items()))
            p['sent_api_requests'] = len(sent_inner)
            p['unsent_api_events'] = len(api_events) - len(sent_inner)
            programs.append(p)
        calls.append({'call_id': u['id'], 'usage_status': u['status'],
            'input_tokens': u['input_tokens'], 'output_tokens': u['output_tokens'],
            'cached_input_tokens': u['cached_input_tokens'],
            'known_total_tokens': u['input_tokens'] + u['output_tokens'] if known else None,
            'model_request_wall_seconds': u['wall_seconds'],
            'sent_api_requests': len(sent),
            'sent_api_names': dict(sorted(Counter(spans[e['span_id']]['action']['name'] for e in sent).items())),
            'model_tool_counts': dict(sorted(Counter((spans[e['span_id']]['action'] or {}).get('name', '<none>') for e in outer).items())),
            'category': 'unknown_usage_unexecuted' if not known else
                'known_with_sent_api' if sent else 'known_without_sent_api'})
    if linked != {e['span_id'] for e in events if e['stage'] == 'python_api'}:
        raise ValueError('unassigned_inner_api_event')
    total = cost(calls)
    for key, source_key in [('model_calls','model_calls'),('known_total_tokens','known_total_tokens'),
                            ('unknown_usage_calls','unknown_usage_calls'),('sent_api_requests','api_requests')]:
        if total[key] != expected[source_key]: raise ValueError('original_all_call_total_disagrees')
    if (dict(Counter(p['status'] for p in programs)) != expected['program_status_counts']
            or len(repeats) != expected['repeat_identical_request_excess']):
        raise ValueError('original_program_or_repeat_total_disagrees')
    return {'run_id': expected['run_id'], 'task_id': expected['task_id'], 'arm': expected['arm'],
            'original_success': expected['success'], 'original_stop_reason': expected['stop_reason'],
            'calls': calls, 'programs': programs, 'repeated_requests': repeats, 'total': total,
            'partition': {category: cost([c for c in calls if c['category'] == category]) for category in
                ('known_with_sent_api', 'known_without_sent_api', 'unknown_usage_unexecuted')},
            'measured_savings': None, 'safe_omission_verified': False}
