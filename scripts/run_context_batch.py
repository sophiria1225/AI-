"""Execute a frozen development schedule, stopping on infrastructure errors."""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--freeze-record", type=Path, required=True)
    parser.add_argument("--storage-root", type=Path, required=True)
    parser.add_argument("--batch-id", required=True)
    args = parser.parse_args()
    if not args.batch_id.replace("_", "").isalnum():
        raise ValueError("unsafe batch ID")
    config = json.loads(args.plan.read_text())
    for name, digest in json.loads(args.freeze_record.read_text())["source_hashes"].items():
        if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != digest:
            raise RuntimeError("frozen source changed: " + name)
    out = args.storage_root / "records/context_pilot" / args.batch_id
    out.mkdir(exist_ok=False)
    (out / "plan.json").write_bytes(args.plan.read_bytes())
    state = {"started_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
             "git_commit": subprocess.check_output(
                 ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
             "completed": [], "status": "running"}
    for task, arm, run_id in config["run_order"]:
        state["active"] = run_id
        (out / "status.json").write_text(json.dumps(state, indent=2) + "\n")
        command = [sys.executable, str(ROOT / "scripts/run_context_comparison.py"),
                   "--plan", str(args.plan.absolute()), "--arm", arm,
                   "--task-id", task, "--run-id", run_id,
                   "--storage-root", str(args.storage_root),
                   "--appworld-root", str(args.storage_root / ".runtime/appworld/r18_probe_01"),
                   "--appworld-python", str(args.storage_root / ".runtime/appworld/venv/bin/python")]
        print(json.dumps({"starting": run_id}), flush=True)
        with (out / (run_id + ".log")).open("w") as stream:
            result = subprocess.run(command, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT)
        state["completed"].append({"run_id": run_id, "exit_code": result.returncode})
        print(json.dumps({"finished": run_id, "exit_code": result.returncode}), flush=True)
        if result.returncode:
            state["status"] = "stopped_on_runtime_error"
            break
    else:
        state["status"] = "complete"
    state.update(active=None, finished_at=datetime.datetime.now(datetime.timezone.utc).isoformat())
    (out / "status.json").write_text(json.dumps(state, indent=2) + "\n")
    print(json.dumps(state), flush=True)
    return state["status"] == "complete"


if __name__ == "__main__":
    raise SystemExit(0 if main() else 1)
