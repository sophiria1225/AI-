"""Real-container checks for execution status and prospective artifact filtering."""
import datetime
import hashlib
import json
import pathlib

import docker

from artifact_capture import capture_artifact
from container_policy import create_task_container
from run_e0_pilot import tool_command, verify_task_environment, TASK_ENV

root = pathlib.Path(__file__).resolve().parents[1]
out = root/'records/p1_controls'/datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
out.mkdir(parents=True)
config=json.loads((root/'configs/P1_large_15957.json').read_text())
task=next(json.loads(line) for line in (root/'data/verified_public_inputs.jsonl').read_text().splitlines()
          if json.loads(line)['instance_id']==config['instance_id'])
client=docker.from_env(timeout=60)
container=create_task_container(client,config['image'],'harness_p1_controls')
checks={}
try:
    container.start()
    environment=[verify_task_environment(container) for _ in range(5)]
    checks['environment_5_repeats']=all(x['python']=='3.9.20' for x in environment)
    for label, command, expected in [('nonzero','exit 3',3),('pipeline','false | cat',1),('timeout','sleep 5',124)]:
        target=out/label
        target.mkdir()
        record=tool_command(container,command,config|{'tool_timeout_seconds':1},target,30)
        checks[label]=record['exit_code']==expected and record['exit_code_known'] and not record['running']
    fixture=r'''
import pathlib
p=pathlib.Path('/testbed')
(p/'.harness_notes').mkdir()
(p/'.harness_notes'/'notes.txt').write_text('temporary notes')
(p/'p1_source.py').write_text('VALUE = 3\n')
(p/'tests'/'p1_regression.py').write_text('def test_probe():\n    assert 1 == 1\n')
(p/'core.py').write_text('# a source file, not a dump\n')
header=bytearray(64)
header[:6]=b'\x7fELF\x02\x01'
header[16:18]=(4).to_bytes(2,'little')
(p/'core').write_bytes(header+b'CONTROL_FIXTURE_NOT_AN_OBSERVED_CRASH')
'''
    result=container.exec_run(['python','-c',fixture],environment=TASK_ENV,workdir='/testbed')
    assert result.exit_code==0, result.output
    artifact=capture_artifact(container,task['base_commit'],out)
    patch=(out/'final.patch').read_text()
    manifest=json.loads((out/'artifact_manifest.json').read_text())
    checks['new_source_and_test_included']=all('b/'+name in patch for name in ['p1_source.py','tests/p1_regression.py','core.py'])
    checks['notes_excluded']='b/.harness_notes' not in patch
    checks['ELF_core_excluded']='diff --git a/core b/core\n' not in patch
    core=next(x for x in manifest['excluded'] if x['reason']=='ELF_core_dump')
    checks['diagnostic_archive_saved']=(out/core['archive_path']).is_file()
    result={'scope':'control fixtures, not a model task or real crash', 'checks':checks,
            'environments':environment, 'artifact':artifact,
            'source_hashes':{name:hashlib.sha256((root/'scripts'/name).read_bytes()).hexdigest()
                             for name in ['check_p1_controls.py','artifact_capture.py','run_e0_pilot.py']}}
    (out/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'path':str(out),'checks':checks}),flush=True)
finally:
    container.remove(force=True)
raise SystemExit(0 if all(checks.values()) else 1)
