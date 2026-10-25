"""Finite Docker replay of a frozen closed prefix; no live APIs or inference.

Every recorded logical action needs an exact ordinary-call or partial-hit
witness. Saved future replies are validation material, never cache initialization.
All generated code stays inside the existing isolated Docker interpreter.
"""
import argparse
import ast
from copy import deepcopy
import hashlib
import inspect
import json
from pathlib import Path
import time

from automatic_projection_runtime import (AutomaticProjectionHost, AutomaticProjectionProgram,
    AutomaticProjectionPython, POLICIES, derived_bootstrap)
from container_api_python import ApiChannel
from field_read_contract import CONTRACT_ID, TARGET, verify_public_implementation
from inspect_appworld_api_schemas import load_public_tools
from public_api_result_transport import PublicResultTransport
from public_name_catalog import PublicNameCatalog
from recorded_python_replay import canonical, load_programs
from shared_api_reservations import RequestBudget

ROOT = Path(__file__).resolve().parents[1]
FIXED_RUN = 'BOC_P122_R02_04_SINGLE_CHECKPOINT'
PROGRAM_COUNT = 10
TOTAL_SECONDS = 600
PROGRAM_SECONDS = 30
CLEANUP_RESERVE_SECONDS = 120
SOURCES = ('scripts/probe_automatic_projection_replay.py', 'scripts/automatic_field_projection.py',
           'scripts/automatic_projection_runtime.py', 'scripts/ordinary_complete_read_cache.py',
           'scripts/public_contract_read_views.py', 'scripts/field_read_contract.py',
           'scripts/deferred_view_protocol.py', 'scripts/shared_api_reservations.py',
           'scripts/persistent_api_python.py', 'scripts/agent_read_view_runtime.py',
           'scripts/persistent_read_view_python.py', 'scripts/container_api_python.py',
           'scripts/public_api_result_transport.py', 'scripts/public_api_envelope.py',
           'scripts/recorded_python_replay.py', 'scripts/public_name_catalog.py',
           'scripts/appworld_native_tools.py', 'scripts/container_data_python.py',
           'configs/python_export_image_v01.json')


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def file_sha(path):
    require(path.is_file() and not path.is_symlink(), 'regular_file_required')
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    require(path.is_file() and not path.is_symlink() and path.stat().st_size <= 32 * 1024 * 1024,
            'bounded_private_record_required')
    return json.loads(path.read_text())


