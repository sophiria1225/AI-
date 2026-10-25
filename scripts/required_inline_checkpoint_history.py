"""Request the ordinary inline checkpoint as a required run_python argument.

P119 remains unchanged. This changes the offered schema and its instructions,
not tool_choice, generation limits, execution, or structural acceptance rules.
The model can still omit the field or choose another response; no retry follows.
"""
from inline_checkpoint_history import BOUNDARY, InlineCheckpoint
from receipt_reasoning_history import digest, require


REQUIRED_OFFER = '''Continue the task with your usual next action. This is one
checkpoint opportunity, not a separate summarization turn. If your response
contains exactly one run_python call, include its required checkpoint argument.
Summarize only the already closed older history before inline_checkpoint_prefix_end_v1.
Do not summarize the two recent turns or predict the result of the code you are
about to submit. This code and its observed result will remain verbatim.
Use completed, usable_state, remaining, uncertainties, each a list of strings.
Preserve task conditions, exact needed identifiers, API signatures, persistent
variables, unresolved work and uncertainty about completeness. Distinguish
observed results, attempted operations and intentions. A normal API return is
not proof of task completion. Use at most 32 strings per field, 2048 characters
per string, and 8192 characters for the compact JSON object. The checkpoint is
fallible, not verified. State uncertainty explicitly instead of inventing facts.
Do not add an extra tool call or retry merely to produce a checkpoint.'''


class RequiredInlineCheckpoint(InlineCheckpoint):
    def begin(self, messages, tools, measured_input_tokens):
        offered = super().begin(messages, tools, measured_input_tokens)
        if offered is None:
            return None
        choices = [tool['function'] for tool in offered['tools']
                   if tool.get('function', {}).get('name') == 'run_python']
        require(len(choices) == 1, 'one_required_checkpoint_tool_required')
        params = choices[0]['parameters']
        require(params['required'] == ['code', 'span_ids'] and
                'checkpoint' in params['properties'], 'original_optional_offer_required')
        params['required'].append('checkpoint')
        offered['messages'][-1] = {'role': 'user', 'content': REQUIRED_OFFER}
        offered['messages_sha256'] = digest(offered['messages'])
        offered['tools_sha256'] = digest(offered['tools'])
        return offered
