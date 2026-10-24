"""Replay only trusted host control logic against saved API replies.

No generated Python, model request, environment API or evaluator is executed.
This checks the factual recorded policy, not an alternate-policy counterfactual.
Values stay private; public rows contain lifecycle counts and reply fingerprints.
"""
from collections import Counter
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
from types import SimpleNamespace
from unittest.mock import patch

from agent_read_view_runtime import SchemaForwardingViewChannel
from container_api_python import ApiChannel
from field_read_contract import CONTRACT_ID
from ordinary_complete_read_cache import OrdinaryCachedReadHost, OrdinaryCachedCoalescedHost
from persistent_read_view_python import ViewControlChannel
from public_api_result_transport import PublicResultTransport
from public_name_catalog import PublicNameCatalog
from shared_api_reservations import BudgetedApiChannel, RequestBudget


def require(value, reason):
    if not value:
        raise ValueError(reason)


def read(path, *, lines=False):
    require(path.is_file() and not path.is_symlink() and path.stat().st_size <= 16*1024*1024,
            'bounded_regular_record_required')
    content = path.read_text()
    return [json.loads(line) for line in content.splitlines()] if lines else json.loads(content)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class SavedReplies:
    """No external transport exists behind this object."""
    def __init__(self, records):
        self.records = records
        self.index = 0

    def request(self, command):
        require(self.index < len(self.records), 'unrecorded_API_request')
        row = self.records[self.index]
        require(command == row['command'], 'recorded_API_request_differs')
        self.index += 1
        if 'error' in row:
            name = row['error']['type']
            require(re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]*', name), 'invalid_recorded_error_name')
            # Reproduce the recorded transport failure, without eval or retry.
            raise type(name, (Exception,), {})(row['error']['message'])
        return deepcopy(row['response'])


class DeferredLifetimes:
    def __init__(self):
        self.rows = {}

    @staticmethod
    def pending_views(host):
        groups = {}
        for name, record in host.records.items():
            number = host.channel.budget._pending.get(record.token)
            if number is not None:
                groups.setdefault(number, []).append(name)
        return groups

    def observe(self, packet, program, before, host, events):
        after = self.pending_views(host)
        for number, names in after.items():
            if number not in self.rows:
                require(any(e['kind'] == 'reserve' and e['reservation'] == number for e in events),
                        'deferred_reservation_without_admission')
                self.rows[number] = dict(reservation=number, created_program=program,
                    created_control=packet['id'], largest_alias_count=len(names),
                    disposition='pending_at_stop', terminal_program=None, terminal_control=None,
                    invocation_status=None)
            self.rows[number]['largest_alias_count'] = max(self.rows[number]['largest_alias_count'], len(names))
        for event in events:
            number = event['reservation']
            if event['kind'] == 'reserve' or number not in self.rows:
                continue  # Immediate ordinary admissions are not deferred views.
            row = self.rows[number]
            require(row['disposition'] == 'pending_at_stop', 'deferred_reservation_closed_twice')
            require(number in before, 'deferred_reservation_without_prior_view')
            if event['kind'] == 'sent':
                row['disposition'] = ('explicit_materialization' if packet['op'] == 'materialize'
                                      else 'conservative_barrier')
                row['invocation_status'] = event['status']
            elif event['kind'] == 'cancel_unused':
                last_released = set(before[number]) <= set(packet['releases'])
                row['disposition'] = ('last_reference_release' if last_released
                                      else 'separate_complete_response')
            else:
                raise ValueError('unexpected_deferred_reservation_terminal')
            row.update(terminal_program=program, terminal_control=packet['id'])

    def summary(self, host):
        pending = self.pending_views(host)
        require({n for n,r in self.rows.items() if r['disposition'] == 'pending_at_stop'} == set(pending),
                'pending_lifetime_inventory_differs')
        rows = list(self.rows.values())
        return dict(deferred_groups=len(rows), disposition_counts=dict(Counter(r['disposition'] for r in rows)),
            lifetimes=rows, pending_groups_at_stop=len(pending),
            cancellation_is_not_counterfactual_API_savings=True,
            field_accesses_satisfied_locally_are_not_in_the_wire=True)


