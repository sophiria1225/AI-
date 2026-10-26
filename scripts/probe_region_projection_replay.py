"""P126 fixed saved-prefix replay. Generated programs run only in isolated Docker.

Future replies are validation witnesses only. The fixed final unreceipted call
is a frontier, not a counterfactual backend response or a normal root boundary.
"""
import argparse
import ast
from copy import deepcopy
import inspect
import hashlib
import json
from pathlib import Path
import time

from compact_api_receipts import decode_receipts
from contract_feedback import UNKNOWN_PARAMETER, canonical as feedback_canonical
from inspect_appworld_api_schemas import load_public_tools
from joined_public_read_views import JOINED_CONTRACT_ID, verify_joined_implementation
from probe_automatic_projection_replay import (ActionTape, ReplayApiChannel, SavedResultTransport,
    action_of, boundary_snapshot, digest, file_sha, put, read, require, require_empty_observations,
    root_inventory)
from public_name_catalog import PublicNameCatalog
from public_api_envelope import PROTOCOL
from recorded_python_replay import canonical, reply_from_receipt
from region_field_projection import plan_region_projection
from region_projection_runtime import (POLICIES, RegionProjectionHost, RegionProjectionProgram,
                                       RegionProjectionPython, derived_region_bootstrap)
from shared_api_reservations import RequestBudget

ROOT = Path(__file__).resolve().parents[1]
FIXED_RUNS = ('BOC_P125_04_EAGER_CACHED', 'BOC_P125_04_AUTOMATIC_PROJECTION_CACHED')
PROGRAM_COUNT = 12
MAX_PROGRAMS = 48
TOTAL_SECONDS = 1800
PROGRAM_SECONDS = 30
CLEANUP_RESERVE_SECONDS = 120
FRONTIER_ERROR = 'fixed_saved_replay_frontier_reached'
ORIGINAL_FRONTIER_ERROR = 'RuntimeError: RequestBudgetError: ordinary_call_cannot_spend_future_reservations'
REQUIRED_IMPLEMENTATION = ('scripts/region_field_projection.py', 'scripts/region_projection_runtime.py',
    'scripts/demand_joined_read_adapter.py', 'scripts/joined_public_read_views.py')


def _same(a, b, reason):
    require(canonical(a) == canonical(b), reason)


def _closed_trial(trial):
    summary, identity, comparison = (read(trial / name) for name in
        ('summary.json', 'source_identity.json', 'comparison_plan.json'))
    require(summary.get('phase') == 'P125' and summary.get('run_id') == trial.name
        and summary.get('cleanup_confirmed') is True and bool(summary.get('finished_at'))
        and summary.get('stop_reason') == 'api_request_limit'
        and summary.get('unknown_usage_calls') == summary.get('unknown_effect_requests') == 0
        and summary.get('api_requests') == 80
        and summary.get('python_session', {}).get('status') == 'closed'
        and summary.get('python_session', {}).get('container_removed') is True
        and summary.get('bridge_cleanup') == dict(process_stopped=True, graceful=True, transport_failed=False)
        and comparison.get('experiment') == 'P125'
        and identity.get('task_id') == summary.get('task_id')
        and identity.get('known_public_task_sha256') == summary.get('initial_public_task_sha256'),
        'closed_known_P125_CSV_required')
    runtime = summary['projection_runtime']
    require(runtime['ordinary_complete_cache_hits'] == runtime['projection_partial_hits'] == 0,
            'source_tape_must_have_no_unreceipted_cache_reuse')
    return summary


