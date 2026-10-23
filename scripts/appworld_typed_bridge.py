"""Separate opt-in public API bridge; historical appworld_bridge.py is unchanged."""
import contextlib
import json
import sys

from public_api_envelope import PROTOCOL, trusted_invocation_code


def execute_public_api(world, call, nonce):
    """Generate the trusted invocation locally, never accept model Python here."""
    source = trusted_invocation_code(call, world.task.api_docs, nonce)
    return {'protocol': PROTOCOL, 'observation': world.execute(source),
            'declared_complete': world.task_completed()}


def main():
    world = None
    for line in sys.stdin:
        command = {}
        try:
            command = json.loads(line)
            if type(command) is not dict:
                raise ValueError('bridge_command_must_be_an_object')
            with contextlib.redirect_stdout(sys.stderr):
                if command.get('op') == 'init':
                    if world is not None:
                        raise ValueError('world already initialized')
                    if set(command) != {'op', 'task_id', 'experiment', 'seed'}:
                        raise ValueError('invalid_init_command')
                    from appworld import AppWorld
                    world = AppWorld(
                        task_id=command['task_id'], experiment_name=command['experiment'],
                        load_ground_truth=False, random_seed=command['seed'],
                        max_interactions=500, timeout_seconds=30,
                        raise_on_unsafe_syntax=True, null_patch_unsafe_execution=True)
                    if world.task.ground_truth is not None:
                        raise RuntimeError('ground truth unexpectedly loaded')
                    result = {'instruction': world.task.instruction,
                              'supervisor': dict(world.task.supervisor),
                              'app_descriptions': world.task.app_descriptions,
                              'helper_docs': {app: dict(world.task.api_docs[app])
                                              for app in ('api_docs', 'supervisor')},
                              'ground_truth_loaded': False, 'api_result_protocol': PROTOCOL}
                elif command.get('op') == 'call_typed':
                    if world is None:
                        raise ValueError('world not initialized')
                    if set(command) != {'op', 'call', 'nonce'}:
                        raise ValueError('invalid_typed_call_command')
                    result = execute_public_api(world, command['call'], command['nonce'])
                elif command.get('op') == 'close':
                    if set(command) != {'op'}:
                        raise ValueError('invalid_close_command')
                    if world is not None:
                        world.close()
                    result = {'closed': True}
                else:
                    raise ValueError('unsupported bridge operation')
            response = {'ok': True, 'result': result}
        except Exception as error:
            # Any error outside the invocation envelope is unknown to the client.
            response = {'ok': False, 'error': f'{type(error).__name__}: {error}'}
        print(json.dumps(response, ensure_ascii=False, allow_nan=False), flush=True)
        if type(command) is dict and command.get('op') == 'close':
            return


if __name__ == '__main__':
    main()
