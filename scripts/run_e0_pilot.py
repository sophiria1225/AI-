"""Bounded, exploratory single / fixed-pair runner. Never reads private_eval."""
import argparse
import datetime
import hashlib
import json
import pathlib
import signal
import time
import urllib.request
import uuid

import docker

from container_policy import POLICY, create_task_container
from artifact_capture import capture_artifact

ROOT = pathlib.Path(__file__).resolve().parents[1]
TASK_ENV = {
    'PATH': '/opt/miniconda3/envs/testbed/bin:/opt/miniconda3/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin',
    'CONDA_PREFIX': '/opt/miniconda3/envs/testbed', 'CONDA_DEFAULT_ENV': 'testbed',
    'BASH_ENV': '', 'PAGER': 'cat', 'MANPAGER': 'cat', 'PIP_PROGRESS_BAR': 'off',
}
TOOLS = [
    {'type': 'function', 'function': {
        'name': 'run_command',
        'description': 'Run a shell command in the isolated repository at /testbed. Read, edit and run visible tests. The conda testbed environment is activated. No external network. Output may be truncated; narrow a query if needed.',
        'parameters': {'type': 'object', 'properties': {'command': {'type': 'string'}}, 'required': ['command']}}},
    {'type': 'function', 'function': {
        'name': 'submit_result',
        'description': 'Declare your work complete and summarize changes, tests and remaining limitations. The current repository diff is the submitted artifact. Use only after inspecting and verifying your work.',
        'parameters': {'type': 'object', 'properties': {'summary': {'type': 'string'}}, 'required': ['summary']}}},
]
COMMON = '''You are resolving a real repository issue. Inspect the repository, implement a correct general solution, and run relevant visible tests. You have run_command to search, read, edit and execute in /testbed, plus submit_result. You can keep external working notes under /tmp or .harness_notes. All repository files are accessible. No internet or hidden evaluation results are available. Preserve existing behavior and unrelated files. Avoid committing changes. The current diff is the final deliverable. Tool calls are not a substitute for checking their outputs. A plain text answer does not submit; use submit_result when ready. Resources and remaining budgets are shown. Tool output is bounded; use targeted searches. Tool failures consume time and must be handled.'''
ROLES = {
    'single': COMMON + '\nYou own investigation, implementation and independent visible checks for the entire issue.',
    'implementer': COMMON + '\nYou are the implementation worker in a fixed two-worker team. Investigate and implement the requested behavior. A validation worker alternates with you in the same worktree. You both have full read/write/test access. Review the other worker\'s latest observations before changes. Explain unresolved interface choices and useful evidence; do not just repeat work. Submit when your implementation and checks are ready.',
    'validator': COMMON + '\nYou are the validation worker in a fixed two-worker team. Independently examine requirements, related code and visible tests. Reproduce defects, identify regressions and verify the current changes. You may add tests or fix issues yourself; you have the same full access. An implementation worker alternates in the same worktree. Communicate concrete evidence and unresolved problems. Submit only when the current result is ready from your perspective.',
}


def save_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def alarm_handler(signum, frame):
    raise TimeoutError('model wall-clock call limit')


def input_bound(messages, previous=None):
    """Measured unchanged prefix plus a conservative bound on the new suffix.

    The template reserve is empirical, not a tokenizer equivalence proof.
    Actual usage is always checked separately.
    """
    if previous is None:
        return len(json.dumps({'messages': messages, 'tools': TOOLS}, ensure_ascii=False).encode()) + 4096
    prefix_length, prefix_tokens, prefix_hash = previous
    prefix = json.dumps(messages[:prefix_length], ensure_ascii=False).encode()
    if hashlib.sha256(prefix).hexdigest() != prefix_hash:
        raise RuntimeError('previously measured message prefix changed')
    return prefix_tokens + len(json.dumps(messages[prefix_length:], ensure_ascii=False).encode()) + 4096


