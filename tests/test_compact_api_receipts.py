"""Synthetic formatting and executor checks; no model/backend/container calls."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from compact_api_receipts import (
    CompactReceiptRecorder, RECEIPT_COLUMNS, ReceiptMetrics, decode_receipts,
    encode_receipts, execute_response)
from context_preservation import compact


def receipt(sid='s1', api='fixture__read', sent=True):
    return {'span_id': sid, 'api': api, 'api_request_sent': sent}


def outer(receipts):
    return {'action': {'name': 'run_python', 'arguments': '{}'},
            'api_request_sent': False, 'new_tools': [],
            'effects_unknown': False,
            'observation': {'status': 'execution_error', 'stdout': 'unchanged\n',
                'error': 'synthetic error', 'stdout_truncated': False,
                'unknown_effects': False, 'declared_complete': False,
                'api_requests': 1, 'api_receipts': receipts}}


class ReceiptCodecTests(unittest.TestCase):
    def test_empty_duplicates_order_types_and_independent_roundtrip(self):
        for source in ([], [receipt(), receipt('同じ', sent=False), receipt()]):
            with self.subTest(source=source):
                before = deepcopy(source)
                table = encode_receipts(source)
                self.assertEqual(table['columns'], list(RECEIPT_COLUMNS))
                self.assertEqual(decode_receipts(table), source)
                self.assertEqual(source, before)
                self.assertEqual(decode_receipts(json.loads(json.dumps(table))), source)
                if source:
                    decoded = decode_receipts(table)
                    self.assertTrue(all(type(r['api_request_sent']) is bool for r in decoded))
                    decoded[0]['span_id'] = 'different'
                    self.assertEqual(table['rows'][0][0], source[0]['span_id'])
                    table['rows'][0][0] = 'changed'
                    self.assertEqual(source, before)

    def test_encode_rejects_lossy_or_wrong_types(self):
        bad = [None, {}, (), [None], [dict(receipt(), extra=1)],
               [{'span_id': 's1', 'api': 'fixture__read'}],
               [receipt(sid=1)], [receipt(sid='')], [receipt(api=None)],
               [receipt(api='')], [receipt(sent=1)], [receipt(sent=0)],
               [receipt(sent='false')]]
        for value in bad:
            with self.subTest(value=value), self.assertRaises(ValueError):
                encode_receipts(value)

    def test_decode_rejects_ambiguous_or_malformed_tables(self):
        good = encode_receipts([receipt()])
        bad = [None, [], dict(good, extra=1), {'rows': good['rows']},
               dict(good, columns=list(reversed(RECEIPT_COLUMNS))),
               dict(good, columns=RECEIPT_COLUMNS), dict(good, rows=()),
               dict(good, rows=[('s1', 'fixture__read', True)]),
               dict(good, rows=[['s1', 'fixture__read']]),
               dict(good, rows=[['s1', 'fixture__read', 1]]),
               dict(good, rows=[['s1', 'fixture__read', False, None]])]
        for value in bad:
            with self.subTest(value=value), self.assertRaises(ValueError):
                decode_receipts(value)


class ReceiptRecorderTests(unittest.TestCase):
    def test_only_outer_python_index_changes_and_metrics_measure_actual_shape(self):
        calls = []
        def record(row, *args, **kwargs):
            calls.append((row, args, kwargs))
            row['caller_marker'] = len(calls)
            return f's{len(calls)}'
        recorder = CompactReceiptRecorder(record)
        original = [receipt(), receipt(sent=False), receipt()]
        row = outer(deepcopy(original))
        before = deepcopy(row)
        self.assertEqual(recorder(row), 's1')
        self.assertIs(calls[0][0], row)
        self.assertEqual(calls[0][1:], ((), {}))
        self.assertEqual(row['caller_marker'], 1)
        restored = deepcopy(row)
        restored.pop('caller_marker')
        restored['observation']['api_receipts'] = decode_receipts(
            restored['observation']['api_receipts'])
        self.assertEqual(restored, before)
        # Even a receipt-like payload inside an inner record is not formatted.
        inner = outer(deepcopy(original))
        inner_before = deepcopy(inner)
        self.assertEqual(recorder(inner, display=False), 's2')
        self.assertIs(calls[1][0], inner)
        self.assertEqual(calls[1][2], {'display': False})
        inner_before['caller_marker'] = 2
        self.assertEqual(inner, inner_before)
        read = outer(deepcopy(original))
        read['action']['name'] = 'read_span'
        read_before = deepcopy(read)
        self.assertEqual(recorder(read, True), 's3')
        self.assertEqual(calls[2][1:], ((True,), {}))
        read_before['caller_marker'] = 3
        self.assertEqual(read, read_before)
        report = recorder.summary()
        self.assertEqual(report['record_calls'], 3)
        self.assertEqual(report['transformed_observations'], 1)
        self.assertEqual(report['receipt_rows'], 3)
        self.assertEqual(report['original_compact_json_bytes'],
                         len(compact(original).encode('utf-8')))
        self.assertEqual(report['table_compact_json_bytes'],
                         len(compact(encode_receipts(original)).encode('utf-8')))
        self.assertGreaterEqual(report['transform_seconds'], 0)
        self.assertEqual(report['validation_failures'], 0)

    def test_empty_expansion_and_record_return_exception_are_not_hidden(self):
        sentinel = object()
        recorder = CompactReceiptRecorder(lambda row: sentinel)
        self.assertIs(recorder(outer([])), sentinel)
        self.assertLess(recorder.summary()['original_minus_table_bytes'], 0)
        error = RuntimeError('caller record failed')
        called = []
        def reject(row):
            called.append(row)
            raise error
        with self.assertRaises(RuntimeError) as caught:
            CompactReceiptRecorder(reject)(outer([]))
        self.assertIs(caught.exception, error)
        self.assertEqual(len(called), 1)

    def test_bad_index_is_rejected_before_callback_without_partial_mutation(self):
        calls = []
        recorder = CompactReceiptRecorder(calls.append)
        row = outer([receipt(), receipt(sent=1)])
        before = deepcopy(row)
        with self.assertRaises(ValueError):
            recorder(row)
        self.assertEqual(row, before)
        self.assertEqual(calls, [])
        self.assertEqual(recorder.summary()['validation_failures'], 1)
        self.assertEqual(recorder.summary()['transformed_observations'], 0)


class SyntheticCatalog:
    def decode(self, function):
        arguments = json.loads(function['arguments'])
        if function['name'] == 'read_span':
            return {'archive': True, **arguments}
        if function['name'] != 'fixture__read':
            raise ValueError('synthetic unknown API')
        return {'app': 'fixture', 'api': 'read', 'args': arguments}

    def expose_requested_document(self, action):
        return []


class SyntheticBridge:
    def __init__(self):
        self.calls = []

    def request(self, command):
        self.calls.append(deepcopy(command))
        return {'ok': True, 'result': {'observation': '{"value":7}',
                                     'declared_complete': False}}


class ReceiptExecutorTests(unittest.TestCase):
    def test_actual_executor_retains_inner_archive_flags_and_read_span(self):
        catalog, bridge = SyntheticCatalog(), SyntheticBridge()
        calls, archived, program_rows = [], {}, []
        def record(row, display=True):
            sid = f's{len(calls) + 1}'
            calls.append((row, display))
            archived[sid] = deepcopy(row)
            return sid
        def program(source, observations, channel, **kwargs):
            self.assertEqual(source, 'synthetic fixture; never executed')
            self.assertEqual(observations, [])
            for number, api in enumerate(('read', 'unknown'), 1):
                channel.exchange({'kind': 'api', 'id': number, 'app': 'fixture',
                                  'api': api, 'arguments': {}})
                program_rows.append(deepcopy(channel.rows[-1]))
                kwargs['on_record'](channel.rows[-1])
            return {'status': 'execution_error', 'stdout': 'exact stdout\n',
                    'stdout_truncated': False, 'api_requests': 1,
                    'declared_complete': False, 'unknown_effects': False,
                    'error': 'exact synthetic error'}
        reads = []
        def read_archive(sid, offset):
            reads.append((sid, offset))
            return deepcopy(archived[sid]['observation'])
        message = {'tool_calls': [
            {'function': {'name': 'run_python', 'arguments': json.dumps({
                'code': 'synthetic fixture; never executed', 'span_ids': []})}},
            {'function': {'name': 'read_span', 'arguments': json.dumps({
                'span_id': 's1', 'offset': 0})}}]}
        metrics = ReceiptMetrics()
        rows = execute_response(message, catalog, bridge, [], record,
            receipt_metrics=metrics, out=Path('.'), storage=Path('.'), call_id='fixture',
            remaining_api=lambda: 80, may_continue=lambda: True,
            remaining_wall=lambda: 30, read_archive=read_archive, program=program)
        self.assertEqual(len(bridge.calls), 1)  # Handwritten fake bridge only.
        self.assertEqual([display for _, display in calls], [False, False, True, True])
        self.assertEqual(rows[:2], program_rows)
        self.assertEqual(archived['s1'], program_rows[0])
        self.assertEqual(archived['s2'], program_rows[1])
        self.assertIs(calls[2][0], rows[2])
        self.assertEqual(decode_receipts(rows[2]['observation']['api_receipts']),
                         [receipt('s1'), receipt('s2', 'fixture__unknown', False)])
        self.assertEqual(rows[2]['observation']['stdout'], 'exact stdout\n')
        self.assertEqual(rows[2]['observation']['error'], 'exact synthetic error')
        self.assertEqual(rows[2]['observation']['api_requests'], 1)
        self.assertFalse(rows[2]['observation']['unknown_effects'])
        self.assertEqual(rows[3]['observation'], program_rows[0]['observation'])
        self.assertEqual(reads, [('s1', 0)])
        self.assertEqual(metrics.summary()['transformed_observations'], 1)
        self.assertEqual(metrics.summary()['receipt_rows'], 2)


if __name__ == '__main__':
    unittest.main()
