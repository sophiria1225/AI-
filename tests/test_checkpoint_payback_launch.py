"""The baseline input stays P123, and unclosed predecessors cannot launch."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import run_whole_task_checkpoint_payback as driver
from whole_task_checkpoint_payback import config_for, fixed_fields, initial_conversation, make_notification
from whole_task_rolling_checkpoint import config_for as old_config
from api_error_comparison import task_snapshot
from tool_choice_local_llama import payload_for
from public_display import CODE_TOOLS


class LaunchTests(unittest.TestCase):
    def test_original_P123_baseline_config_and_actor_payload_both_seeds(self):
        old = json.loads((ROOT / 'configs/P123_whole_task_rolling_checkpoint_v01.json').read_text())
        original = json.loads((ROOT / old['source_plan']).read_text())
        task = next(t for t in old['known_tasks'] if t['source_run'] == 'P29_04_CODE')
        plan = {**fixed_fields(), 'known_tasks': [task]}
        messages, _ = initial_conversation(original, {'instruction': 'Synthetic baseline only.'}).for_model()
        def payload(config, mode):
            supplied, _ = make_notification(messages, task_snapshot(config, [], 0, 0), mode, wall_limit=1800)
            cfg = {**config['model'], 'temperature': original['agent_temperature'],
                'seed': config['seed'], 'num_predict': original['max_output_tokens'], 'cache_prompt': False}
            return payload_for(cfg, supplied, CODE_TOOLS)
        for rep, seed in ((1, 57), (2, 157)):
            previous = old_config(original, {**old, 'model_seed': seed}, task['task_id'], 'rolling_separate')
            for mode in ('rolling_separate', 'empirical_payback'):
                with self.subTest(seed=seed, mode=mode):
                    current = config_for(original, plan, task['task_id'], mode, rep)
                    self.assertEqual({k: current[k] for k in previous}, previous)
                    self.assertEqual(payload(current, mode), payload(previous, 'rolling_separate'))
                    self.assertEqual(current['max_api_requests'], 80)

    def test_unclosed_predecessor_blocks_before_contact_count_or_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'root'; storage = Path(tmp) / 'storage'
            root.mkdir(); storage.mkdir()
            with patch.object(driver, 'sources', return_value=({}, {}, [], [])), \
                 patch.object(driver, 'launch_predecessor_closed', side_effect=ValueError('P132_active')), \
                 patch.object(driver, 'live_identity') as live, \
                 patch.object(driver, 'frozen_hashes') as frozen, \
                 patch.object(driver, 'count_input') as counted:
                with self.assertRaisesRegex(ValueError, 'P132_active'):
                    driver.preflight(storage, root)
                live.assert_not_called(); frozen.assert_not_called(); counted.assert_not_called()
                self.assertFalse((storage / 'records/context_pilot/P133_preflight_v01').exists())


if __name__ == '__main__':
    unittest.main()
