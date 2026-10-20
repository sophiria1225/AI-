"""P3: one shared ledger, pinned mini-swe-agent steps, one or two histories.

No automatic topology changes or hidden evaluation feedback. P2 is unchanged.
"""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import signal
import subprocess
import time
import types
import urllib.request
import uuid

from run_mini_pilot import (
    ROOT, VENDOR, MINI_COMMIT, OllamaModel, DefaultAgent, FormatError,
    BASH_TOOL, parse_toolcall_actions, make_templates, save_json,
    verify_task_environment, tool_command, alarm_handler,
)
from minisweagent.exceptions import LimitsExceeded
import docker
import local_llama
from artifact_capture import capture_artifact
from container_policy import POLICY, create_task_container
from experiment_state import SharedBudget, CompletionState, ProtocolStop
from model_provenance import check_live_model
from visible_checks import run_checks

ROLES = {
    'single': 'You handle investigation, implementation, and validation of the complete issue.',
    'implementation': 'Your primary responsibility is investigation and implementation. A validation worker alternates with you in the same worktree. Both workers may read, edit, and test all relevant files. Use the shared observations and communicate unresolved requirements.',
    'validation': 'Your primary responsibility is reproducing the issue, testing changes, and identifying regressions. An implementation worker alternates with you in the same worktree. Both workers may read, edit, and test all relevant files. You may fix a defect yourself. Communicate concrete evidence and unresolved requirements.',
}


class SharedModel(OllamaModel):
    def __init__(self, config, templates, out, summary, started, budget):
        super().__init__(config, templates, out, summary, started)
        self.budget = budget
        self.unit = 'single'

    def query(self, messages, **kwargs):
        # Appending before tokenization ensures the notice is charged too.
        messages.append({'role': 'user', 'content': self.budget.notice(time.monotonic()-self.started, self.unit)})
        prepared = [{k: v for k, v in m.items() if k != 'extra'} for m in messages]
        left = self.config['max_wall_seconds'] - (time.monotonic()-self.started)
        preflight = local_llama.count_input(self.config, prepared, [BASH_TOOL], timeout=min(60, max(1, left)))
        self.summary['next_input_bound'] = preflight['input_tokens']
        before = self.budget.snapshot()
        number = self.budget.calls + 1
        call_dir = self.out / f'call_{number:03d}_{self.unit}'
        call_dir.mkdir()
        save_json(call_dir / 'preflight.json', preflight)
        save_json(call_dir / 'budget_before.json', before)
        self.budget.begin_request(preflight['input_tokens'], time.monotonic()-self.started)
        left = self.config['max_wall_seconds'] - (time.monotonic()-self.started)
        try:
            response = local_llama.model_call(self.config, prepared, call_dir, left, tools=[BASH_TOOL])
        except Exception as error:
            # A transport/logging failure after authorization cannot be called free.
            response = {'status': 'error', 'input_tokens': None, 'output_tokens': None,
                        'error': repr(error), 'message': {'role': 'assistant', 'content': ''}}
            save_json(call_dir / 'adapter_error.json', response)
        self.summary['calls'].append({k: v for k, v in response.items() if k != 'message'} |
                                     {'path': call_dir.name, 'unit': self.unit,
                                      'precall_input_bound': preflight['input_tokens']})
        try:
            self.budget.finish_request(response)
        finally:
            self.total_tokens = self.budget.total_tokens
            self.summary.update(total_recorded_tokens=self.total_tokens,
                                usage_complete=self.budget.usage_complete,
                                budget=self.budget.snapshot())
            save_json(call_dir / 'budget_after.json', self.budget.snapshot())
            save_json(self.out / 'summary.json', self.summary)
        message = response['message']
        calls = []
        for i, call in enumerate(message.get('tool_calls', [])):
            call['id'] = call.get('id') or f'call_{number}_{i}'
            function = call.get('function', {})
            arguments = function.get('arguments', {})
            calls.append(types.SimpleNamespace(id=call['id'], function=types.SimpleNamespace(
                name=function.get('name', ''), arguments=json.dumps(arguments) if isinstance(arguments, dict) else arguments)))
        actions = parse_toolcall_actions(calls, format_error_template=self.templates['format_error_template'],
                                        template_kwargs={'finish_reason': response.get('done_reason')})
        if len(actions) > 8 or any(not isinstance(a.get('command'), str) for a in actions):
            raise FormatError({'role': 'user', 'content': 'Use 1 to 8 bash calls with string commands.'})
        message['extra'] = {'actions': actions, 'response_path': call_dir.name}
        return message


