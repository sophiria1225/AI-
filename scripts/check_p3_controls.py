"""Real isolated tools with scripted model responses: wiring, not model quality."""
import datetime
import hashlib
import json
from pathlib import Path
import signal
import time
from unittest.mock import patch
import uuid

from run_fixed_comparison import (
    ROOT, SharedModel, SharedEnvironment, DefaultAgent, run_turn, templates_for,
    create_task_container, verify_task_environment, save_json, alarm_handler,
)
from experiment_state import SharedBudget, CompletionState
import docker


def main():
    stamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S') + '_' + uuid.uuid4().hex[:6]
    out = ROOT / 'records/p3_controls' / stamp
    out.mkdir(parents=True)
    config = json.loads((ROOT / 'configs/P2_minimax_15957.json').read_text()) | {
        'phase': 'P3_control_fixture', 'max_calls': 5, 'max_total_tokens': 4000,
        'num_ctx': 2048, 'num_predict': 200, 'max_wall_seconds': 180}
    task = next(json.loads(line) for line in (ROOT/'data/verified_public_inputs.jsonl').read_text().splitlines()
                if json.loads(line)['instance_id'] == config['instance_id'])
    record = {'scope': 'scripted responses plus real container tools; not a model-quality experiment',
              'actual_model_requests': 0, 'synthetic_usage_per_response': {'input': 100, 'output': 20},
              'started_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'checks': {}, 'calls': [], 'tools': [], 'usage_complete': True, 'run_id': stamp}
    sources = ['check_p3_controls.py', 'run_fixed_comparison.py', 'experiment_state.py',
               'run_mini_pilot.py', 'run_e0_pilot.py', 'artifact_capture.py', 'container_policy.py']
    record['source_hashes'] = {}
    for name in sources:
        source = (ROOT/'scripts'/name).read_bytes()
        (out/name).write_bytes(source)
        record['source_hashes'][name] = hashlib.sha256(source).hexdigest()
    save_json(out/'config.json', config)
    client = docker.from_env(timeout=60)
    container = create_task_container(client, config['image'], 'harness_p3_control_' + stamp)
    started = time.monotonic()
    try:
        container.start()
        record['environment'] = verify_task_environment(container)
        budget = SharedBudget(**{k: config[k] for k in ('max_calls', 'max_total_tokens', 'num_ctx', 'num_predict', 'max_wall_seconds')})
        model = SharedModel(config, templates_for(config, 'single', False)['model'], out, record, started, budget)
        env = SharedEnvironment(container, config, out, record, started)
        state = CompletionState(('implementation', 'validation'), hashlib.sha256(b'').hexdigest())
        agents = {}
        for unit in state.units:
            agent = DefaultAgent(model, env, system_template='Control fixture.', instance_template='Control fixture.', step_limit=0)
            agent.messages = [{'role': 'system', 'content': 'Control fixture.'}, {'role': 'user', 'content': 'Control fixture.'}]
            agents[unit] = agent
        commands = ["printf 'VALUE = 1\\n' > p3_control_fixture.py",
                    'echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT',
                    "printf 'VALUE = 2\\n' > p3_control_fixture.py",
                    'echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT',
                    'echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT']
        def answer(cfg, messages, directory, left, tools):
            command = commands[budget.calls-1]
            response = {'status': 'ok', 'input_tokens': 100, 'output_tokens': 20, 'done_reason': 'tool_calls',
                        'message': {'role': 'assistant', 'content': 'Scripted control action.',
                                    'tool_calls': [{'id': f'fixture{budget.calls}', 'function':
                                                    {'name': 'bash', 'arguments': {'command': command}}}]}}
            save_json(directory/'fixture_request.json', {'fixture': True, 'messages': messages})
            save_json(directory/'fixture_response.json', response)
            return response
        events = []
        with patch('run_fixed_comparison.local_llama.count_input', return_value={'input_tokens': 100, 'method': 'CONTROL_FIXTURE_NOT_TOKENIZER'}), \
             patch('run_fixed_comparison.local_llama.model_call', side_effect=answer):
            for n, unit in enumerate(('implementation', 'validation', 'implementation', 'validation', 'implementation'), 1):
                model.unit = env.unit = unit
                event = run_turn(agents[unit], env, state, out, task['base_commit'], n)
                events.append(event)
                for other in state.units:
                    if other != unit:
                        agents[other].add_messages({'role': 'user', 'content': json.dumps(event)})
        record['checks'] = {
            'five_real_tools_completed': len(record['tools']) == 5 and all(o['result']['returncode'] == 0 for e in events for o in e['operations']),
            'first_vote_retained_for_unchanged_artifact': events[1]['artifact']['votes'] == {'validation': events[0]['artifact']['artifact_sha256']},
            'new_artifact_invalidates_first_vote': events[2]['artifact_changed'] and events[2]['artifact']['votes'] == {},
            'no_early_team_completion': all(not e['artifact']['complete'] for e in events[:-1]),
            'both_vote_on_same_final_artifact': state.complete,
            'one_shared_synthetic_ledger': budget.calls == 5 and budget.total_tokens == 600,
            'operation_and_artifact_records_exist': all((out/'artifact_versions'/f'{n:03d}'/'final.patch').is_file() for n in range(1, 6)),
        }
        record['final_completion'] = state.snapshot()
    except Exception as error:
        record['error'] = repr(error)
    finally:
        try:
            container.remove(force=True)
            record['container_removed'] = True
        except Exception as error:
            record['cleanup_error'] = repr(error)
        record['wall_seconds'] = time.monotonic()-started
        save_json(out/'summary.json', record)
        print(json.dumps({'path': str(out), 'checks': record['checks'], 'error': record.get('error'),
                          'container_removed': record.get('container_removed')}), flush=True)
    return bool(record['checks']) and all(record['checks'].values()) and not record.get('error') and record.get('container_removed')


if __name__ == '__main__':
    signal.signal(signal.SIGALRM, alarm_handler)
    raise SystemExit(0 if main() else 1)
