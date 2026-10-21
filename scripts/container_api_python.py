"""Ordinary Python with mediated public-API RPC in a mount/network-free container.

Generated code never executes in the host bridge. All API requests go through
the caller's allowlist, budget and completion controls. This is a CodeAct-like
comparator capability, not a novel algorithm or a correctness verifier.
"""
import json
from pathlib import Path
import selectors
import subprocess
import time
import uuid

from container_data_python import (docker_command, inspect_controls,
    _limit_cli_output, ROOT)

BOOTSTRAP = r'''
import contextlib, io, json, sys, traceback
packet = json.loads(sys.stdin.readline())
wire_out, wire_in = sys.stdout, sys.stdin
counter = 0
api_schemas = packet["api_schemas"]
def call_api(app, api, **kwargs):
    global counter
    counter += 1
    wire_out.write(json.dumps({'kind':'api', 'id':counter,
        'app':app, 'api':api, 'arguments':kwargs}, allow_nan=False)+'\n')
    wire_out.flush()
    reply = json.loads(wire_in.readline())
    if reply.get('id') != counter:
        raise RuntimeError('RPC response identity mismatch')
    if not reply.get('ok'):
        raise RuntimeError(reply.get('error', 'API call rejected'))
    api_schemas.update(reply.get('new_schemas', {}))
    return reply['value']
scope = {'__name__':'__main__', 'call_api':call_api,
         'observations':packet['observations'], 'api_schemas':api_schemas}
capture = io.StringIO()
failure = None
try:
    with contextlib.redirect_stdout(capture):
        exec(compile(packet['code'], '<generated>', 'exec'), scope, scope)
except BaseException as exc:
    failure = type(exc).__name__+': '+str(exc)
content = capture.getvalue()
truncated = len(content)>65536
wire_out.write(json.dumps({'kind':'done', 'python':sys.version.split()[0],
    'stdout':content[:65536], 'stdout_truncated':truncated,
    'error':failure}, allow_nan=False)+'\n')
wire_out.flush()
'''


class ApiChannel:
    """Validate untrusted RPC and stop on ambiguous effects, budget or completion."""
    def __init__(self, catalog, bridge, remaining, may_continue=lambda: True):
        self.catalog, self.bridge = catalog, bridge
        self.remaining, self.may_continue = remaining, may_continue
        self.rows, self.last_id = [], 0
        self.complete, self.fatal = False, False

    def exchange(self, packet):
        if (type(packet) is not dict or set(packet) != {'kind','id','app','api','arguments'}
                or packet['kind'] != 'api' or type(packet['id']) is not int
                or packet['id'] != self.last_id+1 or type(packet['arguments']) is not dict
                or any(type(packet[k]) is not str for k in ('app','api'))):
            raise ValueError('invalid API RPC request')
        self.last_id = packet['id']
        reply = {'id':self.last_id, 'ok':False}
        fn = {'name':packet['app']+'__'+packet['api'],
              'arguments':json.dumps(packet['arguments'], allow_nan=False)}
        row = {'action':fn, 'api_request_sent':False, 'new_tools':[]}
        if self.complete or self.fatal or self.remaining <= 0 or not self.may_continue():
            row['observation'] = {'not_executed':'completion, unknown effects or run budget'}
            reply['error'] = row['observation']['not_executed']
        else:
            try:
                action = self.catalog.decode(fn)
                if set(action) != {'app','api','args'}:
                    raise ValueError('only discovered public APIs in Python')
            except (ValueError, TypeError, KeyError) as exc:
                row['observation'] = {'format_error':str(exc)}
                reply['error'] = str(exc)
            else:
                self.remaining -= 1
                row['api_request_sent'] = True
                try:
                    result = self.bridge.request({'op':'call','call':action})
                    if result['ok']:
                        row['observation'] = result['result']
                        row['new_tools'] = self.catalog.expose_requested_document(action)
                        self.complete |= bool(result['result'].get('declared_complete'))
                        raw = result['result'].get('observation')
                        # Exact JSON when available; preserve non-JSON API responses
                        # as text instead of silently treating them as empty data.
                        try:
                            value = json.loads(raw) if isinstance(raw, str) else raw
                        except ValueError:
                            value = raw
                        reply.update(ok=True, value=value, new_schemas={
                            name:self.catalog.catalog[name]["function"] for name in row["new_tools"]})
                    else:
                        row['observation'] = {'api_error':result['error']}
                        reply['error'] = result['error']
                except Exception as exc:
                    self.fatal = True
                    row.update(observation={'transport_error_type':type(exc).__name__}, effects_unknown=True)
                    reply['error'] = 'API outcome unknown; no further dispatch'
        self.rows.append(row)
        return reply