class SharedEnvironment:
    def __init__(self, container, config, out, summary, started):
        self.container, self.config, self.out, self.summary, self.started = container, config, out, summary, started
        self.unit = 'single'
        self.turn_outputs = []

    def execute(self, action, cwd=''):
        left = self.config['max_wall_seconds'] - (time.monotonic()-self.started)
        if left <= 0:
            raise ProtocolStop('wall_limit')
        directory = self.out / f"tool_{len(self.summary['tools'])+1:03d}"
        directory.mkdir()
        result = tool_command(self.container, action['command'], self.config, directory, left)
        self.summary['tools'].append({k: v for k, v in result.items() if k not in ('command', 'output')} |
                                     {'path': directory.name, 'unit': self.unit})
        save_json(self.out / 'summary.json', self.summary)
        if not result['exit_code_known'] or result.get('running'):
            raise ProtocolStop('tool_execution_status_unknown')
        output = {'output': result['output'], 'returncode': result['exit_code'],
                  'exception_info': result.get('error', '')}
        lines = output['output'].lstrip().splitlines()
        requested = bool(lines and lines[0].strip() == 'COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT' and output['returncode'] == 0)
        self.turn_outputs.append({'command': action['command'], 'result': output,
                                  'completion_requested': requested, 'record': directory.name})
        return output

    def get_template_vars(self, **kwargs):
        return {'cwd': '/testbed'}

    def serialize(self):
        return {'info': {'container_policy': POLICY, 'environment_adapter': 'p3_shared_worktree'}}


def templates_for(config, unit, pair):
    templates = make_templates(config)
    extra = '\n## Work allocation\n\n' + ROLES[unit]
    if pair:
        extra += ('\nCompletion is a vote for the current worktree version. Both workers must agree on '
                  'the same version. An artifact change observed at a turn boundary invalidates earlier votes. You may continue '
                  'after your own vote if your peer is not finished.')
    extra += ('\nUse the completion marker as the only bash call in that response. '
              'Do not combine completion with other calls.\n\n## Public checks\n\n'
              'These commands were selected using public information. They are useful but not a full specification.\n' +
              json.dumps(config.get('visible_checks', []), ensure_ascii=False))
    instance = templates['agent']['instance_template']
    if pair:
        instance = instance.replace('You cannot continue after submitting.',
                                    'The team stops once both votes refer to the current artifact.')
    templates['agent']['instance_template'] = instance.replace('</instructions>', extra + '\n</instructions>')
    # One external ledger controls all calls; local step limits must not multiply it.
    templates['agent']['step_limit'] = 0
    return templates


def run_turn(agent, env, completion, out, base_commit, turn_number):
    """One model step; preserve a public event and artifact-bound completion."""
    start = len(agent.messages)
    env.turn_outputs = []
    error = None
    try:
        agent.step()
        agent.n_consecutive_format_errors = 0
    except FormatError as exception:
        agent.add_messages(*exception.messages)
        agent.n_consecutive_format_errors += 1
        error = 'format_error'
    directory = out / 'artifact_versions' / f'{turn_number:03d}'
    directory.mkdir(parents=True)
    began = time.monotonic()
    captured = capture_artifact(env.container, base_commit, directory)
    changed = completion.observe_artifact(captured['artifact_sha256'])
    vote = len(env.turn_outputs) == 1 and env.turn_outputs[0]['completion_requested']
    if vote:
        completion.vote(env.unit, captured['artifact_sha256'])
    event = {'turn': turn_number, 'unit': env.unit, 'artifact': completion.snapshot(),
             'artifact_changed': changed, 'capture_seconds': time.monotonic()-began,
             'completion_vote_accepted': vote, 'format_error': error,
             'visible_content': [m.get('content') or '' for m in agent.messages[start:] if m['role'] == 'assistant'],
             'operations': env.turn_outputs}
    save_json(directory / 'turn.json', event)
    if any(o['completion_requested'] for o in env.turn_outputs) and not vote:
        agent.add_messages({'role': 'user', 'content': 'Completion was not accepted: submit the marker as the only bash call in a response.'})
    return event


