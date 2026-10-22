"""Measure builtin-value matches for all four fixed development prefixes.

Uses recorded replies in isolated Python only. No live model, application API,
evaluation content, current P33 trajectory, or reserved scenario is read.
"""
import argparse
import hashlib
import json
from pathlib import Path
import time

from appworld_native_tools import NativeCatalog
from handoff_factors import split_turns
from handoff_output_views import make_view
from later_handoff_sources import prepare_later_sources
from native_conversation import recover_turn
from persistent_api_python import PersistentApiPython
from recorded_python_replay import RecordedChannel,replay_programs
from run_context_comparison import write_json
from runtime_recoverability import parse_structured_stdout,probe_source

ROOT=Path(__file__).resolve().parents[1]
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def candidates(prefix):
    _,view=make_view(prefix['conversation_private'],prefix['public_task'],'stdout_mask_keep')
    maskable={s['span_id'] for s in view['masked_spans']}
    rows=[];targets={}
    for number,turn in enumerate(split_turns(prefix['conversation_private'])[:-1],1):
        for span in recover_turn(turn):
            obs=span['observation']
            if not span['action'] or span['action']['name']!='run_python':continue
            label=f'output_{len(rows)+1}'
            row={'id':label,'turn':number,'span_id':span['id'],
                 'stdout_characters':len(obs.get('stdout','')),
                 'maskable_under_P33_rule':span['id'] in maskable}
            if (obs.get('status')!='ok' or obs.get('error') or obs.get('stdout_truncated')
                    or obs.get('unknown_effects') or obs.get('declared_complete')):
                row['classification']='protected_or_incomplete'
            else:
                try:
                    parsed=parse_structured_stdout(obs.get('stdout',''))
                    targets[label]=parsed['digest']
                    row.update(classification='structured_value',syntax=parsed['syntax'])
                except (ValueError,SyntaxError,RecursionError):
                    row['classification']='no_whole_supported_literal'
            rows.append(row)
    return rows,targets


def audit(storage,root):
    _,_,tools,schemas,prepared=prepare_later_sources(storage,root)
    out=storage/'records/context_pilot/P34_output_residency_v01'
    target=root/'reports/P34_output_residency.json'
    if out.exists() or target.exists():raise FileExistsError('preserve inspection')
    out.mkdir(parents=True);rows=[];started=time.monotonic()
    for number,item in enumerate(prepared,1):
        folder=out/f'prefix_{number:02d}';folder.mkdir()
        observations,targets=candidates(item['prefix'])
        row={'source_run':item['source_run'],'source_boundary_sha256':item['boundary_manifest_sha256'],
             'status':'not_started','observations':observations}
        session=PersistentApiPython(storage,folder/'python_session')
        at=time.monotonic()
        try:
            replay=replay_programs(item['programs'],schemas,session,folder/'programs',storage)
            if len(replay)!=len(item['programs']) or not all(r['observable_prefix_matches'] for r in replay):
                raise ValueError('recorded prefix differs')
            row['replay_wall_seconds']=time.monotonic()-at
            row['replayed_programs']=len(replay)
            row['recorded_request_matches']=sum(r['matched_requests'] for r in replay)
            catalog=NativeCatalog(tools)
            for e in item['prefix']['events']:catalog.visible.update(e.get('new_tools',[]))
            channel=RecordedChannel({n:schemas[n] for n in catalog.visible},[],schemas)
            result=session.run(probe_source(targets),[],channel,storage_root=storage,
                               record_dir=folder/'probe',timeout=10)
            if (result['status']!='ok' or result['api_requests'] or channel.rows
                    or result['stdout_truncated'] or not result['session_usable']):
                raise ValueError('residency inspection failed')
            parsed=json.loads(result['stdout'])
            if set(parsed['matches'])!=set(targets):raise ValueError('target identity changed')
            row['probe_wall_seconds']=result['wall_seconds']
            row['inspection']={k:v for k,v in parsed.items() if k!='matches'}
            for observation in observations:
                paths=parsed['matches'].get(observation['id'],[])
                observation.update(witnessed=bool(paths),bounded_matching_routes=len(paths),
                    matching_top_level_routes=sum(len(p)==1 for p in paths))
            row['status']='complete'
        except Exception as exc:
            row.update(status='failed',error_type=type(exc).__name__)
            (folder/'error_private.txt').write_text(str(exc))
        finally:
            session.close();row['container_removed']=session.state['container_removed']
            row['total_wall_seconds']=time.monotonic()-at
            rows.append(row);write_json(folder/'summary.json',row)
    complete=len(rows)==4 and all(r['status']=='complete' for r in rows)
    observations=[o for r in rows for o in r['observations']]
    totals={'outputs':len(observations),'structured':sum(o['classification']=='structured_value' for o in observations),
            'witnessed':sum(o.get('witnessed',False) for o in observations),
            'maskable':sum(o['maskable_under_P33_rule'] for o in observations),
            'maskable_and_witnessed':sum(o.get('witnessed',False) and o['maskable_under_P33_rule'] for o in observations),
            'maskable_stdout_characters':sum(o['stdout_characters'] for o in observations if o['maskable_under_P33_rule']),
            'maskable_and_witnessed_stdout_characters':sum(o['stdout_characters'] for o in observations if o.get('witnessed') and o['maskable_under_P33_rule']),
            'probe_wall_seconds':sum(r.get('probe_wall_seconds',0) for r in rows)}
    report={'phase':'P34_output_residency','all_four_completed':complete,'rows':rows,'totals':totals,
            'model_calls':0,'live_api_requests':0,'evaluator_invocations':0,'reserved_scenarios_read':0,
            'running_P33_results_read':False,'novel_method_established':False,
            'limits':['Only whole JSON/Python literals of supported builtin types. No regex or semantic extraction.',
              'Content equality at this boundary is not provenance, usefulness, external freshness, or future validity.',
              'An unwitnessed output is not proven absent; bounded scan may miss values or unsupported types.',
              'A hash collision is assumed negligible; this is not a formal equivalence proof.',
              'Printed text formatting and Python-versus-JSON presentation may differ despite equal typed values.',
              'Raw routes, values and content digests remain private. No controller was inserted into a model run.'],
            'source_sha256':{n:sha(root/n) for n in ('scripts/runtime_recoverability.py',
                'scripts/inspect_output_residency.py','scripts/recorded_python_replay.py',
                'configs/P29_stateful_code_v01.json','reports/P30_recorded_replay.json')},
            'wall_seconds':time.monotonic()-started}
    write_json(out/'summary.json',report);write_json(target,report)
    print(json.dumps({'complete':complete,'totals':totals,'wall_seconds':report['wall_seconds']}))
    return 0 if complete else 1


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--storage-root',type=Path,required=True)
    p.add_argument('--repo-root',type=Path,default=ROOT);a=p.parse_args()
    raise SystemExit(audit(a.storage_root,a.repo_root))
