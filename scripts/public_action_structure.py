"""Separate public text, JSON action form and Python syntax without execution.

AST equality omits source locations only. Names, literal values, statement and
tool order, and span references are retained. No action is called and no Python
equivalence, task correctness, or cost improvement is inferred.
"""
import ast
import hashlib
from itertools import combinations
import json

from return_use_scope import analyze as code_shape

MAX_CHARS = 65536
MAX_JSON_NODES = 5000
MAX_JSON_DEPTH = 64
MAX_TOOLS = 16


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
        separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def strict_object(text):
    if type(text) is not str or len(text) > MAX_CHARS:
        raise ValueError('argument_text_bound_or_type')
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result: raise ValueError('duplicate_JSON_key')
            result[key] = value
        return result
    def invalid_number(_): raise ValueError('nonfinite_JSON_number')
    try:
        result = json.loads(text, object_pairs_hook=pairs, parse_constant=invalid_number)
        # Also reject an overflowing ordinary JSON number such as 1e999.
        digest(result)
    except (ValueError, TypeError, RecursionError, OverflowError) as error:
        if isinstance(error, ValueError) and str(error) in {'duplicate_JSON_key', 'nonfinite_JSON_number'}:
            raise
        raise ValueError('invalid_JSON_arguments') from None
    if type(result) is not dict: raise ValueError('arguments_not_object')
    queue = [(result, 0)]; count = 0
    while queue:
        value, depth = queue.pop(); count += 1
        if count > MAX_JSON_NODES or depth > MAX_JSON_DEPTH:
            raise ValueError('JSON_structure_bound')
        if type(value) is dict: queue.extend((v, depth+1) for v in value.values())
        elif type(value) is list: queue.extend((v, depth+1) for v in value)
    return result


def argument_strings(value):
    queue = [value]; result = []
    while queue:
        item = queue.pop()
        if type(item) is str: result.append(item)
        elif type(item) is list: queue.extend(item)
        elif type(item) is dict: queue.extend(item.values())
    return result


def transport_ids(request):
    messages = request.get('messages')
    if type(messages) is not list or len(messages) > 512:
        raise ValueError('message_inventory_bound')
    identifiers = set()
    for message in messages:
        if type(message) is not dict: raise ValueError('message_shape')
        values = []
        if message.get('role') == 'tool': values.append(message.get('tool_call_id'))
        if message.get('role') == 'assistant':
            calls = message.get('tool_calls') or []
            if type(calls) is not list: raise ValueError('input_tool_calls_shape')
            values.extend(call.get('id') for call in calls if type(call) is dict)
        for value in values:
            if type(value) is not str or not 0 < len(value) <= 256:
                raise ValueError('transport_reference_bound_or_type')
            identifiers.add(value)
    if len(identifiers) > 512: raise ValueError('transport_reference_count_bound')
    return identifiers


def interface_shape(name, args):
    if name == 'run_python':
        return (set(args) == {'code','span_ids'} and type(args['code']) is str
            and 0 < len(args['code']) <= 20000 and type(args['span_ids']) is list
            and len(args['span_ids']) <= 160 and all(type(x) is str for x in args['span_ids'])
            and len(set(args['span_ids'])) == len(args['span_ids']))
    if name == 'read_span':
        return ('span_id' in args and set(args) <= {'span_id','offset'} and type(args['span_id']) is str
                and ('offset' not in args or type(args['offset']) is int and args['offset'] >= 0))
    return False


