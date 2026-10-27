"""P140 output-envelope clarification over the frozen P139 checkpoint contract.

Only the second delta focus system prompt can change. The old parser, fragment
limits, host combination, trigger arithmetic and immutable archive stay shared.
Study modes are explicit; the candidate is not relabelled as an old experiment.
"""
import hashlib

from checkpoint_prefix_exposure import PrefixExposureLedger
from checkpoint_representation_p139 import (
    MAX_OPPORTUNITIES, MIN_NEW_CLOSED_TURNS, SUMMARY_PROMPT, DELTA_SUMMARY_PROMPT,
    RepresentationCheckpoint, delta_note, summary_note, eligible_prefix_views,
    serialize_fragment_body, validate_fragment_budget, trigger_decision as old_trigger)
from receipt_reasoning_history import require

MODES = ('threshold_recursive', 'exposure_delta', 'exposure_delta_object')
VERSION = 'checkpoint_delta_object_envelope_p140_v1'
OBJECT_DELTA_SUMMARY_PROMPT = DELTA_SUMMARY_PROMPT + '''

Output envelope clarification: return exactly ONE JSON OBJECT for the new delta,
with exactly the keys completed, usable_state, remaining, uncertainties. Do not
return a JSON array or a pair of checkpoints. Do not include the previous
checkpoint in your output. The host, not you, combines its unchanged saved
previous checkpoint with your new delta object. The array notation above
describes that host-side combined size check, not the output you should return.
All stated combined character and item limits still apply. Return the delta
object only, without Markdown or explanatory text.'''
OBJECT_DELTA_PROMPT_SHA256 = hashlib.sha256(OBJECT_DELTA_SUMMARY_PROMPT.encode()).hexdigest()


def base_mode_for(mode):
    require(mode in MODES, 'fixed_P140_envelope_mode_required')
    return 'threshold_recursive' if mode == 'threshold_recursive' else 'exposure_delta'


def timing_for(mode):
    return base_mode_for(mode).split('_', 1)[0]


def representation_for(mode):
    return base_mode_for(mode).split('_', 1)[1]


def prompt_policy_for(mode):
    base_mode_for(mode)
    return 'explicit_delta_object' if mode == 'exposure_delta_object' else 'original'


def trigger_decision(*, mode, **kwargs):
    decision = old_trigger(mode=base_mode_for(mode), **kwargs)
    decision.update(version=VERSION, mode=mode)
    return decision


class DeltaEnvelopeExposureLedger(PrefixExposureLedger):
    """Unchanged paid E/C and unknown/reset arithmetic, with the honest new arm."""
    def __init__(self, mode):
        timing = timing_for(mode)
        super().__init__('rolling_separate' if timing == 'threshold' else 'prefix_exposure')
        self.mode = mode

    def summary(self):
        return {**super().summary(), 'version': VERSION, 'mode': self.mode,
                'timing': timing_for(self.mode), 'representation': representation_for(self.mode)}


class DeltaEnvelopeCheckpoint(RepresentationCheckpoint):
    def __init__(self, mode):
        super().__init__(base_mode_for(mode))
        self.representation_mode = mode
        self.envelope_policy = prompt_policy_for(mode)

    def begin(self, archive, measured_input_tokens, tools=None, *, repeat_ready=False):
        offered = super().begin(archive, measured_input_tokens, tools,
                                repeat_ready=repeat_ready)
        if (offered is not None and self.envelope_policy == 'explicit_delta_object'
                and offered['delta_requested']):
            messages = offered['summary_messages']
            require(offered['opportunity_index'] == 2 and len(messages) == 2
                    and messages[0] == {'role': 'system', 'content': DELTA_SUMMARY_PROMPT}
                    and messages[1]['role'] == 'user', 'second_delta_prompt_boundary_required')
            messages[0] = {'role': 'system', 'content': OBJECT_DELTA_SUMMARY_PROMPT}
        return offered
