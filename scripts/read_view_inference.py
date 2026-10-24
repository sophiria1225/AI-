"""Finite existing inference admission plus the shared API-reservation notice."""
import json
import time

from api_error_comparison import task_snapshot
from budget_signal import digest
from inference_cache_control import cache_measurement
from protocol_stable_history import StableReferenceConversation
from run_context_comparison import write_json
from tool_choice_local_llama import reasoning_budget, tool_choice
from tool_choice_residual import ToolChoiceResidualInference
from whole_task_read_views import read_view_notification


class ReadViewInference(ToolChoiceResidualInference):
    def __init__(self,config,output,*,conversation,budget):
        if type(conversation) is not StableReferenceConversation:
            raise ValueError('source_normalized_read_view_conversation_required')
        if (reasoning_budget(config['model'])!=-1 or tool_choice(config['model'])!='auto'
                or config['max_api_requests']!=budget.limit):
            raise ValueError('fixed_read_view_inference_configuration_required')
        super().__init__(config,output,'residual')
        self.conversation=conversation;self.budget=budget
        self._wall_limit=config['max_wall_seconds'];self._stop_reason=None
        self.api_requests=0;self.snapshots=[];self.reference_views=[]

    def call(self,role,messages,tools):
        if (role!='agent' or self._stop_reason is not None
                or self.config['max_wall_seconds']!=self._wall_limit
                or reasoning_budget(self.config['model'])!=-1
                or tool_choice(self.config['model'])!='auto'):
            raise ValueError('fixed_one_executor_read_view_inference_required')
        self.budget._ready()
        if self.api_requests!=self.budget.spent:
            raise ValueError('API_receipts_and_shared_budget_disagree')
        normalized,_=self.conversation.for_model(self.config['observation_page_characters'])
        if normalized!=messages:raise ValueError('bound_source_history_required')
        self.reference_views.append(dict(next_call_id=f'call_{len(self.calls)+1:03d}',
            original_messages_sha256=digest(self.conversation.messages()),
            canonical_messages_sha256=digest(normalized),policy='source_protocol_fields_before_rendering'))
        write_json(self.output/'protocol_reference_views.json',self.reference_views)
        actual=task_snapshot(self.config,self.calls,self.api_requests,time.monotonic()-self.started)
        requests=self.budget.snapshot()
        supplied,visible=read_view_notification(normalized,actual,requests)
        before,admission_before=len(self.calls),len(self.admissions)
        self.config['model']['cache_prompt']=before!=0
        entry=dict(next_call_id=f'call_{before+1:03d}',time_visibility='not_exposed',
            original_wall_limit_seconds=self._wall_limit,measured_state=actual,visible_state=visible,
            request_budget=requests,base_messages_sha256=digest(normalized),
            model_messages_sha256=digest(supplied),cache_prompt=before!=0,model_attempted=False)
        self.snapshots.append(entry)
        try:
            message=super().call(role,supplied,tools)
            if not before:
                measured=json.loads((self.output/self.calls[0]['id']/'response.json').read_text())
                check=cache_measurement('cold_1',measured,measured['input_tokens'])
                entry['first_input_measurement']=check
                if not check['state_confirmed']:raise ValueError('first_request_must_be_cold')
            entry['status']='returned'
            return message
        except Exception as error:
            self._stop_reason=type(error).__name__
            entry.update(status='stopped',exception_type=self._stop_reason)
            raise
        finally:
            entry['model_attempted']=(len(self.calls)!=before or any(
                a.get('model_request_started') for a in self.admissions[admission_before:]))
            entry['terminal_usage_recorded']=len(self.calls)!=before
            entry['usage_unknown']=entry['model_attempted'] and (
                not entry['terminal_usage_recorded'] or self.calls[-1]['status']!='ok')
            write_json(self.output/'budget_observations.json',self.snapshots)
