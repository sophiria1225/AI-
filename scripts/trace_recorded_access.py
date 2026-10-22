"""Compare ordinary and access-instrumented replays of the closed P33 cohort.

Only saved public responses are available to the isolated interpreter. No model,
live application bridge, evaluator, or reserved task loader is constructed.
"""
import argparse
import hashlib
import json
from pathlib import Path
import time

from diagnose_handoff_programs import require_complete
from inspect_appworld_api_schemas import load_public_tools
from native_access_trace import HELPER
from persistent_api_python import PersistentApiPython
from recorded_python_replay import RecordedChannel, canonical, load_programs, reply_from_receipt

ROOT=Path(__file__).resolve().parents[1]


def read(path):return json.loads(path.read_text())
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def write(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')


def program_files(folder):
    return {name:sha(folder/name) for name in ('input_private.json','result_private.json','wire_private.jsonl')}


def suffix_programs(trial,schemas,start):
    """Load suffix records with their original, nonzero session index."""
    events,spans=read(trial/'events.json'),read(trial/'spans.json')
    by_id={e['span_id']:e for e in events};numbers={};programs=[]
    for event in events:
        if event['stage']!='model_tool':continue
        call=event['call'];numbers[call]=numbers.get(call,0)+1
        folder=trial/'programs'/f'{call}_{numbers[call]:02d}'
        if not folder.exists():continue  # read_span / rejected non-executed tool
        source=read(folder/'input_private.json');expected=read(folder/'result_private.json')
        index=start+len(programs)
        if source['program_index']!=index or expected['program_index']!=index:
            raise ValueError('noncontiguous recorded suffix')
        if expected['status'] not in ('ok','execution_error') or not expected['session_usable']:
            raise ValueError('unusable original boundary remains unsupported')
        wire=[json.loads(line) for line in (folder/'wire_private.jsonl').read_text().splitlines()]
        if not wire or wire[-1].get('kind')!='done':raise ValueError('no completion packet')
        requests=wire[:-1]
        if any(p.get('kind')!='api' or p.get('program_index')!=index for p in requests):
            raise ValueError('unexpected original wire packet')
        if wire[-1].get('program_index')!=index or any(
                wire[-1].get(k)!=expected.get(k) for k in ('stdout','stdout_truncated','error')):
            raise ValueError('saved completion differs')
        receipts=spans[event['span_id']]['observation']['api_receipts']
        if len(requests)!=len(receipts):raise ValueError('receipt count differs')
        entries=[]
        for number,(request,receipt) in enumerate(zip(requests,receipts,strict=True),1):
            sid=receipt['span_id'];api_event=by_id[sid]
            if request['id']!=number or api_event['stage']!='python_api' or api_event['call']!=call:
                raise ValueError('request identity differs')
            entries.append(reply_from_receipt(request,spans[sid],api_event,schemas))
        if sum(e['originally_sent'] for e in entries)!=expected['api_requests']:
            raise ValueError('original dispatch account differs')
        programs.append(dict(name=folder.name,source=source,expected=expected,entries=entries,
                             source_sha256=program_files(folder),phase='continuation'))
    if sum(len(p['entries']) for p in programs)!=sum(e['stage']=='python_api' for e in events):
        raise ValueError('not all suffix requests accounted')
    return programs


def inventory_program(trial):
    folder=trial/'transfer_inventory'
    source=read(folder/'input_private.json');expected=read(folder/'result_private.json')
    wire=[json.loads(line) for line in (folder/'wire_private.jsonl').read_text().splitlines()]
    if (source['program_index']!=9 or expected['program_index']!=9 or expected['status']!='ok'
            or not expected['session_usable'] or expected['api_requests'] or len(wire)!=1
            or wire[0].get('kind')!='done' or wire[0].get('program_index')!=9
            or any(wire[0].get(k)!=expected.get(k) for k in ('stdout','stdout_truncated','error'))):
        raise ValueError('original inventory differs')
    return dict(name='transfer_inventory',source=source,expected=expected,entries=[],
                source_sha256=program_files(folder),phase='control')


def prepare_cell(storage,cell,schemas,schema_hashes):
    trial=storage/'records/context_pilot'/cell['run_id']
    # Evaluation contents and private tests are not read by this measurement.
    for name in ('events.json','spans.json','setup.json','source_identity.json','plan.json','factor_plan.json'):
        if sha(trial/name)!=cell['source_hashes'][name]:raise ValueError('closed source changed: '+name)
    identity=read(trial/'source_identity.json')
    original=storage/'records/context_pilot'/identity['source_run']
    for name,digest in identity['source_sha256'].items():
        if sha(original/name)!=digest:raise ValueError('original source changed: '+name)
    if read(original/'provenance.json')['public_schema_hashes']!=schema_hashes:
        raise ValueError('public schema revision changed')
    prefix=load_programs(original,schemas)[:8]
    if len(prefix)!=8:raise ValueError('all eight prefix programs required')
    for program in prefix:
        recorded=read(trial/'prefix_python'/program['name']/'input_private.json')
        if canonical(recorded)!=canonical(program['source']):raise ValueError('reconstructed prefix input differs')
        program['phase']='prefix'
        program['name']='prefix_'+program['name']
    has_inventory=cell['arm']=='stdout_mask_index_keep'
    extra=[inventory_program(trial)] if has_inventory else []
    suffix=suffix_programs(trial,schemas,10 if has_inventory else 9)
    return prefix+extra+suffix


def install_source(root):
    module=(root/'scripts/native_access_trace.py').read_text()
    code=(f'{HELPER} = (lambda ns: (exec(compile({module!r}, "<measurement>", "exec"), ns, ns), '
          f'ns["Recorder"]())[1])({{"__name__":"_harness_measurement"}})')
    if len(code)>20000:raise ValueError('instrument installation exceeds existing code bound')
    return code


def checked_aux(session,code,schemas,storage,folder):
    channel=RecordedChannel(schemas,[],schemas)
    result=session.run(code,[],channel,storage_root=storage,record_dir=folder,timeout=30)
    if (result['status']!='ok' or result['api_requests'] or channel.rows
            or result['stdout_truncated'] or not result['session_usable']):
        raise ValueError('measurement helper failed')
    return result


def replay_variant(programs,schemas,storage,root,out,instrument):
    out.mkdir();session=PersistentApiPython(storage,out/'session');rows=[]
    started=time.monotonic();measurement=None;error_type=None
    try:
        if instrument:
            checked_aux(session,install_source(root),schemas,storage,out/'install')
        for program in programs:
            source,expected=program['source'],program['expected']
            channel=RecordedChannel(source['api_schemas'],program['entries'],schemas)
            code=source['code']
            if instrument and program['phase']!='control':
                code=f'{HELPER}.execute({code!r}, (lambda:0).__globals__, call_api, {program["phase"]!r})'
            actual=session.run(code,source['observations'],channel,storage_root=storage,
                               record_dir=out/program['name'],timeout=90)
            comparison=channel.compare_result(actual,expected)
            comparison['checks']['session_usable']=actual['session_usable']==expected['session_usable']
            matches=all(comparison['checks'].values())
            rows.append({'program':program['name'],'phase':program['phase'],
                'original_program_index':source['program_index'],'replay_program_index':actual['program_index'],
                'checks':comparison['checks'],'matches':matches,'recorded_requests':len(program['entries']),
                'matched_requests':len(channel.rows),'wall_seconds':actual['wall_seconds'],
                'original_source_sha256':program['source_sha256']})
            if not matches:break
        if instrument and session.usable:
            # Chunk the private summary to respect the unchanged 64 KiB output
            # limit; these are controller queries, not model-generated programs.
            head=checked_aux(session,
                'print(__import__("json").dumps({"count":len('+HELPER+'.responses),'
                '"limits":dict('+HELPER+'.limits),"unsupported_operations":dict('+HELPER+'.dynamic)}))',
                schemas,storage,out/'measure_head')
            measurement=json.loads(head['stdout']);measurement['responses']=[]
            for offset in range(0,measurement['count'],40):
                result=checked_aux(session,
                    'print(__import__("json").dumps('+HELPER+'.summary()["responses"]['+str(offset)+':'+str(offset+40)+']))',
                    schemas,storage,out/f'measure_{offset:04d}')
                measurement['responses'].extend(json.loads(result['stdout']))
    except Exception as exc:
        error_type=type(exc).__name__
        (out/'error_private.txt').write_text(str(exc))
    finally:
        session.close()
    return {'all_programs_match':error_type is None and len(rows)==len(programs) and all(r['matches'] for r in rows),
            'expected_programs':len(programs),'programs':rows,'measurement':measurement,'error_type':error_type,
            'container_removed':session.state['container_removed'],
            'wall_seconds':time.monotonic()-started,'live_api_requests':0,'model_calls':0}


def run(storage,root):
    report=read(root/'reports/P33_comparison.json');plan=read(root/'configs/P33_output_views_v01.json')
    status=read(storage/'records/context_pilot'/plan['batch_id']/'status.json')
    require_complete(report,status,'P33')
    tools,schema_hashes,_=load_public_tools(storage/'.runtime/appworld/r18_probe_01/data')
    schemas={t['function']['name']:t['function'] for t in tools}
    out=storage/'records/context_pilot/P35_read_footprint_v01'
    target=root/'reports/P35_read_footprint.json'
    if out.exists() or target.exists():raise FileExistsError('preserve prior measurement')
    out.mkdir();started=time.monotonic();rows=[]
    paths=('scripts/native_access_trace.py','scripts/trace_recorded_access.py',
           'scripts/recorded_python_replay.py','scripts/persistent_api_python.py',
           'docs/experiments/P35_read_footprint.md','reports/P33_comparison.json')
    sources={p:sha(root/p) for p in paths};write(out/'source_sha256.json',sources)
    for cell in report['rows']:
        folder=out/cell['run_id'];folder.mkdir();row={k:cell[k] for k in ('run_id','task_id','arm')}
        try:
            programs=prepare_cell(storage,cell,schemas,schema_hashes)
            row['plain']=replay_variant(programs,schemas,storage,root,folder/'plain',False)
            # Always retain both results, including native replay mismatches.
            row['instrumented']=replay_variant(programs,schemas,storage,root,folder/'instrumented',True)
        except Exception as exc:
            row['preparation_error_type']=type(exc).__name__
            (folder/'error_private.txt').write_text(str(exc))
        rows.append(row);write(folder/'summary.json',row)
        print(json.dumps({'run_id':cell['run_id'],'plain_matches':row.get('plain',{}).get('all_programs_match',False),
                          'instrumented_matches':row.get('instrumented',{}).get('all_programs_match',False),
                          'error_type':row.get('preparation_error_type')},ensure_ascii=False),flush=True)
    result={'phase':'P35_read_footprint','all_twelve_attempted':len(rows)==12,'rows':rows,
            'all_replays_match':all(row.get(k,{}).get('all_programs_match',False) for row in rows for k in ('plain','instrumented')),
            'source_sha256':sources,'wall_seconds':time.monotonic()-started,
            'model_calls':0,'live_api_requests':0,'final_evaluator_invocations':0,'reserved_scenarios_read':0,
            'complete_read_coverage_claim':False,'unobserved_means_unnecessary':False,
            'token_savings_or_novelty_established':False,
            'limits':['Native values retained; AST rewriting changes frames/introspection/timing and can still change semantics.',
                'Only objects returned by recorded call_api calls are registered. Runtime schemas and separately supplied archive copies are not fully traced.',
                'Scalar roots, C/library operations, dynamic code, aliases to frame-sensitive builtins and mutations limit coverage.',
                'Whole-object presentation and opaque function arguments do not prove every field was semantically needed.',
                'Unobserved fields and scalar JSON bytes are not recoverable token savings or safe omission candidates.',
                'Measured only along fixed recorded programs. No altered agent trajectory or task-quality comparison.']}
    write(out/'summary.json',result);write(target,result)
    return 0 if result['all_replays_match'] else 1


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--storage-root',type=Path,required=True)
    p.add_argument('--repo-root',type=Path,default=ROOT);a=p.parse_args()
    raise SystemExit(run(a.storage_root,a.repo_root))
