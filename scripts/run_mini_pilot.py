"""Pinned mini-swe-agent with measured local model and execution adapters."""
import argparse
import datetime
import hashlib
import json
import os
import pathlib
import signal
import subprocess
import sys
import time
import types
import urllib.request
import uuid

ROOT = pathlib.Path(__file__).resolve().parents[1]
VENDOR = ROOT / 'vendor/mini-swe-agent'
os.environ['MSWEA_GLOBAL_CONFIG_DIR'] = str(ROOT / '.runtime/mini_config')
os.environ['MSWEA_SILENT_STARTUP'] = '1'
sys.path.insert(0, str(VENDOR / 'src'))

import docker
import yaml
from minisweagent.agents.default import DefaultAgent
from minisweagent.environments.docker import DockerEnvironment
from minisweagent.exceptions import FormatError, LimitsExceeded
from minisweagent.models.utils.actions_toolcall import (
    BASH_TOOL, format_toolcall_observation_messages, parse_toolcall_actions,
)

from artifact_capture import capture_artifact
from container_policy import POLICY, create_task_container
from run_e0_pilot import alarm_handler, input_bound, model_call, save_json, tool_command, verify_task_environment
import local_llama
from visible_checks import run_checks

MINI_COMMIT = '04d809ceab9df28f9adaed044884180159172930'


def stop(reason):
    raise LimitsExceeded({'role': 'exit', 'content': reason,
                          'extra': {'exit_status': reason, 'submission': ''}})


class OllamaModel:
    def __init__(self, config, templates, out, summary, started):
        self.config, self.templates, self.out = config, templates, out
        self.summary, self.started = summary, started
        self.previous = None
        self.total_tokens = 0

    def query(self, messages, **kwargs):
        prepared = [{k: v for k, v in message.items() if k != 'extra'} for message in messages]
        is_llama = self.config.get('backend') == 'llama.cpp'
        preflight = local_llama.count_input(self.config, prepared, [BASH_TOOL]) if is_llama else None
        bound = preflight['input_tokens'] if preflight else input_bound(prepared, self.previous)
        remaining = self.config['max_total_tokens'] - self.total_tokens
        if bound + self.config['num_predict'] > min(self.config['num_ctx'], remaining):
            self.summary['next_input_bound'] = bound
            stop('conservative_budget_guard')
        remaining_wall = self.config['max_wall_seconds'] - (time.monotonic() - self.started)
        if remaining_wall <= 0:
            stop('wall_limit')
        out = self.out / f"call_{len(self.summary['calls'])+1:03d}_single"
        out.mkdir()
        if preflight:
            save_json(out / 'preflight.json', preflight)
        call = local_llama.model_call if is_llama else model_call
        response = call(self.config, prepared, out, remaining_wall, tools=[BASH_TOOL])
        self.summary['calls'].append({k: v for k, v in response.items() if k != 'message'} |
                                     {'path': out.name, 'precall_input_bound': bound})
        if response['status'] != 'ok':
            self.summary['usage_complete'] = False
            stop('model_error')
        self.total_tokens += response['input_tokens'] + response['output_tokens']
        self.previous = (len(prepared), response['input_tokens'],
                         hashlib.sha256(json.dumps(prepared, ensure_ascii=False).encode()).hexdigest())
        self.summary['total_recorded_tokens'] = self.total_tokens
        save_json(self.out / 'summary.json', self.summary)
        print(json.dumps({'run_id': self.summary['run_id'], 'call': len(self.summary['calls']),
                          'tokens': self.total_tokens, 'done_reason': response.get('done_reason')}), flush=True)
        if self.total_tokens > self.config['max_total_tokens']:
            stop('measured_token_limit_exceeded')
        if preflight and response['input_tokens'] != preflight['input_tokens']:
            self.summary['input_counter_mismatch'] = True
            stop('input_counter_mismatch')
        if response.get('done_reason') == 'length':
            stop('generation_limit_incomplete_response')
        message = response['message']
        tool_calls = []
        for i, tool in enumerate(message.get('tool_calls', [])):
            tool['id'] = tool.get('id') or f'call_{len(self.summary["calls"])}_{i}'
            function = tool.get('function', {})
            arguments = function.get('arguments', {})
            if isinstance(arguments, dict):
                arguments = json.dumps(arguments)
            tool_calls.append(types.SimpleNamespace(id=tool['id'], function=types.SimpleNamespace(
                name=function.get('name', ''), arguments=arguments)))
        try:
            actions = parse_toolcall_actions(tool_calls,
                format_error_template=self.templates['format_error_template'],
                template_kwargs={'finish_reason': response.get('done_reason')})
            if len(actions) > 8 or any(not isinstance(action.get('command'), str) for action in actions):
                raise FormatError({'role': 'user', 'content': 'Use 1 to 8 bash calls with string commands.',
                                   'extra': {'interrupt_type': 'FormatError'}})
        except FormatError as error:
            error.messages[0].setdefault('extra', {})['response_path'] = str(out.relative_to(self.out))
            raise
        message['extra'] = {'actions': actions, 'response_path': str(out.relative_to(self.out))}
        return message

    def format_message(self, **kwargs):
        return kwargs

    def format_observation_messages(self, message, outputs, template_vars=None):
        results = format_toolcall_observation_messages(actions=message['extra']['actions'], outputs=outputs,
            observation_template=self.templates['observation_template'], template_vars=template_vars)
        for result in results:
            if result['role'] == 'tool':
                result['tool_name'] = 'bash'
        return results

    def get_template_vars(self, **kwargs):
        return {}

    def serialize(self):
        return {'info': {'local_token_usage': self.total_tokens, 'usage_complete': self.summary['usage_complete'],
                         'dollar_cost': None, 'dollar_cost_note': 'local execution; unused mini cost counter is not billed cost'}}


