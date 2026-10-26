"""Opt-in isolated region projection with a shared ordinary field-read control.

This module does not launch a study. Joined fields, explicit demand, complete
cache, feedback and source authority are common components of both policies.
The extra policy only transforms admitted regions of ordinary call_api code.
"""
from copy import deepcopy
import hashlib
import inspect
import json
from pathlib import Path
import time

import automatic_field_projection as base_compiler
import region_field_projection as region_compiler
from agent_read_view_runtime import AgentReadViewPython
from automatic_projection_runtime import (
    AutomaticProjectionHost, AutomaticProjectionPython, ProjectionApiChannel,
    ProjectionWireClient, ProjectionWireFault,
)
from contract_comparison import FeedbackProgram
from demand_joined_read_adapter import DemandJoinedReadAdapter
from field_read_contract import CONTRACT_ID, FIELDS, canonical, target_identity, valid_field
from joined_public_read_views import JoinedPublicReadAuthority, verify_joined_implementation
from online_projection_runtime import OnlineProjectionProgram
from persistent_api_python import BOOTSTRAP
from persistent_read_view_python import ViewControlChannel

POLICIES = ('explicit_joined_fields', 'automatic_region_joined_fields')

EXPLICIT_FIELD_GUIDE = '''
The persistent Python runtime also provides read_fields(app, api, fields, **args).
For spotify/show_song only, fields is a nonempty list of distinct requested names
from song_id, title, album_id, duration, artists. For example,
read_fields("spotify", "show_song", ["title", "artists"], song_id=known_song_id)
returns a dict containing exactly those fields. Prefer it when only those fields
are needed. It reuses consistent information already returned in this task when
available; otherwise it makes the ordinary show_song request and selects fields.
This does not infer song identifiers. A returned field dict is not a full API
response. Use call_api when you need the complete response. All real requests,
failures, recovery and model calls remain subject to the same task budgets.
'''


class RegionWireClient(ProjectionWireClient):
    def read_fields(self, app, api, fields, **args):
        return self.rpc('explicit_fields', dict(app=app, api=api, args=args, fields=fields))


