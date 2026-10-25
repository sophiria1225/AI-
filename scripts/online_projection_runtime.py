"""P125 online adapter with the common existing public-schema error feedback.

The P124 projection engine remains unchanged. Feedback decorates the typed
ordinary reply before its exact error is retained by ProjectionApiChannel.
No explicit read-view capability or model-visible mechanism guide is added.
"""
from collections import Counter
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import time

from automatic_projection_runtime import AutomaticProjectionProgram, AutomaticProjectionHost
from contract_comparison import FeedbackProgram


class OnlineProjectionHost(AutomaticProjectionHost):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.control_wall_seconds_including_backend = 0.0
        self.projection_lookup_wall_seconds = 0.0

    def request(self, packet):
        began = time.monotonic()
        try:
            return super().request(packet)
        finally:
            elapsed = time.monotonic() - began
            self.control_wall_seconds_including_backend += elapsed
            if type(packet) is dict and packet.get('op') == 'projection_lookup':
                self.projection_lookup_wall_seconds += elapsed


class OnlineProjectionProgram(AutomaticProjectionProgram):
    host_class = OnlineProjectionHost

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.feedback = FeedbackProgram(lambda source, observations, channel, **kw: channel,
                                        'public_schema')
        self.program_rows = []

    def make_channel(self, channel):
        wrapped = super().make_channel(channel)
        wrapped.receipted = self.feedback('', [], wrapped.receipted)
        return wrapped

    def __call__(self, source, observations, channel, **kwargs):
        began = time.monotonic()
        row = {'program': Path(kwargs['record_dir']).name,
               'source_sha256': hashlib.sha256(source.encode()).hexdigest(),
               'status': 'incomplete', 'budget_before': self.budget.snapshot()}
        self.program_rows.append(row)
        try:
            result = super().__call__(source, observations, channel, **kwargs)
            row['status'] = result['status']
            return result
        finally:
            row.update(wall_seconds=time.monotonic() - began, budget_after=self.budget.snapshot())
            path = Path(kwargs['record_dir']) / 'projection_program_private.json'
            row['evidence_recorded'] = path.is_file()
            if path.is_file():
                evidence = json.loads(path.read_text())
                row.update({key: deepcopy(evidence[key]) for key in (
                    'source_sha256', 'transformed_sha256', 'executed_source_sha256',
                    'static_eligible', 'static_reason', 'execution_transform_report',
                    'projection_failed', 'control_requests', 'control_request_bytes', 'control_reply_bytes')})
                row['evidence_sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
            forwarding = Path(kwargs['record_dir']) / 'projection_schema_forwarding_private.json'
            row['schema_evidence_recorded'] = forwarding.is_file()
            if forwarding.is_file():
                evidence = json.loads(forwarding.read_text())
                row.update(schema_deliveries=evidence['schema_deliveries'],
                           schema_reply_wire_bytes=evidence['reply_wire_bytes'])
                row['schema_evidence_sha256'] = hashlib.sha256(forwarding.read_bytes()).hexdigest()

    def summary(self):
        host = self.host
        events = host.projection_events if host else []
        kinds = Counter(event['kind'] for event in events)
        reports = [report for row in self.program_rows for report in row.get('execution_transform_report', [])]
        reasons = Counter(report['reason'] for report in reports)
        known = [row for row in self.program_rows if row['evidence_recorded']]
        schema_known = [row for row in self.program_rows if row['schema_evidence_recorded']]
        return {'policy': self.policy, 'budget': self.budget.snapshot(),
            'program_attempts': len(self.program_rows), 'program_evidence_records': len(known),
            'control_accounting_complete': len(known) == len(self.program_rows),
            'schema_accounting_complete': len(schema_known) == len(self.program_rows),
            'static_eligible_programs': sum(row['static_eligible'] for row in known),
            'transformed_programs': sum(report['transformed'] for report in reports),
            'execution_report_reasons': dict(reasons),
            'ordinary_complete_cache_hits': host.ordinary_complete_reuses if host else 0,
            'projection_lookup_requests': sum(kinds[k] for k in ('partial', 'complete', 'miss')),
            'projection_partial_hits': kinds['partial'],
            'projection_complete_lookup_hits': kinds['complete'],
            'projection_lookup_misses': kinds['miss'], 'projection_failure_events': kinds['failed'],
            'projection_failed': host.projection_failed if host else False,
            'known_control_requests': sum(row['control_requests'] for row in known),
            'known_control_request_bytes': sum(row['control_request_bytes'] for row in known),
            'known_control_reply_bytes': sum(row['control_reply_bytes'] for row in known),
            'schema_deliveries': sum(row['schema_deliveries'] for row in schema_known),
            'known_schema_reply_wire_bytes': sum(row['schema_reply_wire_bytes'] for row in schema_known),
            'program_wall_seconds': sum(row['wall_seconds'] for row in self.program_rows),
            'control_wall_seconds_including_backend': host.control_wall_seconds_including_backend if host else 0.0,
            'projection_lookup_wall_seconds': host.projection_lookup_wall_seconds if host else 0.0,
            'timing_counts_inside_task_wall_not_additional_cost': True,
            'feedback': self.feedback.summary(),
            'ordinary_cache_shared_between_policies': True,
            'partial_values_registered_as_full_cache_entries': False,
            'explicit_read_view_interface_exposed': False,
            'extra_model_calls': 0, 'automatic_retries': 0}
