"""Ordinary pre-write public-evidence feedback or deterministic content repair.

Only the actual imminent target write is intercepted. No account deletion,
extra API, model request, hidden answer or speculative source is introduced.
The original program/wire stays intact; typed receipts describe the effective
API arguments. A separate host ledger binds both payloads to prior evidence.
"""
from copy import deepcopy
import json
from pathlib import Path
import time

from public_output_grounding import PublicExportMonitor, WRITES, digest, require
from region_projection_runtime import RegionProjectionProgram

MODES = ('off', 'feedback', 'repair')
GUIDE = '''
The harness records public-source evidence for the requested CSV export. A
pre-write check may leave the API arguments unchanged, reject a contradicted
target write before dispatch, or replace only its content with a deterministic
CSV justified by complete earlier public results. Unknown evidence never
authorizes replacement. A separate output_grounding_notice in the run_python
observation reports any rejection or replacement and its payload hashes.
An unsent rejection is not an API success. An attempted replacement does not
certify a successful write or completion. Raw receipts contain the effective
API arguments and exact API result; original program text remains archived.
The harness does not block, authorize, or perform account deletion for you.
'''


class OutputGroundingController:
    def __init__(self, monitor, *, mode):
        require(type(monitor) is PublicExportMonitor and mode in MODES,
                'trusted_monitor_and_fixed_output_mode_required')
        self.monitor, self.mode = monitor, mode
        self.entries, self.notices = [], []
        self.failed, self.error_type = False, None
        self.program = None
        self.wall_seconds = 0.0
        self.observed_events = 0

    def ready(self):
        require(not self.failed, 'output_grounding_contract_stopped')

    def fail(self, error):
        self.failed, self.error_type = True, type(error).__name__

    def decide(self, packet):
        self.ready()
        name = packet['app'] + '__' + packet['api']
        if name not in WRITES:
            return None, packet
        before = time.monotonic()
        try:
            assessment = self.monitor.propose(name, packet['arguments'],
                mode='repair' if self.mode == 'repair' else 'check')
            replacement = assessment.pop('replacement_args')
            change = ('repair' if self.mode == 'repair' and assessment['status'] == 'contradicted'
                      else 'feedback' if self.mode == 'feedback' and assessment['status'] == 'contradicted'
                      else 'pass')
            effective = deepcopy(packet)
            if change == 'repair':
                require(type(replacement) is dict and set(replacement) == set(packet['arguments'])
                        and all(replacement[k] == v for k,v in packet['arguments'].items() if k != 'content')
                        and type(replacement.get('content')) is str,
                        'only_content_may_be_repaired')
                effective['arguments'] = replacement
            else:
                require(replacement is None, 'replacement_requires_repair_and_contradiction')
            original_action = dict(app=packet['app'], api=packet['api'], args=packet['arguments'])
            effective_action = dict(app=effective['app'], api=effective['api'], args=effective['arguments'])
            entry = dict(index=len(self.entries), mode=self.mode, program=self.program,
                channel_request_id=packet['id'], action_name=name, decision=change,
                prior_record_count=self.observed_events, assessment=assessment,
                original_action_sha256=digest(original_action), effective_action_sha256=digest(effective_action),
                original_payload_sha256=digest(packet['arguments']),
                original_content_sha256=digest(packet['arguments'].get('content')),
                proposed_payload_sha256=digest(replacement) if replacement is not None else None,
                effective_payload_sha256=digest(effective['arguments']),
                effective_content_sha256=digest(effective['arguments'].get('content')),
                environment_API_requests=None, api_execution_nonce=None, outcome='pending',
                supported_backup_confirmed=False,
                record_bound=False, host_span_id=None, host_event_sha256=None,
                effective_span_sha256=None, reply_sha256=None, notice_emitted=False)
            self.entries.append(entry)
            return entry, effective
        except Exception as error:
            self.fail(error); raise
        finally:
            self.wall_seconds += time.monotonic()-before

    def bind_reply(self, entry, row, reply):
        require(type(row) is dict and type(row.get('api_request_sent')) is bool,
                'one_effective_API_record_required')
        fn=row['action']; args=json.loads(fn['arguments'])
        require(fn['name'] == entry['action_name'] and digest(args) == entry['effective_payload_sha256'],
                'effective_API_record_does_not_match_dispatch')
        receipt=row.get('api_execution')
        if entry['decision']=='feedback':
            require(row['api_request_sent'] is False and receipt is None and reply['ok'] is False,
                    'feedback_must_be_unsent_without_typed_receipt')
        if row['api_request_sent']:
            require(type(receipt) is dict and receipt.get('bridge_request_sent') is True,
                    'sent_write_requires_real_typed_receipt')
        entry.update(environment_API_requests=int(row['api_request_sent']),
            api_execution_nonce=receipt.get('nonce') if receipt else None,
            outcome=receipt['status'] if receipt else 'not_dispatched', reply_sha256=digest(reply))
        row['output_grounding_entry'] = entry['index']

    def observe(self, event, span, *, entry_index=None):
        self.ready()
        began=time.monotonic()
        try:
            if entry_index is not None:
                require(type(entry_index) is int and 0 <= entry_index < len(self.entries),
                        'existing_grounding_entry_required')
                entry=self.entries[entry_index]
                require(not entry['record_bound'] and event['stage']=='python_api'
                        and event['span_id']==span['id']
                        and digest(json.loads(span['action']['arguments']))==entry['effective_payload_sha256']
                        and int(event['api_request_sent'])==entry['environment_API_requests'],
                        'grounding_record_binding_changed')
                receipt=event.get('api_execution')
                require((receipt.get('nonce') if receipt else None)==entry['api_execution_nonce'],
                        'grounding_nonce_binding_changed')
                entry.update(record_bound=True,host_span_id=span['id'],
                    host_event_sha256=digest(event),effective_span_sha256=digest(span))
                if entry['decision'] in ('feedback','repair'):
                    self.notices.append(entry['index'])
            self.monitor.observe(event,span)
            if entry_index is not None:
                backup=self.monitor.backup
                entry['supported_backup_confirmed']=bool(entry['decision']=='repair'
                    and entry['original_content_sha256']!=entry['effective_content_sha256']
                    and entry['environment_API_requests']==1 and entry['outcome']=='returned'
                    and type(backup) is dict and backup.get('confirmed') is True
                    and backup.get('content_sha256')==entry['effective_content_sha256'])
            self.observed_events+=1
        except Exception as error:
            self.fail(error); raise
        finally:
            self.wall_seconds+=time.monotonic()-began

    def take_notice(self):
        if not self.notices:
            return None
        values=[]
        for index in self.notices:
            entry=self.entries[index]
            require(entry['record_bound'] and not entry['notice_emitted'],'grounding_notice_once_after_record')
            entry['notice_emitted']=True
            values.append({k:deepcopy(entry[k]) for k in ('index','decision','original_payload_sha256',
                'proposed_payload_sha256','effective_payload_sha256','outcome','environment_API_requests')})
            values[-1]['supported_backup_confirmed']=entry['supported_backup_confirmed']
        self.notices.clear()
        return dict(format='ordinary_output_grounding_notice_v1', interventions=values,
            task_quality_certified=False, account_deletion_authorized=False)

    def summary(self):
        return dict(mode=self.mode, contract_intact=not self.failed, error_type=self.error_type,
            write_checks=len(self.entries), feedback_blocks=sum(e['decision']=='feedback' for e in self.entries),
            repair_attempts=sum(e['decision']=='repair' for e in self.entries),
            grounding_sent_repairs=sum(e['decision']=='repair' and e['environment_API_requests']==1 for e in self.entries),
            grounding_repairs=sum(e['supported_backup_confirmed'] for e in self.entries),
            repaired_write_returns=sum(e['decision']=='repair' and e['outcome']=='returned' for e in self.entries),
            incomplete_write_records=sum(not e['record_bound'] for e in self.entries),
            observed_records=self.observed_events, pending_notices=len(self.notices),
            wall_seconds=self.wall_seconds, ledger_sha256=digest(self.entries),
            monitor=self.monitor.summary(), extra_model_calls=0, extra_API_requests=0,
            deletion_interventions=0, source_program_changed=False,
            ordinary_control_not_novel=True, task_quality_established=False)


