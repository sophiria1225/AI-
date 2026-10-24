"""Show explicit P101 operational fields after the idle-watcher correction."""
import argparse
import json
from pathlib import Path

PATHS=('records/context_pilot/P101_pipeline_v01/status.json',
       'records/context_pilot/P101_preflight_v01/status.json',
       'records/context_pilot/P101_choice_context_v01/status.json',
       '.runtime/P101_closure_operations_v02/status.json')
ALLOWED=('phase','status','active','started_at','updated_at','finished_at',
         'server_owned','server_stopped','error_type','model_calls_attempted')


def inspect(storage):
    for name in PATHS:
        try:data=json.loads((storage/name).read_text())
        except FileNotFoundError:
            print(json.dumps(dict(path=name,status_file_present=False)));continue
        except json.JSONDecodeError:
            print(json.dumps(dict(path=name,status_file_present=True,status_read='transient_write')));continue
        result=dict(path=name,status_file_present=True,**{k:data[k] for k in ALLOWED if k in data})
        if 'stages' in data:
            result['stages']=[{k:row[k] for k in ('name','mode','exit_code','wall_seconds') if k in row}
                              for row in data['stages']]
        print(json.dumps(result))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--storage-root',type=Path,required=True)
    inspect(parser.parse_args().storage_root.resolve())
