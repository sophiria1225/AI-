"""Count runtime bindings at the already fixed prefix, never disclose values.

Post-selection characterization only. Does not alter any running P31 branch or
choose a replacement checkpoint. Replays only saved API replies in isolation.
"""
import argparse
import collections
import datetime
import json
from pathlib import Path
import time

from persistent_api_python import PersistentApiPython
from recorded_python_replay import RecordedChannel, replay_programs
from run_context_comparison import write_json
from run_handoff_factors import prepare_sources, sha, ROOT

INSPECT = '''
import builtins as _inspection_builtins
import types as _inspection_types
import json as _inspection_json
_inspection_types_allowed = {
    _inspection_builtins.dict: 'dict', _inspection_builtins.list: 'list',
    _inspection_builtins.tuple: 'tuple', _inspection_builtins.set: 'set',
    _inspection_builtins.str: 'str', _inspection_builtins.int: 'int',
    _inspection_builtins.float: 'float', _inspection_builtins.bool: 'bool',
    _inspection_builtins.type(None): 'none',
    _inspection_types.ModuleType: 'module', _inspection_types.FunctionType: 'function'}
_inspection_bindings = [(name, value) for name, value in _inspection_builtins.globals().items()
    if not name.startswith('_') and name not in ('call_api', 'api_schemas', 'observations')]
_inspection_counts = {}
_inspection_container_entries = 0
for _inspection_name, _inspection_value in _inspection_bindings:
    _inspection_type = _inspection_builtins.type(_inspection_value)
    _inspection_label = _inspection_types_allowed.get(_inspection_type, 'other')
    _inspection_counts[_inspection_label] = _inspection_counts.get(_inspection_label, 0) + 1
    if _inspection_type in (_inspection_builtins.dict, _inspection_builtins.list,
                            _inspection_builtins.tuple, _inspection_builtins.set):
        _inspection_container_entries += _inspection_builtins.len(_inspection_value)
_inspection_builtins.print(_inspection_json.dumps({
    'user_bindings': _inspection_builtins.len(_inspection_bindings),
    'binding_types': _inspection_counts,
    'top_level_container_entries_with_aliases': _inspection_container_entries}, sort_keys=True))
'''


def run(storage, root, output, report):
    plan, source_plan, tools, schemas, sources = prepare_sources(storage,root)
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
                raise ValueError('inspection did not remain an inert aggregate computation')
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
    result={'phase':'P31_prefix_characterization','at':datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'all_four_attempted':len(rows)==4,'rows':rows,'model_calls':0,'live_api_requests':0,
            'wall_seconds':time.monotonic()-started,'selection_or_running_branches_changed':False,
            'scope':'Counts bindings and top-level container sizes only. Aliases may double count. No variable names, values, credentials, semantic relevance or future correctness are inferred.',
            'source_hashes':{'scripts/inspect_handoff_prefix_state.py':sha(Path(__file__)),
                             'configs/P31_handoff_factors_v01.json':sha(root/'configs/P31_handoff_factors_v01.json')}}
    write_json(output/'summary.json',result);write_json(report,result)
    print(json.dumps(result))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--storage-root',type=Path,required=True)
    p.add_argument('--repo-root',type=Path,default=ROOT);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--report',type=Path,required=True);a=p.parse_args()
    run(a.storage_root,a.repo_root,a.output,a.report)
