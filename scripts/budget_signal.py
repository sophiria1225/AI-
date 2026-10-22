"""Explicit budget notifications: an ordinary baseline, not a new method."""
import copy
import hashlib
import json
import math
import time

from inference_cache_control import cache_measurement
from run_context_comparison import Inference, write_json

ARMS = ('plain_keep', 'budget_keep')
NOTICE = '''<harness_budget_v1>
The following is an authoritative resource snapshot before this model call.
All task requirements still apply. API calls include discovery, reads, writes,
and completion. API limits include the work before this checkpoint. Token and
model-call limits below cover continuation only, including this call's full
input and output. Tokens already spent are measured, not estimated. Wall time
is a snapshot and continues to pass. The harness reserves the maximum output
tokens plus the full next input before admitting each model call. A remaining
model-call count alone therefore does not guarantee that many calls will fit.
Use the remaining resources to finish and verify the requested work. Do not
declare completion while requirements are unmet. No extra budget is granted.
'''


def snapshot(config, calls, prefix_api, suffix_api, elapsed):
    if any(c.get('status') != 'ok' for c in calls):
        raise ValueError('cannot expose an exact budget after unknown model usage')
    if (type(prefix_api) is not int or type(suffix_api) is not int
            or min(prefix_api, suffix_api) < 0 or not math.isfinite(elapsed) or elapsed < 0):
        raise ValueError('invalid measured resource state')
    tokens = 0
    for c in calls:
        for key in ('input_tokens', 'output_tokens'):
            if type(c[key]) is not int or c[key] < 0:
                raise ValueError('invalid measured token count')
            tokens += c[key]
    remaining = {'api_calls': config['max_api_requests'] - prefix_api - suffix_api,
                 'model_calls': config['max_calls'] - len(calls),
                 'logical_input_plus_output_tokens': config['max_total_tokens'] - tokens,
                 'wall_seconds_at_snapshot': max(0, math.floor(config['max_wall_seconds'] - elapsed))}
    if any(remaining[k] < 0 for k in ('api_calls', 'model_calls', 'logical_input_plus_output_tokens')):
        raise ValueError('spent more than the declared resource limit')
    return {'remaining': remaining, 'used': {'api_calls_including_prefix': prefix_api + suffix_api,
             'continuation_model_calls': len(calls), 'continuation_logical_tokens': tokens},
            'max_output_tokens_per_call': config['max_output_tokens'],
            'context_limit_per_call': config['model']['num_ctx']}


def add_notification(messages, state, arm):
    if arm not in ARMS:
        raise ValueError('unknown budget-notification condition')
    result = copy.deepcopy(messages)
    if arm == 'budget_keep':
        result.append({'role': 'user', 'content': NOTICE +
                       json.dumps(state, sort_keys=True, separators=(',', ':')) +
                       '\n</harness_budget_v1>'})
    return result


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(',', ':')).encode()).hexdigest()


class BudgetInference(Inference):
    """Keep the original budget gates; add a snapshot and explicit KV policy.

    The old executor is not edited, because original trajectory adapters are
    pinned. Both conditions process their first input with cache_prompt=false.
    Within a continuation, normal prefix reuse is allowed and measured.
    """
    def __init__(self, config, output, arm):
        if arm not in ARMS:
            raise ValueError('unknown budget condition')
        super().__init__(copy.deepcopy(config), output)
        self.arm = arm
        self.prefix_api = self.suffix_api = 0
        self.snapshots = []

    def set_environment_usage(self, prefix_api, suffix_api):
        self.prefix_api, self.suffix_api = prefix_api, suffix_api

    def call(self, role, messages, tools):
        if role != 'agent':
            raise ValueError('this comparison has one executor and no free controller calls')
        state = snapshot(self.config, self.calls, self.prefix_api, self.suffix_api,
                         time.monotonic() - self.started)
        supplied = add_notification(messages, state, self.arm)
        before = len(self.calls)
        self.config['model']['cache_prompt'] = before != 0
        signal = {'next_call_id': f'call_{before + 1:03d}', 'state': state,
                  'notification_supplied': self.arm == 'budget_keep',
                  'base_messages_sha256': digest(messages), 'model_messages_sha256': digest(supplied),
                  'cache_prompt': self.config['model']['cache_prompt'], 'model_attempted': False}
        self.snapshots.append(signal)
        try:
            result = super().call(role, supplied, tools)
            if before == 0:
                path = self.output / self.calls[0]['id'] / 'response.json'
                measured = json.loads(path.read_text())
                check = cache_measurement('cold_1', measured, measured['input_tokens'])
                signal['first_input_measurement'] = check
                if not check['state_confirmed']:
                    raise ValueError('first call reused a prior branch prefix')
            return result
        finally:
            signal['model_attempted'] = len(self.calls) != before
            write_json(self.output / 'budget_signals.json', self.snapshots)
