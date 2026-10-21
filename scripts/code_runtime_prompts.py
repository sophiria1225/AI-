"""Ordinary environment clarification, kept separate from interpreter state."""
from run_code_appworld import code_system_prompt

CALLABLE_GUIDANCE = '''
Python runtime clarification:
call_api, api_schemas and observations are ALREADY DEFINED global names in every
run_python program. Use call_api directly, for example print(callable(call_api)).
Do not import call_api from a package, install a client, or search the operating
system for an API endpoint. The simulated applications are available only through
the supplied call_api function. The Python standard library is available.
'''

def control_system_prompt(config):
    if config['phase'] != 'P28' or config.get('code_runtime_guidance_version') != 'provided_callables_v1':
        raise ValueError('only the frozen P28 clarification')
    return code_system_prompt() + CALLABLE_GUIDANCE
