"""P99 tool-choice transport with unchanged residual admission logic."""
import time

from tool_choice_local_llama import count_input, model_call
from residual_output_budget import ResidualInference, admission
from run_context_comparison import BudgetStop, write_json


class ToolChoiceResidualInference(ResidualInference):
    def call(self, role, messages, tools):
        if any(c['status'] != 'ok' for c in self.calls):
            raise RuntimeError('unknown usage: remaining tokens cannot be established')
        elapsed = time.monotonic() - self.started
        if len(self.calls) >= self.config['max_calls']:
            raise BudgetStop('call_limit')
        if elapsed >= self.config['max_wall_seconds']:
            raise BudgetStop('wall_limit')
        cfg = dict(self.config['model'])
        cfg['temperature'] = (self.config['draft_temperature'] if role == 'focus'
                              else self.config['agent_temperature'])
        cfg['seed'] = self.config['seed'] + sum(c['role'] == role for c in self.calls)
        cfg['num_predict'] = self.config['max_output_tokens']
        before = len(self.calls)
        entry = {'next_call_id': f'call_{before + 1:03d}', 'role': role,
                 'policy': self.policy, 'model_attempted': False, 'status': 'counting'}
        self.admissions.append(entry)
        try:
            try:
                count = count_input(cfg, messages, tools, timeout=min(
                    60, self.config['max_wall_seconds'] - elapsed))
            except TimeoutError:
                if time.monotonic() - self.started >= self.config['max_wall_seconds']:
                    raise BudgetStop('wall_limit_during_count')
                raise
            elapsed = time.monotonic() - self.started
            entry['count_wall_seconds'] = count.get('wall_seconds')
            if elapsed >= self.config['max_wall_seconds']:
                raise BudgetStop('wall_limit')
            expected = self.config.get('expected_input_tokens')
            if expected is not None and count['input_tokens'] != expected:
                raise ValueError('input count differs from the frozen diagnostic input')
            choice = admission(self.config['max_total_tokens'] - self.tokens,
                               count['input_tokens'], cfg['num_predict'], cfg['num_ctx'], self.policy)
            entry.update(choice, status='decided')
            write_json(self.output / 'admissions.json', self.admissions)
            if not choice['admitted']:
                raise BudgetStop(choice['stop_reason'])
            cfg['num_predict'] = choice['selected_output_cap']
            out = self.output / entry['next_call_id']
            out.mkdir()
            entry['model_request_started'] = True
            write_json(self.output / 'admissions.json', self.admissions)
            response = model_call(cfg, messages, out, self.config['max_wall_seconds'] - elapsed, tools)
            row = {'id': entry['next_call_id'], 'role': role, 'status': response['status'],
                   'input_tokens': response['input_tokens'], 'output_tokens': response['output_tokens'],
                   'cached_input_tokens': response.get('cached_input_tokens'),
                   'wall_seconds': response['wall_seconds'], 'finish_reason': response.get('done_reason'),
                   'timeout_scope': response.get('timeout_scope'), 'error_kind': response.get('error_kind'),
                   'predicted_input_tokens': count['input_tokens'], 'output_cap': cfg['num_predict']}
            self.calls.append(row)
            write_json(self.output / 'usage.json', self.calls)
            if response['status'] != 'ok':
                if response.get('error_kind') == 'timeout' and response.get('timeout_scope') == 'run_wall':
                    raise BudgetStop('wall_limit_during_model_call')
                raise RuntimeError('model failure; usage unknown, no free retry')
            if response['input_tokens'] != count['input_tokens']:
                raise RuntimeError('preflight and terminal input counts differ')
            if response['output_tokens'] > cfg['num_predict'] or self.tokens > self.config['max_total_tokens']:
                raise RuntimeError('terminal usage exceeded the reserved output or total budget')
            entry['status'] = 'generated'
            return response['message']
        except Exception as error:
            entry.update(status='stopped' if isinstance(error, BudgetStop) else 'error',
                         exception_type=type(error).__name__, reason=str(error))
            raise
        finally:
            entry['model_attempted'] = entry.get('model_request_started', False)
            write_json(self.output / 'admissions.json', self.admissions)

