import json
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from replay_context_prefix import replay_span, replay_prefix


class PrefixReplayControls(unittest.TestCase):
    def test_malformed_action_is_never_executed(self):
        bridge = Mock()
        value, sent = replay_span(bridge, {"action": {
            "name": "appworld_api", "arguments": '{"app":"unfinished'}})
        bridge.request.assert_not_called()
        self.assertFalse(sent)
        self.assertIn("format_error", value)

    def test_replay_stops_at_first_observation_difference(self):
        bridge = Mock()
        bridge.request.return_value = {"ok": True, "result": {"value": 2}}
        span = {"action": {"name": "appworld_api", "arguments": json.dumps({
            "app": "demo", "api": "read", "args": {}})}, "observation": {"value": 1}}
        rows = replay_prefix(bridge, {"s1": span, "s2": span}, 2)
        self.assertEqual(bridge.request.call_count, 1)
        self.assertEqual(len(rows), 1)
        self.assertFalse(rows[0]["observation_matches"])

    def test_arbitrary_code_or_other_wrappers_are_not_replayed(self):
        bridge = Mock()
        with self.assertRaises(ValueError):
            replay_span(bridge, {"action": {"name": "shell", "arguments": "{}"}})
        bridge.request.assert_not_called()


if __name__ == "__main__":
    unittest.main()