def model_call(config, messages, out, remaining_wall, tools=None):
    payload = {
        'model': config['model'], 'messages': messages, 'tools': TOOLS if tools is None else tools,
        'stream': True, 'think': config['think'], 'keep_alive': '2m',
        'options': {key: config[key] for key in ['num_ctx', 'num_predict', 'temperature', 'seed']},
    }
    save_json(out / 'request.json', payload)
    record = {'status': 'error', 'input_tokens': None, 'output_tokens': None}
    message = {'role': 'assistant', 'content': ''}
    started = time.monotonic()
    signal.alarm(max(1, min(config['call_timeout_seconds'], int(remaining_wall))))
    try:
        request = urllib.request.Request(
            'http://127.0.0.1:11434/api/chat', data=json.dumps(payload).encode(),
            headers={'Content-Type': 'application/json'})
        terminal = None
        with urllib.request.urlopen(request, timeout=config['call_timeout_seconds']) as response, (out / 'events.jsonl').open('w') as events:
            for line in response:
                event = json.loads(line)
                events.write(json.dumps(event, ensure_ascii=False) + '\n')
                events.flush()
                if 'error' in event:
                    raise RuntimeError(event['error'])
                part = event.get('message', {})
                message['content'] += part.get('content', '')
                if part.get('thinking'):
                    message['thinking'] = message.get('thinking', '') + part['thinking']
                if part.get('tool_calls'):
                    message.setdefault('tool_calls', []).extend(part['tool_calls'])
                if event.get('done'):
                    terminal = event
                    break
        if terminal is None:
            raise RuntimeError('missing terminal usage')
        if any(not isinstance(terminal.get(k), int) for k in ['prompt_eval_count', 'eval_count']):
            raise RuntimeError('missing token counters')
        record.update(status='ok', input_tokens=terminal['prompt_eval_count'],
                      output_tokens=terminal['eval_count'],
                      cached_input_tokens=terminal.get('prompt_eval_cached_count'),
                      done_reason=terminal.get('done_reason'),
                      timing_nanoseconds={k: terminal.get(k) for k in ['total_duration', 'load_duration', 'prompt_eval_duration', 'eval_duration']})
    except Exception as error:
        record['error'] = repr(error)
    finally:
        signal.alarm(0)
        record['wall_seconds'] = time.monotonic() - started
        record['message'] = message
        save_json(out / 'response.json', record)
    return record


