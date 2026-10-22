"""Passive input attribution. Text equality is not dataflow or irrelevance.

These artificial inputs are used only for token counting, never generation.
The cumulative differences depend on the declared order and may be negative.
"""
import copy
import hashlib
import json

from context_preservation import compact
from documentation_exposure import DOCUMENTATION_APIS

COMPONENTS = ('tools', 'system', 'task', 'assistant_text', 'assistant_actions',
              'receipt_metadata', 'stdout_documentation_only', 'stdout_mixed',
              'stdout_other', 'stdout_uncertain')


def digest(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def documentation_renderings(value):
    """Only full deterministic serializations; no fields or fuzzy matches."""
    raw = value
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return {}
    if not isinstance(value, (dict, list)) or (
            isinstance(value, dict) and {'error', 'detail'} & value.keys()):
        return {}
    result = {'python_print': str(value) + '\n', 'raw_print': str(raw) + '\n'}
    for ascii_mode in (False, True):
        for indent in (None, 2, 4):
            result[f'json_{ascii_mode}_{indent}'] = json.dumps(
                value, ensure_ascii=ascii_mode, indent=indent) + '\n'
        result[f'compact_{ascii_mode}'] = json.dumps(
            value, ensure_ascii=ascii_mode, separators=(',', ':')) + '\n'
    return result


def receipt_group(observation, spans, events):
    """Describe recorded calls, without declaring the whole stdout a schema."""
    if type(observation) is not dict or not isinstance(observation.get('stdout'), str):
        raise ValueError('expected a complete recorded Python stdout field')
    receipts = observation.get('api_receipts')
    if not isinstance(receipts, list):
        raise ValueError('expected recorded API receipts')
    seen, docs, healthy = set(), [], True
    for receipt in receipts:
        sid = receipt.get('span_id')
        if not isinstance(sid, str) or sid in seen or sid not in spans or sid not in events:
            raise ValueError('missing or duplicate receipt correspondence')
        seen.add(sid)
        span, event = spans[sid], events[sid]
        action, obs = span.get('action'), span.get('observation')
        if (not isinstance(action, dict) or receipt.get('api') != action.get('name')
                or event.get('stage') != 'python_api'
                or receipt.get('api_request_sent') != event.get('api_request_sent')):
            raise ValueError('receipt identity or dispatch correspondence differs')
        valid = (event.get('api_request_sent') is True and not event.get('effects_unknown')
                 and isinstance(obs, dict) and 'observation' in obs
                 and set(obs) <= {'observation', 'declared_complete'}
                 and not obs.get('declared_complete'))
        if valid:
            payload = obs['observation']
            if isinstance(payload, str):
                try:
                    payload = json.loads(payload)
                except ValueError:
                    pass
            if isinstance(payload, dict) and {'error', 'detail'} & payload.keys():
                valid = False
        healthy &= valid
        if action['name'] in DOCUMENTATION_APIS:
            renderings = documentation_renderings(obs['observation']) if valid else {}
            healthy &= bool(renderings)
            docs.append((sid, renderings))
    healthy &= (observation.get('status') == 'ok' and not observation.get('error')
                and not observation.get('stdout_truncated') and not observation.get('unknown_effects')
                and not observation.get('declared_complete'))
    if not healthy or not receipts:
        group = 'uncertain'
    elif len(docs) == len(receipts):
        group = 'documentation_only'
    elif docs:
        group = 'mixed'
    else:
        group = 'other'
    return group, docs


def match_receipt_text(stdout, documentation):
    """Unique nonoverlapping whole-response matches, with ambiguity explicit.

    Even a unique match does not establish which expression printed it. Never
    turn the covered length into a safe-to-delete label or achievable savings.
    """
    if len({sid for sid, _ in documentation}) != len(documentation):
        raise ValueError('duplicate documentation identity')
    choices, absent, repeated = [], [], []
    for sid, renderings in documentation:
        positions = {}
        for renderer, text in renderings.items():
            if not text:
                raise ValueError('empty renderer is not evidence')
            start = stdout.find(text)
            while start >= 0:
                positions.setdefault((start, start + len(text)), []).append(renderer)
                start = stdout.find(text, start + 1)
        if not positions:
            absent.append(sid)
        elif len(positions) > 1:
            repeated.append(sid)
        else:
            (start, end), styles = next(iter(positions.items()))
            choices.append({'receipt_id': sid, 'start': start, 'end': end,
                            'renderers': sorted(styles)})
    conflicts = {a['receipt_id'] for a in choices for b in choices
                 if a is not b and max(a['start'], b['start']) < min(a['end'], b['end'])}
    # An ambiguous occurrence must not lend false certainty to another receipt.
    for sid, renderings in documentation:
        if sid not in repeated:
            continue
        for text in set(renderings.values()):
            start = stdout.find(text)
            while start >= 0:
                for choice in choices:
                    if max(start, choice['start']) < min(start + len(text), choice['end']):
                        conflicts.add(choice['receipt_id'])
                start = stdout.find(text, start + 1)
    matches = sorted((m for m in choices if m['receipt_id'] not in conflicts), key=lambda m: m['start'])
    covered_chars = sum(m['end'] - m['start'] for m in matches)
    covered_bytes = sum(len(stdout[m['start']:m['end']].encode('utf-8')) for m in matches)
    residue, previous = [], 0
    for match in matches:
        residue.append(stdout[previous:match['start']]); previous = match['end']
    residue.append(stdout[previous:])
    residue = ''.join(residue)
    if len(residue) + covered_chars != len(stdout) or (
            len(residue.encode('utf-8')) + covered_bytes != len(stdout.encode('utf-8'))):
        raise ValueError('text partition failed')
    return {'stdout_characters': len(stdout), 'stdout_utf8_bytes': len(stdout.encode('utf-8')),
            'stdout_sha256': digest(stdout), 'whole_response_matches': matches,
            'covered_characters': covered_chars, 'covered_utf8_bytes': covered_bytes,
            'unattributed_characters': len(residue), 'unattributed_sha256': digest(residue),
            'absent_receipts': absent, 'repeated_match_receipts': repeated,
            'overlapping_receipts': sorted(conflicts), 'dataflow_proven': False,
            'safe_to_remove_claim': False}


def cumulative_inputs(messages, tools, groups):
    """Count valid chat envelopes while restoring each declared component.

    Inputs must already be formatted for the model. Paged/fallback receipts are
    rejected rather than accidentally counted as unpaged observations.
    """
    if len(messages) < 2 or [m.get('role') for m in messages[:2]] != ['system', 'user']:
        raise ValueError('system and task must lead the recorded input')
    base = copy.deepcopy(messages)
    observations, seen = {}, set()
    for index, message in enumerate(base):
        message['content'] = ''
        if message.get('role') == 'assistant':
            for call in message.get('tool_calls', []):
                arguments = json.loads(call['function']['arguments'])
                if not isinstance(arguments, dict):
                    raise ValueError('unrepresentable action arguments')
                call['function']['arguments'] = '{}'
        elif index >= 2:
            if message.get('role') not in ('tool', 'user'):
                raise ValueError('unrecognized receipt role')
            value = json.loads(messages[index]['content'])
            if set(value) != {'span_id', 'observation'} or not isinstance(value['observation'], dict):
                raise ValueError('paged or fallback observation is outside the fixed accounting')
            sid = value['span_id']
            if sid in seen:
                raise ValueError('duplicate outer observation')
            seen.add(sid)
            if not isinstance(value['observation'].get('stdout'), str) or sid not in groups:
                raise ValueError('unclassified stdout')
            if groups[sid] not in ('documentation_only', 'mixed', 'other', 'uncertain'):
                raise ValueError('unknown receipt group')
            observations[index] = value
    if set(groups) != seen:
        raise ValueError('classification and actual input cohort differ')
    cases = [{'component': 'envelope', 'messages': copy.deepcopy(base), 'tools': []}]
    for component in COMPONENTS:
        if component in ('system', 'task'):
            index = 0 if component == 'system' else 1
            base[index] = copy.deepcopy(messages[index])
        elif component == 'assistant_text':
            for index, message in enumerate(base):
                if message['role'] == 'assistant':
                    message['content'] = messages[index]['content']
        elif component == 'assistant_actions':
            for index, message in enumerate(base):
                if message['role'] == 'assistant' and 'tool_calls' in message:
                    message['tool_calls'] = copy.deepcopy(messages[index]['tool_calls'])
        elif component == 'receipt_metadata':
            for index, value in observations.items():
                metadata = copy.deepcopy(value)
                metadata['observation']['stdout'] = ''
                base[index]['content'] = compact(metadata)
        elif component.startswith('stdout_'):
            for index, value in observations.items():
                if groups[value['span_id']] == component.removeprefix('stdout_'):
                    base[index]['content'] = messages[index]['content']
        cases.append({'component': component, 'messages': copy.deepcopy(base), 'tools': copy.deepcopy(tools)})
    if cases[-1]['messages'] != messages or cases[-1]['tools'] != tools:
        raise ValueError('full input was not exactly reconstructed')
    return cases


def token_increments(counts):
    names = ('envelope',) + COMPONENTS
    if list(counts) != list(names) or any(type(v) is not int or v < 1 for v in counts.values()):
        raise ValueError('complete ordered exact token counts required')
    previous, result = 0, {}
    for name, count in counts.items():
        result[name] = count - previous
        previous = count
    if sum(result.values()) != counts[names[-1]]:
        raise ValueError('token accounting identity failed')
    return result
