"""Fixed one-time history/runtime interventions, not an adaptive method.

Only complete public assistant/tool turns are reconstructed. Hidden reasoning,
evaluation results and future trajectory values are never inserted.
"""
import copy
import json

from native_conversation import NativeConversation, recover_turn

ARMS = ('full_keep', 'recent_keep', 'full_reset', 'recent_reset')
BOUNDARY_CALL = 4


def split_turns(messages):
    if len(messages) < 2 or [m['role'] for m in messages[:2]] != ['system', 'user']:
        raise ValueError('missing original system/task prefix')
    turns = []
    position = 2
    while position < len(messages):
        first = messages[position]
        if first.get('role') != 'assistant':
            raise ValueError('orphaned tool or user message')
        count = len(first.get('tool_calls') or []) or 1
        turn = messages[position:position+count+1]
        recover_turn(turn)
        turns.append(copy.deepcopy(turn))
        position += count+1
    return turns


def handoff_conversation(messages, task, arm):
    if arm not in ARMS:
        raise ValueError('unknown factor cell')
    turns = split_turns(messages)
    if len(turns) != BOUNDARY_CALL:
        raise ValueError('only the fixed fourth-response boundary')
    history, runtime = arm.split('_')
    notice = ('\nOne-time handoff: the simulated environment and public API schema set '
              'are unchanged. All prior public API receipts remain available through '
              'read_span or span_ids. Continue the original task using the current state. ')
    notice += ('The Python variables, functions and imports from earlier programs are retained. '
               if runtime == 'keep' else
               'The Python interpreter has been restarted once; no user variables, functions '
               'or imports from earlier programs remain. ')
    notice += 'Subsequent run_python calls share this task-local interpreter as described above.'
    conversation = NativeConversation(messages[0]['content']+notice, task)
    if conversation.messages()[1] != messages[1]:
        raise ValueError('public task changed')
    retained = turns if history == 'full' else turns[-1:]
    for turn in retained:
        conversation.append(turn[0], recover_turn(turn))
    return conversation, {
        'source_turns': len(turns), 'retained_turns': len(retained),
        'runtime_retained': runtime == 'keep', 'one_time_history_removal': True,
        'all_public_receipts_still_accessible': True,
        'accurate_runtime_notice_differs_by_condition': True}


def boundary_object(trial, manifest, name):
    entry = manifest['files'][name]
    return json.loads((trial/'boundaries/objects'/entry['sha256']).read_text())


def prefix_at_fixed_boundary(trial):
    from native_boundary_record import verify_boundary
    checkpoint = f'call_{BOUNDARY_CALL:03d}'
    verify_boundary(trial/'boundaries', checkpoint)
    manifest = json.loads((trial/'boundaries/manifests'/f'{checkpoint}.json').read_text())
    state = manifest['state']
    if state['model_calls'] != BOUNDARY_CALL or state['declared_complete']:
        raise ValueError('fixed boundary is not an eligible unfinished state')
    result = {'manifest': manifest, 'checkpoint_id': checkpoint}
    for name in ('spans', 'events', 'usage', 'conversation_private', 'public_task'):
        result[name] = boundary_object(trial, manifest, 'harness/'+name+'.json')
    if len(result['usage']) != BOUNDARY_CALL or any(c['status'] != 'ok' for c in result['usage']):
        raise ValueError('source prefix has unknown model usage')
    if len(split_turns(result['conversation_private'])) != BOUNDARY_CALL:
        raise ValueError('source public conversation boundary differs')
    if any(e['effects_unknown'] for e in result['events']):
        raise ValueError('source API effect is unknown')
    if sum(e['api_request_sent'] for e in result['events']) != state['api_requests']:
        raise ValueError('prefix API accounting differs')
    if set(result['spans']) != {e['span_id'] for e in result['events']}:
        raise ValueError('prefix receipt identities differ')
    return result


def replay_environment(prefix, catalog, bridge, db_directory, *, deadline, clock, accounting=None):
    """Rebuild an isolated simulated world; compare every public response + DB."""
    from probe_prefix_replay import db_hashes
    from recorded_python_replay import canonical
    account = accounting if accounting is not None else {}
    account.update(api_requests=0, observation_matches=0, db_files_match=False,
                   unknown_effect_requests=0, full_process_restore_claim=False)
    for event in prefix['events']:
        if event['stage'] != 'python_api':
            continue
        span = prefix['spans'][event['span_id']]
        if not event['api_request_sent']:
            continue
        if clock() >= deadline:
            raise TimeoutError('environment reconstruction deadline')
        decoded = catalog.decode(span['action'])
        account['api_requests'] += 1
        try:
            response = bridge.request({'op': 'call', 'call': decoded})
        except Exception:
            account['unknown_effect_requests'] += 1
            raise
        observation = response['result'] if response['ok'] else {'api_error': response['error']}
        exposed = catalog.expose_requested_document(decoded) if response['ok'] else []
        if (canonical(observation) != canonical(span['observation'])
                or exposed != event['new_tools']):
            raise ValueError('environment replay observation differs')
        account['observation_matches'] += 1
    expected = {n: e['sha256'] for n, e in prefix['manifest']['files'].items() if n.startswith('dbs/')}
    actual = db_hashes(db_directory)
    if actual != expected:
        raise ValueError('environment replay saved DB bytes differ')
    if sorted(catalog.visible) != prefix['manifest']['state']['visible_api_schemas']:
        raise ValueError('environment replay discovered schema set differs')
    account.update(db_files_match=True, db_files=len(actual))
    return account
