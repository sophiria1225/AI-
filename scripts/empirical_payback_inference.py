"""P133 ordinary rolling comparator plus a past-only payback heuristic.

First summary, tools, prompt, native counts and shared budgets are unchanged.
No prior cost estimate is represented as a guarantee of completion or savings.
"""
import time
from empirical_checkpoint_payback import MODES, REJECT_REASONS, VERSION, evaluate_payback
from fixed_budget_residual import FixedBudgetResidualInference
from receipt_reasoning_history import digest, require
from rolling_checkpoint_inference import RollingCheckpointInference, AdmissionAwareRollingCheckpoint
from single_checkpoint_history import closed_turns
from run_context_comparison import BudgetStop, write_json


class PaybackAwareRollingCheckpoint(AdmissionAwareRollingCheckpoint):
    def skip_unstarted_summary(self, archive, reason):
        if reason not in REJECT_REASONS:
            return super().skip_unstarted_summary(archive, reason)
        self._check(archive)
        require(self.mode == 'separate' and self.pending is not None
                and self.pending['stage'] == 'offered'
                and archive == self.pending['before'], 'unstarted_summary_required')
        self._bind(archive)
        self._last_closed_turns = len(closed_turns(archive))
        self.pending.update(stage='closed', close_status='not_dispatched')
        return self._finish(False, reason, None, None)


class EmpiricalPaybackInference(RollingCheckpointInference):
    def __init__(self, config, output, *, conversation):
        require(config.get('checkpoint_policy') == 'rolling_separate'
                and config.get('payback_mode') in MODES, 'fixed_P133_payback_mode_required')
        super().__init__(config, output, conversation=conversation)
        self.checkpoint = PaybackAwareRollingCheckpoint('separate')
        self.payback_mode = config['payback_mode']
        self.payback_events = []
        self.payback_contract_failed = False

    def _summarize_separately(self, normalized, tools, offered):
        began = time.monotonic()
        before_calls, before_tokens, before_admissions = len(self.calls), self.tokens, len(self.admissions)
        event = {'status': 'separate_summary_started', 'opportunity_index': offered['opportunity_index'],
                 'after_model_calls': len(self.calls), 'model_attempted': False,
                 'summary_calls': 0, 'summary_known_tokens': 0, 'semantics_verified': False}
        self.controls.append(event)
        payback = None
        try:
            count = self._count('focus', 'separate_summary_input', offered['summary_messages'], [])
            reserve = count['input_tokens'] + offered['trigger_input_tokens'] + 2 * self.config['max_output_tokens']
            event.update(summary_input_count=count, screening_tokens_using_current_agent_input=reserve)
            reason = ('insufficient_shared_call_budget' if len(self.calls) + 2 > self.config['max_calls'] else
                      'insufficient_shared_token_budget' if self.tokens + reserve > self.config['max_total_tokens'] else
                      'summary_context_limit' if count['input_tokens'] + self.config['max_output_tokens'] > self.config['model']['num_ctx'] else None)
            if reason is not None:
                decision = self.checkpoint.skip_unstarted_summary(normalized, reason)
                event.update(status='separate_summary_not_dispatched', decision=decision)
                return
            remaining_wall = self.config['max_wall_seconds'] - (time.monotonic() - self.started)
            if remaining_wall <= 0:
                raise BudgetStop('wall_limit')
            try:
                payback = evaluate_payback(mode=self.payback_mode,
                    opportunity_index=offered['opportunity_index'], calls=self.calls,
                    controls=self.controls, summary_input_tokens=count['input_tokens'],
                    output_cap=self.config['max_output_tokens'],
                    remaining_calls=self.config['max_calls']-len(self.calls),
                    remaining_wall_seconds=remaining_wall)
                payback.update(offer_sha256=digest(offered), source_archive_sha256=digest(normalized),
                    shared_screening_passed=True,
                    clock_source='host_monotonic_after_summary_input_count_before_dispatch',
                    work_wall_limit_seconds=self.config['max_wall_seconds'],
                    observed_elapsed_seconds=self.config['max_wall_seconds']-remaining_wall,
                    status='decided', model_attempted=False,
                    terminal_usage_recorded=False, unknown_usage_calls=0)
                self.payback_events.append(payback)
            except Exception:
                self.payback_contract_failed = True
                raise
            if not payback['admitted']:
                decision = self.checkpoint.skip_unstarted_summary(normalized, payback['reason'])
                event.update(status='separate_summary_not_dispatched', decision=decision)
                payback['status'] = 'skipped_unstarted'
                return
            message = FixedBudgetResidualInference.call(self, 'focus', offered['summary_messages'], [])
            views = self.checkpoint.close_separate(normalized, message,
                self.calls[-1]['finish_reason'], usage_known=self.calls[-1]['status'] == 'ok')
            self.closed.append({'mode': 'separate', 'call_id': self.calls[-1]['id'],
                'opportunity_index': offered['opportunity_index'], 'source_archive_sha256': digest(normalized),
                'ordinary_sha256': views['ordinary_sha256'], 'compacted_sha256': views['compacted_sha256']})
            write_json(self.output / 'rolling_closed_private.json', self.closed)
            event['status'] = 'separate_summary_closed'
            payback['status'] = 'summary_closed'
            self._resolve(normalized, tools)
        except Exception as error:
            event.update(status='separate_summary_aborted', exception_type=type(error).__name__)
            if payback is not None:
                payback.update(status='aborted', exception_type=type(error).__name__)
            raise
        finally:
            dispatched = sum(bool(a.get('model_request_started')) for a in self.admissions[before_admissions:])
            missing = max(0, dispatched - (len(self.calls) - before_calls))
            unknown = missing + sum(c['status'] != 'ok' for c in self.calls[before_calls:])
            event.update(summary_calls=len(self.calls) - before_calls,
                summary_known_tokens=self.tokens - before_tokens, model_attempted=bool(dispatched),
                dispatched_without_terminal_usage=missing, unknown_usage_calls=unknown,
                control_wall_seconds=time.monotonic() - began)
            if payback is not None:
                payback.update(model_attempted=bool(dispatched),
                    terminal_usage_recorded=len(self.calls) != before_calls,
                    summary_known_tokens=self.tokens-before_tokens, unknown_usage_calls=unknown)
            self._save()

    def _save(self):
        super()._save()
        if hasattr(self, 'payback_events'):
            write_json(self.output / 'empirical_payback_events.json', self.payback_events)

    def payback_summary(self):
        decisions = self.payback_events
        return dict(version=VERSION, mode=self.payback_mode,
            ledger_scope='opportunities_passing_existing_shared_screening',
            evaluated_opportunities=len(decisions),
            existing_screening_rejections=sum(x.get('status')=='separate_summary_not_dispatched'
                and x.get('decision', {}).get('reason') not in REJECT_REASONS for x in self.controls),
            repeated_opportunities=sum(x['opportunity_index']>1 for x in decisions),
            skipped_unstarted_summaries=sum(x['status']=='skipped_unstarted' for x in decisions),
            shadow_rejected_opportunities=sum(not x['predicted_admit'] for x in decisions),
            dispatched_focus_calls=sum(x['model_attempted'] for x in decisions),
            unknown_focus_usage_calls=sum(x['unknown_usage_calls'] for x in decisions),
            contract_failed=self.payback_contract_failed,
            accounting_complete=not self.payback_contract_failed and all(
                x['status'] in ('skipped_unstarted','summary_closed','aborted') for x in decisions),
            events_sha256=digest(decisions), extra_model_calls=0, extra_native_counts=0,
            prediction_guaranteed=False, task_quality_established=False, novel_method_claim=False)
