"""One ordinary inline checkpoint, using only a closed old history prefix.

Pure controller: no model, tokenizer, Python execution, API, or semantic judge.
External accounting must count the offer instructions/schema and entire response.
"""
from copy import deepcopy

from inline_checkpoint_protocol import (
    choose_counted_projection, inline_tools, projection_after_turn)
from receipt_reasoning_history import digest, require
from single_checkpoint_history import TRIGGER_INPUT_TOKENS, candidate, closed_turns, project

BOUNDARY = '''<inline_checkpoint_prefix_end_v1>
The closed assistant turns before this marker are the older history eligible
for this one checkpoint. The following two closed turns stay verbatim.
The original system instructions and task also stay verbatim.
</inline_checkpoint_prefix_end_v1>'''

OFFER = '''Continue the task with your usual next action. This is one optional
checkpoint opportunity, not a separate summarization turn. If your response
contains exactly one run_python call, you may add its checkpoint argument.
Summarize only the already closed older history before inline_checkpoint_prefix_end_v1.
Do not summarize the two recent turns or predict the result of the code you are
about to submit. This code and its observed result will remain verbatim.
Use completed, usable_state, remaining, uncertainties, each a list of strings.
Preserve task conditions, exact needed identifiers, API signatures, persistent
variables, unresolved work and uncertainty about completeness. Distinguish
observed results, attempted operations and intentions. A normal API return is
not proof of task completion. Use at most 32 strings per field, 2048 characters
per string, and 8192 characters for the compact JSON object. The checkpoint is
fallible, not verified. If you cannot provide one, omit it and continue normally.
Do not add an extra tool call or retry merely to produce a checkpoint.'''


class InlineCheckpoint:
    def __init__(self):
        self.opportunity_used = False
        self.before = self.proposal = self.after = self.split = None
        self.views = self.decision = None

    def begin(self, messages, tools, measured_input_tokens):
        require(type(measured_input_tokens) is int and measured_input_tokens > 0,
                'measured_native_input_required')
        if self.opportunity_used or measured_input_tokens < TRIGGER_INPUT_TOKENS:
            return None
        proposal = candidate(messages)
        if proposal is None:
            return None
        changed_tools = inline_tools(tools)
        self.opportunity_used = True
        self.before = deepcopy(messages)
        self.proposal = {k: deepcopy(v) for k, v in proposal.items() if k != 'summary_messages'}
        cutoff = proposal['cutoff']
        offered = deepcopy(messages[:cutoff]) + [{'role': 'user', 'content': BOUNDARY}]
        offered += deepcopy(messages[cutoff:]) + [{'role': 'user', 'content': OFFER}]
        return {'messages': offered, 'tools': changed_tools,
                'source_archive_sha256': digest(messages), 'cutoff': cutoff,
                'messages_sha256': digest(offered), 'tools_sha256': digest(changed_tools)}

    def close(self, messages, split):
        require(self.opportunity_used and self.after is None,
                'one_offered_closed_turn_required')
        views = projection_after_turn(self.before, messages, split)
        self.after, self.split, self.views = deepcopy(messages), deepcopy(split), views
        if views['compacted'] is None:
            self.decision = {'accepted': False, 'reason': 'no_structurally_valid_checkpoint',
                             'ordinary_input_tokens': None, 'compacted_input_tokens': None}
        return deepcopy(views)

    def decide(self, ordinary_input_tokens, compacted_input_tokens):
        require(self.views is not None and self.decision is None,
                'unresolved_closed_checkpoint_required')
        _, accepted = choose_counted_projection(
            self.views, ordinary_input_tokens, compacted_input_tokens)
        self.decision = {'accepted': accepted,
            'reason': 'shorter_native_input' if accepted else 'not_shorter',
            'ordinary_input_tokens': ordinary_input_tokens,
            'compacted_input_tokens': compacted_input_tokens}
        return deepcopy(self.decision)

    def view(self, messages):
        if not self.opportunity_used:
            closed_turns(messages)
            return deepcopy(messages)
        require(self.after is not None and self.decision is not None,
                'checkpoint_must_close_and_resolve_before_continuation')
        closed_turns(messages)
        require(messages[:len(self.after)] == self.after, 'closed_inline_archive_changed')
        ordinary = deepcopy(messages)
        if self.split['binding'] is not None:
            # The exact closed archive prefix was checked above. Future action
            # and result pairs are never rewritten by this transport omission.
            ordinary[len(self.before)]['tool_calls'][0]['function'] = deepcopy(
                self.split['execution_message']['tool_calls'][0]['function'])
        if self.decision['accepted']:
            return project(ordinary, self.proposal, self.split['checkpoint'])
        return ordinary
