"""Bounded ordinary feedback for an unexecuted request to an exposed public API.

This neither renames arguments nor retries a request. A schema is copied only
from the catalog already available to the running program. Generic feedback and
parameter-name feedback remain explicit controls, not hidden weak baselines.
"""
import copy
import hashlib
import json

from container_api_python import ApiChannel

MODES = ('generic', 'parameter_names', 'public_schema')
UNKNOWN_PARAMETER = 'unknown API parameter'


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def make_feedback(row, exposed_schemas, mode, max_characters=16000):
    if mode not in MODES or type(max_characters) is not int or max_characters < 512:
        raise ValueError('invalid feedback policy')
    if (mode == 'generic' or row.get('api_request_sent') is not False
            or row.get('effects_unknown') or row.get('observation') != {'format_error': UNKNOWN_PARAMETER}):
        return None
    action = row.get('action')
    if not isinstance(action, dict) or action.get('name') not in exposed_schemas:
        return None
    name = action['name']
    function = exposed_schemas[name]
    if function.get('name') != name or type(function.get('parameters', {}).get('properties')) is not dict:
        return None
    try:
        arguments = json.loads(action['arguments'])
    except (KeyError, TypeError, ValueError):
        return None
    properties = function['parameters']['properties']
    if (type(arguments) is not dict or not set(arguments) - set(properties)
            or any(type(k) is not str for k in properties)):
        return None
    feedback = {'kind': 'already_exposed_public_contract', 'api': name,
                'requested_mode': mode, 'mode': mode,
                'schema_sha256': hashlib.sha256(canonical(function).encode()).hexdigest(),
                'request_dispatched': False, 'automatic_retry': False,
                'scope': 'This rejected request only. Earlier API effects are unchanged.'}
    # Do not echo argument values or invent required fields missing from the
    # distributed public schema. The schema's original defaults are retained.
    if mode == 'public_schema':
        feedback['public_schema'] = copy.deepcopy(function)
    else:
        feedback['allowed_parameters'] = sorted(properties)
    if len(canonical(feedback)) > max_characters:
        feedback.pop('public_schema', None)
        feedback.update(mode='parameter_names', allowed_parameters=sorted(properties),
                        fallback='schema_exceeds_feedback_character_bound')
    if len(canonical(feedback)) > max_characters:
        # Preserve the original rejection when even the names would be large.
        return None
    return feedback


class ContractFeedbackChannel(ApiChannel):
    def __init__(self, catalog, bridge, remaining, may_continue=lambda: True,
                 *, feedback_mode='generic', feedback_max_characters=16000):
        if feedback_mode not in MODES or type(feedback_max_characters) is not int or feedback_max_characters < 512:
            raise ValueError('invalid feedback policy')
        super().__init__(catalog, bridge, remaining, may_continue)
        self.feedback_mode = feedback_mode
        self.feedback_max_characters = feedback_max_characters

    def exchange(self, packet):
        # The base channel remains the sole dispatch/permission/budget authority.
        reply = super().exchange(packet)
        row = self.rows[-1]
        exposed = {name: self.catalog.catalog[name]['function'] for name in self.catalog.visible}
        feedback = make_feedback(row, exposed, self.feedback_mode, self.feedback_max_characters)
        if feedback is not None:
            row['observation']['contract_feedback'] = feedback
            reply['error'] = canonical({'format_error': UNKNOWN_PARAMETER, 'contract_feedback': feedback})
        return reply