def load_region_programs(trial, schemas, *, expected_count=PROGRAM_COUNT):
    """Decode P125 control wire and pair every ordinary call with its inner row.

    Only the final call of the final fixed program may lack a receipt. Reports
    are controls, never task API replies. All returned values remain private.
    """
    events, spans = read(trial / 'events.json'), read(trial / 'spans.json')
    ids = [e['span_id'] for e in events]
    require(len(ids) == len(set(ids)) and set(ids) == set(spans), 'event_span_inventory_differs')
    by_id, position = dict(zip(ids, events)), {sid: i for i, sid in enumerate(ids)}
    used, nonces, programs, numbers = set(), set(), [], {}
    previous_control_id = 0
    for outer in events:
        if outer['stage'] != 'model_tool':
            continue
        call = outer['call']
        numbers[call] = numbers.get(call, 0) + 1
        directory = trial / 'programs' / f'{call}_{numbers[call]:02d}'
        if not directory.exists():
            continue
        source, result, evidence = (read(directory / name) for name in
            ('input_private.json', 'result_private.json', 'projection_program_private.json'))
        ordinal = len(programs) + 1
        require(source['program_index'] == result['program_index'] == ordinal,
                'fixed_source_program_order_differs')
        require(result['status'] in ('ok', 'execution_error') and result['session_usable'] is True
                and result['unknown_effects'] is False, 'closed_replayable_program_required')
        require(evidence['projection_failed'] is False
                and evidence['source_sha256'] == hashlib.sha256(source['code'].encode()).hexdigest(),
                'source_or_original_projection_evidence_changed')
        saved_schemas = source['api_schemas']
        require(type(saved_schemas) is dict and all(name in schemas and canonical(value) == canonical(schemas[name])
                for name, value in saved_schemas.items()), 'saved_public_schema_map_differs')
        span = spans[outer['span_id']]
        require(span['action']['name'] == 'run_python', 'program_requires_outer_python_action')
        _same(json.loads(span['action']['arguments'])['code'], source['code'], 'outer_source_binding_differs')
        for key in ('status', 'stdout', 'stdout_truncated', 'error', 'declared_complete', 'unknown_effects', 'api_requests'):
            _same(span['observation'][key], result[key], 'outer_program_observable_differs')
        wire = [json.loads(line) for line in (directory / 'wire_private.jsonl').read_text().splitlines()]
        require(wire and wire[-1].get('kind') == 'done'
                and wire[-1].get('program_index') == ordinal, 'program_done_required')
        for key in ('stdout', 'stdout_truncated', 'error'):
            _same(wire[-1][key], result[key], 'wire_program_result_differs')
        requests, reports = [], []
        for index, packet in enumerate(wire[:-1], 1):
            require(set(packet) == {'kind', 'id', 'program_index', 'app', 'api', 'arguments'}
                and packet['kind'] == 'api' and packet['id'] == index and packet['program_index'] == ordinal
                and packet['app'] == '__harness_views__' and packet['api'] == 'control'
                and set(packet['arguments']) == {'packet'}, 'P125_control_wire_required')
            control = packet['arguments']['packet']
            require(set(control) == {'id', 'op', 'args', 'releases'} and control['releases'] == []
                    and type(control['id']) is int and control['id'] == previous_control_id + 1,
                    'continuous_control_sequence_required')
            previous_control_id = control['id']
            if control['op'] == 'call':
                action = control['args']
                require(set(action) == {'app', 'api', 'args'}, 'ordinary_action_shape_required')
                requests.append(dict(kind='api', id=len(requests) + 1,
                    app=action['app'], api=action['api'], arguments=deepcopy(action['args'])))
            elif control['op'] == 'projection_report':
                require(index == len(wire) - 1 and not reports, 'one_terminal_report_only')
                reports.append(control['args'])
            else:
                raise ValueError('source_trace_contains_nonordinary_projection_control')
        _same(reports, evidence['execution_transform_report'], 'saved_execution_reports_differ')
        receipts = decode_receipts(span['observation']['api_receipts'])
        frontier = ordinal == expected_count
        require(len(requests) == len(receipts) + int(frontier), 'logical_request_receipt_count_differs')
        if frontier:
            require(result['status'] == 'execution_error' and not reports
                    and result['error'] == ORIGINAL_FRONTIER_ERROR,
                    'fixed_original_budget_frontier_required')
            tree = ast.parse(source['code'])
            require(not any(isinstance(n, (ast.Try, ast.TryStar, ast.With, ast.AsyncWith)) for n in ast.walk(tree)),
                    'frontier_source_must_not_intercept_stop')
        entries = []
        for request, receipt in zip(requests, receipts):
            sid = receipt['span_id']
            require(sid in by_id and sid not in used and position[sid] < position[outer['span_id']],
                    'unique_prior_inner_receipt_required')
            event = by_id[sid]
            require(event['stage'] == 'python_api' and event['call'] == call
                    and type(event['api_request_sent']) is bool
                    and receipt['api_request_sent'] is event['api_request_sent']
                    and receipt['api'] == request['app'] + '__' + request['api']
                    and not event.get('effects_unknown'), 'inner_receipt_binding_differs')
            used.add(sid)
            entry = reply_from_receipt(request, spans[sid], event, schemas)
            observation = spans[sid]['observation']
            if 'contract_feedback' in observation:
                require(not entry['originally_sent'] and observation.get('format_error') == UNKNOWN_PARAMETER,
                        'only_confirmed_schema_rejection_feedback_supported')
                # Preserve the original rendered exception exactly. Replay's
                # predispatch row is not decorated a second time.
                entry['reply']['error'] = feedback_canonical(dict(format_error=UNKNOWN_PARAMETER,
                    contract_feedback=observation['contract_feedback']))
            execution = event.get('api_execution')
            if event['api_request_sent']:
                require(type(execution) is dict and execution['bridge_request_sent'] is True
                    and execution.get('protocol') == PROTOCOL
                    and execution['status'] == ('returned' if entry['reply']['ok'] else 'raised')
                    and execution['automatic_retries'] == 0
                    and type(execution['nonce']) is str and execution['nonce'] not in nonces
                    and len(execution['nonce']) == 32 and all(c in '0123456789abcdef' for c in execution['nonce'])
                    and type(execution['raw_reply_sha256']) is str
                    and len(execution['raw_reply_sha256']) == 64
                    and all(c in '0123456789abcdef' for c in execution['raw_reply_sha256']),
                    'known_unique_typed_receipt_required')
                nonces.add(execution['nonce'])
            else:
                require(execution is None, 'unsent_request_cannot_have_typed_execution')
            entries.append(entry)
        require(sum(e['originally_sent'] for e in entries) == result['api_requests'],
                'program_sent_count_differs')
        if frontier:
            entries.append(dict(request=requests[-1], reply=None, originally_sent=False,
                                declared_complete=False, effects_unknown=False, frontier=True))
        files = {str(p.relative_to(trial)): file_sha(p) for p in directory.iterdir() if p.is_file()}
        programs.append(dict(name=directory.name, source=source, expected=result, entries=entries,
                             source_sha256=files, frontier=frontier))
    require(len(programs) == expected_count and used == {e['span_id'] for e in events if e['stage'] == 'python_api'},
            'every_fixed_program_and_inner_receipt_required')
    require_empty_observations(programs)
    return programs


