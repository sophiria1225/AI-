"""Run the predeclared visible test groups on pristine development task images."""
import datetime
import hashlib
import json
from pathlib import Path
import docker

from container_policy import create_task_container
from run_e0_pilot import verify_task_environment
from visible_checks import run_checks

ROOT = Path(__file__).resolve().parents[1]


def main():
    plan_path = ROOT / 'configs/P2_visible_checks.json'
    plan = json.loads(plan_path.read_text())
    stamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    root = ROOT / 'records/p2_public_baselines' / stamp
    root.mkdir(parents=True)
    tasks = [json.loads(line) for line in (ROOT / 'data/verified_public_inputs.jsonl').read_text().splitlines()]
    client = docker.from_env(timeout=60)
    rows = []
    for suffix in ('15380', '15957'):
        config = json.loads((ROOT / f'configs/P1_small_{suffix}.json').read_text())
        task = next(t for t in tasks if t['instance_id'] == config['instance_id'])
        container = create_task_container(client, config['image'], 'harness_visible_base_' + suffix)
        out = root / task['instance_id']
        out.mkdir()
        try:
            container.start()
            environment = verify_task_environment(container)
            base = container.exec_run(['git', 'rev-parse', 'HEAD'], workdir='/testbed')
            head_tree = container.exec_run(['git', 'rev-parse', 'HEAD^{tree}'], workdir='/testbed')
            expected_tree = container.exec_run(['git', 'rev-parse', task['base_commit'] + '^{tree}'], workdir='/testbed')
            diff = container.exec_run(['git', 'diff', '--exit-code', task['base_commit'], '--'], workdir='/testbed')
            clean = container.exec_run(['git', 'status', '--porcelain'], workdir='/testbed')
            if (any(v.exit_code for v in (base, head_tree, expected_tree, diff, clean)) or
                    head_tree.output != expected_tree.output or clean.output.strip()):
                raise RuntimeError('public task source tree/worktree mismatch')
            result = run_checks(container, plan[task['instance_id']], out / 'checks', 200)
            row = {'instance_id': task['instance_id'], 'base_commit': task['base_commit'],
                   'image_head': base.output.decode().strip(), 'source_tree': head_tree.output.decode().strip(),
                   'image': config['image'], 'environment': environment, **result}
            rows.append(row)
            print(json.dumps({'instance_id': task['instance_id'], 'all_passed': result['all_passed'],
                              'wall_seconds': result['wall_seconds']}), flush=True)
        except Exception as error:
            (out / 'failure.json').write_text(json.dumps({'error': repr(error),
                'instance_id': task['instance_id'], 'phase': 'visible_baseline'}, indent=2) + '\n')
            raise
        finally:
            container.remove(force=True)
    summary = {'scope': 'visible pre-change test groups; no model and no hidden test injection',
               'plan_sha256': hashlib.sha256(plan_path.read_bytes()).hexdigest(), 'tasks': rows}
    (root / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print('recorded ' + str(root), flush=True)


if __name__ == '__main__':
    main()
