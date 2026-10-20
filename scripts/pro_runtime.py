"""Public inputs and offline execution for the fixed Pro development candidate."""
import hashlib
import json
from pathlib import Path
import uuid

from prepare_pro_environment import validate_image
from repository_runtime import runtime_for

ROOT = Path(__file__).resolve().parents[1]
PUBLIC_FIELDS = {
    'repo', 'instance_id', 'base_commit', 'problem_statement', 'requirements',
    'interface', 'repo_language', 'docker_image', 'version',
}
POLICY = {
    'network_mode': 'none', 'cap_drop': ['ALL'],
    'security_opt': ['no-new-privileges:true'],
    'mem_limit': '4g', 'nano_cpus': 1_000_000_000, 'pids_limit': 256,
}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_public_task(storage, spec):
    path = storage / spec['public_inputs']
    if sha(path) != spec['public_inputs_sha256']:
        raise ValueError('Public input projection changed')
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    selected = [r for r in rows if r.get('instance_id') == spec['instance_id']]
    if len(selected) != 1 or set(selected[0]) != PUBLIC_FIELDS:
        raise ValueError('Unexpected public fields or non-unique task')
    task = selected[0]
    if task['base_commit'] != spec['base_commit']:
        raise ValueError('Public base revision differs from runtime')
    if any(not isinstance(task[k], str) for k in ('problem_statement', 'requirements', 'interface')):
        raise ValueError('All three public instruction fields must be strings')
    return task


def task_text(task):
    return '\n\n'.join('## ' + title + '\n\n' + task[key] for title, key in (
        ('Problem statement', 'problem_statement'),
        ('Requirements', 'requirements'), ('Interface', 'interface')))


def require_controls(storage, spec):
    """Read only outcome metadata; never load verifier inputs into a generator."""
    proof = spec['environment_controls']
    for phase, expected in (('negative', 0), ('reference', 1)):
        item = proof[phase]
        path = storage / item['record']
        if sha(path) != item['sha256']:
            raise ValueError('Control record changed')
        data = json.loads(path.read_text())
        if (data.get('status') != 'completed'
                or data.get('reward') != expected
                or not data.get('expected_outcome_observed')
                or not data.get('required_results_complete')
                or data.get('plan_sha256') != spec['environment_plan_sha256']):
            raise ValueError('Required environment control did not pass')
    negative = json.loads((storage / proof['negative']['record']).read_text())
    if 'original_summary_sha256' in negative:
        original = (storage / proof['negative']['record']).with_name('summary.json')
        if sha(original) != negative['original_summary_sha256']:
            raise ValueError('Original negative record changed after assessment')


def create_container(client, spec, prefix):
    plan_path = ROOT / 'configs/pro_environment_feasibility_v01.json'
    if sha(plan_path) != spec['environment_plan_sha256']:
        raise ValueError('Fixed environment plan changed')
    plan = json.loads(plan_path.read_text())
    if any(spec[k] != plan[k] for k in ('instance_id', 'base_commit', 'image')):
        raise ValueError('Runtime differs from the calibrated candidate')
    manifest = json.loads((ROOT / 'reports/pro_candidate_image_manifest.json').read_text())
    validate_image(client.images.get(spec['image']), plan, manifest)
    container = client.containers.create(
        image=spec['image'], name=prefix + '_' + uuid.uuid4().hex[:8],
        entrypoint=[], command=['tail', '-f', '/dev/null'], user='root',
        labels={'harness_research': 'pro_public_execution'}, **POLICY)
    try:
        container.reload()
        host = container.attrs['HostConfig']
        if (container.attrs.get('Mounts') or host.get('Privileged') or host.get('CapAdd')
                or host['NetworkMode'] != 'none' or host['Memory'] != 4 * 1024**3
                or host['NanoCpus'] != POLICY['nano_cpus']
                or host['PidsLimit'] != 256):
            raise ValueError('Unexpected Pro execution isolation')
        container.start()
        runtime = runtime_for(spec, {})
        check = container.exec_run(
            ['git', 'rev-parse', 'HEAD'], workdir=runtime['workdir'])
        status = container.exec_run(
            ['git', 'status', '--porcelain'], workdir=runtime['workdir'])
        if (check.exit_code != 0 or check.output.decode().strip() != spec['base_commit']
                or status.exit_code != 0 or status.output.strip()):
            raise ValueError('Runtime does not start from the clean public base')
        return container
    except Exception:
        container.remove(force=True)
        raise
