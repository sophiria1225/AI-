"""Posthoc known-field and complete-response scope for the fixed CSV request.

Pure analysis of public receipts. It neither executes nor suppresses calls.
Whole-object equality is checked AFTER the response; it is not an online oracle.
No observed opportunity is reported as token savings or a removable generation.
"""
from collections import Counter
import hashlib
import json

from inspect_public_move_scope import payload
from public_export_evidence import SAFE_OTHER, TEMPLATE

READS = frozenset({'spotify__show_song', 'spotify__show_album', 'spotify__show_playlist',
    'spotify__show_song_library', 'spotify__show_album_library', 'spotify__show_playlist_library'})
OTHER_SAFE = SAFE_OTHER | frozenset({'spotify__login', 'file_system__login',
    'file_system__create_directory', 'file_system__create_file', 'file_system__read_file'})


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
        separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def song_pair(value):
    if not isinstance(value, dict) or type(value.get('song_id')) is not int or value['song_id'] <= 0:
        return None
    artists = value.get('artists')
    if (not isinstance(value.get('title'), str) or not isinstance(artists, list) or not artists
            or any(not isinstance(a, dict) or not isinstance(a.get('name'), str)
                or not a['name'] or '|' in a['name'] for a in artists)):
        return None
    return value['title'], '|'.join(a['name'] for a in artists)


