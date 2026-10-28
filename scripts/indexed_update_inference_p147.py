"""Only a requested second UPDATE focus uses P147 indexed-action transport.

Actor requests, first summaries, TR summaries and count-only actor views use the
frozen P144 path. Only indexed response decoding is new; state validation,
application and checkpoint installation still use the unchanged P144 rules.
The UPDATE branch copies the existing finite focus admission/closure wrappers
because their frozen implementation directly names its transport class.
"""
from copy import deepcopy
import time

from checkpoint_state_update_inference_p144 import StateUpdateInference
from checkpoint_indexed_update_p147 import IndexedStateUpdateCheckpoint, INDEXED_UPDATE_PROMPT_SHA256, VERSION
from receipt_reasoning_history import digest, require
from residual_output_budget import admission
from run_context_comparison import BudgetStop, write_json
import indexed_update_transport_p147 as transport


class IndexedUpdateInference(StateUpdateInference):
    def __init__(self, config, output, *, conversation):
        super().__init__(config, output, conversation=conversation)
        self.checkpoint=IndexedStateUpdateCheckpoint(self.representation_mode)

    def _save(self):
        super()._save()
        if hasattr(self.checkpoint, 'indexed_conversions'):
            write_json(self.output/'indexed_update_conversions.json',self.checkpoint.indexed_conversions)

    def _focus_config(self):
        cfg = dict(self.config['model'])
        cfg.update(temperature=self.config['draft_temperature'],
            seed=self.config['seed']+sum(c['role']=='focus' for c in self.calls),
            num_predict=self.config['max_output_tokens'])
        return cfg

    def _count_update_focus(self, messages, old):
        elapsed = time.monotonic()-self.started
        if elapsed >= self.config['max_wall_seconds']:
            raise BudgetStop('wall_limit_before_rolling_count')
        entry = dict(role='focus', purpose='separate_summary_input', after_model_calls=len(self.calls),
            messages_sha256=digest(messages), tools_sha256=digest([]), status='counting')
        self.input_counts.append(entry)
        try:
            result = transport.count_input(self._focus_config(), messages, [], old,
                timeout=min(60, self.config['max_wall_seconds']-elapsed))
            entry.update(status='complete', **result)
            return result
        except Exception as error:
            entry.update(status='failed', exception_type=type(error).__name__)
            raise
        finally:
            write_json(self.output/'rolling_input_counts.json', self.input_counts)

    def _call_update_focus(self, messages, old, *, screened_count):
        if any(c['status']!='ok' for c in self.calls):
            raise RuntimeError('unknown usage: remaining tokens cannot be established')
        elapsed = time.monotonic()-self.started
        if len(self.calls)>=self.config['max_calls']:
            raise BudgetStop('call_limit')
        if elapsed>=self.config['max_wall_seconds']:
            raise BudgetStop('wall_limit')
        cfg=self._focus_config()
        entry=dict(next_call_id=f'call_{len(self.calls)+1:03d}', role='focus',
            policy=self.policy, model_attempted=False, status='counting',
            update_transport=transport.TRANSPORT, reasoning_budget_tokens=transport.REASONING_BUDGET)
        self.admissions.append(entry)
        try:
            try:
                count=transport.count_input(cfg,messages,[],old,
                    timeout=min(60,self.config['max_wall_seconds']-elapsed))
            except TimeoutError:
                if time.monotonic()-self.started>=self.config['max_wall_seconds']:
                    raise BudgetStop('wall_limit_during_count')
                raise
            elapsed=time.monotonic()-self.started
            entry.update(count_wall_seconds=count.get('wall_seconds'),
                request_sha256=count['request_sha256'])
            require(count['request_sha256']==screened_count['request_sha256'] and
                count['input_tokens']==screened_count['input_tokens'],
                'P147_screen_admission_request_and_count_must_match')
            if elapsed>=self.config['max_wall_seconds']:
                raise BudgetStop('wall_limit')
            expected=self.config.get('expected_input_tokens')
            if expected is not None and count['input_tokens']!=expected:
                raise ValueError('input count differs from the frozen diagnostic input')
            choice=admission(self.config['max_total_tokens']-self.tokens,
                count['input_tokens'],cfg['num_predict'],cfg['num_ctx'],self.policy)
            entry.update(choice,status='decided')
            write_json(self.output/'admissions.json',self.admissions)
            if not choice['admitted']:
                raise BudgetStop(choice['stop_reason'])
            # The pre-screen reserves a full 4096-token focus and next actor.
            # Changing the cap after native count would break exact transport binding.
            require(choice['selected_output_cap']==cfg['num_predict']==4096,
                'P147_screened_full_focus_reservation_required')
            out=self.output/entry['next_call_id']
            out.mkdir()
            entry['model_request_started']=True
            write_json(self.output/'admissions.json',self.admissions)
            response=transport.model_call(cfg,messages,out,self.config['max_wall_seconds']-elapsed,
                [],old,expected_request_sha256=count['request_sha256'])
            row=dict(id=entry['next_call_id'],role='focus',status=response['status'],
                input_tokens=response['input_tokens'],output_tokens=response['output_tokens'],
                cached_input_tokens=response.get('cached_input_tokens'),wall_seconds=response['wall_seconds'],
                finish_reason=response.get('done_reason'),timeout_scope=response.get('timeout_scope'),
                error_kind=response.get('error_kind'),predicted_input_tokens=count['input_tokens'],
                output_cap=cfg['num_predict'],request_sha256=count['request_sha256'],
                update_transport=transport.TRANSPORT,reasoning_budget_tokens=transport.REASONING_BUDGET)
            self.calls.append(row)
            write_json(self.output/'usage.json',self.calls)
            if response['status']!='ok':
                if response.get('error_kind')=='timeout' and response.get('timeout_scope')=='run_wall':
                    raise BudgetStop('wall_limit_during_model_call')
                raise RuntimeError('model failure; usage unknown, no free retry')
            if response['input_tokens']!=count['input_tokens']:
                raise RuntimeError('preflight and terminal input counts differ')
            if response['output_tokens']>cfg['num_predict'] or self.tokens>self.config['max_total_tokens']:
                raise RuntimeError('terminal usage exceeded the reserved output or total budget')
            entry['status']='generated'
            return response['message']
        except Exception as error:
            entry.update(status='stopped' if isinstance(error,BudgetStop) else 'error',
                exception_type=type(error).__name__,reason=str(error))
            raise
        finally:
            entry['model_attempted']=entry.get('model_request_started',False)
            write_json(self.output/'admissions.json',self.admissions)

    def _summarize_separately(self, normalized, tools, offered):
        if offered.get('update_requested') is not True:
            return super()._summarize_separately(normalized,tools,offered)
        pending=self.checkpoint.pending
        require(self.representation_mode=='threshold_delta_update' and
            offered['opportunity_index']==2 and self.checkpoint.revision==1 and
            pending.get('update_requested') is True and self.checkpoint._update_state_matches(),
            'P147_only_bound_second_UPDATE_focus_may_use_schema')
        old=deepcopy(pending['update_prior_state'])
        before_calls,before_admissions,before_events=len(self.calls),len(self.admissions),len(self.checkpoint.events)
        try:
            return self._summarize_update(normalized,tools,offered,old)
        finally:
            try:
                new=self.calls[before_calls:]
                sent=[a for a in self.admissions[before_admissions:] if a.get('model_request_started')]
                require(len(new)<=1 and len(sent)<=1,'one_focus_attempt_per_opportunity')
                if new:
                    call=new[0]
                    require(call['role']=='focus' and len(sent)==1,'focus_usage_dispatch_binding_required')
                    self.exposure.record_focus(call_id=call['id'],model_attempted=True,
                        usage_known=call['status']=='ok',input_tokens=call.get('input_tokens'),
                        output_tokens=call.get('output_tokens'))
                else:
                    self.exposure.record_focus(call_id=f'call_{before_calls+1:03d}',
                        model_attempted=bool(sent),usage_known=False)
            finally:
                for decision in self.checkpoint.events[before_events:]:
                    if not any(c.get('status')=='checkpoint_decided' and
                        c.get('opportunity_index')==decision['opportunity_index'] for c in self.controls):
                        self.controls.append(dict(status='checkpoint_terminal_without_counted_decision',
                            after_model_calls=len(self.calls),**deepcopy(decision)))
                self._save()

    def _summarize_update(self,normalized,tools,offered,old):
        began=time.monotonic()
        before_calls,before_tokens,before_admissions=len(self.calls),self.tokens,len(self.admissions)
        event=dict(status='separate_summary_started',opportunity_index=offered['opportunity_index'],
            after_model_calls=len(self.calls),model_attempted=False,summary_calls=0,
            summary_known_tokens=0,semantics_verified=False,update_transport=transport.TRANSPORT)
        self.controls.append(event)
        try:
            count=self._count_update_focus(offered['summary_messages'],old)
            reserve=count['input_tokens']+offered['trigger_input_tokens']+2*self.config['max_output_tokens']
            event.update(summary_input_count=count,screening_tokens_using_current_agent_input=reserve)
            reason=('insufficient_shared_call_budget' if len(self.calls)+2>self.config['max_calls'] else
                'insufficient_shared_token_budget' if self.tokens+reserve>self.config['max_total_tokens'] else
                'summary_context_limit' if count['input_tokens']+self.config['max_output_tokens']>self.config['model']['num_ctx'] else None)
            if reason is not None:
                decision=self.checkpoint.skip_unstarted_summary(normalized,reason)
                event.update(status='separate_summary_not_dispatched',decision=decision)
                return
            message=self._call_update_focus(offered['summary_messages'],old,screened_count=count)
            views=self.checkpoint.close_separate(normalized,message,self.calls[-1]['finish_reason'],
                usage_known=self.calls[-1]['status']=='ok')
            self.closed.append(dict(mode='separate',call_id=self.calls[-1]['id'],
                opportunity_index=offered['opportunity_index'],source_archive_sha256=digest(normalized),
                ordinary_sha256=views['ordinary_sha256'],compacted_sha256=views['compacted_sha256']))
            write_json(self.output/'rolling_closed_private.json',self.closed)
            event['status']='separate_summary_closed'
            self._resolve(normalized,tools)
        except Exception as error:
            event.update(status='separate_summary_aborted',exception_type=type(error).__name__)
            raise
        finally:
            dispatched=sum(bool(a.get('model_request_started')) for a in self.admissions[before_admissions:])
            missing=max(0,dispatched-(len(self.calls)-before_calls))
            event.update(summary_calls=len(self.calls)-before_calls,summary_known_tokens=self.tokens-before_tokens,
                model_attempted=bool(dispatched),dispatched_without_terminal_usage=missing,
                unknown_usage_calls=missing+sum(c['status']!='ok' for c in self.calls[before_calls:]),
                control_wall_seconds=time.monotonic()-began)
            self._save()

    def schema_transport_summary(self):
        rows=[a for a in self.admissions if a.get('update_transport')==transport.TRANSPORT]
        return dict(phase='P147',candidate='schema_indexed_bounded',
            mode=self.representation_mode,
            configured_transport=self.config.get('update_transport'),
            schema_applicable=self.representation_mode=='threshold_delta_update',
            actor_transport_unchanged=True,first_focus_transport_unchanged=True,
            recursive_transport_unchanged=True,host_update_parser_unchanged=True,
            indexed_representation=VERSION,indexed_prompt_sha256=INDEXED_UPDATE_PROMPT_SHA256,
            indexed_conversion_count=len(self.checkpoint.indexed_conversions),
            indexed_conversions_sha256=digest(self.checkpoint.indexed_conversions),
            update_focus_reasoning_budget_tokens=2048,output_cap=4096,
            screened_focus_counts=sum(c.get('update_transport')==transport.TRANSPORT for c in self.input_counts),
            update_admissions=len(rows),update_dispatched=sum(bool(a.get('model_request_started')) for a in rows),
            update_admissions_sha256=digest(rows),novel_method_claim=False)
