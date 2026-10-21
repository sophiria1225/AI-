"""Describe ordinary task-local Python state without changing task guidance."""
from code_runtime_prompts import control_system_prompt

FRESH = '''No Python variables
persist across programs. To reuse earlier results, provide the recorded span_ids;
observations then contains those complete prior records (id, action, observation).'''
PERSISTENT = '''Python variables, imports and functions persist between run_python
programs within this task. Supplied call_api, api_schemas and observations are
refreshed for each program. To include earlier API receipts, provide span_ids;
observations contains those complete prior records (id, action, observation).
A Python exception keeps assignments already made. A timeout ends the task's
interpreter; it is not silently restarted or replayed.'''

def stateful_system_prompt(config):
    if config['phase']!='P29' or config.get('python_state_version')!='task_namespace_v1':
        raise ValueError('only the P29 task-local state control')
    baseline=control_system_prompt({**config,'phase':'P28'})
    if baseline.count(FRESH)!=1:raise ValueError('fresh-state description changed')
    return baseline.replace('In each fresh Python 3.12\nprogram','In this task-local Python 3.12\ninterpreter').replace(FRESH,PERSISTENT)
