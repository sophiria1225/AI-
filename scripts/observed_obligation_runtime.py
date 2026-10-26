"""Host-only accounting around observed field obligations; no API is dispatched."""
from copy import deepcopy
import time

from observed_field_obligations import ObservedFieldObligations, ObligationQueryError
from public_output_grounding import digest, require
from run_context_comparison import write_json


class ObservedObligationRuntime:
    def __init__(self, public_task, output, *, execution_scope, public_source_directory):
        self.store = ObservedFieldObligations(public_task, execution_scope=execution_scope,
                                             public_source_directory=public_source_directory)
        self.output = output
        self.execution_scope_sha256 = digest(execution_scope)
        self.records, self.captures, self.queries = [], [], []
        self.failed = False
        self.error_type = None
        self.wall_seconds = 0.0

    def ready(self):
        if self.failed:
            raise RuntimeError('observed_obligation_runtime_stopped')

    def observe(self, event, span):
        self.ready()
        began = time.monotonic()
        try:
            self.store.observe(event, span)
            self.records.append(dict(index=len(self.records), span_id=span['id'],
                event_sha256=digest(event), span_sha256=digest(span)))
        except Exception as error:
            self.failed, self.error_type = True, type(error).__name__
            raise RuntimeError('obligation_observation_or_capture_contract_failed') from error
        finally:
            self.wall_seconds += time.monotonic() - began

    def capture(self, *, revision, source_boundary_sha256):
        self.ready()
        require(type(revision) is int and revision > 0, 'positive_checkpoint_revision_required')
        began = time.monotonic()
        try:
            packet = self.store.capture()
            self.captures.append(dict(index=len(self.captures), checkpoint_revision=revision,
                after_records=len(self.records), records_sha256=digest(self.records),
                source_boundary_sha256=source_boundary_sha256, packet=deepcopy(packet)))
            return packet
        except Exception as error:
            self.failed, self.error_type = True, type(error).__name__
            raise RuntimeError('obligation_observation_or_capture_contract_failed') from error
        finally:
            self.wall_seconds += time.monotonic() - began
            self.save()

    def query(self, arguments, *, call_id, tool_index):
        """Transport errors return feedback; core failures stop this runtime."""
        self.ready()
        began = time.monotonic()
        entry = dict(index=len(self.queries), call_id=call_id, tool_index=tool_index,
            after_records=len(self.records), records_sha256=digest(self.records),
            arguments_sha256=digest(arguments), arguments=deepcopy(arguments),
            status='started', environment_API_requests=0)
        self.queries.append(entry)
        try:
            value = self.store.query(**arguments)
            entry.update(status='returned', observation_sha256=digest(value), observation=deepcopy(value))
            return value
        except ObligationQueryError as error:
            # Caller-controlled invalid handles/cursors are ordinary tool feedback.
            value = {'status': 'invalid_obligation_query', 'error': str(error)}
            entry.update(status='rejected', observation_sha256=digest(value), observation=deepcopy(value))
            return value
        except Exception as error:
            self.failed, self.error_type = True, type(error).__name__
            entry.update(status='failed', error_type=type(error).__name__)
            raise RuntimeError('obligation_query_contract_failed') from error
        finally:
            entry['wall_seconds'] = time.monotonic() - began
            self.wall_seconds += entry['wall_seconds']
            self.save()

    def save(self):
        write_json(self.output / 'obligation_records_private.json', self.records)
        write_json(self.output / 'obligation_captures_private.json', self.captures)
        write_json(self.output / 'obligation_queries_private.json', self.queries)

    def summary(self):
        self.save()
        return dict(contract_failed=self.failed, error_type=self.error_type,
            observed_records=len(self.records), checkpoint_captures=len(self.captures),
            queries=len(self.queries), query_rejections=sum(q['status']=='rejected' for q in self.queries),
            query_failures=sum(q['status']=='failed' for q in self.queries),
            records_sha256=digest(self.records), captures_sha256=digest(self.captures),
            queries_sha256=digest(self.queries), wall_seconds=self.wall_seconds,
            extra_model_calls=0, extra_environment_API_requests=0,
            source_program_changed=False, official_task_success_claimed=False)
