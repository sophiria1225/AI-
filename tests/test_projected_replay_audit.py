import copy
import json
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from audit_projected_replay import replay_kind, observation_matches


class ProjectedReplayAuditTests(unittest.TestCase):
    def setUp(self):
        self.event = {"stage": "python_api", "api_request_sent": False, "effects_unknown": False}
        self.obs = {"observation": '{"title":"example"}',
                    "field_read": {"source": "cross_api", "full_api_response": False,
                                   "requested_fields": ["title"]}}
        self.span = {"action": {"name": "spotify__show_song"}, "observation": self.obs}

    def test_cache_hit_needs_a_real_verification_dispatch(self):
        self.assertEqual(replay_kind(self.event, self.span), "cached")
        self.assertTrue(observation_matches("cached", self.obs,
                        {"observation": '{"title":"example","extra":3}', "declared_complete": False}))

    def test_changed_missing_or_error_reply_cannot_pass(self):
        for actual in ({"observation": '{"title":"changed"}'}, {"observation": '{}'},
                       {"api_error": "failure"}, {"observation": '{"title":"example"}', "declared_complete": True}):
            self.assertFalse(observation_matches("cached", self.obs, actual))

    def test_sent_receipt_strips_only_harness_metadata(self):
        actual = {"observation": '{"title":"example"}'}
        self.assertTrue(observation_matches("sent", self.obs, actual))
        self.assertFalse(observation_matches("sent", self.obs, actual | {"declared_complete": True}))
        self.assertIn("field_read", self.obs)

    def test_unsent_rejection_is_not_miscounted_as_cached(self):
        self.assertEqual(replay_kind(self.event, {"observation": {"not_executed": "budget"}}), "skip")
        with self.assertRaises(ValueError):
            replay_kind(self.event | {"effects_unknown": True}, self.span)

    def test_cross_api_cannot_claim_a_full_object_or_other_api(self):
        span = copy.deepcopy(self.span); span["observation"]["field_read"].update(full_api_response=True, requested_fields=None)
        with self.assertRaises(ValueError): replay_kind(self.event, span)
        span = copy.deepcopy(self.span); span["action"]["name"] = "other__read"
        with self.assertRaises(ValueError): replay_kind(self.event, span)

    def test_exact_full_object_requires_all_fields_to_match(self):
        obs = copy.deepcopy(self.obs); obs["field_read"].update(source="exact", full_api_response=True, requested_fields=None)
        self.assertFalse(observation_matches("cached", obs, {"observation": '{"title":"example","extra":3}'}))


if __name__ == "__main__": unittest.main()
