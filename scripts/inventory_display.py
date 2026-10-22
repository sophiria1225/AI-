"""P55 matched display controls; API inventories and details are separate axes.

Only the old, fully attributed documentation segments are eligible. This is a
development ablation of ordinary disclosure, not a novel retention algorithm.
"""
import copy
import json
import time

from context_preservation import compact
from documentation_comparison import OriginBudgetInference
from documentation_print_origin import build_origin_view
from handoff_factors import split_turns
from input_exposure_accounting import digest
from native_conversation import NativeConversation, recover_turn
from residual_output_budget import ResidualInference

ARMS = ('full_keep', 'details_omitted_keep', 'details_and_listings_omitted_keep')
LISTINGS = {'api_docs__show_api_descriptions', 'api_docs__show_app_descriptions'}


def build_condition(item, arm):
    if arm not in ARMS:
        raise ValueError('unknown inventory-display condition')
    started = time.monotonic()
    views, recognition = build_origin_view(item)
    full = views['full_keep']
    details, listings = set(), set()
    prefix = item['prefix']
    for event in prefix['events']:
        if event['stage'] != 'python_api':
            continue
        action = prefix['spans'][event['span_id']]['action']
        if action['name'] in LISTINGS:
            listings.add(event['span_id'])
        elif action['name'] == 'api_docs__show_api_doc':
            arguments = json.loads(action['arguments'])
            if arguments.get('app_name') not in ('api_docs', 'supervisor'):
                details.add(event['span_id'])
    eligible = (set() if arm == ARMS[0] else details if arm == ARMS[1] else details | listings)
    checks = {row['span_id']: row for row in recognition['checks']}
    output = NativeConversation(full.messages()[0]['content'], prefix['public_task'])
    changes = []
    for turn in split_turns(full.messages()):
        spans = recover_turn(turn)
        for span in spans:
            check = checks.get(span['id'], {})
            if not check.get('recognized'):
                continue
            old = span['observation']
            parts, omitted = [], set()
            for segment in check['segments']:
                text = old['stdout'][segment['start']:segment['end']]
                if digest(text) != segment['text_sha256']:
                    raise ValueError('recognized documentation segment changed')
                sid = segment['receipt_id']
                if sid in eligible:
                    parts.append(f'[API documentation omitted; read archived span {sid}.]')
                    omitted.add(sid)
                else:
                    parts.append(text)
            if not omitted:
                continue
            replacement = copy.deepcopy(old)
            replacement['stdout'] = ''.join(parts)
            # Identical marker/metadata rules in D and B; no arm label is shown.
            replacement['stdout_view'] = {
                'omitted': True, 'source_span_id': span['id'],
                'documentation_receipt_ids': sorted(omitted),
                'literal_output_preserved': True}
            if len(compact(replacement)) >= len(compact(old)):
                continue
            span['observation'] = replacement
            changes.append({'span_id': span['id'], 'documentation_receipt_ids': sorted(omitted),
                'detail_receipt_ids': sorted(omitted & details),
                'listing_receipt_ids': sorted(omitted & listings)})
        output.append(turn[0], spans)
    return output, {'transfer_wall_seconds': time.monotonic() - started,
        'view_arm': arm, 'selection': {'changes': changes, 'changed_outputs': len(changes),
            'eligible_details': sorted(details), 'eligible_listings': sorted(listings)},
        'original_archive_modified': False, 'runtime_retained': True,
        'latest_turn_retained': True, 'mixed_outputs_retained': True,
        'one_time_boundary_display_change': True, 'novel_method_claim': False,
        'future_irrelevance_proven': False, 'contract_feedback_mode': 'public_schema'}


class InventoryInference(OriginBudgetInference):
    """Inherit the unchanged common admission, notification and cache policy."""
    def __init__(self, config, output, arm):
        if arm not in ARMS:
            raise ValueError('unknown inventory-display condition')
        ResidualInference.__init__(self, config, output, 'residual')
        self.arm = arm
        self.prefix_api = self.suffix_api = 0
        self.snapshots = []


def validate_matched_views(item):
    built = {arm: build_condition(item, arm) for arm in ARMS}
    full = build_origin_view(item)[0]['full_keep']
    if built[ARMS[0]][0].messages() != full.messages():
        raise ValueError('full control changed')
    removed = {}
    for arm, (_, transfer) in built.items():
        changes = transfer['selection']['changes']
        removed[arm] = {kind: sorted({sid for row in changes for sid in row[kind]})
                       for kind in ('detail_receipt_ids', 'listing_receipt_ids')}
    if (removed[ARMS[1]]['listing_receipt_ids']
            or removed[ARMS[1]]['detail_receipt_ids'] != removed[ARMS[2]]['detail_receipt_ids']):
        raise ValueError('shortening guard confounds the matched detail removal')
    return removed


def disposition(summary):
    """Unknown model use can end one cell; unknown API effects end the batch."""
    if (summary['setup']['status'] != 'matched_observable_prefix'
            or summary['unknown_effect_requests']
            or summary['stop_reason'] in ('runtime_error', 'cleanup_error', 'setup_failure')):
        return 'stop_batch'
    if summary['unknown_usage_calls']:
        return ('evaluate_unknown_usage' if summary['stop_reason'] in
                ('wall_limit_during_model_call', 'model_usage_unknown') else 'stop_batch')
    return 'evaluate'
