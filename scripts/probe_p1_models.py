"""Bounded adapter calibration: two-step shell flow and deliberate truncation, both models."""
import datetime
import json
import pathlib
import signal
import time

import docker
from run_mini_pilot import (DefaultAgent, LimitsExceeded, OllamaModel, RestrictedEnvironment,
    ROOT, alarm_handler, create_task_container, make_templates, save_json, verify_task_environment)

signal.signal(signal.SIGALRM,alarm_handler)
out=ROOT/'records/p1_model_probes'/datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
out.mkdir(parents=True)
results=[]
for label in ['large','small']:
    config=json.loads((ROOT/f'configs/P1_{label}_15957.json').read_text())
    for mode in ['normal','forced_length']:
        target=out/(label+'_'+mode)
        target.mkdir()
        settings=config|{'max_calls':4,'max_total_tokens':30000,'max_wall_seconds':240,
                         'num_predict':4096 if mode=='normal' else 1}
        save_json(target/'config.json',settings)
        summary={'run_id':target.name,'calls':[],'tools':[],'usage_complete':True}
        started=time.monotonic()
        templates=make_templates(settings)
        model=OllamaModel(settings,templates['model'],target,summary,started)
        container=None
        try:
            if mode=='normal':
                container=create_task_container(docker.from_env(timeout=60),settings['image'],'harness_p1_probe')
                container.start()
                summary['environment']=verify_task_environment(container)
                env=RestrictedEnvironment(container,settings,target,summary,started)
                agent=DefaultAgent(model,env,system_template='Use bash to follow the user instructions. Do not change any files.',
                    instance_template='First run python -c \'import sys; assert sys.prefix == "/opt/miniconda3/envs/testbed"; print("P1_ENV_OK")\'. After observing success, use a separate bash call to run echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT. You must inspect the first result before submitting.',
                    step_limit=4,cost_limit=0,wall_time_limit_seconds=240,output_path=target/'trajectory.json')
                result=agent.run('adapter calibration')
                summary['result']=result
                observations=[json.loads((target/t['path']/'result.json').read_text()) for t in summary['tools']]
                summary['passed']=result.get('exit_status')=='Submitted' and len(observations)>=2 and any(
                    'P1_ENV_OK' in r['output'] and r['exit_code']==0 for r in observations)
            else:
                try:
                    model.query([{'role':'system','content':'Use the bash tool.'},
                                 {'role':'user','content':'Run a bash command that prints P1_LIMIT_PROBE.'}])
                    summary['passed']=False
                except LimitsExceeded as error:
                    summary['result']=error.messages[-1]['extra']
                    summary['passed']=(summary['result']['exit_status']=='generation_limit_incomplete_response'
                                       and not summary['tools'] and summary['usage_complete'])
        except Exception as error:
            summary.update(passed=False,error=repr(error))
        finally:
            if container is not None:
                container.remove(force=True)
            summary['wall_seconds']=time.monotonic()-started
            save_json(target/'summary.json',summary)
            results.append({'model_label':label,'mode':mode,'passed':summary['passed'],
                'calls':len(summary['calls']),'tokens':summary.get('total_recorded_tokens'),
                'wall_seconds':summary['wall_seconds'],'path':str(target.relative_to(ROOT))})
            print(json.dumps(results[-1]),flush=True)
save_json(out/'summary.json',results)
raise SystemExit(0 if all(r['passed'] for r in results) else 1)
