"""Ordinary finite access strategies for an explicit subset's maximum.

This component does not interpret a task, establish that its target set is
complete, or authorize external writes. Sorted stopping relies on a trusted
adapter's coverage/order/snapshot contract, not on an agent-supplied claim.
All tied maxima are returned, so a tie at a page boundary cannot stop a scan.
"""
from dataclasses import dataclass
import math


@dataclass(frozen=True)
class AccessContract:
    source_id: str
    snapshot_id: str
    id_field: str
    score_field: str
    value_fields: tuple[str, ...]
    order: str  # global_desc, within_page_desc, or unspecified
    covers_target_universe: bool
    stable_snapshot: bool

    @property
    def permits_ranked_stop(self):
        return (self.order == 'global_desc' and self.covers_target_universe
                and self.stable_snapshot)


@dataclass(frozen=True)
class ReadReceipt:
    source_id: str
    snapshot_id: str
    records: list[dict]


class ReadFailure(Exception):
    """The source did not support a complete result within the fixed contract."""


def subset_maximum(target_ids, *, contract, point_read, page_read, mode,
                   max_requests, page_limit=20, exploratory_pages=1):
    """Return all maxima over caller-selected IDs, or an explicitly incomplete result.

    point_read(id) and page_read(page_index, page_limit) each count as one
    attempted request even on failure. Their complete original responses belong
    in the caller's private cost ledger. No failed call is retried. The bounded
    strategy reuses target records from its exploratory pages before point reads.
    These are conventional lookup, sorted access and bounded lookahead controls;
    no algorithmic novelty or LLM-token benefit is claimed here.
    """
    if mode not in ('point', 'ranked', 'bounded'):
        raise ValueError('unsupported mode')
    if (type(max_requests) is not int or not 0 <= max_requests <= 2000
            or type(page_limit) is not int or not 1 <= page_limit <= 100
            or type(exploratory_pages) is not int or not 0 <= exploratory_pages <= 20):
        raise ValueError('invalid finite request limits')
    if (not isinstance(contract, AccessContract)
            or any(not isinstance(value, str) or not value for value in
                   (contract.source_id, contract.snapshot_id, contract.id_field, contract.score_field))
            or contract.id_field == contract.score_field
            or contract.order not in ('global_desc', 'within_page_desc', 'unspecified')
            or type(contract.covers_target_universe) is not bool
            or type(contract.stable_snapshot) is not bool
            or not isinstance(contract.value_fields, tuple)
            or any(not isinstance(f, str) or not f for f in contract.value_fields)):
        raise ValueError('invalid adapter contract')
    if not isinstance(target_ids, (list, tuple)) or len(target_ids) > 1000:
        raise ValueError('target IDs must be an explicit finite sequence')
    if any(type(i) is not int or i <= 0 for i in target_ids) or len(set(target_ids)) != len(target_ids):
        raise ValueError('target IDs must be unique positive integers')
    targets = set(target_ids)
    effective = mode if mode == 'point' or contract.permits_ranked_stop else 'point'
    state = {'status': 'incomplete', 'requested_mode': mode, 'effective_mode': effective,
             'ranked_contract_eligible': contract.permits_ranked_stop,
             'requests_attempted': 0, 'point_requests': 0, 'page_requests': 0,
             'records_received': 0, 'target_records_observed': 0,
             'target_count': len(targets), 'max_requests': max_requests,
             'winners': [], 'stop_reason': None,
             'claim_scope': 'All maxima of the supplied ID set under the adapter contract; not task completeness.'}
    seen = {}

    def request(kind, argument):
        if state['requests_attempted'] >= max_requests:
            raise ReadFailure('request_budget_exhausted')
        state['requests_attempted'] += 1
        state[kind + '_requests'] += 1
        try:
            receipt = point_read(argument) if kind == 'point' else page_read(argument, page_limit)
        except Exception as error:
            raise ReadFailure('source_exception:' + type(error).__name__) from error
        if not isinstance(receipt, ReadReceipt):
            raise ReadFailure('invalid_receipt')
        if receipt.source_id != contract.source_id or receipt.snapshot_id != contract.snapshot_id:
            raise ReadFailure('source_or_snapshot_changed')
        records = receipt.records
        if not isinstance(records, list):
            raise ReadFailure('invalid_record_list')
        state['records_received'] += len(records)
        if (kind == 'point' and len(records) != 1) or (kind == 'page' and len(records) > page_limit):
            raise ReadFailure('invalid_response_cardinality')
        checked = []
        for row in records:
            if not isinstance(row, dict):
                raise ReadFailure('invalid_record')
            key, score = row.get(contract.id_field), row.get(contract.score_field)
            if type(key) is not int or key <= 0:
                raise ReadFailure('invalid_record_id')
            if type(score) not in (int, float) or (type(score) is float and not math.isfinite(score)):
                raise ReadFailure('invalid_record_score')
            if any(field not in row for field in contract.value_fields):
                raise ReadFailure('required_value_missing')
            projected = {field: row[field] for field in dict.fromkeys(
                (contract.id_field, contract.score_field) + contract.value_fields)}
            checked.append((key, score, projected))
        if kind == 'point' and checked[0][0] != argument:
            raise ReadFailure('point_id_mismatch')
        return checked

    def retain(rows):
        for key, score, projected in rows:
            if key in targets:
                if key in seen and seen[key] != projected:
                    raise ReadFailure('conflicting_target_record')
                seen[key] = projected
        state['target_records_observed'] = len(seen)

    def finish(reason):
        if seen:
            best = max(row[contract.score_field] for row in seen.values())
            state['winners'] = [seen[key] for key in sorted(seen)
                                if seen[key][contract.score_field] == best]
        state.update(status='complete', stop_reason=reason)
        return state

    if not targets:
        return finish('empty_supplied_set')
    if not contract.stable_snapshot:
        state['stop_reason'] = 'unstable_snapshot_contract'
        return state
    try:
        if effective in ('ranked', 'bounded'):
            previous_score = math.inf
            ranked_ids = set()
            page = 0
            while effective == 'ranked' or page < exploratory_pages:
                rows = request('page', page)
                for key, score, _ in rows:
                    if score > previous_score:
                        raise ReadFailure('observed_rank_violation')
                    if key in ranked_ids:
                        raise ReadFailure('duplicate_ranked_id')
                    previous_score = score
                    ranked_ids.add(key)
                retain(rows)
                if len(seen) == len(targets):
                    return finish('all_target_records_observed')
                if seen:
                    best = max(row[contract.score_field] for row in seen.values())
                    if rows and rows[-1][1] < best:
                        return finish('global_rank_frontier_below_best')
                if len(rows) < page_limit:
                    # Every target is required to occur in this complete source.
                    # A missing target at exhaustion contradicts that contract.
                    raise ReadFailure('target_missing_from_exhausted_source')
                page += 1
        for key in target_ids:
            if key not in seen:
                retain(request('point', key))
        return finish('all_target_records_observed')
    except ReadFailure as error:
        state['stop_reason'] = str(error)
        # Partial maxima are never returned as an answer.
        state['winners'] = []
        return state
