"""Conservative ordinary completion monitor for one declared public task template.

Only the current public prefix is an input. The monitor neither reads a file nor
executes an API. The runner owns budgets and the one allowed completion request.
This hand-authored obligation check is not a general task interpreter.
"""
import hashlib
import json

from inspect_new_move_scope import inspect_records

SAFE_OTHER_APIS = frozenset({
    'api_docs__show_app_descriptions', 'api_docs__show_api_descriptions',
    'api_docs__show_api_doc', 'supervisor__show_account_passwords',
    'supervisor__show_profile', 'phone__get_current_date_and_time',
})


def prefix_digest(task, spans, events, usage):
    packet = {'task': task, 'spans': spans, 'events': events, 'usage': usage}
    return hashlib.sha256(json.dumps(packet, ensure_ascii=False, sort_keys=True,
        separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def check_prefix(task, spans, events, usage):
    """Return support only for complete, same-scope, current chronological evidence."""
    def unknown(reason): return {'trace_support': 'unknown', 'reasons': [reason]}
    if not usage or len(usage) > 80 or len(events) > 4000:
        return unknown('outside_bounded_prefix')
    ids = [u['id'] for u in usage]
    if ids != [f'call_{i:03d}' for i in range(1, len(ids)+1)]:
        return unknown('nonsequential_model_call_ids')
    if any(not u.get('usage_known') for u in usage):
        return unknown('unaccounted_model_call')
    if (len(events) != len(spans) or {e['span_id'] for e in events} != set(spans)
            or len({e['span_id'] for e in events}) != len(events)):
        return unknown('unaccounted_public_event')
    positions = {cid: n for n, cid in enumerate(ids)}
    ranks = [positions.get(e.get('call'), -1) for e in events]
    if -1 in ranks or ranks != sorted(ranks):
        return unknown('nonchronological_public_event')
    for e in events:
        if e.get('effects_unknown'):
            return unknown('unknown_effects')
        span = spans[e['span_id']]
        if span.get('observation', {}).get('declared_complete'):
            return unknown('completion_already_declared')
        if e.get('api_request_sent'):
            name = (span.get('action') or {}).get('name')
            if not isinstance(name, str): return unknown('missing_api_name')
            if not name.startswith('file_system__') and name not in SAFE_OTHER_APIS:
                return unknown('unhandled_other_app_effect')
    try:
        result = inspect_records(task, spans, [], events, usage,
            {'run_id': 'live_public_prefix', 'arm': 'ordinary_completion', 'success': None,
             'api_requests': sum(bool(e.get('api_request_sent')) for e in events), 'prefix_api_requests': 0})
    except (ValueError, TypeError, KeyError, OverflowError, AttributeError):
        return unknown('outside_declared_normalizer_scope')
    return result['final']