def expected_program_rows(folder, events, spans):
    result = {}; pending = []; indices = Counter()
    for event in events:
        span = spans[event['span_id']]
        if event['stage'] == 'python_api':
            pending.append(dict(action=span['action'], observation=span['observation'],
                api_request_sent=event['api_request_sent'], new_tools=event['new_tools'],
                effects_unknown=event.get('effects_unknown', False), api_execution=event.get('api_execution')))
            continue
        require(event['stage'] == 'model_tool', 'unexpected_saved_event_stage')
        indices[event['call']] += 1
        name = event['call'] + '_' + str(indices[event['call']]).zfill(2)
        if (folder/'programs'/name/'view_program_private.json').exists():
            require(span['action']['name'] == 'run_python', 'host_program_without_code_tool')
            result[name] = pending; pending = []
        else:
            require(not pending, 'API_rows_without_recorded_program')
    require(not pending, 'unclosed_program_API_rows')
    return result


def compare_row(row, expected):
    for key in ('action', 'observation', 'api_request_sent', 'new_tools'):
        require(row[key] == expected[key], 'replayed_API_row_differs:' + key)
    require(row.get('effects_unknown', False) == expected['effects_unknown'], 'replayed_effect_status_differs')
    receipt = row.get('api_execution')
    original = expected['api_execution']
    if original is None:
        require(receipt is None, 'unexpected_replayed_receipt')
    else:
        omit = {'transport_and_decode_wall_seconds'}
        require({k:v for k,v in receipt.items() if k not in omit} ==
                {k:v for k,v in original.items() if k not in omit}, 'replayed_receipt_differs')


