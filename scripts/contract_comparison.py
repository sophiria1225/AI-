"""P47 display/feedback controls without changing the original execution adapter."""
import time

from contract_feedback import UNKNOWN_PARAMETER, canonical, make_feedback
from documentation_comparison import build_condition as build_display

ARMS = ('full_contract_keep', 'selected_names_keep', 'selected_contract_keep')
CONDITIONS = {
    'full_contract_keep': ('full_keep', 'public_schema'),
    'selected_names_keep': ('documentation_origin_keep', 'parameter_names'),
    'selected_contract_keep': ('documentation_origin_keep', 'public_schema'),
}


def build_condition(item, arm):
    if arm not in CONDITIONS:
        raise ValueError('unknown contract comparison condition')
    view, mode = CONDITIONS[arm]
    conversation, transfer = build_display(item, view)
    transfer.update(feedback_mode=mode, feedback_max_characters=16000,
                    feedback_only_after_undispatched_unknown_parameter=True)
    return conversation, transfer


class FeedbackProgram:
    """Decorate the original channel; completion/budget/effect state stays shared."""
    def __init__(self, program, mode, max_characters=16000):
        if mode not in ('parameter_names', 'public_schema') or max_characters != 16000:
            raise ValueError('outside fixed P47 feedback policy')
        self.program, self.mode, self.max_characters = program, mode, max_characters
        self.checks = 0
        self.feedback = []
        self.control_seconds = 0.0

    def __call__(self, source, observations, channel, **kwargs):
        return self.program(source, observations, _Channel(channel, self), **kwargs)

    def summary(self):
        return {'mode': self.mode, 'checked_requests': self.checks,
                'feedback_events': self.feedback, 'control_wall_seconds': self.control_seconds,
                'automatic_retries': 0, 'extra_model_calls': 0, 'extra_environment_requests': 0}


class _Channel:
    def __init__(self, base, runtime):
        self.base, self.runtime = base, runtime

    def __getattr__(self, name):
        return getattr(self.base, name)

    def exchange(self, packet):
        reply = self.base.exchange(packet)
        started = time.monotonic()
        try:
            self.runtime.checks += 1
            row = self.base.rows[-1]
            exposed = {name: self.catalog.catalog[name]['function'] for name in self.catalog.visible}
            feedback = make_feedback(row, exposed, self.runtime.mode, self.runtime.max_characters)
            if feedback is not None:
                row['observation']['contract_feedback'] = feedback
                reply['error'] = canonical({'format_error': UNKNOWN_PARAMETER, 'contract_feedback': feedback})
                self.runtime.feedback.append({'api': feedback['api'], 'mode': feedback['mode'],
                    'schema_sha256': feedback['schema_sha256'], 'characters': len(canonical(feedback))})
            return reply
        finally:
            self.runtime.control_seconds += time.monotonic() - started
