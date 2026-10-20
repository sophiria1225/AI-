"""Common local Docker limits. No host mounts or network for task execution."""
import uuid

POLICY = {
    'network_mode': 'none',
    'cap_drop': ['ALL'],
    'security_opt': ['no-new-privileges:true'],
    'mem_limit': '6g',
    'nano_cpus': 4_000_000_000,
    'pids_limit': 256,
}


def create_task_container(client, image, name):
    # The selected image has no declared volumes. Check actual isolation, too.
    container = client.containers.create(
        image=image, name=name + '_' + uuid.uuid4().hex[:8],
        user='root', command=['tail', '-f', '/dev/null'], detach=True,
        labels={'harness_research': 'e0'}, **POLICY,
    )
    container.reload()
    host = container.attrs['HostConfig']
    if (container.attrs.get('Mounts') or host['NetworkMode'] != 'none'
            or host.get('Privileged') or host.get('CapAdd')):
        container.remove(force=True)
        raise RuntimeError('Unexpected container isolation configuration')
    return container


def evaluator_create_container(test_spec, client, run_id, logger):
    container = create_task_container(client, test_spec.image, 'harness_eval_' + run_id)
    logger.info('Research container policy: %s', POLICY)
    return container
