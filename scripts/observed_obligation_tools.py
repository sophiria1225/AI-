"""Common explicit observation-ledger tool for both P134 presentation policies."""
from copy import deepcopy
import json

from public_display import CODE_TOOLS
from public_output_grounding import require

GUIDE = '''
The harness can track which fields required by this public export request have
been observed in successful API results. This is limited public evidence, not
the database, a final evaluator, or proof of task completion. A checkpoint may
show observed_source_progress with collection status and missing fields.
The read_obligations tool reads this observed evidence. Call op="snapshot"
with handle=null, cursor=0, limit=16 to obtain the current evidence handle and
counts. Call op="page" with that handle, a cursor and limit from 1 to 32 for
observed entity IDs, missing title/artists fields, and already observed artist
IDs whose names are still missing. Follow next_cursor; a partial page is not a
complete list. Unknown or open enumeration does not mean zero remaining work.
A stale handle returns fresh metadata, not old rows; explicitly query the fresh
handle if needed. This tool makes no environment API call and does not retrieve
new facts, generate API arguments, write a CSV or delete anything. Its model
input/output and time still share the ordinary task budget. Existing variables,
raw receipts, read_span and discovered public APIs remain available.
'''

OBLIGATION_TOOL = {'type': 'function', 'function': {
    'name': 'read_obligations',
    'description': 'Inspect bounded missing-field obligations from already observed public API evidence. No new API data or task-success judgment.',
    'parameters': {'type': 'object', 'properties': {
        'op': {'type': 'string', 'enum': ['snapshot', 'page']},
        'handle': {'type': ['string', 'null'], 'maxLength': 64},
        'cursor': {'type': 'integer', 'minimum': 0},
        'limit': {'type': 'integer', 'minimum': 1, 'maximum': 32}},
        'required': ['op', 'handle', 'cursor', 'limit'], 'additionalProperties': False}}}
OBLIGATION_TOOLS = deepcopy(CODE_TOOLS) + [OBLIGATION_TOOL]


def checked_arguments(raw):
    args = json.loads(raw)
    require(type(args) is dict and set(args) == {'op', 'handle', 'cursor', 'limit'}, 'exact_obligation_arguments_required')
    require(args['op'] in ('snapshot', 'page') and type(args['cursor']) is int and args['cursor'] >= 0
        and type(args['limit']) is int and 1 <= args['limit'] <= 32, 'bounded_obligation_query_required')
    if args['op'] == 'snapshot':
        require(args['handle'] is None and args['cursor'] == 0, 'fresh_snapshot_requires_null_handle_and_zero_cursor')
    else:
        handle = args['handle']
        require(type(handle) is str and len(handle) == 64 and all(c in '0123456789abcdef' for c in handle),
                'page_requires_snapshot_handle')
    return args