class RestrictedEnvironment:
    def __init__(self, container, config, out, summary, started):
        self.container, self.config, self.out = container, config, out
        self.summary, self.started = summary, started

    def execute(self, action, cwd=''):
        remaining = self.config['max_wall_seconds'] - (time.monotonic() - self.started)
        if remaining <= 0:
            stop('wall_limit')
        out = self.out / f"tool_{len(self.summary['tools'])+1:03d}"
        out.mkdir()
        result = tool_command(self.container, action['command'], self.config, out, remaining)
        self.summary['tools'].append({k: v for k, v in result.items() if k not in ['command', 'output']} |
                                     {'path': out.name})
        save_json(self.out / 'summary.json', self.summary)
        output = {'output': result['output'], 'returncode': result['exit_code'],
                  'exception_info': result.get('error', '')}
        if not result['exit_code_known'] or result.get('running'):
            stop('tool_execution_status_unknown')
        DockerEnvironment._check_finished(self, output)
        return output

    def get_template_vars(self, **kwargs):
        return {'cwd': '/testbed'}

    def serialize(self):
        return {'info': {'container_policy': POLICY, 'environment_adapter': 'explicit_testbed_path'}}


def make_templates(config):
    templates = yaml.safe_load((VENDOR / 'src/minisweagent/config/benchmarks/swebench.yaml').read_text())
    # Preserve the upstream workflow; align modification rights and submission with E0.
    instance = templates['agent']['instance_template']
    instance = instance.replace('make changes to non-test files', 'make changes to relevant source and test files')
    start = instance.index('## Important Boundaries')
    end = instance.index('## Recommended Workflow')
    instance = instance[:start] + '''## Important Boundaries

- Work in /testbed. All repository files can be read. You may modify relevant source, tests, and configuration when the issue requires it.
- Preserve unrelated behavior. There is no internet; use the already installed testbed Python environment.
- Put temporary reproduction scripts and notes under /tmp or .harness_notes. Do not commit changes.

''' + instance[end:]
    instance = instance.replace("- If a tool isn't available, you can also install it", '- Network installation is unavailable; use installed tools.')
    instance = instance[:instance.index('## Submission')] + '''## Submission

Inspect git diff and run relevant visible checks. The harness submits the final worktree diff, including new source/tests, after excluding reserved .harness_notes and recognized core dumps. No hidden evaluation results are available during execution.
When complete, issue `echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT` in a bash tool call. A nonzero exit does not submit. You cannot continue after submitting.

## Budget

At most ''' + str(config['max_calls']) + ''' model calls and ''' + str(config['max_total_tokens']) + ''' total input plus output tokens for this task. One response is capped at ''' + str(config['num_predict']) + ''' tokens; keep explanation concise and finish tool calls. The wall-clock limit is ''' + str(config['max_wall_seconds']) + ''' seconds. Failed attempts consume budget. Tool commands have a timeout and pipefail enabled.
</instructions>
'''
    templates['agent']['instance_template'] = instance
    templates['agent'].update(step_limit=config['max_calls'], cost_limit=0,
                              wall_time_limit_seconds=config['max_wall_seconds'])
    return templates