class FrontierTape(ActionTape):
    def __init__(self, entries):
        super().__init__(entries)
        self.frontier_reached = False

    def at_frontier(self, action):
        entry = self.next(action)
        if not entry.get('frontier'):
            return False
        require(self.index == len(self.entries) - 1 and entry['reply'] is None,
                'only_final_unobserved_action_can_be_frontier')
        self.events.append(dict(index=self.index, kind='fixture_saved_frontier',
                                action_sha256=digest(action)))
        self.index += 1
        self.frontier_reached = True
        self.active_dispatched = False
        return True

    def finish(self):
        super().finish()
        require(self.frontier_reached is bool(self.entries and self.entries[-1].get('frontier')),
                'fixed_frontier_must_be_reached_exactly_once')


class RegionReplayHost(RegionProjectionHost):
    def __init__(self, *args, **kwargs):
        self.boundaries = []
        self.frontier_controls = []
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
        op = packet.get('op') if type(packet) is dict else None
        if op in ('call', 'projection_lookup'):
            require(set(packet) == {'id', 'op', 'args', 'releases'} and packet['releases'] == []
                and type(packet['id']) is int and packet['id'] == self.last_id + 1
                and type(packet['args']) is dict, 'valid_replay_control_required')
            args = packet['args']
            if op == 'projection_lookup':
                require(self.region_policy == POLICIES[1] and self.expected_plan.eligible,
                        'eligible_automatic_region_lookup_required')
                self._field_shape(args)  # Catalog/demand validation only; no provider lookup.
            else:
                require(set(args) == {'app', 'api', 'args'} and type(args['app']) is str
                        and type(args['api']) is str and type(args['args']) is dict,
                        'ordinary_replay_action_shape_required')
            action = {k: args[k] for k in ('app', 'api', 'args')}
            if self.tape.at_frontier(action):
                # Intercept before provider lookup, exact cache, reservation or
                # channel. The tape has no value for this final action.
                self.last_id = packet['id']
                self.frontier_controls.append(dict(op=op, action_sha256=digest(action),
                    provider_lookup_performed=False, saved_backend_response_used=False))
                self.control_events.append(dict(id=self.last_id, op='fixture_frontier', released=0))
                self.channel.budget.stopped = True
                return dict(id=self.last_id, ok=False, error=FRONTIER_ERROR, fatal=True)
        if op == 'replay_boundary':
            require(set(packet) == {'id', 'op', 'args', 'releases'} and packet['releases'] == []
                and packet['id'] == self.last_id + 1 and not self.tape.frontier_reached,
                'valid_nonfrontier_boundary_required')
            value = packet['args']
            require(set(value) == {'program_index', 'roots', 'plain_namespace_sha256', 'unsupported_names'},
                    'exact_boundary_snapshot_shape_required')
            self.last_id = packet['id']
            self.control_events.append(dict(id=self.last_id, op='replay_boundary', released=0))
            self.boundaries.append(deepcopy(value))
            return dict(id=self.last_id, ok=True, value=None, fatal=self.channel.budget.stopped)
        require(op != 'explicit_fields', 'unchanged_saved_source_has_no_explicit_field_requests')
        if op != 'call':
            return super().request(packet)
        self.tape.begin_call(packet['args'])
        before = self.ordinary_complete_reuses
        reply = super().request(packet)
        self.tape.finish_call(reply, self.ordinary_complete_reuses - before)
        return reply


