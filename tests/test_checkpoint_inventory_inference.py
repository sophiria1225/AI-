"""Real rolling decisions/admission with handwritten replies and local capture."""
from contextlib import ExitStack
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from checkpoint_attempt_usage import attempt_usage
from checkpoint_inventory_inference import CheckpointInventoryInference
from checkpoint_inventory_runtime import CheckpointInventoryRuntime
from code_agent_interface import CODE_TOOLS
from protocol_stable_history import StableReferenceConversation
from receipt_reasoning_history import digest
from single_checkpoint_history import FIELDS
from test_checkpoint_inventory_runtime import synthetic_session, SCOPE
from test_receipt_disclosure_rolling_inference import config as base_config

MARKER = 'checkpoint_runtime_inventory_v1'


def inference_fixture(mode='checkpoint_inventory', *, notice_cost=777, unknown_focus=False,
                      unknown_actor=False, invalid_focus=False, turns=7):
    conversation = StableReferenceConversation('Synthetic shared instructions', {'instruction': 'Synthetic task'})
    captured, counts = [], []
    def measured(messages, tools):
        value = 5000 + 4000 * sum(m['role'] == 'assistant' for m in messages) if tools else 1000
        return value + (notice_cost if MARKER in messages[0]['content'] else 0)
    def count(cfg, messages, tools, timeout):
        counts.append(dict(messages=deepcopy(messages), tools=deepcopy(tools)))
        return dict(input_tokens=measured(messages, tools), wall_seconds=0)
    def send(cfg, messages, output, timeout, tools):
        # Real residual code must dispatch the very same view its admission counted.
        assert counts[-1]['messages'] == messages and counts[-1]['tools'] == tools
        role = 'agent' if tools else 'focus'
        captured.append(dict(role=role, messages=deepcopy(messages), config=deepcopy(cfg)))
        if (not tools and unknown_focus) or (tools and unknown_actor and MARKER in messages[0]['content']):
            response = dict(status='error', input_tokens=None, output_tokens=None, wall_seconds=0,
                            error_kind='request_or_response')
        else:
            message = dict(role='assistant', content='Synthetic actor response' if tools else
                           '{}' if invalid_focus else json.dumps({k: ['synthetic'] for k in FIELDS}))
            tokens = measured(messages, tools)
            response = dict(status='ok', input_tokens=tokens, output_tokens=20, cached_input_tokens=0,
                wall_seconds=0, done_reason='stop', message=message,
                timings=dict(cache_n=0, prompt_n=tokens, predicted_n=20, prompt_ms=1, predicted_ms=1))
        (output / 'response.json').write_text(json.dumps(response))
        return response
    cfg = base_config('full')
    cfg.update(run_id=SCOPE, checkpoint_inventory_policy=mode, output_grounding_policy='feedback',
               projection_policy='explicit_joined_fields')
    with tempfile.TemporaryDirectory() as tmp, ExitStack() as stack:
        root = Path(tmp)
        session = synthetic_session(root)
        runtime = CheckpointInventoryRuntime(session, root, execution_scope=SCOPE)
        for name in ('rolling_checkpoint_inference.count_agent_input', 'rolling_checkpoint_inference.count_summary_input',
                     'tool_choice_residual.count_input', 'fixed_budget_residual.count_input'):
            stack.enter_context(patch(name, side_effect=count))
        for name in ('tool_choice_residual.model_call', 'fixed_budget_residual.model_call'):
            stack.enter_context(patch(name, side_effect=send))
        infer = CheckpointInventoryInference(cfg, root, conversation=conversation, inventory_runtime=runtime)
        error = None
        try:
            for n in range(turns):
                try:
                    response = infer.call('agent', conversation.for_model()[0], CODE_TOOLS)
                except Exception as exc:
                    error = exc
                    break
                conversation.append(response, [dict(id=f'synthetic-{n}', assistant=response['content'],
                    action=None, observation={'status': 'synthetic_no_operation'})])
            saved = {p.stem: json.loads(p.read_text()) for p in root.glob('*.json')}
            return dict(infer=infer, runtime=runtime, conversation=conversation, captured=captured, counts=counts,
                        saved=saved, error=error, usage=attempt_usage(infer))
        finally:
            session.close()


