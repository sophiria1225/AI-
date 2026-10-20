"""Execute one frozen Pro development trial with the shared agent and ledger."""
import argparse
import datetime
import json
from pathlib import Path
import signal
import subprocess
import time
import urllib.request
import docker

from pro_runtime import ROOT, POLICY, sha, load_public_task, task_text, require_controls, create_container
from repository_runtime import runtime_for
from run_fixed_comparison import (
    MINI_COMMIT, DefaultAgent, SharedModel, SharedEnvironment, templates_for,
    SharedBudget, CompletionState, ProtocolStop, LimitsExceeded,
    run_turn, capture_artifact, run_checks, save_json, alarm_handler,
)
from model_provenance import check_live_model
from audit_p2 import audit_run
from audit_p3 import audit_protocol


class ProEnvironment(SharedEnvironment):
    def serialize(self):
        return {'info': {'container_policy': POLICY,
                         'environment_adapter': 'pro_shared_public_worktree'}}


def prepare(plan_path, storage):
    plan = json.loads(plan_path.read_text())
    if plan.get('trial_count') != 1 or plan.get('strategy') != 'single':
        raise ValueError('This plan allows exactly one single-agent development trial')
    for path, expected in plan['config_sha256'].items():
        if sha(ROOT / path) != expected:
            raise ValueError('Frozen configuration changed: ' + path)
    for name, expected in plan['source_sha256'].items():
        if sha(ROOT / 'scripts' / name) != expected:
            raise ValueError('Frozen source changed: ' + name)
    config = json.loads((ROOT / plan['config']).read_text())
    if (config['phase'] != 'P4' or config['backend'] != 'llama.cpp'
            or config['max_calls'] != plan['max_model_calls']
            or config['max_total_tokens'] != plan['max_total_input_output_tokens']
            or config['max_wall_seconds'] != plan['max_wall_seconds']):
        raise ValueError('Model configuration and plan differ')
    require_controls(storage, config)
    calibrated = storage / plan['runtime_calibration']['record']
    if sha(calibrated) != plan['runtime_calibration']['sha256']:
        raise ValueError('Runtime calibration record changed')
    proof = json.loads(calibrated.read_text())
    if proof['status'] != 'completed' or not proof.get('container_removed'):
        raise ValueError('Public runtime did not complete')
    for name, digest in proof['source_sha256'].items():
        if sha(ROOT / 'scripts' / name) != digest:
            raise ValueError('Runtime code differs from the live calibration: ' + name)
    runtime_config = json.loads(calibrated.with_name('config.json').read_text())
    for key in ('instance_id', 'base_commit', 'image', 'repository_runtime', 'visible_checks',
                'public_inputs', 'public_inputs_sha256'):
        if config[key] != runtime_config[key]:
            raise ValueError('Pilot differs from public calibration: ' + key)
    task = load_public_task(storage, config)
    vendor = storage / 'vendor/mini-swe-agent'
    import minisweagent
    if not Path(minisweagent.__file__).resolve().is_relative_to(vendor.resolve()):
        raise ValueError('Imported mini-swe-agent differs from the pinned checkout')
    if (subprocess.check_output(['git', '-C', str(vendor), 'rev-parse', 'HEAD'], text=True).strip() != MINI_COMMIT
            or subprocess.check_output(['git', '-C', str(vendor), 'status', '--porcelain'])):
        raise ValueError('Pinned agent checkout changed')
    return plan, config, task, vendor


