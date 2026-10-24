"""Opt-in isolated-interpreter adapter for the explicit deferred-view protocol.

Existing experiments retain their original bootstrap. This derived runtime adds
the same read_view interface under eager and deferred policies. It does not
execute generated code in the host, certify API contracts, or run an experiment.
"""
import copy
import inspect
import json
from pathlib import Path
import selectors
import subprocess
import time

from container_data_python import inspect_controls, _limit_cli_output
from deferred_view_protocol import DeferredReadHost, RemoteReadViews
from explicit_deferred_read_views import ClosedReadView, ReadView
from persistent_api_python import BOOTSTRAP as ORIGINAL_BOOTSTRAP, PersistentApiPython
from shared_api_reservations import BudgetedApiChannel


def client_source():
    return ('from collections.abc import Mapping\nfrom copy import deepcopy\nimport weakref\n'
            + inspect.getsource(ClosedReadView) + '\n' + inspect.getsource(ReadView)
            + '\n' + inspect.getsource(RemoteReadViews)
            + '\n_harness_view_wire = call_api\n'
            'def _harness_view_exchange(packet):\n'
            "    return _harness_view_wire('__harness_views__', 'control', packet=packet)\n"
            '_harness_read_views_v1 = RemoteReadViews(_harness_view_exchange)\n')


def derived_bootstrap():
    anchor = '    capture = io.StringIO()\n'
    finish = '    content=capture.getvalue()\n'
    if ORIGINAL_BOOTSTRAP.count(anchor) != 1 or ORIGINAL_BOOTSTRAP.count(finish) != 1:
        raise ValueError('persistent_bootstrap_boundary_changed')
    result = ORIGINAL_BOOTSTRAP.replace(anchor,
        "    if '_harness_read_views_v1' in scope:\n"
        "        scope['call_api'] = scope['_harness_read_views_v1'].call\n"
        "        scope['read_view'] = scope['_harness_read_views_v1'].read\n" + anchor)
    result = result.replace(finish,
        "    if '_harness_read_views_v1' in scope:\n"
        '        try:\n'
        "            scope['_harness_read_views_v1'].flush_releases()\n"
        '        except BaseException as exc:\n'
        "            release_error = type(exc).__name__+': '+str(exc)\n"
        "            failure = (failure+'; release flush: ' if failure else '')+release_error\n"
        + finish)
    compile(result, '<trusted read-view bootstrap>', 'exec')
    return result


class PersistentReadViewPython(PersistentApiPython):
    """Same pinned container and limits; only this subclass uses the new bootstrap."""
    def _start(self):
        self.creation_attempted = True
        create = subprocess.run(self.cmd+['create','--name',self.name,
            '--label','harness.export-purpose=bounded-python-comparator',
            '--platform',self.selection['platform'],'--network','none','--read-only','--cap-drop','ALL',
            '--security-opt','no-new-privileges=true','--user','65534:65534','--memory','256m',
            '--memory-swap','256m','--cpus','1','--pids-limit','64','--log-driver','none',
            '--env','PYTHONDONTWRITEBYTECODE=1','-i',self.selection['image'],
            'python','-I','-S','-c',derived_bootstrap()], capture_output=True, timeout=30)
        (self.folder/'create_stderr_private.txt').write_bytes(create.stderr)
        if create.returncode:
            raise RuntimeError('container creation failed')
        info = json.loads(subprocess.check_output(self.cmd+['inspect',self.name],timeout=15))[0]
        self.controls = inspect_controls(info,self.selection)
        self.stderr = (self.folder/'stderr_private.txt').open('wb')
        self.process = subprocess.Popen(self.cmd+['start','-a','-i',self.name],stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,stderr=self.stderr,preexec_fn=_limit_cli_output)
        self.selector = selectors.DefaultSelector()
        self.selector.register(self.process.stdout,selectors.EVENT_READ)
        self.created_monotonic = time.monotonic()
        self.state.update(status='active',controls=self.controls,
                          explicit_read_view_protocol=True)
        self._save()


