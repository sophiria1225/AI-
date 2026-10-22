"""Pure, one-proposal binding for a limited unknown-parameter repair.

Only unknown parameter names can change; values remain in host memory. This
does not choose a mapping, execute an API, resume Python, or certify semantics.
It is not connected to the experimental runner.
"""
import json
import threading
import uuid

from contract_feedback import UNKNOWN_PARAMETER


class RepairNotAdmitted(ValueError):
    """Fixed reason code only, never the rejected value or credential."""


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def strict_json(text):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result: raise RepairNotAdmitted('duplicate_json_key')
            result[key] = value
        return result

    def constant(_): raise RepairNotAdmitted('nonfinite_json_number')
    try:
        return json.loads(text, object_pairs_hook=pairs, parse_constant=constant)
    except (ValueError, TypeError, RecursionError):
        raise RepairNotAdmitted('invalid_json') from None


def scalar_kind(value):
    return {str: 'string', int: 'integer', float: 'number', bool: 'boolean',
            type(None): 'null'}.get(type(value), 'unsupported_container')


def fits_scalar_contract(value, spec):
    """Conservative supported fragment, not a replacement JSON Schema engine."""
    if type(spec) is not dict or set(spec) - {'type', 'description', 'title', 'default', 'enum'}:
        return False
    expected = spec.get('type')
    if type(expected) is not str or expected not in {'string', 'integer', 'number', 'boolean', 'null'}:
        return False
    actual = scalar_kind(value)
    if actual != expected and not (actual == 'integer' and expected == 'number'):
        return False
    if 'enum' in spec:
        choices = spec['enum']
        if type(choices) is not list or not choices:
            return False
        if not any(canonical(value) == canonical(choice) for choice in choices):
            return False
    return True


def maximum_matching(edges):
    """A finite matching check says nothing about intended argument meanings."""
    owners = {}
    def place(source, visited):
        for target in edges[source]:
            if target in visited: continue
            visited.add(target)
            if target not in owners or place(owners[target], visited):
                owners[target] = source
                return True
        return False
    for source in sorted(edges): place(source, set())
    return len(owners)


def admission(function, exposed, *, api_request_sent, effects_unknown, format_error):
    if api_request_sent is not False or effects_unknown is not False:
        raise RepairNotAdmitted('dispatch_not_known_absent')
    if format_error != UNKNOWN_PARAMETER:
        raise RepairNotAdmitted('not_unknown_parameter_rejection')
    if type(function) is not dict or set(function) != {'name', 'arguments'}:
        raise RepairNotAdmitted('invalid_function_shape')
    if type(function['name']) is not str or type(function['arguments']) is not str:
        raise RepairNotAdmitted('invalid_function_shape')
    if len(function['arguments']) > 65536:
        raise RepairNotAdmitted('private_binding_size_limit')
    if type(exposed) is not dict or function['name'] not in exposed:
        raise RepairNotAdmitted('api_not_exposed')
    schema = exposed[function['name']]
    if type(schema) is not dict or schema.get('name') != function['name']:
        raise RepairNotAdmitted('invalid_public_schema')
    params = schema.get('parameters')
    if type(params) is not dict or type(params.get('properties')) is not dict:
        raise RepairNotAdmitted('invalid_public_schema')
    props = params['properties']
    if len(props) > 128:
        raise RepairNotAdmitted('binding_field_count_limit')
    if any(type(key) is not str or not key.isidentifier() for key in props):
        raise RepairNotAdmitted('unsupported_public_parameter_name')
    args = strict_json(function['arguments'])
    if type(args) is not dict or any(not key.isidentifier() for key in args):
        raise RepairNotAdmitted('unsupported_argument_shape')
    if len(args) > 128:
        raise RepairNotAdmitted('binding_field_count_limit')
    if not args.keys() - props.keys():
        raise RepairNotAdmitted('no_unknown_parameters')
    try:
        if len(canonical(function)) > 65536 or len(canonical(schema)) > 65536:
            raise RepairNotAdmitted('private_binding_size_limit')
    except (TypeError, ValueError, RecursionError):
        raise RepairNotAdmitted('invalid_or_oversized_binding') from None
    return args, schema


