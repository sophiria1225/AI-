"""One explicit action per old index, converted to the frozen P144 contract.

Fixed object keys avoid the cross-array duplicate-index ambiguity observed in
P145. This changes representation and its system prompt, not state semantics.
Every generated response remains untrusted: duplicate JSON keys, omitted or
extra old indices, malformed actions, and all old size limits are rejected.

Pinned llama.cpp 620d2225 accepts anyOf, const, required, properties,
additionalProperties:false, and string/array bounds through common/json-schema.cpp
and common/json-schema-to-grammar.cpp. No unsupported uniqueItems is assumed.
No model, tokenizer, task API, evaluator, or generated program runs here.
"""
from copy import deepcopy
import hashlib
import json

from checkpoint_state_update_p144 import (
    StateUpdateCheckpoint, parse_update_patch, apply_update_patch, validate_fragment_budget,
)
from checkpoint_update_schema_p145 import structured_payload
from receipt_reasoning_history import digest, require
from single_checkpoint_history import FIELDS, _unique_pairs

VERSION='checkpoint_indexed_update_p147_v1'
SCHEMA_NAME='checkpoint_indexed_update_p147'
REASONING_BUDGET=2048
OUTPUT_CAP=4096
MAX_RAW_CHARACTERS=8192

INDEXED_UPDATE_PROMPT='''Update the previous fallible checkpoint using the new older_history.
Return exactly one JSON object with the four keys completed, usable_state,
remaining, uncertainties. Each field must have exactly two keys: by_index and
add. by_index is an object with EVERY existing zero-based index from that same
field of previous_checkpoint as a string key: "0", "1", and so on. Include each
old index exactly once, including items you preserve. Do not omit an index,
invent an index, use leading zeros, or duplicate a JSON key. For an empty old
field, by_index must be {}.
For each old index, choose exactly one of these objects:
{"action":"keep"}
{"action":"delete"}
{"action":"update","text":"replacement text"}
keep and delete must not contain text or any extra key. update must contain
only action and text. Use keep to preserve the old item's text exactly,
update to replace it, and delete to explicitly remove it. add is a list of new
item strings, or [] when no new item is needed.
Keep useful facts and unresolved uncertainties; previous_checkpoint is
fallible, not verified truth. Do not silently drop old items. The host converts
these decisions into keep/update/delete/add operations and applies them
atomically. Retained/updated old items stay in their original relative order,
followed by adds in their given order. The host supplies the resulting SINGLE
checkpoint, not these decisions, to the actor.
Do not output an array, the old checkpoint, Markdown, or commentary. Every
replacement/add must be a nonempty string of at most 2048 characters. Your
entire JSON output, the compact host-converted operation object, and the
resulting compact JSON checkpoint must each be at most 8192 characters. The
resulting checkpoint may contain at most 32 items in EACH field.
The original task and recent_context are context only; summarize new
older_history while preserving or explicitly revising the old state.'''
INDEXED_UPDATE_PROMPT_SHA256=hashlib.sha256(INDEXED_UPDATE_PROMPT.encode()).hexdigest()


def _object(properties):
    return dict(type='object',properties=properties,required=list(properties),additionalProperties=False)


def schema_for(old_state):
    """Bind each old position once without embedding any old-state string."""
    validate_fragment_budget([old_state])
    text=dict(type='string',minLength=1,maxLength=2048)
    action=dict(anyOf=[
        _object({'action':{'const':'keep'}}),
        _object({'action':{'const':'delete'}}),
        _object({'action':{'const':'update'},'text':deepcopy(text)}),
    ])
    return _object({field:_object({
        'by_index':_object({str(i):deepcopy(action) for i in range(len(old_state[field]))}),
        'add':dict(type='array',items=deepcopy(text),minItems=0,maxItems=32),
    }) for field in FIELDS})


def payload_for(saved_request,old_state):
    """Authenticate the P144 saved request, preserving its complete user packet.

Only the update system prompt, response schema, and fixed reasoning allowance
change. P145's validator keeps messages, sampling and 4096-cap preconditions
explicit. Count and generation must use this exact returned payload.
"""
    result=structured_payload(saved_request,old_state,REASONING_BUDGET)
    result['messages'][0]={'role':'system','content':INDEXED_UPDATE_PROMPT}
    result['response_format']={'type':'json_schema','json_schema':{
        'name':SCHEMA_NAME,'strict':True,'schema':schema_for(old_state)}}
    require(result['messages'][1]==saved_request['messages'][1],
        'P147_saved_user_packet_must_remain_identical')
    require(result['max_tokens']==OUTPUT_CAP,'P147_unchanged_4096_output_cap_required')
    return result


