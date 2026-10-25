"""Ordinary inline adapter with a required checkpoint field on its one offer."""
from inline_checkpoint_inference import InlineCheckpointInference
from receipt_reasoning_history import require
from required_inline_checkpoint_history import RequiredInlineCheckpoint


class RequiredInlineCheckpointInference(InlineCheckpointInference):
    def __init__(self, config, output, *, conversation):
        require(config.get('inline_checkpoint_requirement') == 'required_when_run_python',
                'explicit_required_inline_policy_required')
        super().__init__(config, output, conversation=conversation)
        self.checkpoint = RequiredInlineCheckpoint()

    def checkpoint_summary(self):
        return {**super().checkpoint_summary(), 'schema_checkpoint_required': True,
                'tool_choice_forced': False}