class GroundedReceiptExchange:
    """Inside shared reservations, before the one ordinary typed dispatch."""
    def __init__(self, inner, base, controller):
        self.inner,self.base,self.controller=inner,base,controller

    def __getattr__(self,name):
        return getattr(self.inner,name)

    def exchange(self,packet):
        base,controller=self.base,self.controller
        controller.ready()
        valid=(type(packet) is dict and set(packet)=={'kind','id','app','api','arguments'}
            and packet['kind']=='api' and type(packet['id']) is int and packet['id']==base.last_id+1
            and type(packet['arguments']) is dict and all(type(packet[k]) is str for k in ('app','api')))
        if not valid or base.complete or base.fatal or base.remaining<=0 or not base.may_continue():
            return self.inner.exchange(packet)
        fn=dict(name=packet['app']+'__'+packet['api'],arguments=json.dumps(packet['arguments'],allow_nan=False))
        try:
            decoded=base.catalog.decode(fn)
            if set(decoded)!={'app','api','args'}:
                return self.inner.exchange(packet)
        except (ValueError,KeyError,TypeError):
            return self.inner.exchange(packet)
        entry,effective=controller.decide(packet)
        if entry is None:
            return self.inner.exchange(packet)
        before=len(base.rows)
        try:
            if entry['decision']=='feedback':
                base.last_id=packet['id']
                feedback=dict(code='public_export_payload_contradicted',
                    reasons=entry['assessment']['reasons'],evidence=entry['assessment']['evidence'],
                    original_payload_sha256=entry['original_payload_sha256'],environment_API_requests=0,
                    correction='Use the earlier public source records to construct the requested CSV.')
                base.rows.append(dict(action=fn,api_request_sent=False,new_tools=[],effects_unknown=False,
                    observation={'output_grounding_feedback':feedback}))
                reply=dict(id=packet['id'],ok=False,error='Output grounding rejected this target write before dispatch: '
                    +json.dumps(feedback,ensure_ascii=False,sort_keys=True))
            else:
                reply=self.inner.exchange(effective)
            require(len(base.rows)==before+1,'one_grounded_write_record_required')
            controller.bind_reply(entry,base.rows[-1],reply)
            return reply
        except BaseException as error:
            entry['outcome']='unbound_failure'
            controller.fail(error)
            raise


class OutputGroundingProgram(RegionProjectionProgram):
    def __init__(self,*args,controller,**kwargs):
        require(type(controller) is OutputGroundingController,'trusted_grounding_controller_required')
        require(kwargs.get('policy')=='explicit_joined_fields','automatic_projection_disabled')
        self.grounding=controller
        super().__init__(*args,**kwargs)

    def make_channel(self,channel):
        wrapped=super().make_channel(channel)
        wrapped.receipted=GroundedReceiptExchange(wrapped.receipted,wrapped.base,self.grounding)
        return wrapped

    def __call__(self,*args,**kwargs):
        self.grounding.ready()
        self.grounding.program=Path(kwargs['record_dir']).name
        try:
            return super().__call__(*args,**kwargs)
        finally:
            if self.grounding.failed:
                self.budget.stopped=True
