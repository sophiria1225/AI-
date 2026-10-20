import hashlib
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from artifact_capture import capture_artifact
from repository_runtime import runtime_for
from run_e0_pilot import TASK_ENV, tool_command
from visible_checks import run_checks


CUSTOM = {"workdir": "/app", "python": "/usr/local/bin/python3",
          "environment": {"PATH": "/usr/local/bin:/usr/bin:/bin", "PYTHONPATH": "/app/lib:/app"}}


class RepositoryRuntimeTests(unittest.TestCase):
    def test_default_is_preserved_and_custom_does_not_inherit_conda(self):
        default = runtime_for({}, TASK_ENV)
        self.assertEqual(default["workdir"], "/testbed")
        self.assertEqual(default["environment"], TASK_ENV)
        custom = runtime_for({"repository_runtime": CUSTOM}, TASK_ENV)
        self.assertEqual(custom, CUSTOM)
        self.assertNotIn("CONDA_PREFIX", custom["environment"])
        custom["environment"]["EXTRA"] = "changed"
        self.assertNotIn("EXTRA", CUSTOM["environment"])

    def test_incomplete_or_ambiguous_runtime_is_rejected(self):
        for change in ({"workdir": "../app"}, {"python": "/app/../bin/python"},
                       {"environment": {}}, {"extra": True},
                       {"environment": {"PATH": "/bin", "X": None}}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                runtime_for({"repository_runtime": {**CUSTOM, **change}}, TASK_ENV)

    def test_tool_execution_uses_selected_runtime_and_keeps_nonzero_exit(self):
        calls = []
        def create(*args, **kwargs):
            calls.append((args, kwargs))
            return {"Id": "test-exec"}
        api = types.SimpleNamespace(exec_create=create,
                                    exec_start=lambda *a, **k: iter([b"failed visible check"]),
                                    exec_inspect=lambda *a, **k: {"ExitCode": 3, "Running": False})
        container = types.SimpleNamespace(id="container", client=types.SimpleNamespace(api=api))
        config = {"repository_runtime": CUSTOM, "tool_timeout_seconds": 2,
                  "max_visible_tool_characters": 1000}
        with tempfile.TemporaryDirectory() as temporary:
            result = tool_command(container, "python3 -m pytest", config, Path(temporary), 10)
            recorded = json.loads((Path(temporary) / "result.json").read_text())
        self.assertEqual(calls[0][1]["workdir"], "/app")
        self.assertEqual(calls[0][1]["environment"], CUSTOM["environment"])
        self.assertIn("test -x /usr/local/bin/python3", calls[0][0][1][-1])
        self.assertTrue(result["exit_code_known"])
        self.assertEqual(result["exit_code"], 3)
        self.assertEqual(recorded["environment"], CUSTOM["environment"])

    def test_artifact_capture_uses_selected_python_and_repository(self):
        calls = []
        def execute(argv, **kwargs):
            calls.append((argv, kwargs))
            output = b'{"excluded": [], "included_new_files": ["new.py"]}' if len(calls) == 1 else b"fixed diff\n"
            return types.SimpleNamespace(exit_code=0, output=output)
        container = types.SimpleNamespace(exec_run=execute)
        with tempfile.TemporaryDirectory() as temporary:
            result = capture_artifact(container, "base", Path(temporary),
                                      workdir="/app", python_path="/usr/local/bin/python3")
            self.assertEqual((Path(temporary) / "final.patch").read_bytes(), b"fixed diff\n")
        self.assertEqual(calls[0][0][0], "/usr/local/bin/python3")
        self.assertEqual(calls[0][0][-1], "/app")
        self.assertTrue(all(call[1]["workdir"] == "/app" for call in calls))
        self.assertEqual(result["artifact_sha256"], hashlib.sha256(b"fixed diff\n").hexdigest())

    def test_visible_check_uses_selected_runtime_and_separate_exit_status(self):
        calls = []
        def execute(argv, **kwargs):
            calls.append((argv, kwargs))
            return types.SimpleNamespace(exit_code=1, output=b"visible failure")
        container = types.SimpleNamespace(exec_run=execute)
        with tempfile.TemporaryDirectory() as temporary:
            result = run_checks(container, [{"id": "public", "argv": ["python3", "-m", "pytest"]}],
                                Path(temporary) / "checks", 5, workdir="/app",
                                environment=CUSTOM["environment"])
        self.assertFalse(result["all_passed"])
        self.assertEqual(result["checks"][0]["exit_code"], 1)
        self.assertEqual(calls[0][1], {"workdir": "/app", "environment": CUSTOM["environment"]})


if __name__ == "__main__":
    unittest.main()
