"""Handwritten patch/control/admission tests; no model, native count or API calls."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import checkpoint_state_update_p144 as core
from checkpoint_early_threshold_p143 import DeltaEnvelopeCheckpoint as PriorCheckpoint
from checkpoint_state_update_inference_p144 import StateUpdateInference
import rolling_checkpoint_inference as rolling
from receipt_reasoning_history import digest
from single_checkpoint_history import FIELDS, candidate


def history(n):
    rows = [{'role': 'system', 'content': 'handwritten synthetic instructions'},
            {'role': 'user', 'content': 'handwritten synthetic task'}]
    for i in range(n):
        rows += [{'role': 'assistant', 'content': '', 'tool_calls': [{'id': f'c{i}',
            'type': 'function', 'function': {'name': 'run_python', 'arguments': '{}'}}]},
            {'role': 'tool', 'tool_call_id': f'c{i}', 'content': f'synthetic {i}'}]
    return rows


def state():
    return {f: [f + ' original A', f + ' original B'] for f in FIELDS}


def message(value):
    return {'role': 'assistant', 'content': json.dumps(value, ensure_ascii=False)}


def keep(old):
    return {f: {'keep': list(range(len(old[f]))), 'update': [], 'delete': [], 'add': []} for f in FIELDS}


def edited(old):
    result = keep(old)
    result['completed'] = {'keep': [], 'update': [{'index': 0, 'text': 'replacement'}],
                           'delete': [1], 'add': ['new item']}
    return result


def installed(mode=core.MODES[2], value=None):
    c = core.StateUpdateCheckpoint(mode)
    c.begin(history(6), 8192)
    c.close_separate(history(6), message(state() if value is None else value), 'stop', usage_known=True)
    c.decide(8192, 4000)
    return c


def update_installed(patch_value=None):
    c = installed()
    c.begin(history(9), 8192)
    c.close_separate(history(9), message(edited(state()) if patch_value is None else patch_value),
                     'stop', usage_known=True)
    c.decide(8192, 4000)
    return c


class StateUpdateTests(unittest.TestCase):
    def test_old_two_controllers_packets_events_and_views_unchanged(self):
        for mode in core.MODES[:2]:
            a, b = PriorCheckpoint(mode), core.StateUpdateCheckpoint(mode)
            for raw, value in ((history(6), state()), (history(9), {f: ['delta ' + f] for f in FIELDS})):
                self.assertEqual(a.begin(raw, 8192), b.begin(raw, 8192))
                self.assertEqual(a.close_separate(raw, message(value), 'stop', usage_known=True),
                                 b.close_separate(raw, message(value), 'stop', usage_known=True))
                self.assertEqual(a.decide(8192, 4000), b.decide(8192, 4000))
                self.assertEqual(a.view(raw), b.view(raw))
            self.assertFalse(b.update_applied)

    def test_first_packet_identical_and_second_user_packet_identical(self):
        first = [core.StateUpdateCheckpoint(m).begin(history(6), 8192)['summary_messages'] for m in core.MODES]
        self.assertEqual(first, [candidate(history(6))['summary_messages']] * 3)
        second = [installed(m).begin(history(9), 8192) for m in core.MODES]
        self.assertEqual([x['summary_messages'][1] for x in second], [second[0]['summary_messages'][1]] * 3)
        self.assertEqual(second[2]['summary_messages'][0]['content'], core.UPDATE_SUMMARY_PROMPT)
        self.assertFalse(second[2]['delta_requested'])
        self.assertTrue(second[2]['update_requested'])
        self.assertEqual(second[2]['update_prior_state_sha256'], digest(state()))

    def test_atomic_keep_update_delete_add_original_order_and_no_input_mutation(self):
        old = {f: ['a', 'b', 'c', 'd'] for f in FIELDS}
        operations = {f: {'keep': [3, 0], 'update': [{'index': 1, 'text': 'B'}],
                         'delete': [2], 'add': ['e', 'f']} for f in FIELDS}
        before = deepcopy((old, operations))
        new, counts = core.apply_update_patch(old, operations)
        self.assertEqual(new, {f: ['a', 'B', 'd', 'e', 'f'] for f in FIELDS})
        self.assertEqual((old, operations), before)
        self.assertEqual(counts, dict(kept_old_items=8, update_operations=4, unchanged_update_operations=0,
            updated_old_items=4, deleted_old_items=4, added_items=8, changed_old_items=8, final_items=20))

    def test_partition_rejects_missing_duplicate_cross_action_wrong_type_and_range(self):
        cases = []
        for bad in ([0], [0, 0, 1], [True, 1], [-1, 0], [0, 2], ['0', 1]):
            p = keep(state()); p['completed']['keep'] = bad; cases.append(p)
        p = keep(state()); p['completed']['delete'] = [0]; cases.append(p)
        p = keep(state()); p['completed']['update'] = [{'index': 1, 'text': 'x'}]; cases.append(p)
        for p in cases:
            with self.subTest(p=p), self.assertRaises(ValueError): core.apply_update_patch(state(), p)

    def test_schema_and_text_limits_and_duplicate_json_keys(self):
        cases = []
        p = keep(state()); p['extra'] = {}; cases.append(p)
        p = keep(state()); p['completed']['extra'] = []; cases.append(p)
        p = keep(state()); p['completed']['keep'] = (0, 1); cases.append(p)
        for bad in ('', 'x' * 2049, 1, None):
            p = keep(state()); p['completed']['add'] = [bad]; cases.append(p)
        for p in cases:
            with self.assertRaises((ValueError, TypeError)): core.apply_update_patch(state(), p)
        content = message(keep(state()))['content'].replace('"keep":', '"keep": [], "keep":', 1)
        with self.assertRaises(ValueError): core.parse_update_patch({'role': 'assistant', 'content': content}, 'stop', state())
        for body, finish in ((message(keep(state())), 'length'),
                             ({'role': 'assistant', 'content': 'x' * 8193}, 'stop'),
                             ({**message(keep(state())), 'tool_calls': [{}]}, 'stop')):
            with self.assertRaises(ValueError): core.parse_update_patch(body, finish, state())

    def test_materialized_field_and_character_limits_not_just_patch_size(self):
        old = {f: ['x'] * 32 for f in FIELDS}; p = keep(old); p['completed']['add'] = ['x']
        with self.assertRaisesRegex(ValueError, 'combined_summary_field_too_long'): core.apply_update_patch(old, p)
        old = {f: ['x' * 1800] for f in FIELDS}; p = keep(old); p['completed']['add'] = ['y' * 1500]
        self.assertLess(len(message(p)['content']), 8192)
        with self.assertRaisesRegex(ValueError, 'combined_summary_body_too_long'): core.parse_update_patch(message(p), 'stop', old)
        old = {f: [] for f in FIELDS}; p = keep(old)
        self.assertEqual(core.apply_update_patch(old, p)[0], old)

    def test_installed_single_note_unchanged_archive_recent_suffix_and_edit_counts(self):
        raw = history(9); saved = deepcopy(raw); c = installed(); c.begin(raw, 8192)
        views = c.close_separate(raw, message(edited(state())), 'stop', usage_known=True)
        event = c.decide(8192, 4000)
        self.assertEqual(raw, saved)
        self.assertEqual(c.view(raw), views['compacted'])
        self.assertEqual(c.view(raw)[-4:], raw[-4:])
        self.assertEqual(c.fragment_count, 1); self.assertFalse(c.delta_applied); self.assertTrue(c.update_applied)
        self.assertEqual(c.summary_notes, [core.summary_note(core.apply_update_patch(state(), edited(state()))[0])])
        self.assertTrue(event['update_state_changed']); self.assertEqual(event['update_operation_counts']['changed_old_items'], 2)
        self.assertIsNone(c.begin(history(12), 99999))

    def test_allkeep_identical_replacement_and_add_only_not_old_change(self):
        patches = [keep(state())]
        p = keep(state()); p['completed']['keep'] = [1]
        p['completed']['update'] = [{'index': 0, 'text': state()['completed'][0]}]; patches.append(p)
        p = keep(state()); p['completed']['add'] = ['addition']; patches.append(p)
        for i, p in enumerate(patches):
            c = update_installed(p); e = c.events[-1]
            self.assertTrue(e['update_applied']); self.assertEqual(e['update_operation_counts']['changed_old_items'], 0)
            self.assertEqual(e['update_state_changed'], i == 2)
        self.assertEqual(update_installed(patches[1]).events[-1]['update_operation_counts']['unchanged_update_operations'], 1)

    def test_nonshorter_does_not_install_or_advance_cutoff(self):
        c = installed(); before = c.view(history(9)); cutoff = c.cutoff
        c.begin(history(9), 8192); c.close_separate(history(9), message(edited(state())), 'stop', usage_known=True)
        e = c.decide(8192, 8192)
        self.assertEqual(e['reason'], 'not_shorter'); self.assertFalse(e['update_applied'])
        self.assertEqual(c.view(history(9)), before); self.assertEqual(c.cutoff, cutoff)
        self.assertFalse(c.update_applied)

    def test_stale_state_rejected_before_close_and_before_decide(self):
        for stage in ('close', 'decide'):
            c = installed(); c.begin(history(9), 8192)
            if stage == 'decide': c.close_separate(history(9), message(keep(state())), 'stop', usage_known=True)
            c._values[0]['completed'][0] = 'unexpected host mutation'
            if stage == 'close': c.close_separate(history(9), message(keep(state())), 'stop', usage_known=True)
            else: c.decide(8192, 4000)
            self.assertEqual(c.events[-1]['reason'], 'stale_update_state')
            self.assertFalse(c.update_applied); self.assertEqual(c.revision, 1)

    def test_known_invalid_reason_and_first_rejection_fallback(self):
        for content, finish, reason in ((message({'bad': 1}), 'stop', 'invalid_update_patch'),
                                        (message(keep(state())), 'length', 'update_finish_not_stop')):
            c = installed(); before = c.view(history(9)); c.begin(history(9), 8192)
            views = c.close_separate(history(9), content, finish, usage_known=True)
            self.assertIsNone(views['compacted']); self.assertEqual(c.events[-1]['reason'], reason)
            self.assertEqual(c.view(history(9)), before); self.assertIsNone(c.pending)
        c = core.StateUpdateCheckpoint(core.MODES[2]); c.begin(history(6), 8192)
        c.close_separate(history(6), message({'bad': 1}), 'stop', usage_known=True)
        offer = c.begin(history(9), 8192)
        self.assertFalse(offer['update_requested']); self.assertEqual(offer['summary_messages'], candidate(history(9))['summary_messages'])

    def test_unknown_focus_blocks_without_installation_or_fictitious_rejection(self):
        c = installed(); c.begin(history(9), 8192)
        with self.assertRaisesRegex(ValueError, 'unknown_usage_blocks'):
            c.close_separate(history(9), None, None, usage_known=False)
        self.assertEqual(len(c.events), 1); self.assertFalse(c.update_applied)
        with self.assertRaises(ValueError): c.view(history(9))

    def test_all_three_modes_same_threshold_freshness_limits(self):
        for mode in core.MODES:
            kwargs = dict(mode=mode, opportunities=1, fresh_turns=3, eligible_raw=True,
                          measured_input_tokens=8192, accumulated_exposure=0, previous_focus_cost=100)
            self.assertTrue(core.trigger_decision(**kwargs)['offer'])
            for changes in ({'measured_input_tokens': 8191}, {'fresh_turns': 2},
                            {'opportunities': 2}, {'eligible_raw': False}):
                self.assertFalse(core.trigger_decision(**{**kwargs, **changes})['offer'])
        with self.assertRaises(ValueError): core.StateUpdateCheckpoint('exposure_delta_object')


class InferenceBoundaryTests(unittest.TestCase):
    def fake_inference(self, output, *, mode=core.MODES[2]):
        infer = object.__new__(StateUpdateInference)
        infer.output = Path(output)
        infer.config = {'max_calls': 80, 'max_total_tokens': 450000, 'max_output_tokens': 4096,
                        'model': {'num_ctx': 65536}, 'checkpoint_timing': 'threshold',
                        'checkpoint_representation': core.representation_for(mode)}
        infer.calls, infer.admissions = [], []
        infer.checkpoint = installed(mode)
        infer.representation_mode = mode
        infer.controls, infer.closed, infer.offers = [], [], []
        infer.exposure = core.StateUpdateExposureLedger(mode)
        infer.exposure.previous_focus_cost, infer.exposure.accumulated_exposure = 100, 77
        infer.exposure_contract_failed = False
        infer.exposure_decisions, infer.exposure_counts = [], []
        infer.representation_views, infer.state_update_views = [], []
        infer._save = lambda: None
        infer._count = lambda *args: {'input_tokens': 200}
        return infer

    def test_known_paid_invalid_focus_reason_and_exposure_reset_preserved(self):
        for mode in core.MODES:
            with tempfile.TemporaryDirectory() as folder:
                infer = self.fake_inference(folder, mode=mode)
                offered = infer.checkpoint.begin(history(9), 8192)
                infer.offers = [dict(after_model_calls=0, offer=offered)]
                def focus(instance, role, messages, tools):
                    instance.admissions.append(dict(next_call_id='call_001', role='focus', model_request_started=True))
                    instance.calls.append(dict(id='call_001', role='focus', status='ok', input_tokens=200,
                                               output_tokens=31, finish_reason='stop'))
                    return message({'invalid': True})
                with patch.object(rolling.FixedBudgetResidualInference, 'call', focus):
                    infer._summarize_separately(history(9), [], offered)
                self.assertEqual(infer.tokens, 231)
                self.assertEqual(infer.exposure.previous_focus_cost, 231)
                self.assertEqual(infer.exposure.accumulated_exposure, 0)
                self.assertEqual(infer.exposure.events[-1]['status'], 'known_paid_focus')
                terminal = [c for c in infer.controls if c['status'] == 'checkpoint_terminal_without_counted_decision']
                self.assertEqual(len(terminal), 1); self.assertFalse(terminal[0]['accepted'])
                self.assertIsNone(infer.checkpoint.pending)
                if mode == core.MODES[2]:
                    summary = infer.state_update_summary()
                    self.assertEqual(summary['update_prompt_known_focus_calls'], 1)
                    self.assertEqual(summary['update_installations'], 0)

    def test_unstarted_focus_neither_paid_nor_fake_installation(self):
        with tempfile.TemporaryDirectory() as folder:
            infer = self.fake_inference(folder); infer.config['max_calls'] = 1
            offered = infer.checkpoint.begin(history(9), 8192)
            infer.offers = [dict(after_model_calls=0, offer=offered)]
            with patch.object(rolling.FixedBudgetResidualInference, 'call', side_effect=AssertionError('must not dispatch')):
                infer._summarize_separately(history(9), [], offered)
            self.assertEqual(infer.calls, []); self.assertEqual(infer.tokens, 0)
            self.assertEqual(infer.exposure.previous_focus_cost, 100)
            summary = infer.state_update_summary()
            self.assertEqual(summary['update_prompt_offers'], 1)
            self.assertEqual(summary['update_prompt_dispatched_focus_calls'], 0)
            self.assertEqual(summary['actual_update_actor_calls'], 0)

    def test_actor_update_exposure_known_unknown_and_unsent_are_separate(self):
        with tempfile.TemporaryDirectory() as folder:
            infer = self.fake_inference(folder); infer.checkpoint = update_installed()
            infer.snapshots, infer.projections = [], []
            for index, attempted, terminal, unknown in ((1, True, True, False), (2, False, False, False), (3, True, False, True)):
                snapshot = dict(next_call_id=f'call_{index:03d}', model_messages_sha256='a' * 64,
                    model_tools_sha256='b' * 64, model_attempted=attempted,
                    terminal_usage_recorded=terminal, usage_unknown=unknown)
                infer.snapshots.append(snapshot)
                infer.projections.append(dict(next_agent_call_id=snapshot['next_call_id'], checkpoint_revision=2))
                infer._record_representation_view(index - 1)
            summary = infer.state_update_summary()
            self.assertEqual(summary['actual_update_actor_calls'], 2)
            self.assertEqual(summary['actual_update_known_actor_calls'], 1)
            self.assertEqual(summary['actual_update_unknown_actor_calls'], 1)
            self.assertEqual(summary['actual_changed_old_actor_calls'], 2)
            self.assertEqual(summary['changed_old_items'], 2)
            self.assertEqual(infer.representation_summary()['actual_delta_actor_calls'], 0)

    def test_delete_readd_identical_state_not_effective_old_item_exposure(self):
        old = state(); p = keep(old)
        p['completed'] = {'keep': [0], 'update': [], 'delete': [1], 'add': [old['completed'][1]]}
        with tempfile.TemporaryDirectory() as folder:
            infer = self.fake_inference(folder); infer.checkpoint = update_installed(p)
            self.assertEqual(infer.checkpoint.installed_update_counts['changed_old_items'], 1)
            self.assertFalse(infer.checkpoint.installed_update_state_changed)
            infer.snapshots = [dict(next_call_id='call_001', model_messages_sha256='a'*64,
                model_tools_sha256='b'*64, model_attempted=True, terminal_usage_recorded=True, usage_unknown=False)]
            infer.projections = [dict(next_agent_call_id='call_001', checkpoint_revision=2)]
            infer._record_representation_view(0)
            summary = infer.state_update_summary()
            self.assertEqual(summary['update_installations'], 1)
            self.assertEqual(summary['actual_update_known_actor_calls'], 1)
            for key in ('state_changed_installations', 'old_items_changed_installations',
                        'actual_changed_old_known_actor_calls'):
                self.assertEqual(summary[key], 0)

    def test_initialization_rejects_wrong_trigger_before_external_io(self):
        for threshold in (None, True, 16384):
            with self.assertRaisesRegex(ValueError, 'fixed_P144_8192_threshold_required'):
                StateUpdateInference({'checkpoint_trigger_input_tokens': threshold}, Path('unused'), conversation=None)


if __name__ == '__main__':
    unittest.main()
