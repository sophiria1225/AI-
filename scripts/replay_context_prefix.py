"""Replay recorded public operations without model calls or evaluator access.

This creates a NEW prefix state. Matching observations cannot certify that the
unrecorded original checkpoint's full state was identical.
"""
import argparse
import datetime
import hashlib
import json
from pathlib import Path

from run_context_comparison import Bridge, write_json


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def value_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def replay_span(bridge, span):
    action = span.get("action") or {}
    if action.get("name") != "appworld_api":
        raise ValueError("prefix replay supports only recorded public API actions")
    try:
        args = json.loads(action["arguments"])
    except (ValueError, KeyError, TypeError) as error:
        # The generator did not execute malformed arguments; replay must not either.
        return {"format_error": str(error)}, False
    response = bridge.request({"op": "call", "call": args})
    return (response["result"] if response["ok"] else {"api_error": response["error"]}), True


def replay_prefix(bridge, spans, turns):
    rows = []
    for index in range(1, turns + 1):
        span = spans[f"s{index}"]
        observation, called = replay_span(bridge, span)
        matched = value_hash(observation) == value_hash(span["observation"])
        rows.append({"turn": index, "api_request_sent": called,
                     "observation_matches": matched,
                     "expected_sha256": value_hash(span["observation"]),
                     "replayed_sha256": value_hash(observation)})
        if not matched:
            break
    return rows


def run(source, turns, run_id, storage):
    if not run_id.replace("_", "").isalnum() or not run_id.startswith("P6_PREFIX_"):
        raise ValueError("safe P6_PREFIX_ run ID required")
    provenance = json.loads((source / "provenance.json").read_text())
    plan = json.loads((source / "plan.json").read_text())
    spans = json.loads((source / "spans.json").read_text())
    if not 0 < turns <= len(spans):
        raise ValueError("prefix length is outside the recorded trajectory")
    appworld_root = storage / ".runtime/appworld/r18_probe_01"
    world_output = appworld_root / "experiments/outputs" / run_id
    if world_output.exists():
        raise FileExistsError("refusing to replace a world")
    output = storage / "records/context_replay" / run_id
    output.mkdir(parents=True, exist_ok=False)
    script = Path(__file__).resolve()
    (output / "replay_source.py").write_bytes(script.read_bytes())
    source_hashes = {n: sha(source / n) for n in ("provenance.json", "plan.json", "spans.json")}
    task_id = provenance["task_id"]
    if sha(appworld_root / "data/tasks" / task_id / "specs.json") != provenance["spec_sha256"]:
        raise RuntimeError("task specification changed")
    rows, error = [], None
    bridge = Bridge(storage / ".runtime/appworld/venv/bin/python", appworld_root, output)
    try:
        response = bridge.request({"op": "init", "task_id": task_id,
                                   "experiment": run_id, "seed": plan["seed"]})
        if not response["ok"]:
            raise RuntimeError(response["error"])
        rows = replay_prefix(bridge, spans, turns)
    except Exception as exc:
        error = type(exc).__name__
        write_json(output / "error_private.json", {"type": error, "message": str(exc)})
    finally:
        bridge.close()
    dbs = world_output / "tasks" / task_id / "dbs"
    database_hashes = {p.name: sha(p) for p in sorted(dbs.glob("*")) if p.is_file()}
    result = {
        "run_id": run_id, "source_run_id": source.name, "turns_requested": turns,
        "turns_replayed": len(rows), "api_requests": sum(r["api_request_sent"] for r in rows),
        "all_observations_match": len(rows) == turns and all(r["observation_matches"] for r in rows),
        "database_hashes": database_hashes,
        "source_hashes": source_hashes, "replay_script_sha256": sha(script),
        "bridge_sha256": sha(script.parent / "appworld_bridge.py"),
        "error": error, "model_calls": 0, "evaluation_run": False,
        "finished_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "scope": "New replay states only. Original prefix DB was not captured; original full-state identity is unverified."
    }
    write_json(output / "comparison.json", rows)
    write_json(output / "summary.json", result)
    print(json.dumps(result))
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-trial", type=Path, required=True)
    parser.add_argument("--turns", type=int, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--storage-root", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.source_trial, args.turns, args.run_id, args.storage_root)
    return result["all_observations_match"] and not result["error"] and bool(result["database_hashes"])


if __name__ == "__main__":
    raise SystemExit(0 if main() else 1)
