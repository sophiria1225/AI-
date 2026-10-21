"""Correct the baseline's declared provenance contract; not a new method."""
import copy
import json

from context_preservation import LEDGER_TOOL, validate_ledger
from native_ledger_memory import draft_messages

TASK_SOURCE = 'task'
CONTRACT_NOTE = """
Source registry: the supplied task object has source ID 'task'. Other allowed IDs
are the supplied interaction spans and cited sources in the previous ledger.
Every item needs at least one allowed source ID; use distinct, nonempty item keys.
The task is evidence of what was requested, not evidence an operation was executed.
An observation or completed operation still needs supporting interaction evidence.
Use only pending/done/uncertain/excluded. Do not invent an ID to fill a source list.
"""


class LedgerContract:
    def __init__(self, spans, previous=None):
        if TASK_SOURCE in spans:
            raise ValueError('task source ID collides with an interaction span')
        self.source_ids = set(spans) | {TASK_SOURCE}
        self.source_ids.update(s for item in (previous or {}).get('items', [])
                               for s in item['source_ids'])
        if not all(isinstance(s, str) for s in self.source_ids):
            raise ValueError('source IDs must be strings')

    def tool(self):
        tool = copy.deepcopy(LEDGER_TOOL)
        item = tool['function']['parameters']['properties']['items']['items']['properties']
        item['source_ids'].update(minItems=1, items={'type': 'string', 'enum': sorted(self.source_ids)})
        # The legacy schema reuses STR for several fields. Do not modify that
        # shared dictionary inside the deep copy and tighten unrelated fields.
        item['key'] = dict(item['key'], minLength=1)
        return tool

    def validate(self, value):
        if not isinstance(value, dict) or set(value) != {'items', 'constraints', 'unresolved'}:
            raise ValueError('ledger fields must match the declared contract')
        if not isinstance(value.get('items'), list):
            raise ValueError('items must be an array')
        for item in value['items']:
            if not isinstance(item, dict) or set(item) != {'key', 'requirement', 'status', 'source_ids'}:
                raise ValueError('item fields must match the declared contract')
        return validate_ledger(value, self.source_ids)


def inputs(case, variant, page_limit):
    """Same task, spans and inert API descriptions in both variants."""
    messages = draft_messages(case['task'], case['spans'], list(case['spans']), None,
                              case['tools'], page_limit)
    if variant == 'legacy':
        return messages, copy.deepcopy(LEDGER_TOOL)
    if variant != 'aligned':
        raise ValueError('unknown contract variant')
    messages[0]['content'] += CONTRACT_NOTE
    body = json.loads(messages[1]['content'])
    body['task_source_id'] = TASK_SOURCE
    messages[1]['content'] = json.dumps(body, ensure_ascii=False, separators=(',', ':'))
    return messages, LedgerContract(case['spans']).tool()


def validate(value, case, variant):
    if variant == 'legacy':
        return validate_ledger(value, set(case['spans']))
    if variant == 'aligned':
        return LedgerContract(case['spans']).validate(value)
    raise ValueError('unknown contract variant')