def inspect(response, *, input_transport_ids=()):
    if response.get('status') != 'ok':
        return dict(status='unknown_response', public_output_sha256=None, content_sha256=None,
            tool_names_sha256=None, json_actions_sha256=None, syntax_actions_sha256=None,
            tool_calls=None, syntax_or_semantic_correctness_established=False, actions_executed=0)
    message = response.get('message')
    if type(message) is not dict: raise ValueError('response_message_shape')
    content = message.get('content'); calls = message.get('tool_calls') or []
    if content is not None and (type(content) is not str or len(content) > MAX_CHARS):
        raise ValueError('public_content_bound_or_type')
    if type(calls) is not list or len(calls) > MAX_TOOLS: raise ValueError('tool_count_bound_or_type')
    if any(type(call) is not dict or type(call.get('function')) is not dict for call in calls):
        raise ValueError('function_envelope_shape')
    functions = [call['function'] for call in calls]
    public = dict(content=content, functions=functions, done_reason=response.get('done_reason'))
    details=[]; json_actions=[]; syntax_actions=[]; names=[]; texts=[content] if content else []
    all_json = all_syntax = all_names = bool(calls)
    for index, function in enumerate(functions, 1):
        name = function.get('name'); args = None
        name_valid = type(name) is str and 0 < len(name) <= 120
        all_names &= name_valid
        if name_valid: names.append(name)
        detail = dict(index=index, name=name if name_valid and name in {'run_python','read_span'} else 'unrecognized',
            name_sha256=digest(name) if name_valid else None, JSON_object=False,
            interface_shape_valid=False, Python_AST_valid=None, error=None)
        try:
            if set(function) != {'name','arguments'} or not name_valid:
                raise ValueError('function_fields_unsupported')
            args = strict_object(function['arguments']); detail['JSON_object'] = True
            texts.extend(argument_strings(args))
            json_actions.append(dict(name=name, arguments=args))
            detail['interface_shape_valid'] = interface_shape(name,args)
            if not detail['interface_shape_valid']: raise ValueError('interface_shape_unsupported')
            normalized = dict(args)
            if name == 'run_python':
                syntax = code_shape(args['code'])
                tree = ast.parse(args['code'])
                normalized['code'] = ast.dump(tree, annotate_fields=True, include_attributes=False)
                detail.update(Python_AST_valid=True, code_sha256=syntax['source_sha256'],
                    code_ast_sha256=digest(normalized['code']), ast_nodes=syntax['ast_nodes'],
                    call_api_syntax_sites=syntax['call_api_syntax_sites'],
                    literal_API_syntax=[site['api'] for site in syntax['sites']],
                    current_program_hazards=syntax['current_program_hazards'],
                    bridge_name_non_call_loads=syntax['bridge_name_non_call_loads'])
            syntax_actions.append(dict(name=name, arguments=normalized))
        except (ValueError, RecursionError) as error:
            detail['error'] = 'AST_recursion_bound' if isinstance(error,RecursionError) else str(error)
            if not detail['JSON_object']: all_json=False
            if name == 'run_python' and detail['interface_shape_valid']: detail['Python_AST_valid']=False
            all_syntax=False
        details.append(detail)
    identifiers = set(input_transport_ids)
    if any(type(value) is not str or not 0 < len(value) <= 256 for value in identifiers) or len(identifiers)>512:
        raise ValueError('input_transport_reference_bound')
    matched = sum(any(value in text for text in texts) for value in identifiers)
    return dict(status='structured_calls' if calls else 'no_structured_tool_calls',
        public_output_sha256=digest(public), content_sha256=digest(content), content_characters=len(content or ''),
        tool_calls=len(calls), tool_names_sha256=digest(names) if all_names else None,
        json_actions_sha256=digest(json_actions) if all_json else None,
        syntax_actions_sha256=digest(syntax_actions) if all_syntax else None,
        functions=details, JSON_objects=sum(d['JSON_object'] for d in details),
        interface_shapes_valid=sum(d['interface_shape_valid'] for d in details),
        Python_ASTs_valid=sum(d['Python_AST_valid'] is True for d in details),
        input_transport_reference_count=len(identifiers),
        distinct_transport_references_with_public_text_substring_match=matched,
        transport_match_scope_complete=all_json or not calls,
        literals_and_identifiers_preserved=True, statement_and_tool_order_preserved=True,
        task_correctness_established=False, semantic_equivalence_established=False, actions_executed=0)


def comparison(rows, cases):
    metrics=('public_output_sha256','content_sha256','tool_names_sha256',
             'json_actions_sha256','syntax_actions_sha256')
    def summarize(pairs):
        result=dict(pairs=len(pairs), pairs_are_independent_samples=False,
            both_without_structured_calls=sum(a['structure'].get('tool_calls')==0 and b['structure'].get('tool_calls')==0 for a,b in pairs))
        for metric in metrics:
            known=[(a['structure'][metric],b['structure'][metric]) for a,b in pairs
                   if a['structure'].get(metric) is not None and b['structure'].get(metric) is not None]
            result[metric.replace('_sha256','')]=dict(comparable=len(known),equal=sum(a==b for a,b in known),
                different=sum(a!=b for a,b in known),unavailable=len(pairs)-len(known))
        return result
    groups={case:[r for r in rows if r['case']==case] for case in cases}
    if any(len(group)!=3 for group in groups.values()): raise ValueError('all_six_times_three_rows_required')
    return dict(within=[dict(case=case,**summarize(list(combinations(group,2)))) for case,group in groups.items()],
        cross=[dict(left=a,right=b,**summarize([(x,y) for x in groups[a] for y in groups[b]])) for a,b in combinations(cases,2)],
        no_action_is_not_valid_action_equality=True, source_location_only_removed_from_AST=True,
        semantic_equivalence_claim=False, task_quality_measured=False)
