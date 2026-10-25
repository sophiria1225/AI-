"""Recognize whole literal public schemas, never infer why a program printed them."""
import ast
from collections import Counter
from copy import deepcopy
import json

from context_preservation import compact
from public_action_structure import digest
from receipt_reasoning_history import require
from runtime_recoverability import parse_structured_stdout


def literal_value(text):
    checked = parse_structured_stdout(text)  # Bounds, duplicate keys and types.
    value = json.loads(text) if checked['syntax'] == 'json' else ast.literal_eval(text.strip())
    return value, checked


def match_public_functions(value, functions):
    """Every value must equal a complete pinned public function schema."""
    by_fingerprint = {digest(v):name for name,v in functions.items()}
    direct = by_fingerprint.get(digest(value))
    if direct is not None:
        return dict(shape='single_function', names=[direct])
    if type(value) is dict and value:
        if all(type(name) is str and name in functions
               and digest(v) == digest(functions[name]) for name,v in value.items()):
            return dict(shape='mapping_of_functions', names=list(value))
    if type(value) is list and value:
        names=[by_fingerprint.get(digest(v)) for v in value]
        if all(name is not None for name in names):
            return dict(shape='list_of_functions', names=names)
    return None


def public_syntax(action):
    if type(action) is not dict or action.get('name') != 'run_python':
        return dict(status='not_run_python')
    try:
        args=action['arguments']
        args=json.loads(args) if type(args) is str else args
        source=args['code']
        require(type(source) is str and len(source)<=20000, 'bounded_program_source_required')
        tree=ast.parse(source);nodes=list(ast.walk(tree))
        require(len(nodes)<=20000,'bounded_program_AST_required')
        return dict(status='parsed', api_schemas_name_loaded=any(isinstance(n,ast.Name)
            and n.id=='api_schemas' and isinstance(n.ctx,ast.Load) for n in nodes),
            direct_print_syntax_sites=sum(isinstance(n,ast.Call) and isinstance(n.func,ast.Name)
                and n.func.id=='print' for n in nodes), actual_dataflow_proven=False)
    except (ValueError,SyntaxError,KeyError,TypeError,RecursionError):
        return dict(status='unavailable_or_invalid',actual_dataflow_proven=False)


def describe_tool_observation(message, spans, functions, visible_by_span):
    require(type(message) is dict and message.get('role')=='tool'
            and type(message.get('content')) is str, 'bounded_tool_message_required')
    content=message['content']
    require(len(content)<=16777216,'tool_message_size_bound')
    result=dict(message_sha256=digest(message),tool_content_characters=len(content),
        archive_correspondence='unrecognized_or_paged',whole_public_metadata_match=False,
        provenance_of_printed_value_proven=False,safe_to_omit=False,measured_token_savings=None)
    try: data=json.loads(content)
    except (ValueError,RecursionError):return result
    if type(data) is not dict or set(data)!={'span_id','observation'}:
        return result
    sid=data['span_id'];obs=data['observation']
    if type(sid) is not str or sid not in spans or sid not in visible_by_span or type(obs) is not dict:
        return result
    span=spans[sid]
    if digest(obs)!=digest(span['observation']):
        result['archive_correspondence']='observation_mismatch';return result
    result.update(archive_correspondence='exact',span_id=sid,
        outer_tool=span.get('action',{}).get('name') if span.get('action') else None,
        syntax=public_syntax(span.get('action')))
    if result['outer_tool']!='run_python':
        result['stdout_classification']='not_run_python';return result
    stdout=obs.get('stdout')
    if type(stdout) is not str:
        result['stdout_classification']='no_stdout_text';return result
    protected=bool(obs.get('status')!='ok' or obs.get('error') or obs.get('stdout_truncated')
        or obs.get('unknown_effects') or obs.get('declared_complete'))
    without=deepcopy(data);without['observation']['stdout']=''
    result.update(stdout_characters=len(stdout),protected_by_execution_status=protected,
        compact_wrapper_matches_record=compact(data)==content,
        encoded_stdout_characters_if_compact=len(compact(data))-len(compact(without)),
        model_execution_not_changed=True)
    try:
        value,checked=literal_value(stdout)
        result.update(stdout_classification='whole_literal',literal_syntax=checked['syntax'],
                      literal_value_sha256=checked['digest'])
    except (ValueError,SyntaxError,TypeError,RecursionError,MemoryError):
        result['stdout_classification']='not_whole_supported_literal';return result
    match=match_public_functions(value,functions)
    if match is None:return result
    names=match['names'];visible=all(n in visible_by_span[sid] for n in names)
    result.update(whole_public_metadata_match=True,metadata_shape=match['shape'],
        public_function_names=names,all_names_exposed_by_program_end=visible,
        normal_complete_metadata_match=not protected and visible,
        source_schema_identity_is_not_runtime_alias_or_semantic_irrelevance=True)
    return result


def exposure_summary(rows):
    matched=[r for r in rows if r['whole_public_metadata_match']]
    eligible=[r for r in matched if r['normal_complete_metadata_match']]
    return dict(observation_occurrences=len(rows),archive_correspondence=dict(Counter(r['archive_correspondence'] for r in rows)),
        whole_public_metadata_matches=len(matched),normal_complete_metadata_matches=len(eligible),
        matched_whole_tool_exposure_characters=sum(r['tool_content_characters']*r['exposures'] for r in matched),
        matched_stdout_exposure_characters=sum(r['stdout_characters']*r['exposures'] for r in matched),
        matched_encoded_stdout_exposure_characters=sum(r['encoded_stdout_characters_if_compact']*r['exposures']
            for r in matched if r['compact_wrapper_matches_record']),
        observed_exposure_is_not_removable_work=True,character_counts_are_not_token_counts=True)
