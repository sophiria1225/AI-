"""Bind ordinary tool choice to source-normalized, time-hidden task inference."""
from tool_choice_local_llama import reasoning_budget, tool_choice
from tool_choice_residual import ToolChoiceResidualInference
from stable_clock_observation import StableClockInference


class ToolChoiceInference(StableClockInference, ToolChoiceResidualInference):
    """Retain the clock/reference wrapper, then use explicit tool choice.

The MRO sends StableClockInference.super().call to ToolChoiceResidualInference,
whose admission logic is unchanged but imports the tool-choice transport.
No process-global monkey patch or mutation of old experiment modules is used.
"""
    def __init__(self, config, output, *, conversation, time_visibility='not_exposed'):
        if time_visibility != 'not_exposed':
            raise ValueError('whole_task_tool_choice_requires_hidden_wall_time')
        self._fixed_reasoning_budget = reasoning_budget(config['model'])
        self._fixed_tool_choice = tool_choice(config['model'])
        if config['tool_choice_policy'] != self._fixed_tool_choice:
            raise ValueError('matching_tool_choice_policy_required')
        super().__init__(config, output, conversation=conversation, time_visibility=time_visibility)

    def call(self, role, messages, tools):
        if reasoning_budget(self.config['model']) != self._fixed_reasoning_budget:
            raise ValueError('reasoning_budget_changed_during_task')
        if (tool_choice(self.config['model']) != self._fixed_tool_choice
                or self.config['tool_choice_policy'] != self._fixed_tool_choice):
            raise ValueError('tool_choice_changed_during_task')
        return super().call(role, messages, tools)
