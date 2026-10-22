"""Apply the unchanged P67 checker to only the current accounted public prefix."""
from ordinary_completion_control import prefix_digest
from public_export_evidence import inspect_export


def check_prefix(task, spans, events, usage):
    def unknown(reason): return {'trace_support': 'unknown', 'reasons': [reason]}
    if not usage or len(usage) > 80 or len(events) > 4000:
        return unknown('outside_bounded_prefix')
    if [u.get('id') for u in usage] != [f'call_{n:03d}' for n in range(1, len(usage)+1)]:
        return unknown('nonsequential_model_call_ids')
    if any(not u.get('usage_known') or u.get('status', 'ok') != 'ok' for u in usage):
        return unknown('unaccounted_or_failed_model_call')
    if any(s.get('observation', {}).get('declared_complete') for s in spans.values()):
        return unknown('completion_already_declared')
    try:
        result = inspect_export(task, spans, events, usage)
    except (ValueError, TypeError, KeyError, OverflowError, AttributeError):
        return unknown('outside_declared_normalizer_scope')
    return result['final']