def run_program(source, observations, channel, *, storage_root, record_dir, timeout=90,
                on_record=lambda row: None):
    if type(source) is not str or not 0<len(source)<=20000 or not 0<timeout<=90:
        raise ValueError('code or execution time limit')
    payload = json.dumps({'code':source,'observations':observations,
        'api_schemas':{n:channel.catalog.catalog[n]['function'] for n in sorted(channel.catalog.visible)}},
        allow_nan=False).encode()+b'\n'
    if len(payload)>4*1024*1024:
        raise ValueError('public input exceeds 4 MiB')
    selection = json.loads((ROOT/'configs/python_export_image_v01.json').read_text())
    cmd = docker_command(Path(storage_root))
    folder = Path(record_dir); folder.mkdir(parents=True, exist_ok=False)
    (folder/'input_private.json').write_bytes(payload)
    name = 'harness-api-python-'+uuid.uuid4().hex
    result = {'status':'not_started','image':selection['image'],'container_removed':False,
              'api_requests':0,'stdout':'','stdout_truncated':False}
    process, creation_attempted, created = None, False, False
    started = time.monotonic()
    try:
        creation_attempted = True
        create = subprocess.run(cmd+['create','--name',name,'--label','harness.export-purpose=bounded-python-comparator',
            '--platform',selection['platform'],'--network','none','--read-only','--cap-drop','ALL',
            '--security-opt','no-new-privileges=true','--user','65534:65534','--memory','256m',
            '--memory-swap','256m','--cpus','1','--pids-limit','64','--log-driver','none',
            '--env','PYTHONDONTWRITEBYTECODE=1','-i',selection['image'],
            'python','-I','-S','-c',BOOTSTRAP],capture_output=True,timeout=30)
        (folder/'create_stderr_private.txt').write_bytes(create.stderr)
        if create.returncode: raise RuntimeError('container creation failed')
        created = True
        info = json.loads(subprocess.check_output(cmd+['inspect',name],timeout=15))[0]
        result['controls'] = inspect_controls(info,selection)
        (folder/'controls.json').write_text(json.dumps(result['controls'],indent=2)+'\n')
        with (folder/'stderr_private.txt').open('wb') as err:
            process = subprocess.Popen(cmd+['start','-a','-i',name],stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,stderr=err,preexec_fn=_limit_cli_output)
            process.stdin.write(payload);process.stdin.flush()
            selector=selectors.DefaultSelector();selector.register(process.stdout,selectors.EVENT_READ)
            buf=b''; total=0; done=False
            with (folder/'wire_private.jsonl').open('wb') as wire:
                while not done:
                    if time.monotonic()-started>timeout:
                        result['status']='timeout';break
                    ready=selector.select(min(1,max(.01,timeout-(time.monotonic()-started))))
                    if not ready:
                        if process.poll() is not None: break
                        continue
                    chunk=process.stdout.read1(65536)
                    if not chunk: break
                    buf+=chunk;total+=len(chunk)
                    if total>8*1024*1024 or len(buf)>2*1024*1024:
                        raise ValueError('RPC output limit')
                    while b'\n' in buf:
                        line,buf=buf.split(b'\n',1);wire.write(line+b'\n');wire.flush()
                        packet=json.loads(line)
                        if packet.get('kind')=='api':
                            reply=channel.exchange(packet)
                            on_record(channel.rows[-1])
                            process.stdin.write(json.dumps(reply,allow_nan=False).encode()+b'\n');process.stdin.flush()
                        elif packet.get('kind')=='done':
                            if (set(packet)!={'kind','python','stdout','stdout_truncated','error'}
                                    or packet['python']!=selection['expected_python']
                                    or type(packet['stdout']) is not str or len(packet['stdout'])>65536
                                    or type(packet['stdout_truncated']) is not bool
                                    or packet['error'] is not None and type(packet['error']) is not str):
                                raise ValueError('invalid completion protocol')
                            result.update(status='execution_error' if packet['error'] else 'ok',
                                stdout=packet['stdout'],stdout_truncated=packet['stdout_truncated'],error=packet['error'])
                            done=True;break
                        else: raise ValueError('unknown RPC message')
                selector.close()
            if not done and result['status']=='not_started':
                result['status']='execution_error'
        if process.poll() is None:
            process.stdin.close()
            try: process.wait(timeout=2)
            except subprocess.TimeoutExpired: process.kill();process.wait(timeout=5)
    except Exception as exc:
        result.update(status='harness_error',error_type=type(exc).__name__)
        (folder/'error_private.txt').write_text(str(exc))
    finally:
        if process and process.poll() is None: process.kill();process.wait(timeout=5)
        try:
            if creation_attempted:
                probe=subprocess.run(cmd+['inspect',name],capture_output=True,timeout=15)
                if probe.returncode==0:
                    info=json.loads(probe.stdout)[0]
                    if info['Config'].get('Labels',{}).get('harness.export-purpose')!='bounded-python-comparator':
                        raise RuntimeError('container ownership mismatch')
                    result['oom_killed']=info['State']['OOMKilled']
                    result['container_exit_code']=info['State']['ExitCode'] if not info['State']['Running'] else None
                    if result['status']=='ok' and (info['State']['OOMKilled'] or result['container_exit_code'] not in (0,None)):
                        result.update(status='execution_error', error='container ended abnormally')
                    removal=subprocess.run(cmd+['rm','-f',name],capture_output=True,timeout=30)
                    result['container_removed']=removal.returncode==0
                    if removal.returncode: raise RuntimeError('container cleanup failed')
                elif b'No such object' not in probe.stderr and b'No such container' not in probe.stderr:
                    raise RuntimeError('cannot verify container absence')
        except Exception as exc:
            result.update(status='harness_error',cleanup_error_type=type(exc).__name__)
        result.update(api_requests=sum(int(r['api_request_sent']) for r in channel.rows),
            declared_complete=channel.complete,unknown_effects=channel.fatal,wall_seconds=time.monotonic()-started)
        (folder/'result_private.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    return result
