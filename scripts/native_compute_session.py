"""Accounted ordinary computation over the pre-response public snapshot.

This is a comparator capability, not an independent verifier. It cannot fetch
environment state and deliberately cannot consume earlier results in the same
model response. Every attempt, including rejected inputs, is recorded.
"""
import hashlib
import json
from pathlib import Path
import time

from native_data_compute import compute, selected_receipts, validate_arguments
from container_data_python import prepare_payload


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    allow_nan=False).encode()).hexdigest()


class NativeComputeSession:
    def __init__(self, config, *, storage_root, output):
        if (set(config) != {'max_executions', 'timeout_seconds'}
                or type(config['max_executions']) is not int
                or not 1 <= config['max_executions'] <= 80
                or type(config['timeout_seconds']) not in (int, float)
                or not 0 < config['timeout_seconds'] <= 30):
            raise ValueError('invalid ordinary-compute controls')
        self.config = dict(config)
        self.storage_root, self.output = Path(storage_root), Path(output)
        self.records, self.snapshot, self.call_id = [], {}, None
        self.executions, self.fatal = 0, False

    def before_response(self, spans):
        # Deep-copy only public fields; no private assistant text or labels.
        self.snapshot = {row['id']: row for row in selected_receipts(list(spans), spans)}
        self.call_id = None

    def bind_response(self, call_id):
        self.call_id = call_id

    def invoke(self, arguments):
        if self.call_id is None:
            raise RuntimeError('compute response was not bound')
        started = time.monotonic()
        entry = {'attempt': len(self.records) + 1, 'call_id': self.call_id,
                 'execution_started': False}
        receipt = {}
        try:
            args = validate_arguments(arguments)
            observations = selected_receipts(args['span_ids'], self.snapshot)
            entry.update(source_span_ids=args['span_ids'], input_sha256=digest(observations),
                         code_sha256=hashlib.sha256(args['code'].encode()).hexdigest())
            prepare_payload(args['code'], observations, self.config['timeout_seconds'])
            if self.executions >= self.config['max_executions']:
                receipt = {'computation_status': 'not_executed',
                           'compute_limit_reached': True,
                           'environment_state_changed': False}
            else:
                self.executions += 1
                entry['execution_started'] = True
                folder = self.output/'compute'/f"attempt_{entry['attempt']:03d}"
                receipt, execution = compute(
                    args, self.snapshot, storage_root=self.storage_root, record_dir=folder,
                    timeout=self.config['timeout_seconds'])
                entry['execution'] = execution
                self.fatal |= execution['status'] == 'harness_error'
        except (ValueError, KeyError, TypeError) as exc:
            receipt = {'computation_status': 'input_error', 'compute_input_error': str(exc),
                       'environment_state_changed': False}
        except Exception as exc:
            self.fatal = True
            receipt = {'computation_status': 'harness_error', 'error_type': type(exc).__name__,
                       'environment_state_changed': False}
        finally:
            entry.update(status=receipt.get('computation_status', 'harness_error'),
                         receipt_sha256=digest(receipt), wall_seconds=time.monotonic()-started)
            self.records.append(entry)
            (self.output/'compute_records.json').write_text(
                json.dumps(self.records, ensure_ascii=False, indent=2)+'\n')
        return receipt

    def summary(self):
        return {'attempts': len(self.records), 'executions': self.executions,
                'wall_seconds': sum(r['wall_seconds'] for r in self.records),
                'status_counts': {s: sum(r['status'] == s for r in self.records)
                                  for s in sorted({r['status'] for r in self.records})},
                'fatal_harness_error': self.fatal,
                'environment_api_requests': 0,
                'scope': 'Ordinary model-provided Python; not independent task verification.'}
