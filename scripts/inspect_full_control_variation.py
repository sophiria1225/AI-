"""Describe P47/P55 full-control variation; no additional model/tool requests.

These runs were not prospectively allocated as a replication study. Inspect
all four known controls and identify the first differing serialized request
or generated message. A first divergence is not proof of its cause.
"""
import argparse
import copy
from pathlib import Path

from run_context_comparison import write_json
from run_handoff_factors import ROOT, read, sha


def without_transport_ids(messages):
    out = copy.deepcopy(messages)
    names = {}
    for message in out:
        for call in message.get('tool_calls', []):
            if 'id' in call:
                value = call['id']
                names.setdefault(value, f'transport_{len(names)}')
                call['id'] = names[value]
        if 'tool_call_id' in message:
            value = message['tool_call_id']
            if value not in names:
                raise ValueError('tool response without prior call id')
            message['tool_call_id'] = names[value]
    return out


def compare_cells(folders, number):
    row = {'known_task_index': number, 'cell_ids': [p.name for p in folders],
        'comparable_cells_available': all((p / 'usage.json').exists() for p in folders)}
    if not row['comparable_cells_available']:
        return row
    usage = [read(p / 'usage.json') for p in folders]
    row['independent_success'] = [read(p / 'evaluation.json')['official_success']
        if (p / 'evaluation.json').exists() else None for p in folders]
    row['first_request_difference'] = None
    row['first_content_difference'] = None
    row['compared_calls'] = []
    for index in range(min(map(len, usage))):
        cid = f'call_{index + 1:03d}'
        requests = [read(p / cid / 'request.json') for p in folders]
        responses = [read(p / cid / 'response.json') for p in folders]
        normalized = [without_transport_ids(v['messages']) for v in requests]
        if any(m[-1]['role'] != 'user' or not m[-1]['content'].startswith('<harness_residual_budget_v1>')
               for m in normalized):
            raise ValueError('expected common budget notification')
        values = [{'messages': m, **{k: v for k, v in request.items() if k != 'messages'}}
                  for request, m in zip(requests, normalized, strict=True)]
        other_fields_equal = all(requests[0].get(k) == requests[1].get(k)
                                 for k in set(requests[0]) | set(requests[1]) if k != 'messages')
        both_known = all(r['status'] == 'ok' for r in responses)
        content_equal = (without_transport_ids([responses[0]['message']]) ==
                         without_transport_ids([responses[1]['message']])) if both_known else None
        entry = {'call_id': cid, 'actual_serialized_requests_equal': requests[0] == requests[1],
            'requests_equal_except_transport_ids': values[0] == values[1],
            'only_budget_notice_differs_after_transport_normalization': other_fields_equal and
                normalized[0][:-1] == normalized[1][:-1] and normalized[0][-1] != normalized[1][-1],
            'both_terminal_usage_known': both_known,
            'generated_messages_equal_except_transport_ids': content_equal,
            'request_sha256': [sha(p / cid / 'request.json') for p in folders],
            'response_sha256': [sha(p / cid / 'response.json') for p in folders]}
        row['compared_calls'].append(entry)
        if values[0] != values[1] and row['first_request_difference'] is None:
            row['first_request_difference'] = cid
        if content_equal is False:
            row['first_content_difference'] = cid
            break  # Later different trajectories have no aligned causal prefix.
        if not both_known:
            break
    row['source_sha256'] = {p.name: {name: sha(p / name) for name in
        ('usage.json', 'summary.json', 'source_identity.json', 'budget_signals.json') if (p / name).exists()}
        for p in folders}
    return row


def compare(storage):
    base = storage / 'records/context_pilot'
    status = read(base / 'P55_batch_v01/status.json')
    if status['status'] not in ('complete', 'stopped'):
        raise ValueError('wait until fixed P55 comparison closes')
    rows = [compare_cells([base / f'P47_{number:02d}_FULL_CONTRACT_KEEP',
                           base / f'P55_{number:02d}_FULL_KEEP'], number) for number in range(1, 5)]
    negative = compare_cells([base / 'P55_03_DETAILS_OMITTED_KEEP',
                              base / 'P55_03_DETAILS_AND_LISTINGS_OMITTED_KEEP'], 3)
    preflight = read(base / 'P55_batch_v01/preflight.json')
    if not preflight['rows'][2]['detail_vs_both_base_equal']:
        raise ValueError('expected prespecified identical-view negative control')
    negative.update(prespecified_identical_base=True,
        inventory_causal_attribution_allowed=False, replicate_variance_estimate=False)
    return {'phase': 'P55_full_control_variation', 'rows': rows, 'refund_negative_control': negative,
        'inspector_sha256': sha(Path(__file__)),
        'additional_model_calls': 0, 'additional_tokenizer_calls': 0,
        'additional_api_requests': 0, 'additional_evaluator_calls': 0,
        'causal_attribution_claim': False, 'prospective_replication_study': False,
        'limits': ['All four available known controls, not a representative task sample.',
            'P47/P55 run in different server sessions and were not allocated as repeat trials.',
            'Transport-id normalization describes request structure, not independent prompt retokenization.',
            'A differing clock notice coincident with diverging output does not prove timing caused failure.',
            'P55 conditions and thresholds were not changed in response to this inspection.']}


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--storage-root', type=Path, required=True)
    args = p.parse_args(); target = ROOT / 'reports/P55_full_control_variation.json'
    if target.exists(): raise FileExistsError('preserve prior inspection')
    result = compare(args.storage_root); write_json(target, result)
    print([{k: r.get(k) for k in ('known_task_index', 'independent_success', 'first_request_difference',
                                'first_content_difference')} for r in result['rows']])
