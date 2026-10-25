"""Lossless receipt-table formatting shared by both ordinary execution policies.

Only a displayed run_python observation's API receipt index changes shape.
Inner records, archive reads, stdout, errors, dispatch and completion retain
their existing paths. JSON byte counts are formatting measurements, not model
token savings. This module starts no model, container, or environment API.
"""
from dataclasses import dataclass
import time

import code_agent_interface
from context_preservation import compact


RECEIPT_COLUMNS = ('span_id', 'api', 'api_request_sent')
RECEIPT_GUIDE = '''
run_python's api_receipts index uses {"columns":["span_id","api","api_request_sent"],
"rows":[[span_id,api,api_request_sent],...]}. Each row preserves one receipt in
its original order, including repeated IDs and true/false request-sent flags.
These are archive references; read_span still retrieves the original API record.
'''


def _validate_values(span_id, api, sent):
    if (type(span_id) is not str or not span_id
            or type(api) is not str or not api or type(sent) is not bool):
        raise ValueError('receipt_requires_nonempty_string_ID_API_and_boolean_sent')


def encode_receipts(receipts):
    """Encode exactly the supported list shape, without dropping any field."""
    if type(receipts) is not list:
        raise ValueError('receipt_list_required')
    rows = []
    for receipt in receipts:
        if type(receipt) is not dict or set(receipt) != set(RECEIPT_COLUMNS):
            raise ValueError('exact_receipt_fields_required')
        values = [receipt[column] for column in RECEIPT_COLUMNS]
        _validate_values(*values)
        rows.append(values)
    return {'columns': list(RECEIPT_COLUMNS), 'rows': rows}


def decode_receipts(table):
    """Strict inverse of encode_receipts; return independent ordinary dicts."""
    if (type(table) is not dict or set(table) != {'columns', 'rows'}
            or type(table['columns']) is not list
            or any(type(column) is not str for column in table['columns'])
            or table['columns'] != list(RECEIPT_COLUMNS)
            or type(table['rows']) is not list):
        raise ValueError('exact_receipt_table_required')
    receipts = []
    for row in table['rows']:
        if type(row) is not list or len(row) != len(RECEIPT_COLUMNS):
            raise ValueError('three_column_receipt_row_required')
        _validate_values(*row)
        receipts.append(dict(zip(RECEIPT_COLUMNS, row)))
    return receipts


@dataclass
class ReceiptMetrics:
    record_calls: int = 0
    transformed_observations: int = 0
    receipt_rows: int = 0
    original_compact_json_bytes: int = 0
    table_compact_json_bytes: int = 0
    transform_seconds: float = 0.0
    validation_failures: int = 0

    def summary(self):
        return {
            'record_calls': self.record_calls,
            'transformed_observations': self.transformed_observations,
            'receipt_rows': self.receipt_rows,
            'original_compact_json_bytes': self.original_compact_json_bytes,
            'table_compact_json_bytes': self.table_compact_json_bytes,
            'original_minus_table_bytes': (
                self.original_compact_json_bytes - self.table_compact_json_bytes),
            'transform_seconds': self.transform_seconds,
            'validation_failures': self.validation_failures,
            'byte_scope': 'UTF-8 compact JSON of api_receipts only; not tokens',
            'extra_environment_API_requests': 0,
            'extra_model_calls': 0,
        }


class CompactReceiptRecorder:
    """Preserve record order, return values, flags and callback mutations.

The existing executor owns the outer row. Replacing only its receipt field in
place keeps the executor's returned rows identical to the caller's recorded
rows, including mutations made by the caller. Inner rows and read_span outputs
are passed to the original recorder as the same objects, without modification.
"""
    def __init__(self, record, *, metrics=None):
        if not callable(record):
            raise TypeError('callable_record_required')
        if metrics is not None and not isinstance(metrics, ReceiptMetrics):
            raise TypeError('ReceiptMetrics_required')
        self.record = record
        self.metrics = ReceiptMetrics() if metrics is None else metrics

    def __call__(self, row, *args, **kwargs):
        self.metrics.record_calls += 1
        # Forward the original calling convention exactly, including omitted
        # display=True. This also supports record(row)-only outer callbacks.
        if len(args) > 1 or args and 'display' in kwargs:
            return self.record(row, *args, **kwargs)
        display = args[0] if args else kwargs.get('display', True)
        action = row.get('action') if type(row) is dict else None
        observation = row.get('observation') if type(row) is dict else None
        if (display is True and type(action) is dict
                and action.get('name') == 'run_python'
                and type(observation) is dict and 'api_receipts' in observation):
            began = time.perf_counter()
            try:
                original = observation['api_receipts']
                table = encode_receipts(original)
                original_bytes = len(compact(original).encode('utf-8'))
                table_bytes = len(compact(table).encode('utf-8'))
                observation['api_receipts'] = table
                self.metrics.transformed_observations += 1
                self.metrics.receipt_rows += len(table['rows'])
                self.metrics.original_compact_json_bytes += original_bytes
                self.metrics.table_compact_json_bytes += table_bytes
            except ValueError:
                self.metrics.validation_failures += 1
                raise
            finally:
                self.metrics.transform_seconds += time.perf_counter() - began
        return self.record(row, *args, **kwargs)

    def summary(self):
        return self.metrics.summary()


def execute_response(message, catalog, bridge, prior, record, *, receipt_metrics=None,
                     **kwargs):
    """Use the unchanged executor with the common, lossless record wrapper.

All ordinary executor keyword arguments, including an injected program, pass
through unchanged. Pass a ReceiptMetrics instance to accumulate across turns.
"""
    recorder = CompactReceiptRecorder(record, metrics=receipt_metrics)
    return code_agent_interface.execute_response(
        message, catalog, bridge, prior, recorder, **kwargs)
