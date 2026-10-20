"""Rebuild public task inputs and private evaluator files from pinned sources."""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import urllib.request

import pyarrow.parquet as pq
import yaml

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ['repo', 'instance_id', 'base_commit', 'problem_statement', 'created_at',
          'version', 'environment_setup_commit']


def write_unless_equal(path, values, lines=False, private=False):
    if path.exists():
        old = [json.loads(x) for x in path.read_text().splitlines()] if lines else json.loads(path.read_text())
        if old != values:
            raise ValueError('existing data differs and is preserved: ' + str(path.name))
        return 'verified_existing'
    if not path.resolve().is_relative_to(ROOT):
        raise ValueError('new data would traverse an external symlink')
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x') as stream:
        if private:
            path.chmod(0o600)
        if lines:
            stream.write(''.join(json.dumps(v, ensure_ascii=False) + '\n' for v in values))
        else:
            stream.write(json.dumps(values, ensure_ascii=False, indent=2) + '\n')
    return 'created'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--destination', default='.')
    parser.add_argument('--parquet-cache')
    parser.add_argument('--pull-images', action='store_true')
    args = parser.parse_args()
    destination = (ROOT / args.destination).resolve()
    if not destination.is_relative_to(ROOT):
        raise ValueError('destination must be inside repository')
    dependencies = json.loads((ROOT / 'configs/dependencies.json').read_text())
    pin = dependencies['dataset']
    source_pin = next(x for x in dependencies['repositories'] if x['directory'] == 'vendor/swe-bench-tasks')
    source_repo = ROOT / source_pin['directory']
    revision = subprocess.check_output(['git', '-C', str(source_repo), 'rev-parse', 'HEAD'], text=True).strip()
    dirty = subprocess.check_output(['git', '-C', str(source_repo), 'status', '--porcelain'])
    if revision != source_pin['commit'] or dirty:
        raise RuntimeError('task source checkout differs from pinned revision')
    tasks = json.loads((ROOT / 'configs/development_tasks.json').read_text())['tasks']
    out = ROOT / 'records/environment/data_bootstrap' / datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    out.mkdir(parents=True)
    (out / Path(__file__).name).write_bytes(Path(__file__).read_bytes())
    record = {'status': 'running', 'destination': args.destination, 'dataset_revision': pin['revision'],
              'public_columns': PUBLIC, 'tasks': [], 'error': None}
    try:
        raw = destination / 'private_eval/verified.parquet'
        if not raw.exists():
            if not raw.resolve().is_relative_to(ROOT):
                raise ValueError('new data would traverse an external symlink')
            raw.parent.mkdir(parents=True, exist_ok=True)
            raw.parent.chmod(0o700)
            partial = raw.with_suffix('.partial')
            if args.parquet_cache:
                shutil.copyfile(ROOT / args.parquet_cache, partial)
            else:
                url = f"https://huggingface.co/datasets/{pin['repo_id']}/resolve/{pin['revision']}/{pin['filename']}"
                with urllib.request.urlopen(url, timeout=60) as source, partial.open('wb') as target:
                    data = source.read(pin['bytes'] + 1)
                    target.write(data)
            partial.chmod(0o600)
            if partial.stat().st_size != pin['bytes'] or hashlib.sha256(partial.read_bytes()).hexdigest() != pin['private_parquet_sha256']:
                raise ValueError('download/cache does not match the dataset pin')
            partial.replace(raw)
        digest = hashlib.sha256(raw.read_bytes()).hexdigest()
        if digest != pin['private_parquet_sha256']:
            raise ValueError('existing dataset differs from pin')
        rows = pq.read_table(raw).to_pylist()
        if len(rows) != pin['rows']:
            raise ValueError('dataset row count differs')
        record.update(dataset_sha256=digest, rows=len(rows))
        public = [{key: row[key] for key in PUBLIC} for row in rows]
        record['public_result'] = write_unless_equal(destination / 'data/verified_public_inputs.jsonl', public, lines=True)
        for selected in tasks:
            task = next(row for row in rows if row['instance_id'] == selected['instance_id'])
            source = ROOT / 'vendor/swe-bench-tasks/tasks' / selected['instance_id']
            reference = yaml.safe_load((source / 'task.yaml').read_text())
            checks = {key: reference[key] == task[key] for key in PUBLIC if key in reference}
            checks.update(gold_patch=task['patch'].strip() == (source / 'gold.patch').read_text().strip(),
                          test_patch=task['test_patch'].strip() == (source / 'test.patch').read_text().strip())
            labels = json.loads((source / 'tests.json').read_text())
            for key in ['FAIL_TO_PASS', 'PASS_TO_PASS']:
                expected = json.loads(task[key]) if isinstance(task[key], str) else task[key]
                checks[key] = set(expected) == set(labels[key])
                reference[key] = expected
            if not all(checks.values()):
                raise ValueError('pinned task sources disagree: ' + selected['instance_id'])
            for key in ['patch', 'test_patch', 'problem_statement', 'hints_text']:
                reference[key] = task[key]
            reference.update(image=selected['image'], eval_script=(source / 'eval.sh').read_text())
            result = write_unless_equal(destination / 'private_eval' / selected['private_filename'], [reference], private=True)
            record['tasks'].append({'instance_id': selected['instance_id'], 'checks': checks, 'result': result})
        if args.pull_images:
            import docker
            client = docker.from_env(timeout=120)
            for selected in tasks:
                for event in client.api.pull(selected['image'], stream=True, decode=True):
                    if 'error' in event:
                        raise RuntimeError('pinned image pull failed')
        record['status'] = 'prepared'
    except Exception as error:
        record.update(status='failed', error=repr(error))
    finally:
        (out / 'summary.json').write_text(json.dumps(record, indent=2) + '\n')
        print(json.dumps({'record': str(out.relative_to(ROOT)), **record}), flush=True)
    return record['status'] == 'prepared'


if __name__ == '__main__':
    raise SystemExit(0 if main() else 1)