class RepairBinding:
    """Process-local single proposal; no durable/distributed exactly-once claim."""

    def __init__(self, function, exposed, *, api_request_sent, effects_unknown, format_error):
        args, schema = admission(function, exposed, api_request_sent=api_request_sent,
            effects_unknown=effects_unknown, format_error=format_error)
        self._original = canonical(function)
        self._schema = canonical(schema)
        self._args = canonical(args)
        props = schema['parameters']['properties']
        self._unknown = frozenset(args.keys() - props.keys())
        self._protected = frozenset(args.keys() & props.keys())
        edges = {source: [target for target in sorted(props.keys() - self._protected)
                          if fits_scalar_contract(args[source], props[target])]
                 for source in sorted(self._unknown)}
        size = maximum_matching(edges)
        self._ticket = uuid.uuid4().hex
        packet = {
            'ticket': self._ticket, 'api': function['name'],
            'public_api_description': schema.get('description', ''),
            'unknown_parameters': [{'name': key, 'value_type': scalar_kind(args[key])}
                                   for key in sorted(self._unknown)],
            'protected_parameter_names': sorted(self._protected),
            'destination_properties': {key: props[key] for key in sorted(props.keys() - self._protected)},
            'allowed_rename_targets': edges,
            'complete_type_compatible_renaming_exists': size == len(self._unknown),
            'drop_allowed_only_for_empty_contract': not props,
            'instructions': 'Return ticket, renames [{from,to}], and drop [from]. Account for every unknown parameter exactly once. Never return or transform values, edit protected fields, or change API. If names and public schema do not determine an intended mapping, return ticket and decline:true. This packet omits task meaning and values; do not guess.',
        }
        self._packet = canonical(packet)
        if len(self._packet) > 16000:
            raise RepairNotAdmitted('packet_size_limit')
        self._lock = threading.Lock()
        self._consumed = False

    def packet(self):
        return strict_json(self._packet)

    def evaluate(self, proposal, current_function, current_exposed, *, api_request_sent,
                 effects_unknown, format_error):
        with self._lock:
            if self._consumed: return self._result(False, 'proposal_already_consumed')
            self._consumed = True
        try:
            _, schema = admission(current_function, current_exposed,
                api_request_sent=api_request_sent, effects_unknown=effects_unknown,
                format_error=format_error)
            if canonical(current_function) != self._original or canonical(schema) != self._schema:
                return self._result(False, 'binding_changed')
        except (ValueError, TypeError, RecursionError):
            return self._result(False, 'current_admission_failed')
        if type(proposal) is not dict or proposal.get('ticket') != self._ticket:
            return self._result(False, 'proposal_identity_mismatch')
        if set(proposal) == {'ticket', 'decline'} and proposal['decline'] is True:
            return self._result(False, 'declined')
        if set(proposal) != {'ticket', 'renames', 'drop'}:
            return self._result(False, 'proposal_shape')
        renames, drops = proposal['renames'], proposal['drop']
        if type(renames) is not list or type(drops) is not list:
            return self._result(False, 'proposal_shape')
        if len(renames) + len(drops) != len(self._unknown):
            return self._result(False, 'source_scope_mismatch')
        if any(type(r) is not dict or set(r) != {'from', 'to'}
               or type(r['from']) is not str or type(r['to']) is not str for r in renames):
            return self._result(False, 'proposal_shape')
        if any(type(key) is not str for key in drops):
            return self._result(False, 'proposal_shape')
        sources = [r['from'] for r in renames] + drops
        targets = [r['to'] for r in renames]
        if len(sources) != len(set(sources)) or set(sources) != self._unknown:
            return self._result(False, 'source_scope_mismatch')
        props = schema['parameters']['properties']
        if drops and props:
            return self._result(False, 'drop_requires_empty_contract')
        if len(targets) != len(set(targets)) or any(t in self._protected or t not in props for t in targets):
            return self._result(False, 'destination_scope_mismatch')
        original = strict_json(self._args)
        for rename in renames:
            if not fits_scalar_contract(original[rename['from']], props[rename['to']]):
                return self._result(False, 'unsupported_or_incompatible_property')
        corrected = {key: value for key, value in original.items() if key in self._protected}
        for rename in renames:
            corrected[rename['to']] = original[rename['from']]
        function = strict_json(self._original)
        function['arguments'] = canonical(corrected)
        # Only a private candidate is assembled; the caller must perform normal
        # permission, schema, state, budget and dispatch checks independently.
        return self._result(True, 'candidate_assembled', function=function,
                            renamed=len(renames), dropped=len(drops))

    @staticmethod
    def _result(accepted, reason, *, function=None, renamed=0, dropped=0):
        return {
            'accepted': accepted, 'reason': reason, 'private_candidate_function': function,
            'renamed_parameter_count': renamed, 'dropped_parameter_count': dropped,
            'api_dispatched': False, 'python_resumed': False,
            'semantic_equivalence_verified': False,
            'normal_dispatch_checks_still_required': True,
        }