class RegionProjectionHost(AutomaticProjectionHost):
    def __init__(self, *args, policy, execution_scope, public_source_directory, **kwargs):
        if policy not in POLICIES:
            raise ValueError('explicit_region_policy_required')
        self.region_policy = policy
        self.public_source_directory = Path(public_source_directory)
        # Inherit the ordinary cache, exact replies, barriers and typed channel.
        internal = 'automatic_projection_cached' if policy == POLICIES[1] else 'eager_cached'
        super().__init__(*args, policy=internal, execution_scope=execution_scope,
                         verified_contract=CONTRACT_ID, **kwargs)
        verified = verify_joined_implementation(self.public_source_directory)
        self.provider = JoinedPublicReadAuthority(execution_scope, verified_contract=verified)
        self.authority = self.provider.grant
        self.field_events = []
        self.control_wall_seconds_including_backend = 0.0
        self.projection_lookup_wall_seconds = 0.0
        self._make_demand_adapter()

    def _make_demand_adapter(self):
        # The adapter also verifies pinned sources; a contract name is not proof.
        self.demand_adapter = DemandJoinedReadAdapter(
            self.provider, self.channel.catalog, self.channel.budget,
            lambda: self.epoch, public_source_directory=self.public_source_directory)

    def attach(self, channel):
        super().attach(channel)
        if channel.catalog is not self.demand_adapter.catalog:
            self.projection_failed = self.channel.budget.stopped = True
            raise ValueError('same_task_catalog_required')

    def request(self, packet):
        began = time.monotonic()
        op = packet.get('op') if type(packet) is dict else None
        try:
            if op == 'explicit_fields':
                return self._explicit_fields(packet)
            return super().request(packet)
        finally:
            elapsed = time.monotonic() - began
            self.control_wall_seconds_including_backend += elapsed
            if op == 'projection_lookup':
                self.projection_lookup_wall_seconds += elapsed

    def _field_shape(self, args):
        if (type(args) is not dict or set(args) != {'app', 'api', 'args', 'fields'}
                or type(args['app']) is not str or type(args['api']) is not str
                or type(args['args']) is not dict or type(args['fields']) is not list
                or not args['fields'] or len(args['fields']) > len(FIELDS)
                or any(type(f) is not str for f in args['fields'])
                or len(set(args['fields'])) != len(args['fields'])
                or not set(args['fields']).issubset(FIELDS)):
            raise ValueError('supported_distinct_field_list_required')
        action = {k: deepcopy(args[k]) for k in ('app', 'api', 'args')}
        if target_identity(action['app'] + '__' + action['api'], action['args']) is None:
            raise ValueError('explicit_fields_supports_public_show_song_only')
        if not self._ordinary_catalog_valid(action):
            raise ValueError('ordinary_public_API_capability_required')
        return action

    def _lookup_fields(self, action, fields, *, origin):
        result = self.demand_adapter.lookup_fields(action, fields, self.epoch)
        # Adapter API is deliberately separate from ordinary full-response reuse.
        kind = result.kind
        value = result.value
        event = dict(kind=kind, origin=origin, epoch=self.epoch,
            action_sha256=hashlib.sha256(canonical(action).encode()).hexdigest(),
            fields=sorted(fields), environment_API_requests=0, full_cache_updated=False)
        self.field_events.append(event)
        return kind, value

    def _lookup(self, args):
        self.channel.budget._ready()
        if self.region_policy != POLICIES[1] or not self.expected_plan.eligible:
            raise ValueError('admitted_region_projection_required')
        action = self._field_shape(args)
        kind, value = self._lookup_fields(action, args['fields'], origin='automatic_region')
        self.projection_events.append(deepcopy(self.field_events[-1]))
        return deepcopy(value) if kind == 'partial' else None

    def _explicit_fields(self, packet):
        if (set(packet) != {'id', 'op', 'args', 'releases'}
                or type(packet['id']) is not int or packet['id'] != self.last_id + 1
                or packet['releases'] != [] or self.expected_plan is None):
            raise ValueError('invalid_explicit_fields_control')
        args = packet['args']
        try:
            action = self._field_shape(args)
        except (ValueError, TypeError) as error:
            # User input errors are ordinary recoverable capability rejections.
            # They do not enter the trusted adapter or dispatch a task API.
            self.last_id = packet['id']
            self.control_events.append({'id': self.last_id, 'op': 'explicit_fields_rejected', 'released': 0})
            return dict(id=self.last_id, ok=False, fatal=self.channel.budget.stopped,
                        error=type(error).__name__ + ': ' + str(error))
        try:
            kind, value = self._lookup_fields(action, args['fields'], origin='explicit_fields')
        except Exception:
            self.projection_failed = self.channel.budget.stopped = True
            self.last_id = packet['id']
            self.control_events.append({'id': self.last_id, 'op': 'explicit_fields_contract_failed', 'released': 0})
            return dict(id=self.last_id, ok=False, fatal=True, error='explicit_field_authority_failed')
        if kind == 'partial':
            self.last_id = packet['id']
            self.control_events.append({'id': self.last_id, 'op': 'explicit_fields', 'released': 0})
            return dict(id=self.last_id, ok=True, fatal=False, value=deepcopy(value))
        # Reuse the exact ordinary cache/barrier/receipt path with this request's
        # single sequence ID. The full return is observed by the provider there.
        ordinary = dict(packet, op='call', args=action)
        reply = super().request(ordinary)
        if reply['ok']:
            full = reply['value']
            if (type(full) is not dict or not set(args['fields']).issubset(full)
                    or any(not valid_field(field, full[field]) for field in args['fields'])):
                self.projection_failed = self.channel.budget.stopped = True
                return dict(id=self.last_id, ok=False, fatal=True,
                            error='explicit_field_full_response_contract_false')
            reply['value'] = {field: deepcopy(full[field]) for field in args['fields']}
        return reply

    def _report(self, value):
        required = {'source_sha256', 'transformed_sha256', 'transformed', 'hits',
                    'misses', 'failed', 'reason', 'regions', 'segments', 'plan_sha256', 'execution_status'}
        if (type(value) is not dict or set(value) != required
                or value['source_sha256'] != self.expected_plan.source_sha256
                or value['transformed_sha256'] != self.expected_plan.transformed_sha256
                or value['plan_sha256'] != self.expected_plan.plan_sha256
                or type(value['transformed']) is not bool or type(value['failed']) is not bool
                or type(value['regions']) is not list or type(value['segments']) is not list
                or type(value['reason']) is not str
                or value['execution_status'] not in ('ok', 'execution_error')
                or any(type(value[k]) is not int or value[k] < 0 for k in ('hits', 'misses'))
                or self.region_policy == POLICIES[0] and (value['transformed'] or value['hits'] or value['regions'] or value['segments'])
                or value['transformed'] and not self.expected_plan.eligible):
            raise ValueError('invalid_region_program_report')
        segments = value['segments']
        regions = value['regions']
        complete = value['execution_status'] == 'ok'
        if segments:
            if (len(segments) > len(self.expected_plan.segments)
                    or complete and len(segments) != len(self.expected_plan.segments)):
                raise ValueError('executed_segment_prefix_required')
            expected_regions = []
            for index, (seen, expected) in enumerate(zip(segments, self.expected_plan.segments[:len(segments)], strict=True)):
                transformed = seen.get('transformed')
                if (type(transformed) is not bool or type(seen.get('segment_index')) is not int
                        or seen['segment_index'] != index
                        or seen.get('kind') != expected['kind'] or type(seen.get('completed')) is not bool
                        or (complete or index < len(segments) - 1) and seen['completed'] is not True
                        or seen.get('original_sha256') != expected['source_sha256']
                        or seen.get('candidate_sha256') != expected['transformed_sha256']
                        or seen.get('selected_sha256') != expected['transformed_sha256' if transformed else 'source_sha256']
                        or transformed and expected['kind'] != 'region'):
                    raise ValueError('segment_selection_hash_mismatch')
                if expected['kind'] == 'region':
                    expected_regions.append((expected, seen))
            if len(regions) != len(expected_regions):
                raise ValueError('every_region_admission_report_required')
            previous_hits = 0
            for region, (expected, selected) in zip(regions, expected_regions, strict=True):
                if (type(region.get('site_index')) is not int or region['site_index'] != expected['site_index']
                        or type(region.get('admitted')) is not bool
                        or region['admitted'] is not selected['transformed']
                        or region.get('transformed') is not selected['transformed']
                        or region.get('original_sha256') != expected['source_sha256']
                        or region.get('executed_sha256') != selected['selected_sha256']
                        or region.get('reason') != selected['reason']
                        or any(type(region.get(k)) is not int or region[k] < 0 for k in ('hits_before', 'hits_after'))
                        or region['hits_before'] != previous_hits
                        or region['hits_after'] < region['hits_before']):
                    raise ValueError('region_admission_evidence_mismatch')
                previous_hits = region['hits_after']
            if value['transformed'] is not any(r['admitted'] for r in regions):
                raise ValueError('region_transform_summary_mismatch')
            if previous_hits != value['hits']:
                raise ValueError('region_hit_intervals_disagree')
        elif regions or value['transformed']:
            raise ValueError('region_execution_evidence_missing')
        events = self.projection_events[self.program_event_start:]
        if (len(self.program_reports) != self.program_report_start
                or value['hits'] != sum(e['kind'] == 'partial' for e in events)
                or value['misses'] != sum(e['kind'] in ('miss', 'complete') for e in events)
                or complete and (value['failed'] or self.projection_failed)
                or value['failed'] and not self.projection_failed
                or not complete and value['hits'] and not self.projection_failed
                or not value['transformed'] and events):
            raise ValueError('region_report_disagrees_with_host_events')
        self.program_reports.append(deepcopy(value))
        return None


