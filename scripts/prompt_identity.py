"""Conservative plain-text request checks and bound tool-ID renaming."""
from copy import deepcopy


PAIR_RUNS = (
    ('P64_01_PHOTO_DOCUMENTED', 'P66_01_PHOTO_DOCUMENTED', 13),
    ('P64_02_PHOTO_NAMED', 'P66_02_PHOTO_NAMED', 12),
    ('P68_01_EXPORT_NATIVE', 'P68_02_EXPORT_CONTROLLED', 8),
)


def renamed_request(request):
    """Rename only identifier fields, preserving every binding and other value.

    A response must refer to one preceding, unanswered call. Never erase IDs,
    replace content literals, merge duplicate declarations or repair bad links.
    """
    if not isinstance(request, dict) or not isinstance(request.get('messages'), list):
        raise ValueError('request messages must be an array')
    result = deepcopy(request)
    declared, answered = {}, set()
    allowed_roles = {'system', 'user', 'assistant', 'tool'}
    for message in result['messages']:
        if not isinstance(message, dict) or message.get('role') not in allowed_roles:
            raise ValueError('unsupported message')
        if message.get('content') is not None and not isinstance(message['content'], str):
            raise ValueError('plain text or null content required; no media')
        role = message['role']
        if message.get('tool_calls'):
            if role != 'assistant' or not isinstance(message['tool_calls'], list):
                raise ValueError('only an assistant may declare calls')
            for call in message['tool_calls']:
                identity = call.get('id')
                function = call.get('function', {})
                if (call.get('type') != 'function' or not isinstance(identity, str) or not identity
                        or identity in declared or not isinstance(function.get('name'), str)
                        or not isinstance(function.get('arguments'), str)):
                    raise ValueError('invalid or duplicate tool-call declaration')
                renamed = f'p73_binding_{len(declared) + 1:04d}'
                declared[identity] = (renamed, function['name'])
                call['id'] = renamed
        if role == 'tool':
            identity = message.get('tool_call_id')
            if identity not in declared or identity in answered:
                raise ValueError('unbound or duplicate tool result')
            renamed, function = declared[identity]
            if message.get('name') not in (None, function):
                raise ValueError('tool result name disagrees with its call')
            answered.add(identity)
            message['tool_call_id'] = renamed
        elif 'tool_call_id' in message:
            raise ValueError('tool response identifier on a non-tool role')
    if set(declared) != answered:
        raise ValueError('request has an unanswered historical tool call')
    return result, len(declared)


def selected_requests(audits):
    """All matched executed prefixes, including the failed export comparison."""
    rows = {}
    for report in audits:
        if report['audit_errors'] or not report['server_stopped']:
            raise ValueError('closed original audit required')
        for row in report['rows']:
            if row['run_id'] in rows:
                raise ValueError('duplicate original run')
            rows[row['run_id']] = row
    selected = []
    for before, after, count in PAIR_RUNS:
        a, b = rows[before], rows[after]
        if len(b['calls']) != count or len(a['calls']) < count:
            raise ValueError('fixed complete controlled prefix differs')
        for index in range(count):
            pair = []
            for run, row in ((before, a), (after, b)):
                call = row['calls'][index]
                if (call['call_id'] != f'call_{index + 1:03d}' or not call['usage_known']
                        or call['status'] != 'ok' or type(call['input_tokens']) is not int):
                    raise ValueError('complete known saved model request required')
                pair.append({'run_id': run, **call})
            selected.append(pair)
    if len(selected) != 33:
        raise ValueError('all thirty-three pairs required')
    return selected
