"""Conservative content matching for API-documentation-only stdout.

An exact content match is not a proof of future irrelevance. The view keeps
the original archive and never substitutes summaries or a guessed schema.
"""
import copy
import json

from handoff_factors import split_turns
from handoff_output_views import make_view
from native_conversation import NativeConversation, recover_turn

DOCUMENTATION_APIS = {'api_docs__show_api_doc', 'api_docs__show_api_descriptions',
                     'api_docs__show_app_descriptions'}


def match_documentation_stdout(observation, spans, events_by_id):
    if (type(observation) is not dict or observation.get('status') != 'ok'
            or observation.get('error') or observation.get('stdout_truncated')
            or observation.get('unknown_effects') or observation.get('declared_complete')
            or not isinstance(observation.get('stdout'), str) or not observation['stdout']):
        return {'matched': False, 'reason': 'not_complete_successful_stdout'}
    receipts = observation.get('api_receipts')
    if not isinstance(receipts, list) or not receipts:
        return {'matched': False, 'reason': 'no_documentation_receipts'}
    values, raw_values = [], []
    for receipt in receipts:
        sid = receipt.get('span_id')
        if sid not in spans or sid not in events_by_id:
            raise ValueError('missing public receipt correspondence')
        span, event = spans[sid], events_by_id[sid]
        action, obs = span.get('action'), span.get('observation')
        if (not isinstance(action, dict) or action.get('name') not in DOCUMENTATION_APIS
                or event.get('stage') != 'python_api' or not event.get('api_request_sent')
                or event.get('effects_unknown') or not receipt.get('api_request_sent')
                or receipt.get('api') != action.get('name')
                or not isinstance(obs, dict) or 'observation' not in obs
                or not set(obs) <= {'observation', 'declared_complete'} or obs.get('declared_complete')):
            return {'matched': False, 'reason': 'mixed_non_documentation_or_failed_receipts'}
        value = obs['observation']; raw_values.append(value)
        if isinstance(value, str):
            try: value = json.loads(value)
            except ValueError: pass
        if not isinstance(value, (dict, list)) or (
                isinstance(value, dict) and ('error' in value or 'detail' in value)):
            return {'matched': False, 'reason': 'unrecognized_or_error_documentation_payload'}
        values.append(value)
    # Match the entire output, not an embedded schema substring. Only explicit
    # deterministic serializations are recognized; mixed narration stays.
    variants = {'python_print': ''.join(str(v) + '\n' for v in values),
                'raw_print': ''.join(str(v) + '\n' for v in raw_values)}
    for ascii_mode in (False, True):
        for indent in (None, 2, 4):
            variants[f'json_{ascii_mode}_{indent}'] = ''.join(
                json.dumps(v, ensure_ascii=ascii_mode, indent=indent) + '\n' for v in values)
        variants[f'compact_json_{ascii_mode}'] = ''.join(
            json.dumps(v, ensure_ascii=ascii_mode, separators=(',', ':')) + '\n' for v in values)
    styles = sorted(name for name, value in variants.items() if value == observation['stdout'])
    return {'matched': bool(styles), 'reason': 'whole_documentation_content_match' if styles else 'stdout_not_exact_documentation',
            'renderers': styles, 'documentation_receipts': len(values)}


def views(prefix):
    full, _ = make_view(prefix['conversation_private'], prefix['public_task'], 'full_keep')
    masked, general_meta = make_view(prefix['conversation_private'], prefix['public_task'], 'stdout_mask_keep')
    full_turns, masked_turns = split_turns(full.messages()), split_turns(masked.messages())
    candidate_ids = {r['span_id'] for r in general_meta['masked_spans']}
    events = {e['span_id']: e for e in prefix['events']}
    selected = NativeConversation(full.messages()[0]['content'], prefix['public_task'])
    checks = []
    for number, (before, after) in enumerate(zip(full_turns, masked_turns, strict=True), 1):
        spans, omitted = recover_turn(before), recover_turn(after)
        for span, replacement in zip(spans, omitted, strict=True):
            if span['id'] not in candidate_ids: continue
            match = match_documentation_stdout(span['observation'], prefix['spans'], events)
            checks.append({'turn': number, 'span_id': span['id'],
                           'stdout_characters': len(span['observation']['stdout']), **match})
            if match['matched']:
                span['observation'] = copy.deepcopy(replacement['observation'])
        selected.append(before[0], spans)
    return {'full_keep': full, 'all_stdout_mask_keep': masked, 'documentation_stdout_mask_keep': selected}, {
        'candidate_outputs': len(candidate_ids), 'matched_documentation_outputs': sum(r['matched'] for r in checks),
        'checks': checks, 'source_archive_modified': False, 'new_runtime_or_tool_calls': 0,
        'future_relevance_claim': False, 'quality_preservation_claim': False,
        'common_notice_in_all_views': True, 'latest_complete_turn_retained': True}