def run(config):
    commit = subprocess.check_output(['git', '-C', str(VENDOR), 'rev-parse', 'HEAD'], text=True).strip()
    if commit != MINI_COMMIT or subprocess.check_output(['git', '-C', str(VENDOR), 'status', '--porcelain']):
        raise RuntimeError('pinned mini-swe-agent checkout changed')
    tasks = [json.loads(line) for line in (ROOT / 'data/verified_public_inputs.jsonl').read_text().splitlines()]
    task = next(t for t in tasks if t['instance_id'] == config['instance_id'])
    if set(task) - {'repo','instance_id','base_commit','problem_statement','created_at','version','environment_setup_commit'}:
        raise RuntimeError('unexpected task input columns')
    if config.get('backend') == 'llama.cpp':
        with urllib.request.urlopen(config['base_url'] + '/props', timeout=10) as response:
            props = json.load(response)
        if pathlib.Path(props.get('model_path', '')).resolve() != (ROOT / config['model_path']).resolve():
            raise RuntimeError('server model path differs from pinned configuration')
        verified = json.loads((ROOT / 'records/models/p2_minimax_download.json').read_text())
        if verified['status'] != 'verified' or verified['manifest']['revision'] != config['model_revision']:
            raise RuntimeError('selected model download is not verified')
    else:
        with urllib.request.urlopen('http://127.0.0.1:11434/api/tags', timeout=10) as response:
            model = next(m for m in json.load(response)['models'] if m['name'] == config['model'])
        if model['digest'] != config['model_digest']:
            raise RuntimeError('model digest changed')
    stamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S') + '_mini_' + uuid.uuid4().hex[:6]
    phase = config.get('phase', 'P1')
    out = ROOT / 'records' / phase.lower() / stamp
    out.mkdir(parents=True)
    sources = ['run_mini_pilot.py','run_e0_pilot.py','container_policy.py','artifact_capture.py',
               'local_llama.py','visible_checks.py']
    hashes = {}
    for source in sources:
        content = (ROOT / 'scripts' / source).read_bytes()
        (out / source).write_bytes(content)
        hashes[source] = hashlib.sha256(content).hexdigest()
    save_json(out / 'config.json', config)
    save_json(out / 'public_task.json', task)
    templates = make_templates(config)
    save_json(out / 'mini_templates.json', templates)
    summary = {'run_id':stamp, 'phase':phase, 'strategy':'mini_single_adapted',
        'instance_id':task['instance_id'], 'model':config['model'], 'mini_commit':commit,
        'source_hashes':hashes, 'calls':[], 'tools':[], 'usage_complete':True,
        'started_at':datetime.datetime.now(datetime.timezone.utc).isoformat(), 'stop_reason':'initializing'}
    save_json(out / 'summary.json', summary)
    client = docker.from_env(timeout=60)
    container = None
    started = time.monotonic()
    try:
        container = create_task_container(client, config['image'], 'harness_p1_' + stamp)
        container.start()
        summary['task_environment'] = verify_task_environment(container)
        check = container.exec_run(['git','diff','--exit-code',task['base_commit'],'--'],workdir='/testbed')
        if check.exit_code != 0:
            raise RuntimeError('image worktree differs from public task base')
        initial = container.exec_run(['git','status','--porcelain'],workdir='/testbed')
        (out / 'initial_status.txt').write_bytes(initial.output)
        if initial.exit_code != 0 or initial.output.strip():
            raise RuntimeError('initial worktree not clean')
        model = OllamaModel(config, templates['model'], out, summary, started)
        env = RestrictedEnvironment(container, config, out, summary, started)
        agent = DefaultAgent(model, env, **templates['agent'], output_path=out/'trajectory.json')
        result = agent.run(task['problem_statement'])
        summary['stop_reason'] = result.get('exit_status','unknown_exit')
        summary['agent_model_queries'] = agent.n_calls
        if config.get('visible_checks'):
            summary['visible_checks'] = run_checks(container, config['visible_checks'], out / 'visible_checks',
                config['max_wall_seconds'] - (time.monotonic() - started))
        summary.update(capture_artifact(container, task['base_commit'], out))
        summary['artifact_frozen_at'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    except Exception as error:
        summary.update(stop_reason='runner_error', error=repr(error))
    finally:
        if container is not None:
            container.remove(force=True)
            summary['container_removed'] = True
        summary['wall_seconds'] = time.monotonic() - started
        save_json(out / 'summary.json', summary)
        print(json.dumps({'path':str(out),'stop_reason':summary['stop_reason'],
                          'tokens':summary.get('total_recorded_tokens'), 'seconds':summary['wall_seconds']}),flush=True)
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', required=True)
    args = parser.parse_args()
    signal.signal(signal.SIGALRM, alarm_handler)
    result = run(json.loads((ROOT / args.config).read_text()))
    raise SystemExit(0 if result.get('artifact_sha256') and result['usage_complete'] else 1)
