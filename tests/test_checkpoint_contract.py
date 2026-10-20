"""Synthetic controls for the E1 contract, not performance or live restore tests."""
from copy import deepcopy
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from checkpoint_contract import COMPONENTS, ContractError, compare_restore, digest, validate


class CheckpointContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "original"
        self.source.mkdir()
        components = {}
        for name in sorted(COMPONENTS):
            # The filesystem payload represents a fake adapter; no container used.
            path = self.source / (name + ".bin")
            path.write_bytes(("synthetic-control:" + name).encode())
            components[name] = {"path": path.name, "sha256": digest(path)}
        self.manifest = {
            "schema_version": 1, "checkpoint_id": "synthetic-01",
            "components": components,
            "boundary": {"active_tool_operations": 0, "pending_model_request": False,
                         "usage_complete": True, "background_processes": 0,
                         "live_external_inputs": False},
            "writable_roots": ["/app", "/tmp"], "captured_roots": ["/app", "/tmp"],
            "runtime": {"model_revision": "fixture", "tool_image": "fixture-image",
                        "inference_settings_sha256": "1" * 64,
                        "tool_config_sha256": "2" * 64, "external_inputs_sha256": "3" * 64},
            "remaining_budget": {"remaining_tokens": 10000, "remaining_calls": 6,
                                 "remaining_wall_milliseconds": 60000},
            "inference_cache_policy": "clear_before_each_branch",
        }
        self.restored = self.root / "restored"
        shutil.copytree(self.source, self.restored)

    def reject(self, manifest, reason):
        with self.assertRaisesRegex(ContractError, reason):
            validate(manifest, self.source)

    def test_matching_files_and_metadata_pass_without_claiming_live_restore(self):
        result = compare_restore(self.manifest, self.source, self.manifest, self.restored)
        self.assertTrue(result["declared_artifacts_match"])
        self.assertFalse(result["certifies_live_environment_restoration"])

    def test_conversation_and_patch_alone_are_insufficient(self):
        del self.manifest["components"]["tool_state"]
        self.reject(self.manifest, "components_fields")

    def test_missing_scratch_coverage_rejected(self):
        self.manifest["captured_roots"] = ["/app"]
        self.reject(self.manifest, "filesystem_scope_mismatch")

    def test_declared_file_missing_rejected(self):
        (self.source / "filesystem.bin").unlink()
        self.reject(self.manifest, "filesystem_missing")

    def test_content_tampering_detected(self):
        (self.source / "conversations.bin").write_bytes(b"later-state")
        self.reject(self.manifest, "conversations_content_mismatch")

    def test_path_escape_and_symlink_rejected(self):
        for name in ("../outside", "/absolute", "nested/../file"):
            m = deepcopy(self.manifest)
            m["components"]["filesystem"]["path"] = name
            self.reject(m, "filesystem_path")
        p = self.source / "filesystem.bin"
        p.unlink()
        p.symlink_to(self.restored / "filesystem.bin")
        self.reject(self.manifest, "filesystem_symlink")

    def test_pending_tool_or_model_rejected(self):
        for key, value, reason in [
            ("active_tool_operations", 1, "tool_operation_in_flight"),
            ("pending_model_request", True, "model_request_in_flight"),
            ("background_processes", 1, "background_processes_not_supported"),
        ]:
            m = deepcopy(self.manifest)
            m["boundary"][key] = value
            self.reject(m, reason)

    def test_unknown_cost_and_live_inputs_rejected(self):
        for key, value, reason in [
            ("usage_complete", False, "unknown_usage"),
            ("live_external_inputs", True, "unfrozen_external_input"),
        ]:
            m = deepcopy(self.manifest)
            m["boundary"][key] = value
            self.reject(m, reason)

    def test_budget_reset_or_environment_change_detected(self):
        for section, field, value in [
            ("remaining_budget", "remaining_tokens", 20000),
            ("runtime", "model_revision", "different-model"),
            ("runtime", "tool_config_sha256", "4" * 64),
        ]:
            m = deepcopy(self.manifest)
            m[section][field] = value
            with self.assertRaisesRegex(ContractError, "restore_mismatch"):
                compare_restore(self.manifest, self.source, m, self.restored)

    def test_different_valid_restored_content_rejected(self):
        m = deepcopy(self.manifest)
        path = self.restored / "task_registry.bin"
        path.write_bytes(b"ownership-already-changed")
        m["components"]["task_registry"]["sha256"] = digest(path)
        with self.assertRaisesRegex(ContractError, "restore_mismatch:component_sha256"):
            compare_restore(self.manifest, self.source, m, self.restored)

    def test_inconsistent_cache_and_invalid_budget_rejected(self):
        m = deepcopy(self.manifest)
        m["inference_cache_policy"] = "reuse_first_arm_only"
        self.reject(m, "cache_policy_not_matched")
        for value in (-1, True, 1.5):
            m = deepcopy(self.manifest)
            m["remaining_budget"]["remaining_tokens"] = value
            self.reject(m, "invalid_remaining_budget")

    def test_different_manifest_structure_rejected(self):
        for key, value in [("schema_version", True), ("checkpoint_id", None),
                           ("components", []), ("runtime", None)]:
            m = deepcopy(self.manifest)
            m[key] = value
            with self.assertRaises(ContractError):
                validate(m, self.source)


if __name__ == "__main__":
    unittest.main()
