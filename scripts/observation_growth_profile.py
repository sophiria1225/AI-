"""Describe replay exposure and repeated API requests without calling them waste.

Character lengths are not native token costs. Exact argument equality includes
authorization values; an equal later result is not an earlier cache contract.
No saved code, request, or private reasoning is executed or interpreted here.
"""
from collections import Counter
import json

from field_read_contract import READ_ONLY_APIS
from public_action_structure import digest
from recorded_action_agreement import action_value
from used_path_diagnosis import message_components, require


def compact_characters(value):
    return len(json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False))


class ObservationExposure:
    """Track each exact tool-message occurrence, including its transport identity."""
    def __init__(self):
        self.messages = {}
        self.ordinal = 0

    def add(self, request, ordinal):
        require(ordinal == self.ordinal + 1, 'chronological_request_ordinals_required')
        self.ordinal = ordinal
        if request is None:
            return dict(status='unavailable', components=None, tool_exposure=None)
        require(type(request) is dict, 'request_object_required')
        components = message_components(request.get('messages'))
        local = Counter(); new = replayed = occurrences = 0
        for message in request['messages']:
            if message['role'] != 'tool':
                continue
            # Keep all metadata in the identity. Never merge equal payloads from
            # distinct tool calls, or two occurrences in the same input.
            fingerprint = digest(message)
            local[fingerprint] += 1
            key = (fingerprint, local[fingerprint])
            count = len(message.get('content') or '')
            occurrences += 1
            if key not in self.messages:
                self.messages[key] = dict(message_sha256=fingerprint,
                    occurrence=local[fingerprint], characters=count,
                    first_input_ordinal=ordinal, last_input_ordinal=ordinal, exposures=0)
                new += count
            else:
                replayed += count
            entry = self.messages[key]
            entry['exposures'] += 1
            entry['last_input_ordinal'] = ordinal
        require(new + replayed == components['tool_content_characters'],
                'tool_character_partition_required')
        return dict(status='checked', components=components,
            tool_schema_compact_JSON_characters=compact_characters(request.get('tools', [])),
            tool_exposure=dict(occurrences=occurrences, first_seen_characters=new,
                replayed_characters=replayed, total_characters=new + replayed),
            token_attribution=False, removable_exposure_claim=False)

    def summary(self):
        rows = list(self.messages.values())
        return dict(unique_message_occurrences=len(rows), messages=rows,
            first_seen_characters=sum(r['characters'] for r in rows),
            replayed_characters=sum(r['characters'] * (r['exposures'] - 1) for r in rows),
            total_characters=sum(r['characters'] * r['exposures'] for r in rows),
            same_payload_with_distinct_transport_ids_not_collapsed=True,
            removable_exposure_claim=False)


def api_repetitions(events, spans):
    require(type(events) is list and len(events) <= 4000
            and type(spans) is dict and len(events) == len(spans), 'bounded_events_required')
    require(len({e['span_id'] for e in events}) == len(events)
            and set(spans) == {e['span_id'] for e in events}, 'complete_span_inventory_required')
    previous = {}; epoch = 0; rows = []; names = {}
    for event in events:
        if not event['api_request_sent']:
            # Unknown outer effects also break the conservative epoch.
            if event.get('effects_unknown'):
                epoch += 1
            continue
        span = spans[event['span_id']]; receipt = event.get('api_execution')
        require(event['stage'] == 'python_api' and span['id'] == event['span_id']
                and type(receipt) is dict and receipt.get('bridge_request_sent') is True
                and receipt.get('automatic_retries') == 0
                and receipt.get('status') in ('returned', 'raised', 'unknown'),
                'typed_actual_API_receipt_required')
        action = action_value(span['action']); name = action['name']
        status = receipt['status']; key = digest(action)
        result_key = digest(dict(status=status, observation=span['observation']))
        old = previous.get(key)
        reviewed_read = name in READ_ONLY_APIS
        candidate = bool(old and old['eligible'] and reviewed_read and status == old['status'] == 'returned'
                         and not event.get('effects_unknown') and old['epoch'] == epoch)
        same_result = (old['result_sha256'] == result_key if old
                       and status == old['status'] == 'returned' else None)
        row = dict(API_ordinal=len(rows) + 1, call_id=event['call'], span_id=span['id'],
            api=name, status=status, request_sha256=key, result_sha256=result_key,
            exact_request_seen_before=old is not None,
            previous_same_request_API_ordinal=old['ordinal'] if old else None,
            previous_same_request_call_id=old['call_id'] if old else None,
            same_returned_observation_as_previous=same_result,
            in_existing_six_read_handler_contract=reviewed_read,
            same_conservative_read_epoch_repeat=candidate,
            observation_compact_JSON_characters=compact_characters(span['observation']),
            cache_validity_or_savings_established=False)
        rows.append(row)
        by_name = names.setdefault(name, Counter())
        by_name['requests'] += 1
        by_name[status] += 1
        by_name['exact_request_repeats'] += int(old is not None)
        by_name['same_returned_observation_repeats'] += int(same_result is True)
        by_name['same_conservative_read_epoch_repeats'] += int(candidate)
        by_name['observation_compact_JSON_characters'] += row['observation_compact_JSON_characters']
        if not reviewed_read or status != 'returned' or event.get('effects_unknown'):
            epoch += 1
        previous[key] = dict(ordinal=row['API_ordinal'], call_id=event['call'],
            status=status, result_sha256=result_key, epoch=epoch,
            eligible=reviewed_read and status == 'returned' and not event.get('effects_unknown'))
    return dict(rows=rows, by_api={name:dict(counts) for name, counts in sorted(names.items())},
        requests=len(rows), exact_request_repeats=sum(r['exact_request_seen_before'] for r in rows),
        same_returned_observation_repeats=sum(r['same_returned_observation_as_previous'] is True for r in rows),
        same_conservative_read_epoch_repeats=sum(r['same_conservative_read_epoch_repeat'] for r in rows),
        no_request_or_result_substituted=True, ordinary_cache_candidates_not_new_method=True,
        runtime_state_equivalence_established=False, token_savings_established=False)


def summarize_call_characters(calls):
    checked = [c for c in calls if c['input']['status'] == 'checked']
    keys = checked[0]['input']['components'] if checked else ()
    fields = {key:sum(c['input']['components'][key] for c in checked)
              for key in keys if key.endswith('_characters')}
    return dict(input_character_exposures=fields,
        checked_requests=len(checked), unavailable_requests=len(calls) - len(checked),
        known_response_calls_with_no_API=sum(c['usage_status'] == 'ok' and c['API_requests'] == 0 for c in calls),
        API_free_calls_are_not_classified_as_waste=True)
