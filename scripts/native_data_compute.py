"""Ordinary Python over selected public receipts; no task/environment access.

Preparation for a stronger baseline, not a completion verifier or new method.
The caller must provide the receipt snapshot from before the model response.
"""
import copy
import json
from pathlib import Path

from container_data_python import run_program

COMPUTE_TOOL = {
    'type': 'function',
    'function': {
        'name': 'compute_data',
        'description': (
            'Run standard Python 3.12 with the standard library over selected prior '
            'public receipts. observations is a list of objects with id, action and '
            'observation. Set result to a string (use json.dumps for structured data). '
            'csv_text(rows, headers) is available for formatting. No environment APIs, '
            'files, network or persistent variables are accessible. The code runs in '
            'a fresh isolated container. This tool does not change the AppWorld state '
            'or establish task completion. Reuse recorded span IDs; do not guess future IDs.'),
        'parameters': {
            'type': 'object',
            'properties': {
                'span_ids': {'type': 'array', 'items': {'type': 'string'},
                             'minItems': 1, 'maxItems': 128, 'uniqueItems': True},
                'code': {'type': 'string', 'maxLength': 20000},
            },
            'required': ['span_ids', 'code'],
            'additionalProperties': False,
        },
    },
}


def validate_arguments(arguments):
    if type(arguments) is not dict or set(arguments) != {'span_ids', 'code'}:
        raise ValueError('compute_data requires only span_ids and code')
    ids, source = arguments['span_ids'], arguments['code']
    if (type(ids) is not list or not 1 <= len(ids) <= 128
            or any(type(s) is not str or not s for s in ids)
            or len(ids) != len(set(ids))):
        raise ValueError('select 1 to 128 distinct recorded span IDs')
    if type(source) is not str or not source or len(source) > 20000:
        raise ValueError('code must contain 1 to 20000 characters')
    return copy.deepcopy(arguments)


def selected_receipts(span_ids, snapshot):
    rows = []
    for sid in span_ids:
        if sid not in snapshot or snapshot[sid].get('id') != sid:
            raise ValueError('span is not in the prior public receipt snapshot')
        # Do not copy assistant reasoning, labels or private metadata, even when a
        # caller accidentally includes such fields in its receipt object.
        rows.append({k: copy.deepcopy(snapshot[sid][k])
                     for k in ('id', 'action', 'observation')})
    return rows


def compute(arguments, snapshot, *, storage_root, record_dir, timeout=10):
    args = validate_arguments(arguments)
    observations = selected_receipts(args['span_ids'], snapshot)
    result = run_program(args['code'], observations, storage_root=storage_root,
                         record_dir=record_dir, timeout=timeout)
    receipt = {
        'computation_status': result['status'],
        'source_span_ids': args['span_ids'],
        'environment_api_requests': 0,
        'environment_state_changed': False,
        'meaning': 'Output of model-provided code, not independent verification of the task.',
    }
    if result['status'] == 'ok':
        receipt['content'] = result['content']
    else:
        error = Path(record_dir)/'stderr_private.txt'
        if error.is_file():
            # This is container stderr from code and selected public inputs only.
            receipt['stderr_tail'] = error.read_bytes()[-8192:].decode('utf-8', errors='replace')
    return receipt, {k: v for k, v in result.items() if k != 'content'}
