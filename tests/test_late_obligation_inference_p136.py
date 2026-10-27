"""Synthetic paid admission and checkpoint boundaries, with no model or API."""
from contextlib import ExitStack
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path[:0] = [str(Path(__file__).resolve().parents[1] / 'scripts'), str(Path(__file__).resolve().parent)]
from checkpoint_attempt_usage import attempt_usage
from late_obligation_inference_p136 import LateObligationInference
from late_obligation_runtime_p136 import LateObligationRuntime
from observed_obligation_tools import OBLIGATION_TOOLS
from late_obligation_core_p136 import CONTRACT_ID, NOTICE_PREFIX
from public_display import CODE_TOOLS
from protocol_stable_history import StableReferenceConversation
from receipt_reasoning_history import digest
from single_checkpoint_history import FIELDS
from test_partitioned_export_monitor import Fixture, TASK
from test_receipt_disclosure_rolling_inference import config as base_config


def fixture(mode='entity_fields', *, notice_cost=777, unknown_focus=False,
            unknown_actor=False, missing_actor=False, invalid_focus=False, turns=7,
            corrupt_boundary=False, folder=None):
    captured, counts = [], []
    conversation = StableReferenceConversation('Synthetic shared instructions', deepcopy(TASK))
    def measured(messages, tools):
        value = 5000 + 4000 * sum(m['role'] == 'assistant' for m in messages) if tools else 1000
        return value + (notice_cost if NOTICE_PREFIX in messages[0]['content'] else 0)
    def count(cfg, messages, tools, timeout):
        counts.append(dict(messages=deepcopy(messages), tools=deepcopy(tools)))
        return dict(input_tokens=measured(messages, tools), wall_seconds=0)
    def send(cfg, messages, output, timeout, tools):
        assert counts[-1]['messages'] == messages and counts[-1]['tools'] == tools
        role = 'agent' if tools else 'focus'
        captured.append(dict(role=role, messages=deepcopy(messages), config=deepcopy(cfg), tools=deepcopy(tools)))
        if tools and missing_actor and NOTICE_PREFIX in messages[0]['content']:
            raise OSError('synthetic paid dispatch without terminal usage')
        if (not tools and unknown_focus) or (tools and unknown_actor and NOTICE_PREFIX in messages[0]['content']):
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
    def execute(root):
        cfg = base_config('full'); cfg.update(run_id='synthetic_execution', obligation_mode=mode)
        with ExitStack() as stack:
            stack.enter_context(patch('late_obligation_core_p136.verify_late_obligation_sources', return_value=CONTRACT_ID))
            runtime = LateObligationRuntime(deepcopy(TASK), root, execution_scope=cfg['run_id'], public_source_directory='synthetic')
            f = Fixture().sources(); f.partition(False); f.partition(True, ids=(2,))
            for event, span in f.rows:
                runtime.observe(event, span)
            for name in ('rolling_checkpoint_inference.count_agent_input', 'rolling_checkpoint_inference.count_summary_input',
                         'tool_choice_residual.count_input', 'fixed_budget_residual.count_input'):
                stack.enter_context(patch(name, side_effect=count))
            for name in ('tool_choice_residual.model_call', 'fixed_budget_residual.model_call'):
                stack.enter_context(patch(name, side_effect=send))
            infer = LateObligationInference(cfg, root, conversation=conversation, obligation_runtime=runtime)
            if corrupt_boundary:
                old = infer.disclosure.prepare_packet
                def corrupt(packet, revision, *, accepted):
                    answer = old(packet, revision, accepted=accepted)
                    runtime.records.append({'index':len(runtime.records), 'synthetic_corruption':True})
                    return answer
                infer.disclosure.prepare_packet = corrupt
            error = None
            for n in range(turns):
                try:
                    response = infer.call('agent', conversation.for_model()[0],
                        CODE_TOOLS)
                except Exception as exc:
                    error = exc; break
                conversation.append(response, [dict(id=f'synthetic-{n}', assistant=response['content'],
                    action=None, observation={'status':'synthetic_no_operation'})])
            summary = infer.obligation_summary()
            saved = {p.stem:json.loads(p.read_text()) for p in root.glob('*.json')}
            return dict(infer=infer, runtime=runtime, conversation=conversation, captured=captured, counts=counts,
                        saved=saved, summary=summary, error=error, usage=attempt_usage(infer))
    if folder is not None:
        return execute(Path(folder))
    with tempfile.TemporaryDirectory() as tmp:
        return execute(Path(tmp))