class ViewControlChannel:
    """Separate control-wire IDs from the underlying typed API invocation IDs."""
    def __init__(self, host, on_record=lambda row: None):
        self.host = host
        self.rows = []
        self.last_id = 0
        self.control_requests = 0
        self.control_request_bytes = 0
        self.control_reply_bytes = 0
        def record(row):
            self.rows.append(copy.deepcopy(row))
            on_record(row)
        host.on_record = record

    @property
    def catalog(self): return self.host.channel.catalog
    @property
    def fatal(self): return self.host.channel.fatal
    @property
    def complete(self): return self.host.channel.complete

    def exchange(self, packet):
        if (type(packet) is not dict or set(packet) != {'kind','id','app','api','arguments'}
                or packet['kind'] != 'api' or type(packet['id']) is not int
                or packet['id'] != self.last_id+1 or packet['app'] != '__harness_views__'
                or packet['api'] != 'control' or type(packet['arguments']) is not dict
                or set(packet['arguments']) != {'packet'}):
            raise ValueError('all_view_runtime_calls_must_use_host_control')
        self.last_id = packet['id']
        control = packet['arguments']['packet']
        self.control_requests += 1
        self.control_request_bytes += len(json.dumps(control,allow_nan=False).encode())
        response = self.host.request(control)
        self.control_reply_bytes += len(json.dumps(response,allow_nan=False).encode())
        # The persistent worker calls on_record for this final control row.
        # The adapter keeps it private; actual API rows were recorded above.
        self.rows.append({'action': {'name':'read_view_control','arguments':'{}'},
            'api_request_sent':False,'new_tools':[],
            'observation':{'control_id':control['id'],'op':control['op'],'ok':response['ok']}})
        return {'id':self.last_id,'ok':True,'value':response,'new_schemas':{}}


class ReadViewProgram:
    """Adapter for a future bounded cell; setup/control/cleanup are counted.

    Call with the original ApiChannel and a PersistentReadViewPython session.
    Do not put the older PublicResultProgram outside it: typed receipts are
    already handled by BudgetedApiChannel. The same interface applies to both
    policies. A real runner and verified authority provider are still required.
    """
    def __init__(self, session, budget, *, authority, defer=True):
        if not isinstance(session, PersistentReadViewPython):
            raise ValueError('isolated_read_view_session_required')
        self.session, self.budget = session, budget
        self.authority, self.defer = authority, defer
        self.host = None
        self.setup_attempted = False
        self.setup_complete = False

    def __call__(self, source, observations, channel, *, storage_root, record_dir,
                 timeout=90, on_record=lambda row:None):
        started = time.monotonic()
        before = self.budget.snapshot()
        wrapped = BudgetedApiChannel(channel, self.budget)
        if self.host is None:
            self.host = DeferredReadHost(wrapped,authority=self.authority,defer=self.defer)
        else:
            self.host.attach(wrapped)
        control = ViewControlChannel(self.host,on_record)
        setup = None
        if not self.setup_complete:
            if self.setup_attempted:
                raise RuntimeError('failed_view_setup_is_not_retried')
            self.setup_attempted = True
            setup = self.session.run(client_source(),[],control,storage_root=storage_root,
                record_dir=Path(record_dir).with_name(Path(record_dir).name+'_view_setup'),
                timeout=timeout,on_record=lambda row:None)
            self.setup_complete = setup['status']=='ok' and control.control_requests==0
            if not self.setup_complete:
                self.session.usable = False
                self.session.close()
                raise RuntimeError('view_client_setup_failed')
        remaining = timeout - (time.monotonic()-started)
        if remaining <= 0:
            self.session.usable = False
            self.session.close()
            raise TimeoutError('view_setup_consumed_program_deadline')
        result = self.session.run(source,observations,control,storage_root=storage_root,
            record_dir=record_dir,timeout=min(90,remaining),on_record=lambda row:None)
        if self.budget.stopped and not control.complete and self.session.usable:
            self.session.usable = False
            self.session.close()
            result.update(status='harness_error',error_type='read_view_budget_or_contract_stopped',
                          session_usable=False,container_removed=self.session.state['container_removed'])
        result.update(api_requests=self.budget.spent-before['spent'],
                      wall_seconds=time.monotonic()-started)
        evidence = dict(budget_before=before,budget_after=self.budget.snapshot(),
            control_requests=control.control_requests,control_request_bytes=control.control_request_bytes,
            control_reply_bytes=control.control_reply_bytes,setup=setup,result=result,
            original_generated_source_unchanged=True)
        (Path(record_dir)/'view_program_private.json').write_text(json.dumps(evidence,indent=2)+'\n')
        return result