def execute(plan_path, storage):
    plan, config, task, vendor = prepare(plan_path, storage)
    out = storage / 'records/pro_pilot' / plan['trial_id']
    out.mkdir(parents=True, exist_ok=False)  # A failed start also consumes this ID.
    (out / 'plan.json').write_bytes(plan_path.read_bytes())
    save_json(out / 'config.json', config)
    save_json(out / 'public_task.json', task)
    summary = {
        'run_id': plan['trial_id'], 'phase': 'P4', 'strategy': 'single',
        'instance_id': task['instance_id'], 'model': config['model'],
        'mini_commit': MINI_COMMIT, 'plan_sha256': sha(plan_path),
        'source_hashes': plan['source_sha256'], 'calls': [], 'tools': [], 'turns': [],
        'started_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'usage_complete': True, 'total_recorded_tokens': 0, 'stop_reason': 'initializing',
        'container_policy': POLICY,
    }
    for name in plan['source_sha256']:
        (out / name).write_bytes((ROOT / 'scripts' / name).read_bytes())
    save_json(out / 'summary.json', summary)
    started = time.monotonic()
    budget = SharedBudget(**{k: config[k] for k in (
        'max_calls', 'max_total_tokens', 'num_ctx', 'num_predict', 'max_wall_seconds')})
    runtime = runtime_for(config, {})
    options = {'workdir': runtime['workdir'], 'python_path': runtime['python']}
    agent = container = None
    try:
        with urllib.request.urlopen(config['base_url'] + '/props', timeout=10) as response:
            props = json.load(response)
        server = json.loads((storage / '.runtime/model_server.json').read_text())
        selection, download, path = check_live_model(
            config['model_selection'], server, props, config['num_ctx'], root=storage,
            expected_cache=(config['cache_type_k'], config['cache_type_v']))
        if (path.resolve() != (storage / config['model_path']).resolve()
                or selection['model_alias'] != config['model']
                or selection['revision'] != config['model_revision']):
            raise ValueError('Model identity differs from the fixed conditions')
        for name, data in (('server_props', props), ('server_runtime', server),
                           ('model_selection', selection), ('model_download_record', download)):
            save_json(out / (name + '.json'), data)
        client = docker.from_env(timeout=60)
        if client.containers.list():
            raise ValueError('Research VM already has an active container')
        container = create_container(client, config, 'harness_pro_pilot')
        summary['container_id'] = container.id
        initial_dir = out / 'artifact_versions/initial'
        initial_dir.mkdir(parents=True)
        initial = capture_artifact(container, task['base_commit'], initial_dir, **options)
        completion = CompletionState(('single',), initial['artifact_sha256'])
        env = ProEnvironment(container, config, out, summary, started)
        templates = templates_for(config, 'single', False, vendor=vendor)
        save_json(out / 'unit_templates.json', {'single': templates})
        model = SharedModel(config, templates['model'], out, summary, started, budget)
        agent = DefaultAgent(model, env, **templates['agent'], output_path=out/'trajectory_single.json')
        agent.extra_template_vars['task'] = task_text(task)
        agent.add_messages(
            {'role': 'system', 'content': agent._render_template(agent.config.system_template)},
            {'role': 'user', 'content': agent._render_template(agent.config.instance_template)})
        turn = 0
        while not completion.complete:
            turn += 1
            event = run_turn(agent, env, completion, out, task['base_commit'], turn, artifact_options=options)
            summary['turns'].append({k: v for k, v in event.items() if k not in ('visible_content', 'operations')})
            agent.save(agent.config.output_path)
            summary['completion'] = completion.snapshot()
            save_json(out / 'summary.json', summary)
            print(json.dumps({'trial': plan['trial_id'], 'turn': turn,
                              'tokens': budget.total_tokens, 'complete': completion.complete}), flush=True)
            if 0 < agent.config.max_consecutive_format_errors <= agent.n_consecutive_format_errors:
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
        if agent is not None:
            agent.save(agent.config.output_path)
        if container is not None:
            try:
                summary.update(capture_artifact(container, task['base_commit'], out, **options))
                summary['artifact_frozen_at'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
                summary['visible_checks'] = run_checks(
                    container, config['visible_checks'], out/'visible_checks',
                    config['max_wall_seconds'] - (time.monotonic()-started),
                    workdir=runtime['workdir'], environment=runtime['environment'])
                after_dir = out / 'after_visible_checks'
                after_dir.mkdir()
                after = capture_artifact(container, task['base_commit'], after_dir, **options)
                summary['visible_checks_changed_artifact'] = after['artifact_sha256'] != summary['artifact_sha256']
            except Exception as error:
                summary['finalization_error'] = repr(error)
            finally:
                try:
                    container.remove(force=True)
                    summary['container_removed'] = True
                except Exception as error:
                    summary['cleanup_error'] = repr(error)
        summary['wall_seconds'] = time.monotonic() - started
        save_json(out / 'summary.json', summary)
    try:
        audit = audit_run(out, root=storage)
        audit['errors'] += audit_protocol(out)
        save_json(out / 'audit.json', audit)
        summary['audit_errors'] = audit['errors']
    except Exception as error:
        summary['audit_errors'] = ['Audit could not finish: ' + repr(error)]
    summary['execution_status'] = 'completed' if (
        not summary['audit_errors'] and summary.get('container_removed')
        and summary['usage_complete'] and not any(summary.get(k) for k in
        ('error', 'cleanup_error', 'finalization_error'))) else 'error'
    save_json(out / 'summary.json', summary)
    print(json.dumps({'record': str(out), 'status': summary['execution_status'],
                      'stop_reason': summary['stop_reason'], 'tokens': budget.total_tokens}), flush=True)
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--storage-root', type=Path, required=True)
    parser.add_argument('--plan', type=Path, required=True)
    args = parser.parse_args()
    signal.signal(signal.SIGALRM, alarm_handler)
    plan_path = (ROOT / args.plan).resolve()
    if not plan_path.is_relative_to(ROOT / 'configs'):
        raise ValueError('Plan must be inside repository configs')
    result = execute(plan_path, args.storage_root.resolve())
    raise SystemExit(0 if result['execution_status'] == 'completed' else 1)
