"""Select a development packet by IDs before reading only public instructions."""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import re
import subprocess


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def select_ids(ids, excluded, count):
    if len(ids) != len(set(ids)) or any(not re.fullmatch(r'[0-9a-f]+_[1-9][0-9]*', x) for x in ids):
        raise ValueError('invalid or duplicate public task IDs')
    scenarios = sorted({x.rsplit('_', 1)[0] for x in ids} - set(excluded))
    selected = [s + '_1' for s in scenarios[:count]]
    if len(selected) != count or not set(selected) <= set(ids):
        raise ValueError('not enough distinct unseen scenarios with variant one')
    return selected


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--data-root', type=Path, required=True)
    parser.add_argument('--storage-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    plan = json.loads(args.plan.read_text())
    if plan['split'] != 'train' or plan['input_fields'] != ['instruction']:
        raise ValueError('only public train instructions are supported')
    ids_path = args.data_root / 'datasets/train.txt'
    ids = ids_path.read_text().splitlines()
    selected = select_ids(ids, plan['prior_instruction_exposed_scenarios'], plan['count'])
    # Keep the selected IDs before loading any corresponding task specification.
    private = args.storage_root / plan['private_packet']
    if not private.resolve().is_relative_to((args.storage_root / 'records/task_selection').resolve()):
        raise ValueError('packet must stay under ignored local selection records')
    private.mkdir(parents=True, exist_ok=False)
    (private / 'selected_ids.json').write_text(json.dumps(selected, indent=2) + '\n')
    (private / 'plan.json').write_bytes(args.plan.read_bytes())
    packet, rows = [], []
    for task_id in selected:
        source = args.data_root / 'tasks' / task_id / 'specs.json'
        instruction = json.loads(source.read_text())['instruction']
        if not isinstance(instruction, str):
            raise ValueError('public instruction must be text')
        packet.append({'task_id': task_id, 'instruction': instruction})
        rows.append({'task_id': task_id, 'scenario_id': task_id.rsplit('_', 1)[0],
                     'instruction_characters': len(instruction), 'spec_sha256': sha(source),
                     'instruction_sha256': hashlib.sha256(instruction.encode()).hexdigest()})
    (private / 'public_instruction_packet.json').write_text(
        json.dumps(packet, ensure_ascii=False, indent=2) + '\n')
    result = {'selected_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'plan_sha256': sha(args.plan), 'selector_sha256': sha(Path(__file__)),
              'train_id_file_sha256': sha(ids_path), 'train_task_ids': len(ids),
              'train_scenarios': len({x.rsplit('_', 1)[0] for x in ids}),
              'selected': rows, 'model_calls': 0, 'environment_requests': 0,
              'evaluator_accessed': False, 'solution_or_difficulty_accessed': False,
              'git_commit_before_instruction_read': subprocess.check_output(
                  ['git', 'rev-parse', 'HEAD'], text=True).strip(),
              'scope': plan['scope']}
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'selected_ids': selected, 'model_calls': 0, 'environment_requests': 0}))


if __name__ == '__main__':
    main()
