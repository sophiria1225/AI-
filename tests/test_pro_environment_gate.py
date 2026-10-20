import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from prepare_pro_environment import check_space, completed_trials, validate_image, validate_probe, GIB, PROBE


class ProEnvironmentGateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.plan = {"trials": [{"trial_id": "P3-01", "task": "task", "strategy": "single"}]}
        self.run = self.root / "records/p3/example"
        self.run.mkdir(parents=True)
        patch = b"fixed artifact"
        self.digest = hashlib.sha256(patch).hexdigest()
        (self.run / "final.patch").write_bytes(patch)
        self.status_path = self.root / "records/p3_plan_runs/P3_development_plan_v01/P3-01/status.json"
        self.status_path.parent.mkdir(parents=True)
        self.status = {"status": "execution_completed", "audit_errors": [], "plan_sha256": "plan",
                       "run_record": "records/p3/example", "artifact_sha256": self.digest}
        self.summary = {"container_removed": True, "usage_complete": True,
                        "artifact_frozen_at": "fixed", "artifact_sha256": self.digest,
                        "instance_id": "task", "strategy": "single"}
        self.evaluation = {"evaluation_status": "completed", "infra_failure": False,
                           "resolved": False, "artifact_sha256": self.digest}
        self.write_records()

    def write_records(self):
        for path, value in [(self.status_path, self.status),
                            (self.run / "summary.json", self.summary),
                            (self.run / "final_evaluation_summary.json", self.evaluation)]:
            path.write_text(json.dumps(value))

    def test_valid_unresolved_trial_is_not_retried_to_pass(self):
        proof = completed_trials(self.root, self.plan, "plan")
        self.assertFalse(proof[0]["resolved"])
        self.assertEqual(proof[0]["artifact_sha256"], self.digest)

    def test_running_and_unknown_usage_block_new_workload(self):
        self.status["status"] = "running"
        self.write_records()
        with self.assertRaisesRegex(ValueError, "incomplete"):
            completed_trials(self.root, self.plan, "plan")
        self.status["status"] = "execution_completed"
        self.summary["usage_complete"] = False
        self.write_records()
        with self.assertRaisesRegex(ValueError, "accounting incomplete"):
            completed_trials(self.root, self.plan, "plan")

    def test_infrastructure_failure_and_changed_artifact_block(self):
        self.evaluation["infra_failure"] = True
        self.write_records()
        with self.assertRaisesRegex(ValueError, "evaluation incomplete"):
            completed_trials(self.root, self.plan, "plan")
        self.evaluation["infra_failure"] = False
        self.write_records()
        (self.run / "final.patch").write_bytes(b"later edit")
        with self.assertRaisesRegex(ValueError, "artifact changed"):
            completed_trials(self.root, self.plan, "plan")

    def test_record_path_escape_is_rejected(self):
        self.status["run_record"] = "../../outside"
        self.write_records()
        with self.assertRaisesRegex(ValueError, "escapes"):
            completed_trials(self.root, self.plan, "plan")

    def test_probe_rejects_private_material_and_wrong_base(self):
        probe = {"roots": ["/app"], "machine": "x86_64", "python": "3.x",
                 **{key: {"exit_code": 0, "stdout": "", "stderr": ""}
                    for key in ("head", "status", "refs", "stash", "unreachable")},
                 "task_id_commit_present": False, "private_locations_present": [],
                 "task_id_commit_probe": {"exit_code": 128, "stdout": "", "stderr": "Not a valid object name"},
                 "rootfs_apparent_bytes": {"exit_code": 0, "stdout": "1000\t/", "stderr": ""}}
        probe["head"]["stdout"] = "base"
        validate_probe(probe, {"base_commit": "base"})
        for key, value in [("private_locations_present", ["/solution"]),
                           ("task_id_commit_present", True),
                           ("task_id_commit_probe", {"exit_code": None, "timed_out": True}),
                           ("unreachable", {"exit_code": None, "stdout": "", "timed_out": True}),
                           ("rootfs_apparent_bytes", {"exit_code": 1, "stdout": "0\t/"}),
                           ("head", {"exit_code": 0, "stdout": "other"})]:
            changed = copy.deepcopy(probe)
            changed[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_probe(changed, {"base_commit": "base"})

    def test_low_storage_is_not_ignored(self):
        check_space({"host_free_bytes": 20 * GIB, "vm_free_bytes": 15 * GIB})
        with self.assertRaises(ValueError):
            check_space({"host_free_bytes": 20 * GIB, "vm_free_bytes": 15 * GIB - 1})

    def test_config_id_and_bound_manifest_id_are_distinguished(self):
        plan = {"image": "registry/image@sha256:manifest"}
        manifest = {"config": {"digest": "sha256:configuration"}}
        attrs = {"RepoDigests": [plan["image"]], "Architecture": "amd64", "Os": "linux"}
        classic = types.SimpleNamespace(id="sha256:configuration", attrs=attrs)
        self.assertEqual(validate_image(classic, plan, manifest)["identity_kind"], "configuration_digest")
        attrs = copy.deepcopy(attrs)
        attrs["Descriptor"] = {"digest": "sha256:manifest", "mediaType": "application/vnd.oci.image.manifest.v1+json"}
        modern = types.SimpleNamespace(id="sha256:manifest", attrs=attrs)
        self.assertEqual(validate_image(modern, plan, manifest)["identity_kind"],
                         "manifest_digest_with_matching_descriptor")

    def test_unbound_or_conflicting_image_identity_is_rejected(self):
        plan = {"image": "registry/image@sha256:manifest"}
        manifest = {"config": {"digest": "sha256:configuration"}}
        attrs = {"RepoDigests": [plan["image"]], "Architecture": "amd64", "Os": "linux"}
        for identity, descriptor in [
            ("sha256:manifest", None),
            ("sha256:other", {"digest": "sha256:manifest", "mediaType": "application/vnd.oci.image.manifest.v1+json"}),
            ("sha256:configuration", {"digest": "sha256:other", "mediaType": "application/vnd.oci.image.manifest.v1+json"}),
            ("sha256:manifest", {"digest": "sha256:manifest", "mediaType": "application/vnd.oci.image.index.v1+json"}),
        ]:
            changed = copy.deepcopy(attrs)
            if descriptor is not None:
                changed["Descriptor"] = descriptor
            with self.subTest(identity=identity, descriptor=descriptor), self.assertRaises(ValueError):
                validate_image(types.SimpleNamespace(id=identity, attrs=changed), plan, manifest)

    def test_probe_timeout_preserves_partial_output_without_claiming_success(self):
        namespace = {}
        exec(PROBE.split("roots =", 1)[0], namespace)
        timeout = subprocess.TimeoutExpired(["git", "fsck"], 30, output=b"partial result", stderr=b"partial error")
        with mock.patch.object(namespace["subprocess"], "run", side_effect=timeout):
            result = namespace["call"]("git", "fsck")
        self.assertIsNone(result["exit_code"])
        self.assertTrue(result["timed_out"])
        self.assertEqual(result["stdout"], "partial result")
        self.assertEqual(result["stderr"], "partial error")


if __name__ == "__main__":
    unittest.main()
