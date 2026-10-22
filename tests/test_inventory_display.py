import copy
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import test_contract_retention_controls as fixtures
from documentation_print_origin import build_origin_view
from handoff_factors import split_turns
from inventory_display import ARMS, InventoryInference, build_condition, disposition, validate_matched_views
from native_conversation import recover_turn
from run_inventory_comparison import run_order


class InventoryTests(unittest.TestCase):
    def test_matched_removal_preserves_actions_literals_latest_and_source(self):
        item = fixtures.DetailControlTests().fixture(); original = copy.deepcopy(item)
        checked = validate_matched_views(item)
        self.assertEqual(checked[ARMS[1]]['detail_receipt_ids'], ['i1', 'i3', 'i5'])
        self.assertEqual(checked[ARMS[2]]['listing_receipt_ids'], ['i0', 'i2', 'i4', 'i6'])
        views = [build_condition(item, arm)[0] for arm in ARMS]
        self.assertEqual(views[0].messages(), build_origin_view(item)[0]['full_keep'].messages())
        for before, detail, both in zip(*(split_turns(v.messages()) for v in views), strict=True):
            self.assertEqual(before[0], detail[0]); self.assertEqual(before[0], both[0])
            a, d, b = [recover_turn(v)[0] for v in (before, detail, both)]
            for candidate in (d, b):
                self.assertEqual(candidate['action'], a['action'])
                self.assertIn('literal task marker', candidate['observation']['stdout'])
                for field, value in a['observation'].items():
                    if field != 'stdout': self.assertEqual(candidate['observation'][field], value)
            if a['id'] in ('o1', 'o3', 'o5'):
                self.assertEqual(d, b)  # identical markers and metadata too
            if a['id'] == 'o7': self.assertEqual(a, d); self.assertEqual(a, b)
        self.assertEqual(item, original)

    def test_unrecognized_or_changed_output_is_not_silently_omitted(self):
        item = fixtures.DetailControlTests().fixture()
        item['programs'][1]['expected']['stdout'] += 'changed'
        for arm in ARMS:
            with self.assertRaises(ValueError): build_condition(item, arm)

    def test_schedule_covers_every_cell_once_without_outcome_selection(self):
        order = run_order([{'task_id': n} for n in range(4)])
        self.assertEqual(len(order), 12)
        self.assertEqual({(n, arm) for n, _, arm in order},
                         {(n, arm) for n in range(1, 5) for arm in ARMS})
        with self.assertRaises(ValueError): run_order([{}, {}, {}])

    def test_unknown_model_usage_is_evaluated_but_never_retried_in_cell(self):
        base = {'setup': {'status': 'matched_observable_prefix'}, 'unknown_effect_requests': 0,
                'stop_reason': 'wall_limit_during_model_call', 'unknown_usage_calls': 1}
        self.assertEqual(disposition(base), 'evaluate_unknown_usage')
        self.assertEqual(disposition({**base, 'stop_reason': 'model_usage_unknown'}), 'evaluate_unknown_usage')
        for change in ({'unknown_effect_requests': 1}, {'stop_reason': 'cleanup_error'},
                       {'stop_reason': 'runtime_error'}, {'stop_reason': 'agent_declared_complete'},
                       {'setup': {'status': 'failed'}}):
            self.assertEqual(disposition({**base, **change}), 'stop_batch')
        self.assertEqual(disposition({**base, 'unknown_usage_calls': 0,
                                     'stop_reason': 'token_reservation_limit'}), 'evaluate')
        with tempfile.TemporaryDirectory() as folder:
            infer = InventoryInference({'model': {}, 'phase': 'P55'}, Path(folder), ARMS[1])
            infer.calls = [{'status': 'error'}]
            # The inherited admission policy refuses unknown residual budgets.
            from residual_output_budget import ResidualInference
            with self.assertRaisesRegex(RuntimeError, 'unknown usage'):
                ResidualInference.call(infer, 'agent', [], [])


if __name__ == '__main__': unittest.main()