def _reject_constant(_):
    raise ValueError('P147_non_json_constant_forbidden')


def to_legacy_patch(message,finish_reason,old_state):
    """Return a deterministic old-contract patch only after full strict validation.

This is a representation conversion, never a repair: absent indices, extra
keys, contradictory actions, duplicates, or invalid strings reject the entire
response. Both source and converted representations retain their size bounds.
"""
    validate_fragment_budget([old_state])
    require(type(message) is dict and message.get('role')=='assistant','P147_assistant_required')
    require(finish_reason=='stop','P147_finish_stop_required')
    require(not message.get('tool_calls'),'P147_tool_calls_forbidden')
    content=message.get('content')
    require(type(content) is str and 0<len(content)<=MAX_RAW_CHARACTERS,
        'P147_raw_output_character_budget')
    value=json.loads(content,object_pairs_hook=_unique_pairs,parse_constant=_reject_constant)
    require(type(value) is dict and set(value)==set(FIELDS),'P147_exact_four_fields_required')
    patch={}
    for field in FIELDS:
        entry=value[field]
        require(type(entry) is dict and set(entry)=={'by_index','add'},'P147_field_shape')
        decisions=entry['by_index']
        expected={str(i) for i in range(len(old_state[field]))}
        require(type(decisions) is dict and set(decisions)==expected,'P147_exact_old_index_keys_required')
        require(type(entry['add']) is list,'P147_add_list_required')
        operations=dict(keep=[],update=[],delete=[],add=deepcopy(entry['add']))
        for index in range(len(old_state[field])):
            decision=decisions[str(index)]
            require(type(decision) is dict,'P147_single_action_object_required')
            action=decision.get('action')
            require(type(action) is str and action in ('keep','update','delete'),'P147_fixed_action_required')
            require(set(decision)==({'action','text'} if action=='update' else {'action'}),
                'P147_action_fields_required')
            if action=='update':
                operations['update'].append({'index':index,'text':decision['text']})
            else:
                operations[action].append(index)
        patch[field]=operations
    converted={'role':'assistant','content':json.dumps(patch,ensure_ascii=False,separators=(',',':'),allow_nan=False)}
    # Includes complete disjoint index coverage, nonempty <=2048-character
    # strings, output <=8192 characters, materialized <=8192, and <=32/field.
    return parse_update_patch(converted,'stop',old_state)


def parse_and_apply(message,finish_reason,old_state):
    patch=to_legacy_patch(message,finish_reason,old_state)
    return apply_update_patch(old_state,patch)


class IndexedStateUpdateCheckpoint(StateUpdateCheckpoint):
    """Only second-update response decoding changes; the P144 state rules remain.

Known-paid invalid indexed output is rejected atomically, including an old
operation-list response that would pass P144 by itself. It is not repaired or
retried. The unchanged actor may continue with its previous history view.
"""
    def __init__(self,mode):
        super().__init__(mode)
        self.indexed_conversions=[]

    def close_separate(self,archive,message,finish_reason,*,usage_known):
        if not (self.pending and self.pending.get('update_requested')):
            return super().close_separate(archive,message,finish_reason,usage_known=usage_known)
        if usage_known is not True:
            self._blocked=True
            raise ValueError('unknown_usage_blocks_rolling_continuation')
        self._check(archive)
        require(self.pending['stage']=='offered' and archive==self.pending['before'],
            'update_offer_archive_binding_required')
        record=dict(opportunity_index=self.pending['opportunity_index'],
            raw_response_sha256=digest(message),finish_reason=finish_reason,
            update_prior_state_sha256=self.pending['update_prior_state_sha256'],
            input_representation=VERSION,status='pending',repair_applied=False,
            host_conversion_not_model_output=True)
        self.indexed_conversions.append(record)
        if not self._update_state_matches():
            record['status']='stale_update_state'
            return self._close(archive,None,'stale_update_state')
        try:
            patch=to_legacy_patch(message,finish_reason,self.pending['update_prior_state'])
        except (ValueError,TypeError,RecursionError) as error:
            record.update(status='rejected',rejection_type=type(error).__name__)
            return self._close(archive,None,
                'update_finish_not_stop' if finish_reason!='stop' else 'invalid_update_patch')
        converted={'role':'assistant','content':json.dumps(patch,ensure_ascii=False,separators=(',',':'))}
        record.update(status='converted_and_strictly_validated',
            converted_message_sha256=digest(converted),converted_patch_sha256=digest(patch),
            unchanged_P144_parser_reapplied=True)
        return super().close_separate(archive,converted,'stop',usage_known=True)