def derived_region_bootstrap(policy):
    if policy not in POLICIES:
        raise ValueError('explicit_region_policy_required')
    install = 'import types\n'
    for module, name in ((base_compiler, 'automatic_field_projection'),
                         (region_compiler, 'trusted_region_projection_v1')):
        source = Path(module.__file__).read_text()
        install += (f'_installed_engine = types.ModuleType({name!r})\n'
            'sys.modules[_installed_engine.__name__] = _installed_engine\n'
            f'exec(compile({source!r}, "<trusted region engine>", "exec"), _installed_engine.__dict__)\n')
    install += ('_region_engine = _installed_engine\n'
        + inspect.getsource(ProjectionWireFault) + '\n'
        + inspect.getsource(ProjectionWireClient) + '\n'
        + inspect.getsource(RegionWireClient) + '\n'
        '_projection_client = RegionWireClient(call_api)\n'
        '_projection_call = _projection_client.call\n'
        '_explicit_fields_call = _projection_client.read_fields\n')
    anchor = "scope = {'__name__':'__main__'}\n"
    refresh = "    scope.update(call_api=call_api, observations=packet['observations'], api_schemas=api_schemas)\n"
    execute = "            exec(compile(packet['code'],'<generated>','exec'),scope,scope)\n"
    if any(BOOTSTRAP.count(s) != 1 for s in (anchor, refresh, execute)):
        raise ValueError('persistent_bootstrap_boundary_changed')
    result = BOOTSTRAP.replace(anchor, install + anchor).replace(refresh,
        "    scope.update(call_api=_projection_call, read_fields=_explicit_fields_call, observations=packet['observations'], api_schemas=api_schemas)\n")
    body = ("            _region_plan = _region_engine.plan_region_projection(packet['code'])\n"
        "            _region_runtime = _region_engine.RegionProjectionRuntime(_projection_call, _projection_client.lookup, _projection_client.stop)\n"
        "            _region_status = 'ok'\n"
        "            try:\n")
    if policy == POLICIES[1]:
        body += '                _region_result = _region_engine.execute_region_projection(_region_plan, scope, _region_runtime)\n'
    else:
        body += '    ' + execute + "                _region_result = {'transformed': False, 'reason': 'ordinary_explicit_field_control', 'hits': 0, 'regions': [], 'segments': []}\n"
    body += ("            except BaseException:\n"
        "                _region_status = 'execution_error'\n"
        "                _region_result = dict(transformed=any(r['transformed'] for r in _region_runtime.region_reports),\n"
        "                    reason='recorded_execution_error', regions=_region_runtime.region_reports, segments=_region_runtime.segment_reports)\n"
        "                raise\n"
        "            finally:\n"
        "                _projection_client.report(dict(source_sha256=_region_plan.source_sha256,\n"
        "                    transformed_sha256=_region_plan.transformed_sha256,\n"
        "                    plan_sha256=_region_plan.plan_sha256, execution_status=_region_status,\n"
        "                    transformed=_region_result['transformed'], reason=_region_result['reason'],\n"
        "                    regions=_region_result['regions'], segments=_region_result['segments'], hits=_region_runtime.hits,\n"
        "                    misses=_region_runtime.misses, failed=_region_runtime.failed))\n")
    result = result.replace(execute, body)
    compile(result, '<trusted region bootstrap>', 'exec')
    return result


