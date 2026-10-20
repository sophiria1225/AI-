import io
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from evaluate_pro_environment import (
    PRIVATE_FILES, make_archive, reward_from_archive, validate_private_paths,
)


class ProVerifierIsolationTests(unittest.TestCase):
    def test_reference_patch_is_absent_from_negative_container(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for path in PRIVATE_FILES:
                target = root / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(b"synthetic private input")
            plan = {"base_commit": "a" * 40}
            for phase in ("negative_control", "reference_control"):
                raw = make_archive(root, plan, phase, "/app")
                with tarfile.open(fileobj=io.BytesIO(raw)) as archive:
                    names = archive.getnames()
                    script = archive.extractfile("research/run.sh").read()
                    self.assertEqual("solution/gold_patch.diff" in names, phase == "reference_control")
                    self.assertEqual(b"git apply --check" in script, phase == "reference_control")
                    self.assertTrue(all(not name.startswith("/") and ".." not in Path(name).parts for name in names))

    def test_private_path_expansion_and_unknown_phase_are_rejected(self):
        validate_private_paths(PRIVATE_FILES)
        with self.assertRaises(ValueError):
            validate_private_paths(PRIVATE_FILES + ("../../host",))
        with self.assertRaises(ValueError):
            make_archive(Path("."), {"base_commit": "a" * 40}, "unknown", "/app")

    def reward_archive(self, value, name="reward.txt", symlink=False):
        result = io.BytesIO()
        with tarfile.open(fileobj=result, mode="w") as archive:
            member = tarfile.TarInfo(name)
            if symlink:
                member.type = tarfile.SYMTYPE
                member.linkname = "../../private"
                archive.addfile(member)
            else:
                member.size = len(value)
                archive.addfile(member, io.BytesIO(value))
        return result.getvalue()

    def test_only_explicit_binary_reward_is_accepted(self):
        self.assertEqual(reward_from_archive(self.reward_archive(b"0\n")), 0.0)
        self.assertEqual(reward_from_archive(self.reward_archive(b"1.0\n")), 1.0)
        for value in (b"", b"NaN", b"error", b"0.5"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                reward_from_archive(self.reward_archive(value))

    def test_reward_archive_cannot_extract_arbitrary_paths(self):
        for archive in (self.reward_archive(b"1", name="../../outside"),
                        self.reward_archive(b"", symlink=True)):
            with self.assertRaises(ValueError):
                reward_from_archive(archive)


if __name__ == "__main__":
    unittest.main()