class LateObligationInferenceTests(unittest.TestCase):
    def test_count_send_exact_notice_capture_common_and_only_next_actor(self):
        runs = [fixture(mode) for mode in ('raw_anchor','ids_only','entity_fields')]
        for run, mode in zip(runs, ('raw_anchor','ids_only','entity_fields'), strict=True):
            self.assertIsNone(run['error']); infer = run['infer']; summary = run['summary']
            self.assertGreater(infer.checkpoint.revision, 0)
            self.assertEqual(summary['prepared'], infer.checkpoint.revision)
            self.assertEqual(summary['runtime']['checkpoint_captures'], infer.checkpoint.revision)
            self.assertEqual(summary['actual_obligation_exposures'], infer.checkpoint.revision if mode != 'raw_anchor' else 0)
            self.assertEqual(summary['entity_rows_exposed'], 2*infer.checkpoint.revision if mode != 'raw_anchor' else 0)
            self.assertEqual(summary['field_rows_exposed'], 2*infer.checkpoint.revision if mode == 'entity_fields' else 0)
            self.assertNotIn(NOTICE_PREFIX, json.dumps(run['conversation'].messages()))
            self.assertNotIn(NOTICE_PREFIX, json.dumps([r['messages'] for r in run['captured'] if r['role']=='focus']))
            self.assertEqual(infer.tokens, sum(c['input_tokens']+c['output_tokens'] for c in run['usage']))
            self.assertEqual(len(run['usage']), len(run['captured']))
            for view in infer.obligation_views:
                sent = next(c for c,u in zip(run['captured'],run['usage'],strict=True) if u['id']==view['next_agent_call_id'])
                self.assertEqual(digest(sent['messages']), view['supplied_messages_sha256'])
                self.assertEqual(sent['messages'][0]['content'].count(NOTICE_PREFIX),int(view['obligation_included']))
        packets = [[c['packet'] for c in r['runtime'].captures] for r in runs]
        self.assertEqual(packets[0],packets[1]); self.assertEqual(packets[1],packets[2])
        self.assertEqual(runs[1]['infer'].tokens-runs[0]['infer'].tokens,
                         777*runs[1]['summary']['actual_obligation_exposures'])

    def test_admission_rejection_never_records_paid_exposure(self):
        run=fixture(notice_cost=70000); self.assertIsNotNone(run['error'])
        summary=run['summary']
        self.assertEqual(summary['runtime']['checkpoint_captures'],1)
        self.assertEqual(summary['actual_obligation_exposures'],0)
        self.assertEqual(summary['submitted'],0); self.assertTrue(summary['pending'])
        self.assertFalse(run['infer'].obligation_views[-1]['model_attempted'])
        self.assertEqual(run['captured'][-1]['role'],'focus')

    def test_paid_unknown_and_missing_terminal_consume_no_free_retry(self):
        for option in ('unknown_actor','missing_actor'):
            run=fixture(**{option:True}); self.assertIsNotNone(run['error'])
            summary=run['summary']
            self.assertEqual(summary['actual_obligation_exposures'],1)
            self.assertEqual(summary['submitted'],1); self.assertFalse(summary['pending'])
            self.assertEqual(sum(c['status']!='ok' for c in run['usage']),1)
            self.assertIsNone(run['usage'][-1]['input_tokens'])
            self.assertTrue(run['infer'].obligation_views[-1]['usage_unknown'])
            with self.assertRaises(ValueError):
                run['infer'].call('agent',run['conversation'].for_model()[0],OBLIGATION_TOOLS)

    def test_bad_or_unknown_focus_cannot_capture(self):
        for option in ('unknown_focus','invalid_focus'):
            run=fixture(**{option:True})
            self.assertEqual(run['summary']['runtime']['checkpoint_captures'],0)
            self.assertGreater(sum(c['role']=='focus' for c in run['usage']),0)

    def test_evidence_boundary_tamper_blocks_next_actor_dispatch(self):
        run=fixture(corrupt_boundary=True)
        self.assertIn('obligation_record_boundary_changed',str(run['error']))
        self.assertTrue(run['summary']['contract_failed'])
        self.assertEqual(run['captured'][-1]['role'],'focus')
        self.assertEqual(run['summary']['actual_obligation_exposures'],0)

    def test_wrong_tool_capabilities_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            run=fixture('raw_anchor', turns=1, folder=tmp)
            with self.assertRaisesRegex(ValueError,'fixed_obligation_tool_capabilities_required'):
                run['infer'].call('agent',run['conversation'].for_model()[0],OBLIGATION_TOOLS)

if __name__=='__main__': unittest.main()
