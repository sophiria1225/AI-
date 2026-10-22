"""P45 selective-display baseline with common measured budget controls."""
import copy
import json
import time

from budget_signal import digest, snapshot
from documentation_print_origin import build_origin_view
from handoff_output_views import make_view
from inference_cache_control import cache_measurement
from residual_output_budget import ResidualInference
from run_context_comparison import write_json

ARMS = ('full_keep', 'documentation_origin_keep')
NOTICE = '''<harness_residual_budget_v1>
The following is an authoritative resource snapshot before this model call.
All task requirements still apply. API calls include discovery, reads, writes,
and completion, including work before this checkpoint. Token and model-call
limits cover continuation only, including this call's full input and output.
Tokens already spent are measured, not estimated. Wall time is a snapshot and
continues to pass. Before each call the harness counts the full input, including
this notice, then limits the output to the smaller of the configured maximum
and the remaining total token budget after that input. A call is rejected if
no output token fits or the input plus that output cap exceeds the context
limit. Remaining call count alone does not guarantee that many calls will fit.
Use the remaining resources to finish and verify the requested work. Do not
declare completion while requirements are unmet. No extra budget is granted.
'''


def add_notification(messages, state):
    result = copy.deepcopy(messages)
    result.append({'role': 'user', 'content': NOTICE +
                   json.dumps(state, sort_keys=True, separators=(',', ':')) +
                   '\n</harness_residual_budget_v1>'})
    return result


def build_condition(item, arm):
    if arm not in ARMS:
        raise ValueError('unknown documentation-display condition')
    started = time.monotonic()
    if arm == 'full_keep':
        prefix = item['prefix']
        conversation, selection = make_view(prefix['conversation_private'], prefix['public_task'], arm)
    else:
        views, selection = build_origin_view(item)
        conversation = views[arm]
    return conversation, {'transfer_wall_seconds': time.monotonic() - started,
                          'view_arm': arm, 'selection': selection,
                          'original_archive_modified': False, 'runtime_retained': True,
                          'one_time_boundary_display_change': True,
                          'novel_method_claim': False}


class OriginBudgetInference(ResidualInference):
    """Same notification, admission and KV rules for both display conditions."""
    def __init__(self, config, output, arm):
        if arm not in ARMS:
            raise ValueError('unknown documentation-display condition')
        super().__init__(config, output, 'residual')
        self.arm = arm
        self.prefix_api = self.suffix_api = 0
        self.snapshots = []

    def set_environment_usage(self, prefix_api, suffix_api):
        self.prefix_api, self.suffix_api = prefix_api, suffix_api

    def call(self, role, messages, tools):
        if role != 'agent':
            raise ValueError('one executor; no free controller calls')
        state = snapshot(self.config, self.calls, self.prefix_api, self.suffix_api,
                         time.monotonic() - self.started)
        supplied = add_notification(messages, state)
        before = len(self.calls)
        self.config['model']['cache_prompt'] = before != 0
        signal = {'next_call_id': f'call_{before + 1:03d}', 'state': state,
                  'notification_supplied': True, 'notification_characters': len(supplied[-1]['content']),
                  'base_messages_sha256': digest(messages), 'model_messages_sha256': digest(supplied),
                  'cache_prompt': self.config['model']['cache_prompt'], 'model_attempted': False}
        self.snapshots.append(signal)
        if not before:
            write_json(self.output / 'initial_messages_private.json', messages)
        try:
            result = super().call(role, supplied, tools)
            if before == 0:
                measured = json.loads((self.output / self.calls[0]['id'] / 'response.json').read_text())
                check = cache_measurement('cold_1', measured, measured['input_tokens'])
                signal['first_input_measurement'] = check
                if not check['state_confirmed']:
                    raise ValueError('first call reused a prior condition prefix')
            return result
        finally:
            signal['model_attempted'] = len(self.calls) != before
            write_json(self.output / 'budget_signals.json', self.snapshots)
