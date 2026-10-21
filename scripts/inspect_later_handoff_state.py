"""Characterize all prespecified eighth-response states without inspecting outcomes."""
import argparse
import datetime
import json
from pathlib import Path
import time

from inspect_handoff_prefix_state import INSPECT
from later_handoff_sources import prepare_later_sources
from persistent_api_python import PersistentApiPython
from recorded_python_replay import RecordedChannel, replay_programs
from run_context_comparison import write_json
from run_handoff_factors import sha, ROOT


def run(storage,root,output,report):
    plan,source_plan,tools,schemas,sources=prepare_later_sources(storage,root)
    if output.exists() or report.exists():raise FileExistsError('preserve characterization records')
    output.mkdir(parents=True);started=time.monotonic();rows=[]
    for source in sources:
        out=output/source['source_run'];out.mkdir()
        session=PersistentApiPython(storage,out/'python_session')
        row={'source_run':source['source_run'],'boundary_manifest_sha256':source['boundary_manifest_sha256']}
        try:
            replayed=replay_programs(source['programs'],schemas,session,out/'prefix_programs',storage)
            if len(replayed)!=len(source['programs']) or not all(x['observable_prefix_matches'] for x in replayed):
                raise ValueError('prefix correspondence failed')
            visible=source['prefix']['manifest']['state']['visible_api_schemas']
            channel=RecordedChannel({name:schemas[name] for name in visible},[],schemas)
            result=session.run(INSPECT,[],channel,storage_root=storage,record_dir=out/'inspection',timeout=10)
            if result['status']!='ok' or result['api_requests'] or channel.rows or channel.mismatch:
                raise ValueError('inspection did not remain inert')
            counts=json.loads(result['stdout'])
            if (set(counts)!={'user_bindings','binding_types','top_level_container_entries_with_aliases'}
                    or sum(counts['binding_types'].values())!=counts['user_bindings']):
                raise ValueError('aggregate inventory invalid')
            row.update(status='counted',**counts)
        except Exception as exc:
            row.update(status='not_established',error_type=type(exc).__name__)
            (out/'error_private.txt').write_text(str(exc))
        finally:
            session.close();row['container_removed']=session.state['container_removed'];rows.append(row)
            write_json(out/'summary.json',row)
    result={'phase':'P32_prefix_characterization','at':datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'all_four_attempted':len(rows)==4,'rows':rows,'model_calls':0,'live_api_requests':0,
        'wall_seconds':time.monotonic()-started,'selection_or_running_branches_changed':False,
        'scope':'Binding and top-level container counts only; aliases may double count. Names, values, credentials, relevance and future correctness are not inferred.',
        'source_hashes':{n:sha(root/n) for n in ('scripts/inspect_later_handoff_state.py',
            'scripts/inspect_handoff_prefix_state.py','scripts/later_handoff_sources.py','configs/P32_handoff_factors_v01.json')}}
    write_json(output/'summary.json',result);write_json(report,result)
    print(json.dumps(result))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--storage-root',type=Path,required=True)
    p.add_argument('--repo-root',type=Path,default=ROOT);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--report',type=Path,required=True);a=p.parse_args()
    run(a.storage_root,a.repo_root,a.output,a.report)
