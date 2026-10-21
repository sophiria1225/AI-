"""Ordinary task-local Python namespace with the same mediated public APIs.

The container lives for one task. Public task state is still owned by the bridge;
interpreter memory is not a checkpoint/restore mechanism or a new algorithm.
"""
import json
from pathlib import Path
import selectors
import subprocess
import time
import uuid

from container_data_python import docker_command, inspect_controls, _limit_cli_output, ROOT

BOOTSTRAP = r'''
import contextlib, io, json, sys
wire_out, wire_in = sys.stdout, sys.stdin
counter = 0
program_index = 0
api_schemas = {}
def call_api(app, api, **kwargs):
    global counter
    counter += 1
    wire_out.write(json.dumps({'kind':'api', 'id':counter, 'program_index':program_index,
        'app':app, 'api':api, 'arguments':kwargs}, allow_nan=False)+'\n')
    wire_out.flush()
    reply = json.loads(wire_in.readline())
    if reply.get('id') != counter:
        raise RuntimeError('RPC response identity mismatch')
    if not reply.get('ok'):
        raise RuntimeError(reply.get('error','API call rejected'))
    api_schemas.update(reply.get('new_schemas',{}))
    return reply['value']
scope = {'__name__':'__main__'}
for line in wire_in:
    packet = json.loads(line)
    counter = 0
    program_index = packet['program_index']
    api_schemas = packet['api_schemas']
    # Refresh only the supplied runtime names. User-created variables/functions
    # remain available in this task, including after a caught Python exception.
    scope.update(call_api=call_api, observations=packet['observations'], api_schemas=api_schemas)
    capture = io.StringIO()
    failure = None
    try:
        with contextlib.redirect_stdout(capture):
            exec(compile(packet['code'],'<generated>','exec'),scope,scope)
    except BaseException as exc:
        failure = type(exc).__name__+': '+str(exc)
    content=capture.getvalue()
    wire_out.write(json.dumps({'kind':'done','python':sys.version.split()[0],
        'program_index':packet['program_index'], 'stdout':content[:65536],
        'stdout_truncated':len(content)>65536, 'error':failure},allow_nan=False)+'\n')
    wire_out.flush()
'''