def analyze(task, spans, events, usage):
    if task.get('ground_truth_loaded') is not False or not TEMPLATE.fullmatch(task.get('instruction', '')):
        raise ValueError('single declared public request required')
    if len(events) > 4000 or len(usage) > 80:
        raise ValueError('fixed public-record bound exceeded')
    positions = {u['id']: n for n, u in enumerate(usage)}
    ranks = [positions.get(e['call'], -1) for e in events]
    if (len(positions) != len(usage) or -1 in ranks or ranks != sorted(ranks)
            or len(events) != len(spans) or len({e['span_id'] for e in events}) != len(events)
            or {e['span_id'] for e in events} != set(spans)):
        raise ValueError('complete chronological records required')
    pairs = {}; objects = {}; exact = {}; reasons = set(); scope = None; source_ids = set()
    rows = []; sent = Counter(); by_call = {u['id']: [] for u in usage}

    def remember(value, ordinal):
        pair = song_pair(value)
        if pair is None:
            return
        sid = value['song_id']
        if sid in pairs and pairs[sid]['pair'] != pair:
            reasons.add('changed_song_metadata')
        pairs[sid] = {'pair': pair, 'event': ordinal}
        objects.setdefault(sid, set()).add(digest(value))
        if len(pairs) > 512:
            raise ValueError('fixed song-ID bound exceeded')

    for ordinal, event in enumerate(events, 1):
        reasons_before = set(reasons)
        if event.get('effects_unknown'):
            reasons.add('unknown_effects')
        if not event.get('api_request_sent'):
            continue
        span = spans[event['span_id']]; action = span.get('action') or {}
        name = action.get('name'); args = action.get('arguments')
        if isinstance(args, str):
            args = json.loads(args)
        if not isinstance(name, str) or not isinstance(args, dict):
            raise ValueError('sent action lacks public name or arguments')
        sent[name] += 1; by_call[event['call']].append(name)
        value = payload(span)
        if name not in READS:
            if name not in OTHER_SAFE:
                reasons.add('unhandled_effect:' + name)
            continue
        receipt = span['observation']
        receipt_ok = (not event.get('effects_unknown') and receipt.get('status', 'ok') == 'ok'
            and 'api_error' not in receipt)
        if not receipt_ok:
            reasons.add('unconfirmed_read_receipt')
        if name not in ('spotify__show_song', 'spotify__show_album'):
            token = args.get('access_token')
            if not isinstance(token, str) or not token:
                reasons.add('missing_credential_scope')
            else:
                current = digest(token)
                if scope is not None and scope != current:
                    reasons.add('changed_credential_scope')
                scope = current

        if name.endswith('_library') and receipt_ok and isinstance(value, list):
            for item in value:
                ids = ([item.get('song_id')] if name == 'spotify__show_song_library'
                       else item.get('song_ids')) if isinstance(item, dict) else None
                if not isinstance(ids, list) or any(type(i) is not int or i <= 0 for i in ids):
                    reasons.add('unsupported_source_membership')
                else:
                    source_ids.update(ids)
            if len(source_ids) > 512:
                raise ValueError('fixed source-ID bound exceeded')

        if name == 'spotify__show_song':
            sid = args.get('song_id'); valid_request = set(args) == {'song_id'} and type(sid) is int and sid > 0
            prior_pair = pairs.get(sid) if type(sid) is int else None
            signature = digest([name, args]); prior_exact = exact.get(signature)
            clean_before = not reasons_before
            row = {'event_ordinal': ordinal, 'call_id': event['call'], 'request_sha256': signature,
                'request_supported': valid_request, 'evidence_untainted_before': clean_before,
                'taint_reasons_before': sorted(reasons_before),
                'source_membership_observed_before': valid_request and sid in source_ids,
                'task_fields_known_before': valid_request and clean_before and sid in source_ids and prior_pair is not None,
                'prior_task_fields_event': prior_pair['event'] if prior_pair else None,
                'same_request_response_known_before': valid_request and clean_before and prior_exact is not None}
            pair = song_pair(value)
            valid_response = receipt_ok and valid_request and pair is not None and value['song_id'] == sid
            row.update(response_supported=valid_response,
                task_fields_unchanged_after=(pair == prior_pair['pair']) if valid_response and prior_pair else None,
                same_request_response_equal_after=(digest(value) == prior_exact) if valid_response and prior_exact else None,
                prior_complete_object_equal_after=(digest(value) in objects.get(sid, set())) if valid_response else None,
                response_field_names=sorted(value) if isinstance(value, dict) else [])
            if not valid_request:
                reasons.add('unsupported_show_song_arguments')
            elif not valid_response:
                reasons.add('unsupported_or_mismatched_song_response')
            else:
                if prior_exact is not None and digest(value) != prior_exact:
                    reasons.add('changed_same_request_response')
                remember(value, ordinal)
                exact[signature] = digest(value)
            row['taint_reasons_after'] = sorted(reasons); rows.append(row)
        elif name == 'spotify__show_song_library':
            if receipt_ok and isinstance(value, list):
                for song in value:
                    remember(song, ordinal)
        elif name in ('spotify__show_album', 'spotify__show_playlist'):
            key = 'album_id' if name.endswith('show_album') else 'playlist_id'
            if receipt_ok and isinstance(value, dict) and value.get(key) == args.get(key) and isinstance(value.get('songs'), list):
                for song in value['songs']:
                    remember(song, ordinal)
    grouped = []
    for call in usage:
        current = [r for r in rows if r['call_id'] == call['id']]
        only_songs = bool(current) and len(current) == len(by_call[call['id']])
        grouped.append({'call_id': call['id'], 'sent_apis': len(by_call[call['id']]),
            'show_song_requests': len(current),
            'all_sent_requests_are_show_song_with_preknown_task_fields': only_songs and all(r['task_fields_known_before'] for r in current),
            'all_sent_requests_have_matching_prior_same_request_responses': only_songs and all(
                r['same_request_response_known_before'] and r['same_request_response_equal_after'] is True for r in current),
            'usage_known': call['usage_known'],
            'known_total_tokens': call['input_tokens'] + call['output_tokens'] if call['usage_known'] else None})
    return {'show_song_requests': len(rows), 'sent_api_counts': dict(sent), 'requests': rows,
        'requests_without_prior_source_membership': sum(not r['source_membership_observed_before'] for r in rows),
        'task_fields_preknown_requests': sum(r['task_fields_known_before'] for r in rows),
        'preknown_task_fields_matching_response': sum(r['task_fields_known_before'] and r['task_fields_unchanged_after'] is True for r in rows),
        'same_request_response_preknown_requests': sum(r['same_request_response_known_before'] for r in rows),
        'same_request_response_matching_after': sum(r['same_request_response_known_before'] and r['same_request_response_equal_after'] is True for r in rows),
        'preknown_task_fields_without_equal_complete_object': sum(r['task_fields_known_before'] and r['response_supported'] and r['prior_complete_object_equal_after'] is False for r in rows),
        'posthoc_prior_complete_object_equal': sum(r['response_supported'] and r['evidence_untainted_before'] and r['prior_complete_object_equal_after'] is True for r in rows),
        'unsupported_responses': sum(not r['response_supported'] for r in rows),
        'final_taint_reasons': sorted(reasons), 'model_boundaries': grouped,
        'observed_logical_tokens': sum(r['known_total_tokens'] or 0 for r in grouped),
        'unknown_usage_calls': sum(not r['usage_known'] for r in grouped),
        'task_metadata_ids_observed': len(pairs), 'measured_savings': None,
        'can_remove_any_model_generation_established': False}
