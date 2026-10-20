"""Shared P3 accounting and artifact-bound completion, independent of an LLM.

All units charge one ledger. An unknown terminal usage closes that ledger;
cached input is part of the logical input, not a discount or an extra charge.
"""
from dataclasses import dataclass, field
import math
import re


class ProtocolStop(RuntimeError):
    def __init__(self, reason):
        self.reason = reason
        super().__init__(reason)


def positive_int(value, name):
    if type(value) is not int or value < 1:
        raise ValueError(name + ' must be a positive integer')
    return value


@dataclass
class SharedBudget:
    max_calls: int
    max_total_tokens: int
    num_ctx: int
    num_predict: int
    max_wall_seconds: int
    calls: int = field(default=0, init=False)
    input_tokens: int = field(default=0, init=False)
    output_tokens: int = field(default=0, init=False)
    usage_complete: bool = field(default=True, init=False)
    _pending_input: int | None = field(default=None, init=False)
    _closed: str | None = field(default=None, init=False)

    def __post_init__(self):
        for key in ('max_calls', 'max_total_tokens', 'num_ctx', 'num_predict', 'max_wall_seconds'):
            positive_int(getattr(self, key), key)
        if self.num_predict >= self.num_ctx:
            raise ValueError('output reserve must leave input space')

    @property
    def total_tokens(self):
        return self.input_tokens + self.output_tokens

    def snapshot(self):
        return {'attempted_calls': self.calls, 'recorded_input_tokens': self.input_tokens,
                'recorded_output_tokens': self.output_tokens,
                'recorded_total_tokens': self.total_tokens,
                'remaining_tokens': self.max_total_tokens - self.total_tokens,
                'remaining_calls': self.max_calls - self.calls,
                'usage_complete': self.usage_complete, 'pending': self._pending_input is not None,
                'closed_reason': self._closed}

    def notice(self, elapsed_seconds, unit):
        self._check_wall(elapsed_seconds)
        return (f'Execution budget before this request: {self.max_calls-self.calls} model calls '
                f'and {self.max_total_tokens-self.total_tokens} total input plus output tokens '
                f'remain across ALL units. At most {self.max_wall_seconds-elapsed_seconds:.1f} '
                f'seconds remain. The next input, including this notice, consumes that budget. '
                f'Each response reserves {self.num_predict} output tokens. Current unit: {unit}. '
                'Review changes and visible checks before declaring completion.')

    def _check_wall(self, elapsed_seconds):
        if not isinstance(elapsed_seconds, (int, float)) or not math.isfinite(elapsed_seconds) or elapsed_seconds < 0:
            raise ValueError('elapsed seconds must be finite and nonnegative')
        if elapsed_seconds >= self.max_wall_seconds:
            raise ProtocolStop('wall_limit')

    def begin_request(self, exact_input_tokens, elapsed_seconds):
        """Call only once immediately before issuing the inference request."""
        if self._closed:
            raise ProtocolStop(self._closed)
        if self._pending_input is not None:
            raise ProtocolStop('request_already_pending')
        self._check_wall(elapsed_seconds)
        positive_int(exact_input_tokens, 'exact input count')
        if self.calls >= self.max_calls:
            raise ProtocolStop('call_limit')
        if exact_input_tokens + self.num_predict > min(self.num_ctx, self.max_total_tokens-self.total_tokens):
            raise ProtocolStop('conservative_budget_guard')
        self._pending_input = exact_input_tokens
        self.calls += 1
        return self.calls

    def finish_request(self, response):
        """Charge measured usage, then reject responses unsafe to execute."""
        if self._pending_input is None:
            raise ProtocolStop('no_pending_request')
        expected = self._pending_input
        self._pending_input = None
        counts = [response.get(k) for k in ('input_tokens', 'output_tokens')]
        if response.get('status') != 'ok' or any(type(n) is not int or n < 0 for n in counts):
            self.usage_complete = False
            self._closed = 'usage_unknown'
            raise ProtocolStop(self._closed)
        self.input_tokens += counts[0]
        self.output_tokens += counts[1]
        reason = None
        if counts[0] != expected:
            reason = 'input_counter_mismatch'
        elif counts[1] > self.num_predict:
            reason = 'output_limit_exceeded'
        elif self.total_tokens > self.max_total_tokens:
            reason = 'measured_token_limit_exceeded'
        elif response.get('done_reason') == 'length':
            reason = 'generation_limit_incomplete_response'
        elif response.get('done_reason') not in ('stop', 'tool_calls'):
            reason = 'invalid_terminal_reason'
        if reason:
            self._closed = reason
            raise ProtocolStop(reason)


@dataclass
class CompletionState:
    units: tuple[str, ...]
    artifact_sha256: str
    votes: dict[str, str] = field(default_factory=dict, init=False)
    revision: int = field(default=0, init=False)

    def __post_init__(self):
        if not self.units or len(set(self.units)) != len(self.units) or not all(isinstance(u, str) and u for u in self.units):
            raise ValueError('units must be unique nonempty names')
        self._validate_sha(self.artifact_sha256)

    @staticmethod
    def _validate_sha(value):
        if not isinstance(value, str) or not re.fullmatch('[0-9a-f]{64}', value):
            raise ValueError('artifact must have a SHA-256')

    def observe_artifact(self, sha256):
        self._validate_sha(sha256)
        changed = sha256 != self.artifact_sha256
        if changed:
            self.artifact_sha256 = sha256
            self.revision += 1
            self.votes.clear()
        return changed

    def vote(self, unit, observed_sha256):
        if unit not in self.units:
            raise ValueError('unknown unit')
        if observed_sha256 != self.artifact_sha256:
            raise ProtocolStop('stale_completion_vote')
        self.votes[unit] = observed_sha256

    @property
    def complete(self):
        return all(self.votes.get(u) == self.artifact_sha256 for u in self.units)

    def snapshot(self):
        return {'units': list(self.units), 'artifact_sha256': self.artifact_sha256,
                'revision': self.revision, 'votes': dict(self.votes), 'complete': self.complete}