def replay_cell(folder, tools):
    """Caller must bind all saved files and confirm the original batch is closed."""
    summary = read(folder/'summary.json'); policy = summary['read_view_policy']
    require(policy in ('eager_cached', 'coalesced_cached'), 'fixed_original_policy_required')
    events = read(folder/'events.json'); spans = read(folder/'spans.json')
    expected = expected_program_rows(folder, events, spans)
    folders = sorted((p for p in (folder/'programs').glob('*')
        if re.fullmatch(r'call_\d+_\d+', p.name)), key=lambda p:tuple(map(int,p.name.split('_')[1:])))
    require(set(expected) == {p.name for p in folders}, 'program_inventory_differs')
    records = [read(p) for p in sorted(folder.glob('bridge_*_private.json'),
        key=lambda p:int(p.name.split('_')[1]))]
    require(records and records[0]['command']['op'] == 'init', 'recorded_initialization_required')
    calls = records[1:]
    require(all(r['command']['op'] == 'call_typed' for r in calls), 'non_call_record_after_init')
    raw = SavedReplies(calls); transport = PublicResultTransport(raw)
    catalog = PublicNameCatalog(tools)
    budget = RequestBudget(summary['read_view_runtime']['budget']['limit'])
    cls = OrdinaryCachedCoalescedHost if policy == 'coalesced_cached' else OrdinaryCachedReadHost
    host = None; lifetimes = DeferredLifetimes(); program_rows = []
    nonces = iter(SimpleNamespace(hex=r['command']['nonce']) for r in calls)
    with patch('public_api_result_transport.uuid.uuid4', side_effect=lambda:next(nonces)):
        for directory in folders:
            saved_rows = expected[directory.name]; recorded_index = 0
            evidence = read(directory/'view_program_private.json')
            require(evidence['budget_before'] == budget.snapshot(), 'replayed_program_start_budget_differs')
            def may_continue():
                return not (recorded_index < len(saved_rows) and
                    saved_rows[recorded_index]['observation'].get('not_executed') ==
                    'completion, unknown effects or run budget')
            def on_record(row):
                nonlocal recorded_index
                require(recorded_index < len(saved_rows), 'extra_replayed_API_row')
                compare_row(row, saved_rows[recorded_index]); recorded_index += 1
            channel = BudgetedApiChannel(ApiChannel(catalog, transport, budget.limit-budget.spent, may_continue), budget)
            if host is None:
                host = cls(channel, execution_scope=folder.name, verified_contract=CONTRACT_ID,
                           defer=policy == 'coalesced_cached')
            else:
                host.attach(channel)
            control = ViewControlChannel(host, on_record)
            forwarding = SchemaForwardingViewChannel(control)
            payload = read(directory/'input_private.json')
            require(payload['api_schemas'] == {n:catalog.catalog[n]['function'] for n in sorted(catalog.visible)},
                    'replayed_public_schema_snapshot_differs')
            wire = read(directory/'wire_private.jsonl', lines=True)
            for packet in wire:
                require(type(packet.get('program_index')) is int and packet['program_index'] == payload['program_index'],
                        'replayed_wire_program_identity_differs')
                if packet.get('kind') != 'api':
                    require(packet.get('kind') == 'done', 'unexpected_wire_message'); continue
                before = lifetimes.pending_views(host); offset = len(budget.events)
                forwarding.exchange({k:v for k,v in packet.items() if k != 'program_index'})
                lifetimes.observe(packet['arguments']['packet'], directory.name, before, host, budget.events[offset:])
            forwarded = read(directory/'schema_forwarding_private.json')
            require(forwarding.exchanges == forwarded['exchanges'], 'replayed_control_reply_differs')
            require(recorded_index == len(saved_rows), 'unconsumed_saved_API_rows')
            require(evidence['budget_after'] == budget.snapshot(), 'replayed_program_end_budget_differs')
            for name in ('control_requests', 'control_request_bytes', 'control_reply_bytes'):
                require(evidence[name] == getattr(control, name), 'replayed_control_cost_differs:' + name)
            program_rows.append(dict(program=directory.name, controls=control.control_requests,
                API_requests=budget.spent-evidence['budget_before']['spent']))
    require(raw.index == len(calls), 'unconsumed_recorded_API_calls')
    require(budget.events == read(folder/'request_budget_events_private.json'), 'replayed_budget_events_differ')
    require((host.control_events if host else []) == read(folder/'view_control_events_private.json'),
            'replayed_control_events_differ')
    runtime = summary['read_view_runtime']
    require(budget.snapshot() == runtime['budget'], 'replayed_terminal_budget_differs')
    for key, value in dict(view_creation_count=host.next_view if host else 0,
            exact_reuses=host.exact_reuses if host else 0,
            ordinary_complete_reuses=host.ordinary_complete_reuses if host else 0,
            coalesced_reuses=getattr(host,'coalesced_reuses',0),
            materialization_cache_reuses=getattr(host,'materialization_cache_reuses',0),
            surviving_host_views_at_stop=len(host.records) if host else 0).items():
        require(runtime[key] == value, 'replayed_runtime_count_differs:' + key)
    lifetime_summary = lifetimes.summary(host) if host else dict(deferred_groups=0,disposition_counts={},lifetimes=[],
        pending_groups_at_stop=0,cancellation_is_not_counterfactual_API_savings=True,
        field_accesses_satisfied_locally_are_not_in_the_wire=True)
    return dict(run_id=folder.name, read_view_policy=policy, programs=program_rows,
        replayed_API_receipts=raw.index, control_requests=sum(r['controls'] for r in program_rows),
        **lifetime_summary, exact_factual_reply_replay=True,
        original_success=summary['final_success'], original_evaluation_field=summary['evaluation'],
        generated_programs_executed=0, additional_model_calls=0, additional_API_calls=0,
        additional_evaluator_calls=0, task_quality_or_savings_established_by_replay=False)
