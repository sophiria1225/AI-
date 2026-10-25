"""Isolated runtime for bounded automatic field projection and its eager control.

Both policies share the existing ordinary complete-response cache. The model's
program stays in the private archive; a separately hashed execution projection
is conditional on the narrow compiler and the pinned public read contract.
This module does not start a model or a research experiment.
"""
from copy import deepcopy
import hashlib
import inspect
import json
from pathlib import Path
import selectors
import subprocess
import time

import automatic_field_projection as compiler
from agent_read_view_runtime import AgentReadViewPython, SchemaForwardingViewChannel
from container_data_python import inspect_controls, _limit_cli_output
from field_read_contract import CONTRACT_ID, FIELDS, canonical
from ordinary_complete_read_cache import OrdinaryCachedReadHost
from persistent_api_python import BOOTSTRAP, PersistentApiPython
from persistent_read_view_python import ViewControlChannel
from shared_api_reservations import BudgetedApiChannel

POLICIES = ('eager_cached', 'automatic_projection_cached')


class ProjectionApiChannel(BudgetedApiChannel):
    """Retain the exact ordinary reply, including known rejection text."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.reply_sequence = 0
        self.ordinary_reply = None

    def _exchange(self, packet, token):
        reply = super()._exchange(packet, token)
        self.reply_sequence += 1
        self.ordinary_reply = deepcopy(reply)
        return reply


class ProjectionWireFault(RuntimeError):
    pass


class ProjectionWireClient:
    """Trusted interpreter-global client; no ledger or provider enters user scope."""
    def __init__(self, wire):
        self.wire = wire
        self.counter = 0
        self.closed = False

    def rpc(self, op, args):
        if self.closed and op not in ('projection_report', 'projection_stop'):
            raise RuntimeError('projection_wire_closed')
        self.counter += 1
        try:
            reply = self.wire('__harness_views__', 'control', packet={
                'id': self.counter, 'op': op, 'args': args, 'releases': []})
            if (type(reply) is not dict or reply.get('id') != self.counter
                    or type(reply.get('ok')) is not bool or type(reply.get('fatal')) is not bool
                    or reply['ok'] and 'value' not in reply
                    or not reply['ok'] and type(reply.get('error')) is not str):
                raise ValueError('invalid_projection_reply')
        except BaseException as error:
            self.closed = True
            raise ProjectionWireFault('projection_control_protocol_failed') from error
        self.closed |= reply['fatal']
        if not reply['ok']:
            raise RuntimeError(reply.get('error', 'projection_control_failed'))
        return reply['value']

    def call(self, app, api, **args):
        return self.rpc('call', dict(app=app, api=api, args=args))

    def lookup(self, app, api, args, fields):
        return self.rpc('projection_lookup', dict(app=app, api=api,
                                                 args=args, fields=list(fields)))

    def stop(self, reason):
        self.rpc('projection_stop', {'reason': reason})

    def report(self, value):
        return self.rpc('projection_report', value)


class AutomaticProjectionHost(OrdinaryCachedReadHost):
    def __init__(self, *args, policy, **kwargs):
        if policy not in POLICIES:
            raise ValueError('explicit_projection_policy_required')
        self.policy = policy
        self.projection_failed = False
        self.projection_events = []
        self.program_reports = []
        self.expected_plan = None
        self.program_event_start = 0
        self.program_report_start = 0
        super().__init__(*args, defer=False, **kwargs)

    def expect(self, plan):
        self.expected_plan = plan
        self.program_event_start = len(self.projection_events)
        self.program_report_start = len(self.program_reports)

    def _ordinary_catalog_valid(self, action):
        try:
            decoded = self.channel.catalog.decode({
                'name': action['app'] + '__' + action['api'],
                'arguments': json.dumps(action['args'], allow_nan=False)})
            return set(decoded) == {'app', 'api', 'args'}
        except (ValueError, TypeError, KeyError):
            return False

    def _ordinary_complete(self, action):
        if not self._ordinary_catalog_valid(action):
            return None
        return super()._ordinary_complete(action)

    def _barrier(self):
        if not self._ordinary_catalog_valid(self.active_action):
            # The ordinary channel records its own pre-dispatch rejection.
            # Such an operation cannot mutate the provider's snapshot.
            return
        return super()._barrier()

    def request(self, packet):
        op = packet.get('op') if type(packet) is dict else None
        if op not in ('projection_lookup', 'projection_stop', 'projection_report'):
            if op != 'call':
                raise ValueError('only_ordinary_calls_and_projection_controls_exposed')
            sequence = getattr(self.channel, 'reply_sequence', None)
            reply = super().request(packet)
            if (sequence is not None and self.channel.reply_sequence == sequence + 1
                    and not reply['ok'] and not self.channel.ordinary_reply['ok']
                    and reply['error'] == 'RuntimeError: ' + self.channel.ordinary_reply['error']):
                # Undo only the adapter's own exception layer, using the exact
                # newly returned channel reply; never normalize saved errors.
                reply['error'] = self.channel.ordinary_reply['error']
            return reply
        if (set(packet) != {'id', 'op', 'args', 'releases'}
                or type(packet['id']) is not int or packet['id'] != self.last_id + 1
                or packet['releases'] != [] or type(packet['args']) is not dict
                or self.expected_plan is None):
            raise ValueError('invalid_projection_control')
        self.last_id = packet['id']
        self.control_events.append({'id': self.last_id, 'op': op, 'released': 0})
        reply = {'id': self.last_id, 'ok': False}
        try:
            args = packet['args']
            if op == 'projection_stop':
                if args != {'reason': 'automatic_projection_execution_failed'}:
                    raise ValueError('bounded_projection_failure_reason_required')
                self.projection_failed = self.channel.budget.stopped = True
                self.projection_events.append({'kind': 'failed', 'program_source_sha256':
                                               self.expected_plan.source_sha256})
                value = None
            elif op == 'projection_report':
                value = self._report(args)
            else:
                value = self._lookup(args)
            reply.update(ok=True, value=value)
        except Exception as error:
            # Malformed control, a failed capability check, or an invalid value
            # is not a cache miss. No API effects are invented by this flag.
            self.projection_failed = self.channel.budget.stopped = True
            reply['error'] = type(error).__name__ + ': ' + str(error)
        reply['fatal'] = self.channel.budget.stopped
        return reply

    def _lookup(self, args):
        self.channel.budget._ready()
        if (self.policy != 'automatic_projection_cached' or not self.expected_plan.eligible
                or set(args) != {'app', 'api', 'args', 'fields'}
                or type(args['app']) is not str or type(args['api']) is not str
                or type(args['args']) is not dict or type(args['fields']) is not list
                or not args['fields'] or any(type(f) is not str for f in args['fields'])
                or len(args['fields']) != len(set(args['fields']))
                or not set(args['fields']).issubset(FIELDS)):
            raise ValueError('admitted_projection_and_supported_fields_required')
        action = {key: deepcopy(args[key]) for key in ('app', 'api', 'args')}
        decoded = self.channel.catalog.decode({'name': action['app']+'__'+action['api'],
            'arguments': json.dumps(action['args'], allow_nan=False)})
        if set(decoded) != {'app', 'api', 'args'}:
            raise ValueError('ordinary_public_API_required')
        found = self.provider.lookup(action, self.epoch)
        kind = 'miss' if found is None else found[0]
        result = None
        if kind == 'partial':
            grant = self.provider.grant(action, self.epoch)
            if (grant is None or grant.epoch != self.epoch
                    or not grant.assumptions.permit_deferral()
                    or type(grant.partial) is not dict
                    or not set(args['fields']).issubset(grant.partial)):
                raise ValueError('pinned_prefix_read_authority_required')
            result = {field: deepcopy(grant.partial[field]) for field in args['fields']}
        elif kind not in ('miss', 'complete'):
            raise ValueError('unknown_prefix_read_authority')
        self.projection_events.append({'kind': kind, 'epoch': self.epoch,
            'action_sha256': hashlib.sha256(canonical(action).encode()).hexdigest(),
            'fields': sorted(args['fields']), 'environment_API_requests': 0,
            'full_cache_updated': False})
        # Complete responses use the same ordinary-call/cache path as control.
        return result

    def _report(self, value):
        expected = {'source_sha256', 'transformed_sha256', 'transformed',
                    'hits', 'misses', 'failed', 'reason'}
        candidate_matches = value.get('transformed_sha256') == self.expected_plan.transformed_sha256
        original_after_builtin_change = (
            value.get('reason') in ('builtin_module_changed', 'ordinary_eager_control')
            and value.get('transformed') is False
            and value.get('transformed_sha256') == self.expected_plan.source_sha256)
        if (set(value) != expected or value['source_sha256'] != self.expected_plan.source_sha256
                or not (candidate_matches or original_after_builtin_change)
                or type(value['transformed']) is not bool or type(value['failed']) is not bool
                or any(type(value[k]) is not int or value[k] < 0 for k in ('hits', 'misses'))
                or value['reason'] not in ('ordinary_eager_control',
                    'namespace_guard_or_static_fallback', 'bounded_normal_path_projection',
                    'builtin_module_changed', 'non_string_namespace_key')
                or self.policy == 'eager_cached' and (value['transformed'] or value['hits'])
                or value['transformed'] and not self.expected_plan.eligible):
            raise ValueError('invalid_projection_program_report')
        events = self.projection_events[self.program_event_start:]
        if (len(self.program_reports) != self.program_report_start
                or value['hits'] != sum(e['kind'] == 'partial' for e in events)
                or value['misses'] != sum(e['kind'] in ('miss', 'complete') for e in events)
                or value['failed'] or self.projection_failed
                or not value['transformed'] and events):
            raise ValueError('projection_report_disagrees_with_host_events')
        self.program_reports.append(deepcopy(value))
        return None


def derived_bootstrap(policy):
    if policy not in POLICIES:
        raise ValueError('explicit_projection_policy_required')
    engine = Path(compiler.__file__).read_text()
    install = ('import types\n'
        '_projection_engine = types.ModuleType("trusted_projection_engine_v1")\n'
        'sys.modules[_projection_engine.__name__] = _projection_engine\n'
        f'exec(compile({engine!r}, "<trusted projection engine>", "exec"), _projection_engine.__dict__)\n'
        + inspect.getsource(ProjectionWireFault) + '\n'
        + inspect.getsource(ProjectionWireClient) + '\n'
        '_projection_client = ProjectionWireClient(call_api)\n'
        '_projection_call = _projection_client.call\n')
    anchor = "scope = {'__name__':'__main__'}\n"
    refresh = '    scope.update(call_api=call_api, observations=packet[\'observations\'], api_schemas=api_schemas)\n'
    execute = "            exec(compile(packet['code'],'<generated>','exec'),scope,scope)\n"
    if any(BOOTSTRAP.count(s) != 1 for s in (anchor, refresh, execute)):
        raise ValueError('persistent_bootstrap_boundary_changed')
    result = BOOTSTRAP.replace(anchor, install + anchor).replace(refresh,
        "    scope.update(call_api=_projection_call, observations=packet['observations'], api_schemas=api_schemas)\n")
    body = ("            _projection_plan = _projection_engine.plan_projection(packet['code'])\n"
        "            _projection_runtime = _projection_engine.ProjectionRuntime(_projection_call, _projection_client.lookup, _projection_client.stop)\n")
    if policy == 'automatic_projection_cached':
        body += '            _projection_result = _projection_engine.execute_projection(_projection_plan, scope, _projection_runtime)\n'
    else:
        body += (execute + "            _projection_result = {'transformed': False, 'reason': 'ordinary_eager_control', 'hits': 0}\n")
    body += ("            _projection_client.report(dict(source_sha256=_projection_plan.source_sha256,\n"
        "                transformed_sha256=_projection_plan.transformed_sha256,\n"
        "                transformed=_projection_result['transformed'], reason=_projection_result['reason'],\n"
        "                hits=_projection_runtime.hits, misses=_projection_runtime.misses, failed=_projection_runtime.failed))\n")
    result = result.replace(execute, body)
    compile(result, '<trusted automatic projection bootstrap>', 'exec')
    return result


class AutomaticProjectionPython(AgentReadViewPython):
    def __init__(self, storage_root, session_dir, *, policy):
        if policy not in POLICIES:
            raise ValueError('explicit_projection_policy_required')
        self.policy = policy
        super().__init__(storage_root, session_dir)

    def _bootstrap(self):
        return derived_bootstrap(self.policy)

    def run(self, source, observations, channel, **kwargs):
        wrapped = SchemaForwardingViewChannel(channel)
        try:
            return PersistentApiPython.run(self, source, observations, wrapped, **kwargs)
        finally:
            folder = Path(kwargs['record_dir'])
            if folder.exists():
                evidence = dict(exchanges=wrapped.exchanges,
                    schema_deliveries=sum(len(e['new_schema_names']) for e in wrapped.exchanges),
                    reply_wire_bytes=sum(e['reply_wire_bytes'] for e in wrapped.exchanges),
                    extra_API_requests=0, submitted_source_sha256=hashlib.sha256(source.encode()).hexdigest(),
                    execution_transform_record='projection_program_private.json')
                with (folder/'projection_schema_forwarding_private.json').open('x') as stream:
                    json.dump(evidence, stream, indent=2, allow_nan=False)
                    stream.write('\n')

    def _start(self):
        # Same pinned container controls as PersistentReadViewPython; only the
        # trusted interpreter bootstrap is replaced for this new experiment.
        self.creation_attempted = True
        bootstrap = self._bootstrap()
        create = subprocess.run(self.cmd+['create','--name',self.name,
            '--label','harness.export-purpose=bounded-python-comparator',
            '--platform',self.selection['platform'],'--network','none','--read-only','--cap-drop','ALL',
            '--security-opt','no-new-privileges=true','--user','65534:65534','--memory','256m',
            '--memory-swap','256m','--cpus','1','--pids-limit','64','--log-driver','none',
            '--env','PYTHONDONTWRITEBYTECODE=1','-i',self.selection['image'],
            'python','-I','-S','-c',bootstrap], capture_output=True, timeout=30)
        (self.folder/'create_stderr_private.txt').write_bytes(create.stderr)
        if create.returncode:
            raise RuntimeError('container_creation_failed')
        info = json.loads(subprocess.check_output(self.cmd+['inspect',self.name],timeout=15))[0]
        self.controls = inspect_controls(info,self.selection)
        self.stderr = (self.folder/'stderr_private.txt').open('wb')
        self.process = subprocess.Popen(self.cmd+['start','-a','-i',self.name], stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,stderr=self.stderr,preexec_fn=_limit_cli_output)
        self.selector = selectors.DefaultSelector()
        self.selector.register(self.process.stdout,selectors.EVENT_READ)
        self.created_monotonic = time.monotonic()
        self.state.update(status='active',controls=self.controls, projection_policy=self.policy,
            trusted_bootstrap_sha256=hashlib.sha256(bootstrap.encode()).hexdigest())
        self._save()


class AutomaticProjectionProgram:
    host_class = AutomaticProjectionHost

    def __init__(self, session, budget, *, execution_scope, verified_contract, policy):
        if (not isinstance(session, AutomaticProjectionPython) or session.policy != policy
                or policy not in POLICIES or verified_contract != CONTRACT_ID):
            raise ValueError('matched_isolated_projection_session_required')
        self.session, self.budget, self.policy = session, budget, policy
        self.execution_scope, self.verified_contract = execution_scope, verified_contract
        self.host = None

    def __call__(self, source, observations, channel, *, storage_root, record_dir,
                 timeout=90, on_record=lambda row: None):
        began = time.monotonic()
        plan = compiler.plan_projection(source)
        before = self.budget.snapshot()
        wrapped = ProjectionApiChannel(channel, self.budget)
        if self.host is None:
            self.host = self.host_class(wrapped, policy=self.policy,
                execution_scope=self.execution_scope, verified_contract=self.verified_contract)
        else:
            self.host.attach(wrapped)
        self.host.expect(plan)
        controls_before = len(self.host.projection_events)
        reports_before = len(self.host.program_reports)
        control = ViewControlChannel(self.host, on_record)
        result = self.session.run(source, observations, control, storage_root=storage_root,
            record_dir=record_dir, timeout=timeout, on_record=lambda row: None)
        if str(result.get('error', '')).startswith('ProjectionWireFault:'):
            self.host.projection_failed = self.budget.stopped = True
        if self.host.projection_failed:
            self.session.usable = False
            self.session.close()
            result.update(status='harness_error',error_type='automatic_projection_contract_stopped',
                session_usable=False,container_removed=self.session.state['container_removed'])
        # Ordinary interpreter failures may still be recoverable, as in control.
        # A transformed failure must already have sent projection_stop. Missing
        # report on success is a protocol failure, never silently eager success.
        reports = self.host.program_reports[reports_before:]
        if result['status'] == 'ok' and len(reports) != 1:
            self.budget.stopped = self.host.projection_failed = True
            self.session.usable = False
            self.session.close()
            result.update(status='harness_error',error_type='projection_report_missing',
                session_usable=False,container_removed=self.session.state['container_removed'])
        result.update(api_requests=self.budget.spent-before['spent'],
                      wall_seconds=time.monotonic()-began)
        evidence = dict(policy=self.policy, source_sha256=plan.source_sha256,
            transformed_sha256=plan.transformed_sha256, static_eligible=plan.eligible,
            executed_source_sha256=(plan.transformed_sha256 if reports[0]['transformed']
                else plan.source_sha256) if len(reports) == 1 else None,
            static_reason=plan.reason, sites=plan.sites, budget_before=before,
            budget_after=self.budget.snapshot(), original_generated_source_unchanged=(
                not reports[0]['transformed'] if len(reports) == 1 else None), execution_transform_report=reports,
            projection_failed=self.host.projection_failed,
            projection_events=self.host.projection_events[controls_before:],
            control_requests=control.control_requests, control_request_bytes=control.control_request_bytes,
            control_reply_bytes=control.control_reply_bytes, result=result)
        folder = Path(record_dir)
        (folder/'projection_candidate_source_private.py').write_text(plan.transformed_source)
        (folder/'projection_program_private.json').write_text(json.dumps(evidence,indent=2)+'\n')
        # Preserve the session's raw result separately from this adapter result.
        (folder/'projection_result_private.json').write_text(json.dumps(result,indent=2)+'\n')
        return result
