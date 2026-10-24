"""Bind the ordinary budget to source-normalized, time-hidden task inference."""
from fixed_budget_local_llama import reasoning_budget
from fixed_budget_residual import FixedBudgetResidualInference
from stable_clock_observation import StableClockInference


class FixedBudgetInference(StableClockInference, FixedBudgetResidualInference):
    """Retain the clock/reference wrapper, then use the explicit-budget adapter.

The MRO sends StableClockInference.super().call to FixedBudgetResidualInference,
whose admission logic is unchanged but imports the explicit-budget transport.
No process-global monkey patch or mutation of old experiment modules is used.
"""
    def __init__(self, config, output, *, conversation, time_visibility='not_exposed'):
        if time_visibility != 'not_exposed':
            raise ValueError('whole_task_budget_comparison_requires_hidden_wall_time')
        self._fixed_reasoning_budget = reasoning_budget(config['model'])
        super().__init__(config, output, conversation=conversation, time_visibility=time_visibility)

    def call(self, role, messages, tools):
        if reasoning_budget(self.config['model']) != self._fixed_reasoning_budget:
            raise ValueError('reasoning_budget_changed_during_task')
        return super().call(role, messages, tools)