class RegionReplayPython(RegionProjectionPython):
    def __init__(self, *args, root_names, **kwargs):
        self.root_names = tuple(root_names)
        super().__init__(*args, **kwargs)

    def _bootstrap(self):
        source = derived_region_bootstrap(self.policy)
        install, boundary = "scope = {'__name__':'__main__'}\n", '    content=capture.getvalue()\n'
        require(source.count(install) == source.count(boundary) == 1, 'trusted_boundary_anchors_changed')
        source = source.replace(install, inspect.getsource(boundary_snapshot) + '\n' + install)
        code = ("    if not _projection_client.closed:\n"
                "        _projection_client.rpc('replay_boundary', boundary_snapshot(scope, "
                + repr(self.root_names) + ", program_index))\n")
        return source.replace(boundary, code + boundary)


class RegionReplayProgram(RegionProjectionProgram):
    host_class = RegionReplayHost


def coverage_binding(path, repo, storage):
    value = read(path)
    require(value.get('status') == 'complete' and value['aggregate']['programs'] == 146
        and len(value['conditions']) == 8 and value['compiler_sha256'] == file_sha(repo / 'scripts/region_field_projection.py')
        and all(value.get(k) == 0 for k in ('models', 'API', 'evaluator', 'tokenizer',
                                          'Docker_launches', 'generated_program_execution')),
        'closed_all_146_AST_only_coverage_required')
    input_count = 0
    for name, expected in value['source_sha256'].items():
        source = Path(name)
        require(source.is_absolute() and (source.resolve().is_relative_to(repo.resolve())
            or source.resolve().is_relative_to((storage / 'records/context_pilot').resolve())
            or source.name.startswith('AI_P125_closed_independent_review_')),
            'bounded_coverage_source_required')
        require(file_sha(source) == expected, 'static_coverage_source_changed')
        if source.name == 'input_private.json':
            saved = read(source)
            require(saved.get('observations') == [] and type(saved['observations']) is list,
                    'all_original_sources_require_empty_observations')
            plan_region_projection(saved['code'])  # AST only, never exec.
            input_count += 1
    require(input_count == 146, 'all_146_original_inputs_required')
    return dict(report_sha256=file_sha(path), original_programs=input_count,
                eligible_programs=value['aggregate']['eligible'], source_hash_count=len(value['source_sha256']))