class RegionProjectionPython(AutomaticProjectionPython):
    def __init__(self, storage_root, session_dir, *, policy):
        if policy not in POLICIES:
            raise ValueError('explicit_region_policy_required')
        self.policy = policy
        AgentReadViewPython.__init__(self, storage_root, session_dir)

    def _bootstrap(self):
        return derived_region_bootstrap(self.policy)


class RegionProjectionProgram(OnlineProjectionProgram):
    host_class = RegionProjectionHost

    def __init__(self, session, budget, *, execution_scope, public_source_directory, policy):
        if not isinstance(session, RegionProjectionPython) or session.policy != policy or policy not in POLICIES:
            raise ValueError('matched_isolated_region_session_required')
        self.session, self.budget, self.policy = session, budget, policy
        self.execution_scope, self.public_source_directory = execution_scope, Path(public_source_directory)
        verify_joined_implementation(self.public_source_directory)
        self.host = None
        self.feedback = FeedbackProgram(lambda source, observations, channel, **kw: channel, 'public_schema')
        self.program_rows = []

    def make_channel(self, channel):
        wrapped = ProjectionApiChannel(channel, self.budget)
        wrapped.receipted = self.feedback('', [], wrapped.receipted)
        return wrapped

    def __call__(self, source, observations, channel, *, storage_root, record_dir,
                 timeout=90, on_record=lambda row: None):
        began = time.monotonic()
        row = dict(program=Path(record_dir).name, status='incomplete',
                   source_sha256=hashlib.sha256(source.encode()).hexdigest(),
                   budget_before=self.budget.snapshot(), evidence_recorded=False,
                   schema_evidence_recorded=False)
        self.program_rows.append(row)
        plan = region_compiler.plan_region_projection(source)
        before = self.budget.snapshot()
        wrapped = self.make_channel(channel)
        if self.host is None:
            self.host = self.host_class(wrapped, policy=self.policy,
                execution_scope=self.execution_scope, public_source_directory=self.public_source_directory)
        else:
            self.host.attach(wrapped)
        self.host.expect(plan)
        events_before = len(self.host.projection_events)
        fields_before = len(self.host.field_events)
        reports_before = len(self.host.program_reports)
        control = ViewControlChannel(self.host, on_record)
        try:
            result = self.session.run(source, observations, control, storage_root=storage_root,
                record_dir=record_dir, timeout=timeout, on_record=lambda row: None)
        except BaseException:
            if any(e['kind'] == 'partial' for e in self.host.projection_events[events_before:]):
                self.host.projection_failed = self.budget.stopped = True
                self.session.usable = False
                self.session.close()
            row.update(status='adapter_exception', wall_seconds=time.monotonic() - began,
                       budget_after=self.budget.snapshot())
            raise
        if str(result.get('error', '')).startswith('ProjectionWireFault:'):
            self.host.projection_failed = self.budget.stopped = True
        reports = self.host.program_reports[reports_before:]
        observed_partial = any(e['kind'] == 'partial' for e in self.host.projection_events[events_before:])
        missing_trace_after_partial = observed_partial and len(reports) != 1
        if missing_trace_after_partial:
            self.host.projection_failed = self.budget.stopped = True
        if result['status'] == 'ok' and len(reports) != 1:
            self.host.projection_failed = self.budget.stopped = True
        if self.host.projection_failed:
            result['underlying_execution_status'] = result['status']
            result['underlying_execution_error'] = result.get('error')
            result['contract_stop_reason'] = ('region_execution_report_missing_after_partial'
                if missing_trace_after_partial else 'region_projection_contract_failed')
            self.session.usable = False
            self.session.close()
            result.update(status='harness_error', error_type='region_projection_contract_stopped',
                          session_usable=False, container_removed=self.session.state['container_removed'])
        result.update(api_requests=self.budget.spent - before['spent'],
                      wall_seconds=time.monotonic() - began)
        evidence = dict(policy=self.policy, source_sha256=plan.source_sha256,
            transformed_sha256=plan.transformed_sha256, region_plan_sha256=plan.plan_sha256,
            transformed_artifact_is_review_only=True,
            executed_source_sha256=plan.source_sha256 if self.policy == POLICIES[0] else None,
            static_eligible=plan.eligible, static_reason=plan.reason, sites=plan.sites,
            budget_before=before, budget_after=self.budget.snapshot(),
            original_generated_archive_unchanged=True, execution_transform_report=reports,
            projection_failed=self.host.projection_failed,
            projection_events=self.host.projection_events[events_before:],
            field_events=self.host.field_events[fields_before:],
            control_requests=control.control_requests, control_request_bytes=control.control_request_bytes,
            control_reply_bytes=control.control_reply_bytes, result=result)
        folder = Path(record_dir)
        (folder / 'projection_candidate_source_private.py').write_text(plan.transformed_source)
        (folder / 'projection_program_private.json').write_text(json.dumps(evidence, indent=2) + '\n')
        (folder / 'projection_result_private.json').write_text(json.dumps(result, indent=2) + '\n')
        row.update(status=result['status'], wall_seconds=time.monotonic() - began,
                   budget_before=before, budget_after=self.budget.snapshot(), evidence_recorded=True)
        for key in ('source_sha256', 'transformed_sha256', 'executed_source_sha256',
                    'static_eligible', 'static_reason', 'execution_transform_report',
                    'projection_failed', 'control_requests', 'control_request_bytes', 'control_reply_bytes'):
            row[key] = deepcopy(evidence[key])
        row['evidence_sha256'] = hashlib.sha256((folder / 'projection_program_private.json').read_bytes()).hexdigest()
        forwarding = folder / 'projection_schema_forwarding_private.json'
        row['schema_evidence_recorded'] = forwarding.is_file()
        if forwarding.is_file():
            schema = json.loads(forwarding.read_text())
            row.update(schema_deliveries=schema['schema_deliveries'],
                       schema_reply_wire_bytes=schema['reply_wire_bytes'],
                       schema_evidence_sha256=hashlib.sha256(forwarding.read_bytes()).hexdigest())
        return result

    def summary(self):
        result = super().summary()
        del result['explicit_read_view_interface_exposed']
        execution_reports_complete = all(len(r.get('execution_transform_report', [])) == 1
                                         for r in self.program_rows)
        result['execution_trace_accounting_complete'] = execution_reports_complete
        result['control_accounting_complete'] &= execution_reports_complete
        field_events = self.host.field_events if self.host else []
        result.update(explicit_field_interface_shared_between_policies=True,
            explicit_field_interface_exposed=True, explicit_read_view_handle_interface_exposed=False,
            joined_provider_shared_between_policies=True,
            explicit_field_requests=sum(e['origin'] == 'explicit_fields' for e in field_events),
            explicit_field_partial_hits=sum(e['origin'] == 'explicit_fields' and e['kind'] == 'partial' for e in field_events),
            automatic_region_partial_hits=sum(e['origin'] == 'automatic_region' and e['kind'] == 'partial' for e in field_events),
            explicit_field_input_rejections=sum(e['op'] == 'explicit_fields_rejected' for e in self.host.control_events) if self.host else 0,
            demand_adapter=self.host.demand_adapter.summary() if self.host else None,
            transformed_artifact_is_review_only=True)
        return result