class PersistentApiPython:
    def __init__(self, storage_root, session_dir):
        self.storage_root=Path(storage_root)
        self.folder=Path(session_dir)
        self.folder.mkdir(parents=True,exist_ok=False)
        self.selection=json.loads((ROOT/'configs/python_export_image_v01.json').read_text())
        self.cmd=docker_command(self.storage_root)
        self.name='harness-api-session-'+uuid.uuid4().hex
        self.process=None;self.selector=None;self.stderr=None
        self.creation_attempted=False;self.closed=False;self.usable=True
        self.controls={};self.programs=[];self.created_monotonic=None
        self.state={'session_id':self.name,'namespace_scope':'one_task',
            'image':self.selection['image'],'status':'not_started','container_removed':False,
            'programs':self.programs,'process_memory_checkpointed':False}
        self._save()

    def _save(self):
        temporary=self.folder/'session_private.tmp'
        temporary.write_text(json.dumps(self.state,ensure_ascii=False,indent=2)+'\n')
        temporary.replace(self.folder/'session_private.json')

    def _start(self):
        self.creation_attempted=True
        create=subprocess.run(self.cmd+['create','--name',self.name,
            '--label','harness.export-purpose=bounded-python-comparator',
            '--platform',self.selection['platform'],'--network','none','--read-only','--cap-drop','ALL',
            '--security-opt','no-new-privileges=true','--user','65534:65534','--memory','256m',
            '--memory-swap','256m','--cpus','1','--pids-limit','64','--log-driver','none',
            '--env','PYTHONDONTWRITEBYTECODE=1','-i',self.selection['image'],
            'python','-I','-S','-c',BOOTSTRAP],capture_output=True,timeout=30)
        (self.folder/'create_stderr_private.txt').write_bytes(create.stderr)
        if create.returncode:raise RuntimeError('container creation failed')
        info=json.loads(subprocess.check_output(self.cmd+['inspect',self.name],timeout=15))[0]
        self.controls=inspect_controls(info,self.selection)
        self.stderr=(self.folder/'stderr_private.txt').open('wb')
        self.process=subprocess.Popen(self.cmd+['start','-a','-i',self.name],stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,stderr=self.stderr,preexec_fn=_limit_cli_output)
        self.selector=selectors.DefaultSelector();self.selector.register(self.process.stdout,selectors.EVENT_READ)
        self.created_monotonic=time.monotonic()
        self.state.update(status='active',controls=self.controls)
        self._save()

    def run(self,source,observations,channel,*,storage_root,record_dir,timeout=90,on_record=lambda row:None):
        if Path(storage_root)!=self.storage_root:raise ValueError('wrong session storage')
        if self.closed or not self.usable:raise RuntimeError('session cannot be resumed')
        if type(source) is not str or not 0<len(source)<=20000 or not 0<timeout<=90:
            raise ValueError('code or execution time limit')
        number=len(self.programs)+1
        payload=json.dumps({'code':source,'observations':observations,'program_index':number,
            'api_schemas':{n:channel.catalog.catalog[n]['function'] for n in sorted(channel.catalog.visible)}},
            allow_nan=False).encode()+b'\n'
        if len(payload)>4*1024*1024:raise ValueError('public input exceeds 4 MiB')
        folder=Path(record_dir);folder.mkdir(parents=True,exist_ok=False)
        (folder/'input_private.json').write_bytes(payload)
        result={'status':'not_started','image':self.selection['image'],'session_id':self.name,
            'program_index':number,'persistent_namespace':True,'container_removed':False,
            'api_requests':0,'stdout':'','stdout_truncated':False}
        started=time.monotonic();done=False
        try:
            if self.process is None:self._start()
            if self.process.poll() is not None:raise RuntimeError('interpreter stopped')
            result['controls']=self.controls
            self.process.stdin.write(payload);self.process.stdin.flush()
            buf=b'';total=0
            with (folder/'wire_private.jsonl').open('wb') as wire:
                while not done:
                    remaining=timeout-(time.monotonic()-started)
                    if remaining<=0:
                        result['status']='timeout';self.usable=False;break
                    ready=self.selector.select(min(1,max(.01,remaining)))
                    if not ready:
                        if self.process.poll() is not None:break
                        continue
                    chunk=self.process.stdout.read1(65536)
                    if not chunk:break
                    buf+=chunk;total+=len(chunk)
                    if total>8*1024*1024 or len(buf)>2*1024*1024:raise ValueError('RPC output limit')
                    while b'\n' in buf:
                        line,buf=buf.split(b'\n',1);wire.write(line+b'\n');wire.flush()
                        packet=json.loads(line)
                        if packet.get('kind')=='api':
                            if type(packet.get('program_index')) is not int or packet['program_index']!=number:
                                raise ValueError('API from a different program boundary')
                            reply=channel.exchange({k:v for k,v in packet.items() if k!='program_index'})
                            on_record(channel.rows[-1])
                            self.process.stdin.write(json.dumps(reply,allow_nan=False).encode()+b'\n');self.process.stdin.flush()
                        elif packet.get('kind')=='done':
                            if (set(packet)!={'kind','python','program_index','stdout','stdout_truncated','error'}
                                or packet['python']!=self.selection['expected_python']
                                or type(packet['program_index']) is not int or packet['program_index']!=number
                                or type(packet['stdout']) is not str or len(packet['stdout'])>65536
                                or type(packet['stdout_truncated']) is not bool
                                or packet['error'] is not None and type(packet['error']) is not str
                                or buf):raise ValueError('invalid completion protocol')
                            result.update(status='execution_error' if packet['error'] else 'ok',
                                stdout=packet['stdout'],stdout_truncated=packet['stdout_truncated'],error=packet['error'])
                            done=True;break
                        else:raise ValueError('unknown RPC message')
            if not done and result['status']=='not_started':
                result.update(status='execution_error',error='interpreter stopped before result');self.usable=False
            if channel.fatal:self.usable=False
        except Exception as exc:
            result.update(status='harness_error',error_type=type(exc).__name__);self.usable=False
            (folder/'error_private.txt').write_text(str(exc))
        finally:
            # A stopped/ambiguous interpreter is never replayed or silently reset.
            if not self.usable:
                try:self.close()
                except Exception as exc:result.update(status='harness_error',cleanup_error_type=type(exc).__name__)
            result.update(api_requests=sum(int(r['api_request_sent']) for r in channel.rows),
                declared_complete=channel.complete,unknown_effects=channel.fatal,
                session_usable=self.usable and not self.closed,
                container_removed=self.state['container_removed'],wall_seconds=time.monotonic()-started)
            self.programs.append({'program_index':number,'record_name':folder.name,
                'status':result['status'],'api_requests':result['api_requests'],
                'wall_seconds':result['wall_seconds'],'session_usable':result['session_usable']})
            self._save()
            (folder/'result_private.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
        return result

    def close(self):
        if self.closed:return self.state
        started=time.monotonic()
        try:
            if self.process and self.process.poll() is None:
                self.process.stdin.close()
                try:self.process.wait(timeout=2)
                except subprocess.TimeoutExpired:self.process.kill();self.process.wait(timeout=5)
            if self.creation_attempted:
                probe=subprocess.run(self.cmd+['inspect',self.name],capture_output=True,timeout=15)
                if probe.returncode==0:
                    info=json.loads(probe.stdout)[0]
                    if info['Config'].get('Labels',{}).get('harness.export-purpose')!='bounded-python-comparator':
                        raise RuntimeError('container ownership mismatch')
                    self.state.update(oom_killed=info['State']['OOMKilled'],
                        container_exit_code=info['State']['ExitCode'] if not info['State']['Running'] else None)
                    removal=subprocess.run(self.cmd+['rm','-f',self.name],capture_output=True,timeout=30)
                    if removal.returncode:raise RuntimeError('container cleanup failed')
                    self.state['container_removed']=True
                elif b'No such object' in probe.stderr or b'No such container' in probe.stderr:
                    self.state['container_removed']=True
                else:raise RuntimeError('cannot verify container absence')
            else:self.state['container_removed']=True
            self.state['status']='closed'
        except Exception as exc:
            self.state.update(status='cleanup_error',cleanup_error_type=type(exc).__name__)
            raise
        finally:
            self.usable=False;self.closed=True
            if self.selector:self.selector.close()
            if self.stderr:self.stderr.close()
            self.state['cleanup_wall_seconds']=time.monotonic()-started
            self._save()
        return self.state
