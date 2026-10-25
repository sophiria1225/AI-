"""Synthetic adapter/executor fixture: no model, tokenizer, API or code execution."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from checkpoint_attempt_usage import attempt_usage
from inline_checkpoint_execution import execute_inline_response
from inline_checkpoint_history import BOUNDARY
from inline_checkpoint_inference import InlineCheckpointInference
from protocol_stable_history import StableReferenceConversation
from public_display import CODE_TOOLS
from single_checkpoint_worker_fixture import configuration
from whole_task_single_checkpoint import worker_config
from test_inline_checkpoint_protocol import VALID


def fixture(*, steps=6, mode='valid', nonshrinking=False, below_trigger=False,
            token_limit=450000, first_cached=0, offer_count_delay=0, omit_close=False):
    original, plan, item = configuration()
    plan['max_total_tokens'] = token_limit
    config = worker_config(original, plan, 'fixture', 'error_exception',
                           'BOC_INLINE_SYNTHETIC', 'single_checkpoint')
    config['checkpoint_policy'] = 'inline_checkpoint'
    clock, captured, counts, executed, archived, errors = [0.0], [], [], [], [], []
    conversation = StableReferenceConversation('synthetic instructions', {'instruction': 'synthetic task'})

    def amount(messages, tools):
        if below_trigger:
            return 100
        compacted = any('ordinary_fallible_summary' in (m.get('content') or '') for m in messages
                        if m['role'] == 'user')
        if nonshrinking and compacted:
            return 50000
        base = 5000 + 4000 * sum(m['role'] == 'assistant' for m in messages)
        if any(m.get('content') == BOUNDARY for m in messages):
            base += 300  # Synthetic counts, not a measurement of the real prompt.
        if 'checkpoint' in tools[0]['function']['parameters']['properties']:
            base += 200  # Includes the offered schema in synthetic admission.
        return base

    def count(cfg, messages, tools, timeout):
        counts.append({'messages': deepcopy(messages), 'tools': deepcopy(tools), 'timeout': timeout})
        if offer_count_delay and 'checkpoint' in tools[0]['function']['parameters']['properties']:
            clock[0] += offer_count_delay
        return {'input_tokens': amount(messages, tools), 'wall_seconds': 0}

    def send(cfg, messages, output, timeout, tools):
        offered = 'checkpoint' in tools[0]['function']['parameters']['properties']
        captured.append({'cfg': deepcopy(cfg), 'messages': deepcopy(messages),
                         'tools': deepcopy(tools), 'offered': offered, 'timeout': timeout})
        if offered and mode == 'transport_error':
            raise OSError('synthetic dispatched transport loss')
        if offered and mode == 'unknown':
            response = {'status': 'error', 'input_tokens': None, 'output_tokens': None,
                'wall_seconds': 1, 'error_kind': 'request_or_response', 'timeout_scope': None}
        else:
            args = {'code': 'synthetic action', 'span_ids': []}
            if offered and mode != 'missing':
                args['checkpoint'] = {} if mode == 'invalid' else deepcopy(VALID)
            arguments = 'not JSON' if offered and mode == 'malformed' else json.dumps(args)
            cached = first_cached if len(captured) == 1 else 10
            response = {'status': 'ok', 'input_tokens': amount(messages, tools),
                'output_tokens': 80 if offered else 20, 'wall_seconds': 1,
                'cached_input_tokens': cached,
                'done_reason': 'length' if offered and mode == 'truncated' else 'tool_calls',
                'message': {'role': 'assistant', 'content': None, 'reasoning_content': 'synthetic reasoning',
                    'tool_calls': [{'id': f'c{len(captured)}', 'type': 'function',
                                   'function': {'name': 'run_python', 'arguments': arguments}}]},
                'timings': {'cache_n': cached, 'prompt_n': amount(messages, tools) - cached,
                            'predicted_n': 80 if offered else 20, 'prompt_ms': 100, 'predicted_ms': 100}}
        (output / 'response.json').write_text(json.dumps(response))
        return response

    def program(source, observations, channel, **kwargs):
        executed.append(source)
        return {'status': 'ok', 'stdout': 'synthetic observation', 'stdout_truncated': False,
                'api_requests': 0, 'declared_complete': False, 'unknown_effects': False}

    with tempfile.TemporaryDirectory() as directory, \
         patch('inline_checkpoint_inference.time.monotonic', side_effect=lambda: clock[0]), \
         patch('inline_checkpoint_inference.count_input', side_effect=count), \
         patch('tool_choice_residual.count_input', side_effect=count), \
         patch('tool_choice_residual.model_call', side_effect=send):
        folder = Path(directory)
        infer = InlineCheckpointInference(config, folder, conversation=conversation)
        for _ in range(steps):
            current = []
            def record(row, display=True):
                sid = f's{len(archived) + 1}'
                saved = {'id': sid, **deepcopy(row)}
                archived.append(saved)
                if display:
                    current.append(saved)
                return sid
            try:
                messages, _ = conversation.for_model()
                message = infer.call('agent', messages, CODE_TOOLS)
                _, split = execute_inline_response(message, None, None, archived, record,
                    offered=infer.current_offer, finish_reason=infer.calls[-1]['finish_reason'],
                    usage_known=infer.calls[-1]['status'] == 'ok',
                    out=folder, storage=folder, call_id=infer.calls[-1]['id'],
                    remaining_api=lambda: 8, may_continue=lambda: True,
                    remaining_wall=lambda: 12, read_archive=lambda *args: None, program=program)
                conversation.append(message, current)
                if not (omit_close and infer.current_offer):
                    infer.close_turn(split)
            except Exception as error:
                errors.append({'type': type(error).__name__, 'message': str(error)})
                break
        saved = {p.stem: json.loads(p.read_text()) for p in folder.glob('*.json')}
        return {'infer': infer, 'calls': deepcopy(infer.calls), 'attempts': attempt_usage(infer),
                'captured': captured, 'counts': counts, 'executed': executed, 'archived': archived,
                'conversation': conversation.messages(), 'errors': errors, 'saved': saved,
                'summary': infer.checkpoint_summary()}
