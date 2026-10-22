"""Ordinary output-only masking and runtime inventory comparison.

This changes one input view at a fixed boundary. It never changes source receipts,
API effects, Python bindings or later turns. This is not a novel relevance policy.
"""
import copy
import json
import time

from context_preservation import compact
from handoff_factors import handoff_conversation, split_turns
from native_conversation import NativeConversation, recover_turn
from recorded_python_replay import RecordedChannel
from runtime_inventory import INVENTORY_CODE, format_inventory, validate_inventory

ARMS = ('full_keep', 'stdout_mask_keep', 'stdout_mask_index_keep')
COMMON_NOTICE = (
    '\nAt this boundary, some older successful Python stdout may be replaced by an '
    'explicit omission marker. Commands, result status, errors and receipt IDs are retained. '
    'An omission is not an empty original output or evidence that a task succeeded. '
    'Use read_span for the original outer receipt, or span_ids in run_python. '
    'Do not repeat an external operation merely to recover its old output. '
    'The original archived observation is historical; check current state when needed.'
)


def make_view(messages, task, arm, *, inventory_text=None):
    if arm not in ARMS:
        raise ValueError('unknown output view')
    if (arm == 'stdout_mask_index_keep') != (inventory_text is not None):
        raise ValueError('inventory belongs only to indexed condition')
    base, meta = handoff_conversation(messages, task, 'full_keep', 8)
    original = base.messages()
    prompt = original[0]['content'] + COMMON_NOTICE
    if inventory_text is not None:
        prompt += '\n' + inventory_text
    view = NativeConversation(prompt, task)
    turns = split_turns(original)
    changes = []
    for number, turn in enumerate(turns, 1):
        spans = recover_turn(turn)
        for span in spans:
            obs = span['observation']
            if (arm == 'full_keep' or number == len(turns)
                    or not span['action'] or span['action']['name'] != 'run_python'
                    or type(obs) is not dict or obs.get('status') != 'ok'
                    or obs.get('error') or obs.get('unknown_effects')
                    or obs.get('declared_complete') or type(obs.get('stdout')) is not str
                    or not obs['stdout']):
                continue
            replacement = copy.deepcopy(obs)
            replacement['stdout'] = (
                '[Older stdout omitted from this input view. '
                f'Read archived span {span["id"]} for the original recorded output.]')
            replacement['stdout_view'] = {
                'omitted': True, 'source_span_id': span['id'],
                'original_characters': len(obs['stdout']),
                'original_stdout_truncated': obs.get('stdout_truncated', False)}
            before, after = len(compact(obs)), len(compact(replacement))
            # Do not lengthen a short result merely to label it as omitted.
            if after >= before:
                continue
            changes.append({'turn': number, 'span_id': span['id'],
                            'original_stdout_characters': len(obs['stdout']),
                            'serialized_observation_characters_removed': before - after})
            span['observation'] = replacement
        view.append(turn[0], spans)
    meta.update(view_arm=arm, omission_scope='older successful stdout only; latest complete turn retained',
                masked_spans=changes, masked_span_count=len(changes),
                inventory_included=inventory_text is not None,
                original_archive_modified=False, novel_method_claim=False)
    return view, meta


def build_view(prefix, arm, session, storage, trial, schemas, catalog):
    started = time.monotonic()
    inventory_text, measurements = None, None
    if arm == 'stdout_mask_index_keep':
        channel = RecordedChannel({name: schemas[name] for name in catalog.visible}, [], schemas)
        result = session.run(INVENTORY_CODE, [], channel, storage_root=storage,
            record_dir=trial/'transfer_inventory', timeout=10)
        if (result['status'] != 'ok' or result['api_requests'] or channel.rows or channel.mismatch
                or result['stdout_truncated'] or not result['session_usable']):
            raise ValueError('inventory inspection failed or issued an API request')
        data = validate_inventory(json.loads(result['stdout']))
        inventory_text = format_inventory(data, catalog.visible)
        measurements = {'eligible_binding_count': data['eligible_binding_count'],
                        'listed_binding_count': len(data['bindings']),
                        'truncated': data['truncated'], 'visible_schema_count': len(catalog.visible),
                        'api_requests': 0, 'wall_seconds': result['wall_seconds']}
    view, meta = make_view(prefix['conversation_private'], prefix['public_task'], arm,
                           inventory_text=inventory_text)
    meta.update(inventory_measurement=measurements,
                transfer_wall_seconds=time.monotonic()-started,
                inventory_scope='Boundary availability only, not relevance, current truth or later variable state.')
    return view, meta