def run(config, strategy):
    if strategy not in ('single', 'fixed_pair'):
        raise ValueError('unsupported comparison strategy')
    if config.get('phase') != 'P3' or config.get('readiness') != 'passed' or config.get('backend') != 'llama.cpp':
        raise RuntimeError('P3 requires explicitly ready, calibrated llama.cpp settings')
    if subprocess.check_output(['git', '-C', str(VENDOR), 'rev-parse', 'HEAD'], text=True).strip() != MINI_COMMIT or subprocess.check_output(['git', '-C', str(VENDOR), 'status', '--porcelain']):
        raise RuntimeError('pinned mini-swe-agent checkout changed')
    with urllib.request.urlopen(config['base_url'] + '/props', timeout=10) as response:
        props = json.load(response)
    runtime = json.loads((ROOT / '.runtime/model_server.json').read_text())
    selection, download, path = check_live_model(config['model_selection'], runtime, props, config['num_ctx'])
    if path.resolve() != (ROOT / config['model_path']).resolve() or selection['model_alias'] != config['model'] or selection['revision'] != config['model_revision']:
        raise RuntimeError('task model identity differs from verified selection')
    tasks = [json.loads(line) for line in (ROOT / 'data/verified_public_inputs.jsonl').read_text().splitlines()]
    task = next(t for t in tasks if t['instance_id'] == config['instance_id'])
    if set(task) - {'repo', 'instance_id', 'base_commit', 'problem_statement', 'created_at', 'version', 'environment_setup_commit'}:
        raise RuntimeError('unexpected task input columns')
    units = ('single',) if strategy == 'single' else ('implementation', 'validation')
    budget = SharedBudget(**{k: config[k] for k in ('max_calls', 'max_total_tokens', 'num_ctx', 'num_predict', 'max_wall_seconds')})
    stamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S') + '_' + strategy + '_' + uuid.uuid4().hex[:6]
    out = ROOT / 'records/p3' / stamp
    out.mkdir(parents=True)
    sources = ['run_fixed_comparison.py', 'experiment_state.py', 'run_mini_pilot.py', 'run_e0_pilot.py',
               'local_llama.py', 'artifact_capture.py', 'container_policy.py', 'model_provenance.py', 'visible_checks.py']
    hashes = {}
    for source in sources:
        content = (ROOT / 'scripts' / source).read_bytes()
        (out / source).write_bytes(content)
        hashes[source] = hashlib.sha256(content).hexdigest()
    for name, value in {'config': config, 'public_task': task, 'server_props': props, 'server_runtime': runtime,
                        'model_selection': selection, 'model_download_record': download}.items():
        save_json(out / (name + '.json'), value)
    summary = {'run_id': stamp, 'phase': 'P3', 'strategy': strategy, 'instance_id': task['instance_id'],
               'model': config['model'], 'mini_commit': MINI_COMMIT, 'source_hashes': hashes,
               'started_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
               'calls': [], 'tools': [], 'turns': [], 'usage_complete': True,
               'stop_reason': 'initializing', 'total_recorded_tokens': 0}
    save_json(out / 'summary.json', summary)
    started = time.monotonic()
    container = None
    agents = {}
    try:
        client = docker.from_env(timeout=60)
        container = create_task_container(client, config['image'], 'harness_p3_' + stamp)
        container.start()
        summary['task_environment'] = verify_task_environment(container)
        check = container.exec_run(['git', 'diff', '--exit-code', task['base_commit'], '--'], workdir='/testbed')
        status = container.exec_run(['git', 'status', '--porcelain'], workdir='/testbed')
        (out / 'initial_status.txt').write_bytes(status.output)
        if check.exit_code or status.exit_code or status.output.strip():
            raise RuntimeError('initial worktree differs from clean public base')
        initial_dir = out / 'artifact_versions/initial'
        initial_dir.mkdir(parents=True)
        initial = capture_artifact(container, task['base_commit'], initial_dir)
        completion = CompletionState(units, initial['artifact_sha256'])
        env = SharedEnvironment(container, config, out, summary, started)
        templates = {unit: templates_for(config, unit, len(units) == 2) for unit in units}
        save_json(out / 'unit_templates.json', templates)
        model = SharedModel(config, templates[units[0]]['model'], out, summary, started, budget)
        for unit in units:
            agent = DefaultAgent(model, env, **templates[unit]['agent'], output_path=out/f'trajectory_{unit}.json')
            agent.extra_template_vars['task'] = task['problem_statement']
            agent.add_messages({'role': 'system', 'content': agent._render_template(agent.config.system_template)},
                               {'role': 'user', 'content': agent._render_template(agent.config.instance_template)})
            agents[unit] = agent
        turn = 0
        while not completion.complete:
            unit = units[turn % len(units)]
            turn += 1
            model.unit = env.unit = unit
            event = run_turn(agents[unit], env, completion, out, task['base_commit'], turn)
            summary['turns'].append({k: v for k, v in event.items() if k not in ('visible_content', 'operations')})
            for other, agent in agents.items():
                if other != unit:
                    agent.add_messages({'role': 'user', 'content': 'Peer observations in the shared worktree:\n' + json.dumps(event, ensure_ascii=False)})
                agent.save(agent.config.output_path)
            summary['completion'] = completion.snapshot()
            save_json(out / 'summary.json', summary)
            print(json.dumps({'run_id': stamp, 'turn': turn, 'unit': unit, 'tokens': budget.total_tokens,
                              'complete': completion.complete}), flush=True)
            if 0 < agents[unit].config.max_consecutive_format_errors <= agents[unit].n_consecutive_format_errors:
                raise ProtocolStop('repeated_format_error')
        summary['stop_reason'] = 'submitted'
    except ProtocolStop as error:
        summary['stop_reason'] = error.reason
    except LimitsExceeded as error:
        summary['stop_reason'] = error.messages[0].get('extra', {}).get('exit_status', 'mini_limit')
    except Exception as error:
        summary.update(stop_reason='runner_error', error=repr(error))
    finally:
        summary.update(total_recorded_tokens=budget.total_tokens, usage_complete=budget.usage_complete,
                       budget=budget.snapshot())
        for agent in agents.values():
            agent.save(agent.config.output_path)
        if container is not None:
            try:
                summary.update(capture_artifact(container, task['base_commit'], out))
                summary['artifact_frozen_at'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
                summary['visible_checks'] = run_checks(container, config.get('visible_checks', []), out/'visible_checks',
                    config['max_wall_seconds'] - (time.monotonic()-started))
                after_dir = out / 'after_visible_checks'
                after_dir.mkdir()
                after = capture_artifact(container, task['base_commit'], after_dir)
                summary['visible_checks_changed_artifact'] = after['artifact_sha256'] != summary['artifact_sha256']
            except Exception as error:
                summary['finalization_error'] = repr(error)
            finally:
                try:
                    container.remove(force=True)
                    summary['container_removed'] = True
                except Exception as error:
                    summary['cleanup_error'] = repr(error)
        summary['wall_seconds'] = time.monotonic()-started
        save_json(out / 'summary.json', summary)
        print(json.dumps({'path': str(out), 'stop_reason': summary['stop_reason'],
                          'tokens': budget.total_tokens, 'seconds': summary['wall_seconds']}), flush=True)
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', required=True)
    parser.add_argument('--strategy', required=True, choices=['single', 'fixed_pair'])
    args = parser.parse_args()
    signal.signal(signal.SIGALRM, alarm_handler)
    result = run(json.loads((ROOT / args.config).read_text()), args.strategy)
    raise SystemExit(0 if result.get('artifact_sha256') and result['usage_complete'] and not result.get('finalization_error') else 1)