def synthetic_binding(path, repo):
    value = read(path)
    require(value.get('status') == 'pass' and type(value.get('tests_run')) is int and value['tests_run'] > 0
            and value.get('failures') == value.get('errors') == 0, 'passing_synthetic_contract_evidence_required')
    hashes = value.get('source_sha256')
    needed = set(REQUIRED_IMPLEMENTATION) | {'tests/test_region_field_projection.py', 'tests/test_region_projection_runtime.py',
                                            'tests/test_demand_joined_read_adapter.py'}
    require(type(hashes) is dict and needed.issubset(hashes), 'bound_normal_path_synthetic_sources_required')
    for name, expected in hashes.items():
        require(not Path(name).is_absolute() and '..' not in Path(name).parts
                and name.split('/')[0] in ('scripts', 'tests') and file_sha(repo / name) == expected,
                'synthetic_contract_source_changed')
    return dict(report_sha256=file_sha(path), tests_run=value['tests_run'])


def dependency_files(repo, roots):
    """Static local-import closure; no unrelated online driver/reporting files.

Dynamic trusted bootstrap sources are imported directly by the runtime; public
schemas and installed serializer bytes have separate manifest/verifier binds.
"""
    available = {p.stem: p for directory in ('scripts', 'tests')
                 for p in (repo / directory).glob('*.py')}
    pending, found = [repo / name for name in roots], set()
    while pending:
        path = pending.pop()
        if path in found:
            continue
        require(path.is_file() and not path.is_symlink() and path.resolve().is_relative_to(repo.resolve()),
                'regular_repository_dependency_required')
        found.add(path)
        if path.suffix != '.py':
            continue
        tree = ast.parse(path.read_text())
        modules = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules.extend(alias.name.split('.')[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules.append(node.module.split('.')[0])
        pending.extend(available[name] for name in modules if name in available and available[name] not in found)
    return sorted(found)


def prepare_manifest(storage, repo, data, coverage_path, synthetic_path):
    require(repo.resolve() == ROOT.resolve(), 'executing_repository_root_must_match')
    coverage = coverage_binding(coverage_path, repo, storage)
    synthetic = synthetic_binding(synthetic_path, repo)
    tools, schema_hashes, _ = load_public_tools(data)
    schemas = {tool['function']['name']: tool['function'] for tool in tools}
    traces = []
    audit = read(repo / 'reports/P125_comparison.json')
    require(audit['phase'] == 'P125' and not audit['audit_errors'] and audit['owned_processes_absent'] is True,
            'closed_P125_audit_required')
    for run_id in FIXED_RUNS:
        trial = storage / 'records/context_pilot' / run_id
        summary = _closed_trial(trial)
        programs = load_region_programs(trial, schemas)
        receipts = [e['api_execution'] for e in read(trial / 'events.json') if 'api_execution' in e]
        _same(receipts, summary['api_execution_receipts'], 'closed_typed_receipt_inventory_differs')
        require(sum(p['expected']['api_requests'] for p in programs) == summary['api_requests'],
                'whole_trace_sent_count_differs')
        row = next(r for r in audit['rows'] if r['run_id'] == run_id)
        require(row['record_status'] == 'evaluated' and row['summary_sha256'] == file_sha(trial / 'summary.json'),
                'closed_summary_must_match_audit')
        files = {name: file_sha(trial / name) for name in ('events.json', 'spans.json', 'summary.json',
            'source_identity.json', 'comparison_plan.json', 'plan.json')}
        for program in programs:
            files.update(program['source_sha256'])
        audited_files = row['runtime_audit_hashes']
        require(all(name in audited_files and audited_files[name] == expected
                    for name, expected in files.items() if name.startswith('programs/')
                    or name in ('events.json', 'spans.json')),
                'replay_inputs_must_match_closed_independent_audit')
        traces.append(dict(run_id=run_id, programs=[p['name'] for p in programs], private_files=files,
            frontier_program=PROGRAM_COUNT, frontier_logical_index=len(programs[-1]['entries']) - 1,
            frontier_action_sha256=digest(action_of(programs[-1]['entries'][-1]))))
    roots = ('scripts/probe_region_projection_replay.py', 'tests/test_region_projection_replay.py',
             'configs/python_export_image_v01.json', 'docs/experiments/P126_region_projection_replay.md',
             *read(synthetic_path)['source_sha256'])
    paths = dependency_files(repo, roots)
    return dict(phase='P126', kind='fixed_saved_frontier_replay', traces=traces, policies=list(POLICIES),
        maximum_programs=MAX_PROGRAMS, maximum_containers=4, total_seconds=TOTAL_SECONDS,
        program_seconds=PROGRAM_SECONDS, cleanup_reserve_seconds=CLEANUP_RESERVE_SECONDS,
        static_coverage_path=str(coverage_path.resolve()), static_coverage=coverage,
        synthetic_evidence_path=str(synthetic_path.resolve()), synthetic_evidence=synthetic,
        schema_files=schema_hashes, P125_audit_sha256=file_sha(repo / 'reports/P125_comparison.json'),
        dependency_scope='Local import AST closure of replay and bound synthetic tests, plus image config and experiment protocol; unrelated online drivers excluded.',
        implementation_files={str(p.relative_to(repo)): file_sha(p) for p in paths},
        additional_model_calls=0, additional_API_requests=0, additional_evaluations=0, additional_tokenizer_calls=0)


def check_manifest(manifest, storage, repo, data):
    expected = prepare_manifest(storage, repo, data, Path(manifest['static_coverage_path']),
                                Path(manifest['synthetic_evidence_path']))
    _same(manifest, expected, 'frozen_manifest_differs')
    return expected


def run_replay(storage, repo, data, manifest_path, output):
    began = time.monotonic()
    manifest = check_manifest(read(manifest_path), storage, repo, data)
    require(not output.exists(), 'preserve_every_replay_attempt')
    output.mkdir(parents=True)
    put(output / 'input_manifest_private.json', manifest)
    tools, _, _ = load_public_tools(data)
    schemas = {tool['function']['name']: tool['function'] for tool in tools}
    public_source = storage / '.runtime/appworld/venv/lib/python3.12/site-packages/appworld/apps/spotify'
    require(verify_joined_implementation(public_source) == JOINED_CONTRACT_ID, 'pinned_join_contract_required')
    rows, errors, attempted, containers, attempted_slots = [], [], 0, 0, set()
    for trace_number, run_id in enumerate(FIXED_RUNS, 1):
        programs = load_region_programs(storage / 'records/context_pilot' / run_id, schemas)
        roots, peers = root_inventory(programs), []
        for policy in POLICIES:
            session = None
            directory = output / f'trace_{trace_number}' / policy
            directory.mkdir(parents=True)
            try:
                require(time.monotonic() - began < TOTAL_SECONDS - CLEANUP_RESERVE_SECONDS,
                        'global_replay_wall_limit')
                session = RegionReplayPython(storage, directory / 'session', policy=policy, root_names=roots)
                containers += 1
                budget, transport, catalog = RequestBudget(80), SavedResultTransport(), PublicNameCatalog(tools)
                catalog.visible = set(programs[0]['source']['api_schemas'])
                runner = RegionReplayProgram(session, budget, execution_scope=f'P126:{trace_number}:{policy}',
                    public_source_directory=public_source, policy=policy)
                for ordinal, program in enumerate(programs, 1):
                    remaining = TOTAL_SECONDS - CLEANUP_RESERVE_SECONDS - (time.monotonic() - began)
                    require(remaining > 0 and attempted < MAX_PROGRAMS, 'finite_replay_limits_exceeded')
                    transport.tape = FrontierTape(program['entries'])
                    source = program['source']
                    require({n: catalog.catalog[n]['function'] for n in sorted(catalog.visible)} == source['api_schemas'],
                            'schema_boundary_differs')
                    channel = ReplayApiChannel(catalog, transport, 80)
                    folder = directory / 'programs' / program['name']
                    prior_boundaries = len(runner.host.boundaries) if runner.host else 0
                    attempted += 1
                    attempted_slots.add((trace_number, policy, ordinal))
                    actual = runner(source['code'], [], channel, storage_root=storage, record_dir=folder,
                                    timeout=min(PROGRAM_SECONDS, remaining))
                    transport.tape.finish()
                    evidence = read(folder / 'projection_program_private.json')
                    boundaries = runner.host.boundaries[prior_boundaries:]
                    frontier = program['frontier']
                    expected = program['expected']
                    checks = dict(logical_action_tape_complete=True,
                        stdout=actual['stdout'] == expected['stdout'],
                        stdout_truncated=actual['stdout_truncated'] == expected['stdout_truncated'],
                        known_effects=actual['unknown_effects'] is False,
                        completion=actual['declared_complete'] == expected['declared_complete'])
                    boundary = None
                    if frontier:
                        checks.update(fixed_frontier=transport.tape.frontier_reached,
                            no_normal_boundary=not boundaries,
                            exact_frontier_exception=actual.get('error') == 'RuntimeError: ' + FRONTIER_ERROR,
                            one_frontier_control=len(runner.host.frontier_controls) == 1,
                            saved_suffix_not_dispatched=not transport.tape.active_dispatched)
                        require(evidence['execution_transform_report'] and
                            evidence['execution_transform_report'][0]['execution_status'] == 'execution_error',
                            'frontier_requires_incomplete_segment_report')
                    else:
                        require(len(boundaries) == 1 and boundaries[0]['program_index'] == ordinal,
                                'one_normal_boundary_per_prefix_program_required')
                        boundary = boundaries[0]
                        checks.update(status=actual['status'] == expected['status'], error=actual['error'] == expected['error'],
                            no_projection_contract_failure=not runner.host.projection_failed)
                        require(all(not value['present'] or value['type'] == 'dict' for value in boundary['roots'].values()),
                                'normal_roots_must_remain_real_dict')
                        if policy == POLICIES[0]:
                            peers.append(dict(boundary=boundary, result=actual))
                        else:
                            checks['paired_normal_boundary'] = boundary == peers[ordinal - 1]['boundary']
                    events = transport.tape.events
                    saved = sum(e['kind'] == 'saved_backend_response' for e in events)
                    require(actual['api_requests'] == saved and budget.pending == 0, 'simulated_program_count_differs')
                    row = dict(trace_slot=trace_number, policy=policy, program_number=ordinal,
                        record_status='matched' if all(checks.values()) else 'mismatch',
                        original_execution_status=expected['status'], actual_execution_status=actual['status'],
                        comparison_scope='saved_frontier_prefix' if frontier else 'normal_prefix_boundary', checks=checks,
                        logical_requests=len(events), saved_backend_responses=saved,
                        ordinary_complete_cache_hits=sum(e['kind'] == 'ordinary_complete_cache' for e in events),
                        projection_hits=sum(e['kind'] == 'observed_partial_projection' for e in events),
                        fixture_frontier_termination=frontier,
                        projection_stop_due_to_fixture_frontier=frontier and runner.host.projection_failed,
                        normal_root_equivalence_claimed=all(checks.values()) and checks.get('paired_normal_boundary') is True,
                        source_sha256=evidence['source_sha256'], segment_trace_sha256=digest(evidence['execution_transform_report']),
                        boundary_sha256=digest(boundary) if boundary is not None else None,
                        stdout_sha256=digest(actual['stdout']), error_sha256=digest(actual['error']),
                        control_requests=evidence['control_requests'], control_request_bytes=evidence['control_request_bytes'],
                        control_reply_bytes=evidence['control_reply_bytes'], wall_seconds=actual['wall_seconds'])
                    rows.append(row)
                    put(folder / 'replay_actions_private.json', events)
                    if boundary is not None:
                        put(folder / 'replay_boundary_private.json', boundary)
                    require(all(checks.values()), 'fixed_observable_prefix_differs')
                    if not frontier:
                        require(actual['session_usable'], 'normal_prefix_interpreter_unusable')
                require(transport.saved_backend_responses == budget.spent <= 80 and budget.pending == 0,
                        'simulated_trace_budget_differs')
            except Exception as error:
                errors.append(dict(trace_slot=trace_number, policy=policy, exception_type=type(error).__name__))
                put(directory / 'failure_private.json', dict(type=type(error).__name__, message=str(error)))
            finally:
                if session is not None:
                    cleanup_started = time.monotonic()
                    try:
                        session.close()
                        require(session.state['container_removed'] and time.monotonic() - cleanup_started <= CLEANUP_RESERVE_SECONDS,
                                'bounded_owned_container_cleanup_required')
                    except Exception as error:
                        errors.append(dict(trace_slot=trace_number, policy=policy, cleanup_exception_type=type(error).__name__))
            if errors:
                break
        if errors:
            break
    unchanged = all(file_sha(repo / name) == expected for name, expected in manifest['implementation_files'].items())
    original_unchanged = all(file_sha(storage / 'records/context_pilot' / trace['run_id'] / name) == expected
        for trace in manifest['traces'] for name, expected in trace['private_files'].items())
    if time.monotonic() - began > TOTAL_SECONDS:
        errors.append(dict(exception_type='FiniteReplayWallLimitExceeded'))
    complete = not errors and len(rows) == MAX_PROGRAMS and unchanged and original_unchanged
    measured_rows = list(rows)
    rows = retain_slots(rows, attempted_slots)
    result = dict(phase='P126', status='complete' if complete else 'failed',
        all_original_sources_accounted=manifest['static_coverage']['original_programs'] == 146,
        observed_region_partial_hits=sum(row['projection_hits'] for row in measured_rows),
        unobserved_suffix_executed=False, original_sources_changed=not original_unchanged,
        additional_model_calls=0, additional_API_requests=0, additional_evaluations=0, additional_tokenizer_calls=0,
        replay_audit_errors=errors, normal_path_synthetic_contract_tests_passed=True,
        synthetic_evidence_sha256=manifest['synthetic_evidence']['report_sha256'],
        static_coverage_sha256=manifest['static_coverage']['report_sha256'],
        source_sha256=manifest['implementation_files'], implementation_unchanged_at_end=unchanged,
        input_manifest_sha256=file_sha(manifest_path), attempted_programs=attempted, containers=containers,
        programs=rows, compared_programs=len(measured_rows),
        normal_boundary_programs=sum(not row['fixture_frontier_termination'] for row in measured_rows),
        frontier_programs=sum(row['fixture_frontier_termination'] for row in measured_rows),
        wall_seconds=time.monotonic() - began, task_completion_established=False,
        whole_task_quality_or_token_savings_established=False,
        raw_task_values_code_prompts_published=False,
        simulated_saved_backend_counts_are_not_environment_API_requests=True)
    put(output / 'summary.json', result)
    return result


def retain_slots(rows, attempted):
    """A failure retains all 48 slots without imputing outcomes or savings."""
    mapping = {(r['trace_slot'], r['policy'], r['program_number']): r for r in rows}
    require(len(mapping) == len(rows), 'duplicate_replay_slot')
    expected = [(trace, policy, n) for trace in (1, 2) for policy in POLICIES for n in range(1, 13)]
    require(set(mapping).issubset(expected) and set(attempted).issubset(expected), 'outside_fixed_replay_slots')
    return [mapping.get(key, dict(trace_slot=key[0], policy=key[1], program_number=key[2],
        record_status='attempted_without_complete_evidence' if key in attempted else 'not_run',
        original_execution_status=None, actual_execution_status=None,
        checks=None, logical_requests=None, saved_backend_responses=None,
        ordinary_complete_cache_hits=None, projection_hits=None, fixture_frontier_termination=None,
        normal_root_equivalence_claimed=False, source_sha256=None, wall_seconds=None)) for key in expected]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--storage-root', type=Path, required=True)
    parser.add_argument('--repo-root', type=Path, default=ROOT)
    parser.add_argument('--data-root', type=Path, required=True)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--coverage', type=Path)
    parser.add_argument('--synthetic-evidence', type=Path)
    parser.add_argument('--prepare-only', action='store_true')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.prepare_only:
        require(args.output is None and args.coverage is not None and args.synthetic_evidence is not None,
                'prepare_requires_static_and_synthetic_evidence_without_output')
        put(args.manifest, prepare_manifest(args.storage_root, args.repo_root, args.data_root,
                                           args.coverage, args.synthetic_evidence))
        print(json.dumps(dict(manifest_prepared=True, generated_programs_executed=0)))
    else:
        require(args.output is not None, 'new_private_replay_output_required')
        result = run_replay(args.storage_root, args.repo_root, args.data_root, args.manifest, args.output)
        print(json.dumps({k: result[k] for k in ('status', 'attempted_programs', 'observed_region_partial_hits',
                                               'additional_API_requests', 'wall_seconds')}))


if __name__ == '__main__':
    main()