class InventoryInferenceTests(unittest.TestCase):
    def test_real_rolling_captures_both_modes_count_send_same_packet_once(self):
        runs = [inference_fixture(mode) for mode in ('off', 'checkpoint_inventory')]
        for run, mode in zip(runs, ('off', 'checkpoint_inventory'), strict=True):
            self.assertIsNone(run['error'])
            infer = run['infer']
            summary = infer.inventory_summary()
            self.assertGreater(infer.checkpoint.revision, 0)
            self.assertEqual(summary['prepared'], infer.checkpoint.revision)
            self.assertEqual(summary['capture']['captures'], infer.checkpoint.revision)
            self.assertEqual(summary['submitted'], infer.checkpoint.revision)
            self.assertEqual(summary['actual_inventory_exposures'], infer.checkpoint.revision if mode != 'off' else 0)
            self.assertNotIn(MARKER, json.dumps(run['conversation'].messages()))
            focuses = [r['messages'] for r in run['captured'] if r['role'] == 'focus']
            self.assertTrue(focuses)
            self.assertNotIn(MARKER, json.dumps(focuses))
            self.assertEqual(infer.tokens, sum(c['input_tokens'] + c['output_tokens'] for c in run['usage']))
            self.assertEqual(len(run['usage']), len(run['captured']))
            for view in infer.inventory_views:
                captured = next(c for c, usage in zip(run['captured'], run['usage'], strict=True)
                                if usage['id'] == view['next_agent_call_id'])
                self.assertEqual(digest(captured['messages']), view['supplied_messages_sha256'])
                if view['inventory_included']:
                    self.assertEqual(captured['messages'][0]['content'].count(MARKER), 1)
            self.assertEqual(len({v['packet_sha256'] for v in infer.inventory_views if v['inventory_prepared']}), summary['prepared'])
        self.assertEqual([r['messages'] for r in runs[0]['captured'] if r['role'] == 'focus'],
                         [r['messages'] for r in runs[1]['captured'] if r['role'] == 'focus'])
        expected_notice_cost = 777 * runs[1]['infer'].inventory_summary()['actual_inventory_exposures']
        self.assertEqual(runs[1]['infer'].tokens - runs[0]['infer'].tokens, expected_notice_cost)

    def test_capture_followed_by_admission_rejection_is_not_paid_exposure(self):
        run = inference_fixture(notice_cost=70000)
        self.assertIsNotNone(run['error'])
        summary = run['infer'].inventory_summary()
        self.assertEqual(summary['capture']['successful_captures'], 1)
        self.assertEqual(summary['actual_inventory_exposures'], 0)
        self.assertEqual(summary['submitted'], 0)
        self.assertTrue(summary['pending'])
        self.assertFalse(run['infer'].inventory_views[-1]['model_attempted'])
        self.assertEqual(run['captured'][-1]['role'], 'focus')
        self.assertEqual(sum(c['role'] == 'agent' for c in run['captured']), 3)

    def test_paid_unknown_actor_consumes_notice_without_free_retry(self):
        run = inference_fixture(unknown_actor=True)
        self.assertIsNotNone(run['error'])
        summary = run['infer'].inventory_summary()
        self.assertEqual(summary['actual_inventory_exposures'], 1)
        self.assertEqual(summary['submitted'], 1)
        self.assertFalse(summary['pending'])
        self.assertEqual(sum(c['status'] != 'ok' for c in run['usage']), 1)
        self.assertIsNone(run['usage'][-1]['input_tokens'])
        self.assertTrue(run['infer'].inventory_views[-1]['usage_unknown'])
        with self.assertRaises(ValueError):
            run['infer'].call('agent', run['conversation'].for_model()[0], CODE_TOOLS)

    def test_invalid_or_unknown_focus_never_captures(self):
        for option in ('unknown_focus', 'invalid_focus'):
            with self.subTest(option=option):
                run = inference_fixture(**{option: True})
                self.assertEqual(run['infer'].inventory_summary()['capture']['captures'], 0)
                self.assertEqual(run['infer'].inventory_summary()['actual_inventory_exposures'], 0)
                self.assertGreater(sum(c['role'] == 'focus' for c in run['usage']), 0)
                if option == 'unknown_focus':
                    self.assertIsNotNone(run['error'])
                    self.assertEqual(run['captured'][-1]['role'], 'focus')
                    self.assertEqual(sum(c['status'] != 'ok' for c in run['usage']), 1)
                else:
                    self.assertIsNone(run['error'])


if __name__ == '__main__':
    unittest.main()