def tool_command(container, command, config, out, remaining_wall):
    started = time.monotonic()
    timeout = max(1, min(config['tool_timeout_seconds'], int(remaining_wall)))
    shell = 'set -o pipefail\ntest -x /opt/miniconda3/envs/testbed/bin/python || exit 125\n' + command
    record = {'command': command, 'timeout_seconds': timeout, 'environment': TASK_ENV,
              'setup_method': 'explicit_environment_path', 'pipefail': True}
    try:
        exec_id = container.client.api.exec_create(container.id,
            ['timeout', '--signal=TERM', '--kill-after=2s', str(timeout), '/bin/bash', '-c', shell],
            workdir='/testbed', environment=TASK_ENV)['Id']
        output_stream = container.client.api.exec_start(exec_id, stream=True)
        kept = bytearray()
        total_bytes = 0
        with (out / 'output.bin').open('wb') as f:
            for chunk in output_stream:
                total_bytes += len(chunk)
                if len(kept) < 8 * 1024 * 1024:
                    part = chunk[:8 * 1024 * 1024 - len(kept)]
                    kept.extend(part)
                    f.write(part)
        execution = container.client.api.exec_inspect(exec_id)
        exit_code = execution.get('ExitCode')
        text = kept.decode('utf-8', errors='replace')
        limit = config['max_visible_tool_characters']
        if len(text) > limit:
            text = text[:limit//2] + '\n[output truncated]\n' + text[-limit//2:]
        record.update(exit_code=exit_code, captured_bytes=len(kept),
                      total_bytes=total_bytes, output=text, exit_code_known=exit_code is not None,
                      timed_out=exit_code in [124, 137], running=execution.get('Running'))
    except Exception as error:
        record.update(error=repr(error), output='Tool execution failed: ' + repr(error), exit_code=None, exit_code_known=False)
    record['wall_seconds'] = time.monotonic() - started
    save_json(out / 'result.json', record)
    return record


def verify_task_environment(container):
    code = "import sys,json,django; assert sys.prefix == '/opt/miniconda3/envs/testbed'; print(json.dumps({'prefix':sys.prefix,'python':sys.version.split()[0],'django':django.get_version()}))"
    result = container.exec_run(['python', '-c', code], environment=TASK_ENV, workdir='/testbed')
    if result.exit_code != 0:
        raise RuntimeError('task environment preflight failed: ' + result.output.decode(errors='replace'))
    return json.loads(result.output)


def run(strategy, config):
    tasks = (json.loads(line) for line in (ROOT / 'data/verified_public_inputs.jsonl').read_text().splitlines())
    task = next(item for item in tasks if item['instance_id'] == config['instance_id'])
    if set(task) - {'repo', 'instance_id', 'base_commit', 'problem_statement', 'created_at', 'version', 'environment_setup_commit'}:
        raise RuntimeError('Unexpected model input columns')
    with urllib.request.urlopen('http://127.0.0.1:11434/api/tags', timeout=10) as response:
        models = json.load(response)['models']
    model = next(item for item in models if item['name'] == config['model'])
    if model['digest'] != config['model_digest']:
        raise RuntimeError('model digest changed')
    stamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S') + '_' + strategy + '_' + uuid.uuid4().hex[:6]
    out = ROOT / 'records/e0' / stamp
    out.mkdir(parents=True)
    (out / 'runner_snapshot.py').write_bytes(pathlib.Path(__file__).read_bytes())
    (out / 'container_policy_snapshot.py').write_bytes((ROOT / 'scripts/container_policy.py').read_bytes())
    (out / 'artifact_capture_snapshot.py').write_bytes((ROOT / 'scripts/artifact_capture.py').read_bytes())
    save_json(out / 'config.json', config)
    save_json(out / 'public_task.json', task)
    roles = ['single'] if strategy == 'single' else ['implementer', 'validator']
    histories = {role: [{'role': 'system', 'content': ROLES[role]}, {'role': 'user', 'content': 'Resolve this issue in the existing repository:\n' + task['problem_statement']}] for role in roles}
    submitted = {role: False for role in roles}
    previous_inputs = {role: None for role in roles}
    summary = {'run_id': stamp, 'strategy': strategy, 'instance_id': task['instance_id'],
               'started_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
               'container_policy': POLICY, 'calls': [], 'tools': [], 'usage_complete': True,
               'source_sha256': hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest()}
    started = time.monotonic()
    client = docker.from_env(timeout=60)
    container = None
    total_tokens = 0
    try:
        container = create_task_container(client, config['image'], 'harness_agent_' + stamp)
        container.start()
        summary['container_id'] = container.id
        summary['task_environment'] = verify_task_environment(container)
        check = container.exec_run(['git', 'diff', '--exit-code', task['base_commit'], '--'], workdir='/testbed')
        if check.exit_code != 0:
            raise RuntimeError('image worktree differs from task base')
        inspect = container.exec_run(['/bin/bash', '-c', 'git rev-parse HEAD; git rev-parse HEAD^{tree}; git remote -v; git status --porcelain; find / -maxdepth 2 -iname "*patch*" 2>/dev/null'], workdir='/testbed')
        (out / 'initial_repository.txt').write_bytes(inspect.output)
        summary['stop_reason'] = 'call_limit'
        for call_number in range(config['max_calls']):
            role = roles[call_number % len(roles)]
            if time.monotonic() - started >= config['max_wall_seconds']:
                summary['stop_reason'] = 'wall_limit'
                break
            histories[role].append({'role': 'user', 'content': f"Budget: {config['max_calls'] - call_number} model calls and {config['max_total_tokens'] - total_tokens} total logical tokens left across all workers. Elapsed {time.monotonic() - started:.1f}s. Current role: {role}."})
            upper_estimate = input_bound(histories[role], previous_inputs[role])
            if upper_estimate + config['num_predict'] > min(config['num_ctx'], config['max_total_tokens'] - total_tokens):
                summary.update(stop_reason='conservative_budget_guard', next_input_bound=upper_estimate)
                break
            call_dir = out / f'call_{call_number + 1:03d}_{role}'
            call_dir.mkdir()
            response = model_call(config, histories[role], call_dir, config['max_wall_seconds'] - (time.monotonic() - started))
            response['precall_input_bound'] = upper_estimate
            summary['calls'].append({k: v for k, v in response.items() if k != 'message'} | {'role': role, 'path': call_dir.name})
            if response['status'] != 'ok':
                summary.update(stop_reason='model_error', usage_complete=False)
                break
            previous_inputs[role] = (
                len(histories[role]), response['input_tokens'],
                hashlib.sha256(json.dumps(histories[role], ensure_ascii=False).encode()).hexdigest())
            total_tokens += response['input_tokens'] + response['output_tokens']
            if response.get('done_reason') == 'length':
                summary['stop_reason'] = 'generation_limit_incomplete_response'
                break
            if total_tokens > config['max_total_tokens']:
                summary['stop_reason'] = 'measured_token_limit_exceeded'
                break
            message = response['message']
            histories[role].append(message)
            shared = [{'role': role, 'content': message.get('content', '')}]
            requests = message.get('tool_calls', [])
            for tool_number, request in enumerate(requests):
                name = request.get('function', {}).get('name')
                arguments = request.get('function', {}).get('arguments', {})
                if not isinstance(arguments, dict):
                    result = {'error': 'tool arguments must be an object'}
                elif tool_number >= 8:
                    result = {'error': 'too many tools in one response'}
                elif name == 'run_command' and isinstance(arguments.get('command'), str):
                    submitted[role] = False
                    tool_dir = call_dir / f'tool_{tool_number + 1:02d}'
                    tool_dir.mkdir()
                    remaining = config['max_wall_seconds'] - (time.monotonic() - started)
                    if remaining <= 0:
                        result = {'error': 'wall budget exhausted'}
                    else:
                        result = tool_command(container, arguments['command'], config, tool_dir, remaining)
                        summary['tools'].append({k: v for k, v in result.items() if k not in ['command', 'output']} | {'role': role, 'path': str(tool_dir.relative_to(out))})
                elif name == 'submit_result' and isinstance(arguments.get('summary'), str):
                    submitted[role] = True
                    result = {'submitted': True, 'summary': arguments['summary']}
                else:
                    result = {'error': 'unknown or malformed tool'}
                reply = {'role': 'tool', 'tool_name': name or 'unknown', 'content': json.dumps(result, ensure_ascii=False)}
                if request.get('id'):
                    reply['tool_call_id'] = request['id']
                histories[role].append(reply)
                shared.append({'tool': name, 'arguments': arguments, 'result': result})
            for other in roles:
                if other != role:
                    histories[other].append({'role': 'user', 'content': 'Other worker update in the shared worktree:\n' + json.dumps(shared, ensure_ascii=False)})
            summary.update(total_recorded_tokens=total_tokens, wall_seconds=time.monotonic() - started)
            save_json(out / 'summary.json', summary)
            print(json.dumps({'run_id': stamp, 'call': call_number + 1, 'role': role,
                              'tokens': total_tokens, 'tools': [r.get('function', {}).get('name') for r in requests]}), flush=True)
            if all(submitted.values()):
                summary['stop_reason'] = 'submitted'
                break
        # Include new source/tests without modifying the contents. Working notes
        # are permitted but not submitted as repository changes.
        summary.update(capture_artifact(container, task['base_commit'], out))
        summary['artifact_frozen_at'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    except Exception as error:
        summary.update(stop_reason='runner_error', error=repr(error))
    finally:
        if container is not None:
            try:
                container.remove(force=True)
                summary['container_removed'] = True
            except Exception as error:
                summary['cleanup_error'] = repr(error)
        summary.update(total_recorded_tokens=total_tokens, wall_seconds=time.monotonic() - started,
                       submitted=submitted)
        save_json(out / 'summary.json', summary)
        print(json.dumps({'path': str(out), 'stop_reason': summary['stop_reason'],
                          'tokens': total_tokens, 'wall_seconds': summary['wall_seconds']}), flush=True)
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--strategy', choices=['single', 'fixed_pair'], required=True)
    parser.add_argument('--config', default='configs/E0_pilot_v02.json')
    args = parser.parse_args()
    signal.signal(signal.SIGALRM, alarm_handler)
    config = json.loads((ROOT / args.config).read_text())
    result = run(args.strategy, config)
    raise SystemExit(0 if result.get('artifact_sha256') and result['usage_complete'] else 1)