def put(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')


def action_of(entry):
    request = entry['request']
    return {'app': request['app'], 'api': request['api'], 'args': request['arguments']}


class ActionTape:
    """One program's immutable logical request sequence, including cache hits."""
    def __init__(self, entries):
        self.entries = deepcopy(entries)
        self.index = 0
        self.active = None
        self.active_dispatched = False
        self.events = []
        self.failed = None

    def fail(self, reason):
        self.failed = reason
        raise ValueError(reason)

    def next(self, action):
        if self.active is not None or self.index >= len(self.entries):
            self.fail('extra_or_reentrant_logical_action')
        entry = self.entries[self.index]
        if canonical(action) != canonical(action_of(entry)):
            self.fail('logical_action_order_or_arguments_differ')
        return entry

    def begin_call(self, action):
        self.active = self.next(action)
        self.active_dispatched = False
        return self.active

    def finish_call(self, reply, ordinary_hits):
        entry = self.active
        require(entry is not None, 'ordinary_action_missing')
        saved = entry['reply']
        if reply.get('ok') != saved['ok']:
            self.fail('ordinary_reply_status_differs')
        if saved['ok']:
            if canonical(reply.get('value')) != canonical(saved['value']):
                self.fail('ordinary_complete_value_differs')
        else:
            # The runtime restores the exact ordinary-channel error from the
            # fresh reply; replay must neither strip nor repair exception text.
            if reply.get('error') != saved['error']:
                self.fail('ordinary_exception_payload_differs')
        if ordinary_hits:
            if (ordinary_hits != 1 or self.active_dispatched or not saved['ok']
                    or not entry['originally_sent'] or entry['declared_complete'] or entry['effects_unknown']
                    or action_of(entry)['app'] + '__' + action_of(entry)['api'] != TARGET):
                self.fail('unjustified_complete_cache_skip')
            kind = 'ordinary_complete_cache'
        elif self.active_dispatched:
            kind = 'saved_backend_response'
        elif not entry['originally_sent'] and not saved['ok']:
            kind = 'recorded_predispatch_rejection'
        else:
            self.fail('logical_action_has_no_dispatch_or_cache_witness')
        self.events.append({'index': self.index, 'kind': kind,
                            'action_sha256': digest(action_of(entry))})
        self.index += 1
        self.active = None

    def partial(self, action, fields, value):
        entry = self.next(action)
        saved = entry['reply']
        if (action['app'] + '__' + action['api'] != TARGET or not saved['ok']
                or not entry['originally_sent'] or entry['declared_complete']
                or entry['effects_unknown'] or type(saved['value']) is not dict
                or any(f not in saved['value'] for f in fields)
                or canonical(value) != canonical({f: saved['value'][f] for f in fields})):
            self.fail('partial_hit_not_a_matching_successful_recorded_read')
        self.events.append({'index': self.index, 'kind': 'observed_partial_projection',
                            'action_sha256': digest(action), 'fields': list(fields)})
        self.index += 1

    def finish(self):
        if self.failed or self.active is not None or self.index != len(self.entries):
            self.fail('unconsumed_or_failed_logical_action_tape')


class SavedResultTransport(PublicResultTransport):
    """A typed-transport-compatible simulator with no external transport object.

    Its receipts count saved backend responses for the simulated request budget;
    they do not represent environment API dispatch. Public output separates both.
    """
    def __init__(self):
        super().__init__(None)
        self.tape = None
        self.saved_backend_responses = 0

    def request(self, command):
        require(set(command) == {'op', 'call'} and command['op'] == 'call', 'saved_call_only')
        tape = self.tape
        require(tape is not None and tape.active is not None, 'logical_call_before_saved_dispatch_required')
        entry = tape.active
        require(canonical(command['call']) == canonical(action_of(entry)), 'saved_dispatch_action_differs')
        require(entry['originally_sent'] and not tape.active_dispatched, 'saved_dispatch_not_permitted')
        require(not entry['effects_unknown'], 'unknown_saved_effects_not_replayable')
        tape.active_dispatched = True
        self.saved_backend_responses += 1
        reply = entry['reply']
        self.receipts.append({'status': 'returned' if reply['ok'] else 'raised',
                             'bridge_request_sent': True, 'simulated_saved_response': True,
                             'automatic_retries': 0, 'rollback_guaranteed': False})
        self.complete |= entry['declared_complete']
        if reply['ok']:
            return {'ok': True, 'result': {'observation': json.dumps(reply['value'], allow_nan=False),
                                          'declared_complete': entry['declared_complete']}}
        return {'ok': False, 'error': reply['error']}


class ReplayApiChannel(ApiChannel):
    def exchange(self, packet):
        entry = self.bridge.tape.active
        if entry is not None and not entry['originally_sent']:
            require(not entry['reply']['ok'] and not entry['effects_unknown'], 'invalid_saved_rejection')
            require(packet['id'] == self.last_id + 1, 'saved_rejection_RPC_order')
            require(canonical({'app': packet['app'], 'api': packet['api'], 'args': packet['arguments']})
                    == canonical(action_of(entry)), 'saved_rejection_action_differs')
            self.last_id = packet['id']
            self.rows.append({'action': {'name': packet['app'] + '__' + packet['api'],
                'arguments': json.dumps(packet['arguments'], allow_nan=False)}, 'api_request_sent': False,
                'new_tools': [], 'observation': {'not_executed': entry['reply']['error']}})
            return {'id': packet['id'], 'ok': False, 'error': entry['reply']['error']}
        return super().exchange(packet)


class ReplayHost(AutomaticProjectionHost):
    def __init__(self, *args, **kwargs):
        self.boundaries = []
        super().__init__(*args, **kwargs)

    @property
    def tape(self):
        return self.channel.bridge.tape

    def _lookup(self, args):
        value = super()._lookup(args)
        if value is not None:
            self.tape.partial({k: args[k] for k in ('app', 'api', 'args')}, args['fields'], value)
        return value

    def request(self, packet):
        if packet.get('op') == 'replay_boundary':
            require(set(packet) == {'id', 'op', 'args', 'releases'} and packet['releases'] == []
                    and packet['id'] == self.last_id + 1, 'invalid_boundary_control')
            value = packet['args']
            require(set(value) == {'program_index', 'roots', 'plain_namespace_sha256', 'unsupported_names'}
                    and type(value['program_index']) is int and type(value['roots']) is dict
                    and type(value['plain_namespace_sha256']) is str
                    and type(value['unsupported_names']) is list, 'invalid_boundary_snapshot')
            self.last_id = packet['id']
            self.control_events.append({'id': self.last_id, 'op': 'replay_boundary', 'released': 0})
            self.boundaries.append(deepcopy(value))
            return {'id': self.last_id, 'ok': True, 'value': None, 'fatal': self.channel.budget.stopped}
        if packet.get('op') != 'call':
            return super().request(packet)
        tape = self.tape
        tape.begin_call(packet['args'])
        before = self.ordinary_complete_reuses
        reply = super().request(packet)
        tape.finish_call(reply, self.ordinary_complete_reuses - before)
        return reply


def boundary_snapshot(scope, root_names, number):
    """Trusted container-only value inspection; no repr, callbacks, or model code."""
    import hashlib
    import json
    def encode(value, ancestors, remaining):
        remaining[0] -= 1
        if remaining[0] < 0 or len(ancestors) > 64:
            raise ValueError('snapshot_structure_limit')
        kind = type(value)
        if kind in (str, int, float, bool, type(None)):
            return [kind.__name__, value]
        if kind not in (dict, list, tuple, set, frozenset) or id(value) in ancestors:
            raise ValueError('snapshot_non_plain_value')
        ancestors.add(id(value))
        if kind is dict:
            encoded = [[encode(k, ancestors, remaining), encode(v, ancestors, remaining)]
                       for k, v in value.items()]
            encoded.sort(key=lambda row: json.dumps(row[0], sort_keys=True, allow_nan=False))
        else:
            encoded = [encode(v, ancestors, remaining) for v in value]
            if kind in (set, frozenset):
                encoded.sort(key=lambda row: json.dumps(row, sort_keys=True, allow_nan=False))
        ancestors.remove(id(value))
        return [kind.__name__, encoded]
    def fingerprint(value):
        encoded = encode(value, set(), [100000])
        data = json.dumps(encoded, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
        return {'type': type(value).__name__, 'value_sha256': hashlib.sha256(data).hexdigest()}
    roots, values, unsupported = {}, {}, []
    for name in root_names:
        roots[name] = {'present': False} if name not in scope else {'present': True, **fingerprint(scope[name])}
    for name, value in scope.items():
        if (type(name) is not str or name.startswith('_harness_projection_')
                or name in ('__builtins__', '__name__', 'call_api', 'observations', 'api_schemas')):
            continue
        try:
            values[name] = fingerprint(value)
        except (ValueError, TypeError, RecursionError):
            unsupported.append(name)
    return {'program_index': number, 'roots': roots,
            'plain_namespace_sha256': hashlib.sha256(json.dumps(values, sort_keys=True).encode()).hexdigest(),
            'unsupported_names': sorted(unsupported)}


class ReplayPython(AutomaticProjectionPython):
    def __init__(self, *args, root_names, **kwargs):
        self.root_names = tuple(root_names)
        super().__init__(*args, **kwargs)

    def _bootstrap(self):
        source = derived_bootstrap(self.policy)
        install = "scope = {'__name__':'__main__'}\n"
        require(source.count(install) == 1, 'snapshot_install_anchor_changed')
        source = source.replace(install, inspect.getsource(boundary_snapshot) + '\n' + install)
        boundary = '    content=capture.getvalue()\n'
        require(source.count(boundary) == 1, 'snapshot_boundary_anchor_changed')
        code = ("    if not _projection_client.closed:\n"
                "        _projection_client.rpc('replay_boundary', boundary_snapshot(scope, "
                + repr(self.root_names) + ", program_index))\n")
        return source.replace(boundary, code + boundary)


class ReplayProgram(AutomaticProjectionProgram):
    host_class = ReplayHost


def require_empty_observations(programs):
    # This fixed prefix reconstructs state only through actual replayed calls.
    # Reusing original nonempty observations could inject omitted full replies.
    require(all(type(p['source'].get('observations')) is list
                and not p['source']['observations'] for p in programs),
            'fixed_prefix_requires_empty_observations')


def prepare_manifest(storage, repo, data):
    require(repo.resolve() == ROOT.resolve(), 'executing_repository_root_must_match')
    implementation = sorted({str(p.relative_to(repo)) for directory in ('scripts', 'tests')
                             for p in (repo / directory).rglob('*.py')}
                            | set(SOURCES) | {'docs/experiments/P124_projection_replay.md'})
    trial = storage / 'records/context_pilot' / FIXED_RUN
    tools, schema_hashes, _ = load_public_tools(data)
    programs = load_programs(trial, {t['function']['name']: t['function'] for t in tools})
    require(len(programs) >= PROGRAM_COUNT, 'ten_closed_programs_required')
    selected = programs[:PROGRAM_COUNT]
    require_empty_observations(selected)
    names = [f'call_{i:03d}_01' for i in range(1, PROGRAM_COUNT + 1)]
    require([p['name'] for p in selected] == names, 'fixed_prefix_inventory_differs')
    files = {name: file_sha(trial / name) for name in ('events.json', 'spans.json', 'summary.json', 'provenance.json')}
    for program in selected:
        files.update(program['source_sha256'])
    provenance = read(trial / 'provenance.json')
    require(provenance['public_schema_hashes'] == schema_hashes, 'public_schema_provenance_differs')
    return {'phase': 'P124', 'kind': 'fixed_saved_response_prefix_replay', 'run_id': FIXED_RUN,
            'programs': names, 'policies': list(POLICIES), 'total_generated_programs': 20,
            'total_seconds': TOTAL_SECONDS, 'program_seconds': PROGRAM_SECONDS,
            'private_files': files, 'schema_files': schema_hashes,
            'implementation_files': {name: file_sha(repo / name) for name in implementation},
            'environment_API_requests': 0, 'model_calls': 0, 'tokenizer_calls': 0, 'evaluator_calls': 0}


def check_manifest(manifest, storage, repo, data):
    expected = prepare_manifest(storage, repo, data)
    require(manifest == expected, 'frozen_manifest_differs')
    return expected


def root_inventory(programs):
    names = set()
    for program in programs:
        for node in ast.walk(ast.parse(program['source']['code'])):
            if (isinstance(node, ast.Assign) and len(node.targets) == 1
                    and isinstance(node.targets[0], ast.Name) and isinstance(node.value, ast.Call)
                    and isinstance(node.value.func, ast.Name) and node.value.func.id == 'call_api'
                    and [getattr(a, 'value', None) for a in node.value.args] == ['spotify', 'show_song']):
                names.add(node.targets[0].id)
    return sorted(names)


def run_replay(storage, repo, data, manifest_path, output):
    began = time.monotonic()
    manifest = check_manifest(read(manifest_path), storage, repo, data)
    require(not output.exists(), 'preserve_prior_replay_output')
    output.mkdir(parents=True)
    put(output / 'input_manifest_private.json', manifest)
    tools, _, _ = load_public_tools(data)
    programs = load_programs(storage / 'records/context_pilot' / FIXED_RUN,
        {t['function']['name']: t['function'] for t in tools})[:PROGRAM_COUNT]
    require_empty_observations(programs)
    roots = root_inventory(programs)
    # This checks public implementation bytes only, never private evaluator code.
    verified = verify_public_implementation(storage / '.runtime/appworld/venv/lib/python3.12/site-packages/appworld/apps/spotify')
    require(verified == CONTRACT_ID, 'pinned_public_contract_required')
    rows, private_results = [], {}
    attempted, completed = 0, 0
    all_match = True
    for policy in POLICIES:
        session = None
        directory = output / policy
        directory.mkdir()
        arm_results = []
        try:
            require(time.monotonic() - began < TOTAL_SECONDS - CLEANUP_RESERVE_SECONDS, 'global_replay_wall_limit')
            session = ReplayPython(storage, directory / 'session', policy=policy, root_names=roots)
            budget = RequestBudget(10000)  # simulated tape admission, never an environment budget
            transport = SavedResultTransport()
            catalog = PublicNameCatalog(tools)
            catalog.visible = set(programs[0]['source']['api_schemas'])
            runner = ReplayProgram(session, budget, execution_scope='P124:' + policy,
                                   verified_contract=verified, policy=policy)
            for index, program in enumerate(programs):
                remaining = TOTAL_SECONDS - CLEANUP_RESERVE_SECONDS - (time.monotonic() - began)
                require(remaining > 0, 'global_replay_wall_limit')
                transport.tape = ActionTape(program['entries'])
                source = program['source']
                expected_schemas = {n: catalog.catalog[n]['function'] for n in sorted(catalog.visible)}
                require(expected_schemas == source['api_schemas'], 'schema_boundary_differs')
                channel = ReplayApiChannel(catalog, transport, 10000)
                record_dir = directory / 'programs' / program['name']
                before_boundaries = len(runner.host.boundaries) if runner.host else 0
                attempted += 1
                actual = runner(source['code'], [], channel, storage_root=storage,
                    record_dir=record_dir, timeout=min(PROGRAM_SECONDS, remaining))
                completed += 1
                transport.tape.finish()
                boundaries = runner.host.boundaries[before_boundaries:]
                require(len(boundaries) == 1 and boundaries[0]['program_index'] == index + 1,
                        'one_snapshot_per_generated_program_required')
                boundary = boundaries[0]
                require(all(not row['present'] or row['type'] == 'dict' for row in boundary['roots'].values()),
                        'root_must_remain_full_real_dict')
                expected = program['expected']
                checks = {key: actual.get(key) == expected.get(key)
                          for key in ('status', 'stdout', 'stdout_truncated', 'error', 'declared_complete', 'unknown_effects')}
                observed = {'result': actual, 'boundary': boundary}
                if policy != POLICIES[0]:
                    peer = private_results[POLICIES[0]][index]
                    checks['paired_boundary'] = boundary == peer['boundary']
                    checks['paired_stdout_error'] = all(actual.get(k) == peer['result'].get(k)
                                                       for k in ('status', 'stdout', 'stdout_truncated', 'error'))
                arm_results.append(observed)
                events = transport.tape.events
                saved_count = sum(e['kind'] == 'saved_backend_response' for e in events)
                require(actual['api_requests'] == saved_count and budget.pending == 0,
                        'simulated_receipt_budget_program_count_differs')
                evidence = read(record_dir / 'projection_program_private.json')
                row = {'policy': policy, 'program_number': index + 1, 'checks': checks,
                    'logical_requests': len(events), 'saved_backend_responses': sum(e['kind'] == 'saved_backend_response' for e in events),
                    'ordinary_complete_cache_hits': sum(e['kind'] == 'ordinary_complete_cache' for e in events),
                    'projection_hits': sum(e['kind'] == 'observed_partial_projection' for e in events),
                    'boundary_sha256': digest(boundary), 'stdout_sha256': digest(actual.get('stdout')),
                    'error_sha256': digest(actual.get('error')), 'control_requests': evidence['control_requests'],
                    'control_request_bytes': evidence['control_request_bytes'],
                    'control_reply_bytes': evidence['control_reply_bytes'],
                    'snapshot_controls': 1, 'wall_seconds': actual['wall_seconds']}
                rows.append(row)
                put(record_dir / 'replay_actions_private.json', events)
                put(record_dir / 'replay_boundary_private.json', boundary)
                if not all(checks.values()):
                    raise ValueError('recorded_or_paired_observable_boundary_differs')
                require(actual['session_usable'], 'replay_session_unusable')
            require(transport.saved_backend_responses == budget.spent
                    == sum(row['saved_backend_responses'] for row in rows if row['policy'] == policy)
                    and budget.pending == 0, 'simulated_arm_accounting_differs')
            private_results[policy] = arm_results
        except Exception as error:
            all_match = False
            put(directory / 'failure_private.json', {'type': type(error).__name__, 'message': str(error)})
        finally:
            if session is not None:
                try:
                    session.close()
                    require(session.state['container_removed'], 'replay_container_cleanup_required')
                except Exception as error:
                    all_match = False
                    put(directory / 'cleanup_failure_private.json', {'type': type(error).__name__, 'message': str(error)})
        if not all_match:
            break
    try:
        implementation_unchanged = all(file_sha(repo / name) == expected
                                       for name, expected in manifest['implementation_files'].items())
    except (OSError, ValueError):
        implementation_unchanged = False
    all_match = all_match and implementation_unchanged
    result = {'phase': 'P124', 'kind': 'fixed_saved_response_prefix_replay',
        'all_20_programs_match': all_match and len(rows) == 20, 'attempted_generated_programs': attempted, 'completed_generated_programs': completed,
        'compared_generated_programs': len(rows),
        'programs': rows, 'wall_seconds': time.monotonic() - began,
        'input_manifest_sha256': file_sha(manifest_path),
        'implementation_unchanged_at_end': implementation_unchanged, 'environment_API_requests': 0,
        'model_calls': 0, 'tokenizer_calls': 0, 'evaluator_calls': 0,
        'private_result_api_requests_meaning': 'simulated_saved_backend_responses_only',
        'live_environment_counterfactual_proved': False, 'task_quality_or_total_token_savings_established': False}
    put(output / 'summary.json', result)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--storage-root', type=Path, required=True)
    parser.add_argument('--repo-root', type=Path, default=ROOT)
    parser.add_argument('--data-root', type=Path, required=True)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--prepare-only', action='store_true')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.prepare_only:
        require(args.output is None, 'prepare_has_no_execution_output')
        put(args.manifest, prepare_manifest(args.storage_root, args.repo_root, args.data_root))
        print(json.dumps({'manifest_prepared': True, 'generated_programs_executed': 0}))
    else:
        require(args.output is not None, 'private_output_required')
        result = run_replay(args.storage_root, args.repo_root, args.data_root, args.manifest, args.output)
        print(json.dumps({k: result[k] for k in ('all_20_programs_match', 'completed_generated_programs',
            'environment_API_requests', 'model_calls', 'tokenizer_calls', 'evaluator_calls', 'wall_seconds')}))


if __name__ == '__main__':
    main()
