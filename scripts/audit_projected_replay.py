"""After P38 closes, verify cached reads in separately reconstructed worlds.

These verification API calls are charged separately and are never returned to
the model. Normal observations, projected hits, discovery, and final DB bytes are
checked. A mismatch stops that trajectory but does not hide the other conditions.
"""
import argparse
import copy
import json
from pathlib import Path
import time

from analyze_structured_reuse import decode
from appworld_native_tools import NativeCatalog
from field_read_contract import TARGET, canonical, project, required_fields
from inspect_appworld_api_schemas import load_public_tools
from probe_prefix_replay import db_hashes
from projected_read_runtime import ARMS
from run_context_comparison import Bridge, write_json
from run_handoff_factors import read, sha

ROOT = Path(__file__).resolve().parents[1]


def replay_kind(event, span):
    if event["stage"] != "python_api": return "skip"
    meta = span["observation"].get("field_read")
    if event.get("effects_unknown"):
        raise ValueError("unknown effects are not reproducibly auditable")
    if event["api_request_sent"]: return "sent"
    if not meta: return "skip"
    if (meta.get("source") not in ("exact", "cross_api")
            or span["action"]["name"] != TARGET
            or "observation" not in span["observation"]
            or type(meta.get("full_api_response")) is not bool):
        raise ValueError("malformed cache receipt")
    if meta["full_api_response"]:
        if meta.get("requested_fields") is not None or meta["source"] != "exact":
            raise ValueError("only exact cache may return the full API object")
    else:
        required_fields(meta["requested_fields"])
    return "cached"


def observation_matches(kind, expected, actual):
    if kind == "sent":
        original = copy.deepcopy(expected); original.pop("field_read", None)
        return canonical(original) == canonical(actual)
    if kind != "cached": raise ValueError("not a replayed observation")
    ok, value = decode(actual)
    cached_ok, cached = decode(expected)
    if not ok or not cached_ok or actual.get("declared_complete"):
        return False
    meta = expected["field_read"]
    try:
        selected = value if meta["full_api_response"] else project(value, meta["requested_fields"])
        return canonical(selected) == canonical(cached)
    except (ValueError, KeyError, TypeError):
        return False


def run(storage, root):
    status = read(storage / "records/context_pilot/P38_batch_v01/status.json")
    report = read(root / "reports/P38_comparison.json")
    expected_ids = ["P38_04_" + arm.upper() for arm in ARMS]
    if (status["status"] != "complete" or status["completed"] != expected_ids
            or not report["all_three_reviewed"]
            or [r["run_id"] for r in report["rows"]] != expected_ids):
        raise ValueError("wait for the closed three-condition cohort")
    activation = read(root / "reports/P38_activation_v01.json")
    for filename in ("scripts/field_read_contract.py", "scripts/projected_read_runtime.py",
                     "scripts/appworld_bridge.py", "scripts/appworld_native_tools.py"):
        if sha(root / filename) != activation["source_hashes"][filename]:
            raise ValueError("execution dependency changed")
    out = storage / "records/context_pilot/P38_cache_replay_v01"
    target = root / "reports/P38_cache_replay.json"
    if out.exists() or target.exists(): raise FileExistsError("preserve cache replay audit")
    out.mkdir(); started = time.monotonic(); rows = []
    source_plan = read(root / "configs/P29_stateful_code_v01.json")
    task = next(t for t, _, rid in source_plan["run_order"] if rid == "P29_04_CODE")
    appworld = storage / ".runtime/appworld/r18_probe_01"
    tools, public_hashes, _ = load_public_tools(appworld / "data")
    if public_hashes != read(storage / "records/context_pilot/P29_04_CODE/provenance.json")["public_schema_hashes"]:
        raise ValueError("public API schemas changed")
    for original in report["rows"]:
        rid = original["run_id"]; trial = storage / "records/context_pilot" / rid
        if original["task_id"] != task: raise ValueError("unexpected audit task")
        for name, digest in original["source_hashes"].items():
            if sha(trial / name) != digest: raise ValueError("closed trial changed")
        audit_id = rid + "_CACHE_AUDIT_V01"
        world = appworld / "experiments/outputs" / audit_id
        if world.exists(): raise FileExistsError("preserve audit world")
        folder = out / rid; folder.mkdir()
        row = {"run_id": rid, "status": "not_started", "verification_api_requests": 0,
               "matched_sent": 0, "matched_cached": 0, "checks": [], "db_files_match": False}
        bridge = None; at = time.monotonic()
        try:
            bridge = Bridge(storage / ".runtime/appworld/venv/bin/python", appworld, folder)
            init = bridge.request({"op": "init", "task_id": task, "experiment": audit_id,
                                   "seed": source_plan["seed"]})
            if not init["ok"] or init["result"] != read(trial / "public_task.json") or init["result"]["ground_truth_loaded"]:
                raise ValueError("initial public task differs")
            c = NativeCatalog(tools)
            all_events = read(trial / "prefix_events.json") + read(trial / "events.json")
            spans = read(trial / "spans.json")
            for number, event in enumerate(all_events):
                if time.monotonic() - at > 600: raise TimeoutError("audit wall limit")
                span = spans[event["span_id"]]; kind = replay_kind(event, span)
                if kind == "skip": continue
                action = c.decode(span["action"])
                row["verification_api_requests"] += 1
                response = bridge.request({"op": "call", "call": action})
                actual = response["result"] if response["ok"] else {"api_error": response["error"]}
                exposed = c.expose_requested_document(action) if response["ok"] else []
                matched = observation_matches(kind, span["observation"], actual) and exposed == event["new_tools"]
                row["checks"].append({"event_index": number, "kind": kind, "matched": matched})
                if not matched: raise ValueError("response or projection differs")
                row["matched_" + kind] += 1
            actual_db = db_hashes(world / "tasks" / task / "dbs")
            expected_db = db_hashes(appworld / "experiments/outputs" / rid / "tasks" / task / "dbs")
            row["db_files_match"] = actual_db == expected_db
            row["db_files"] = len(actual_db)
            if not row["db_files_match"]: raise ValueError("final saved database differs")
            row["status"] = "matched"
        except Exception as error:
            row.update(status="failed", error_type=type(error).__name__)
            (folder / "error_private.txt").write_text(str(error))
        finally:
            if bridge:
                try: bridge.close()
                except Exception as error: row.update(status="cleanup_error", error_type=type(error).__name__)
            row["wall_seconds"] = time.monotonic() - at
            rows.append(row); write_json(folder / "summary.json", row)
            print(json.dumps({k: v for k, v in row.items() if k != "checks"}), flush=True)
    result = {"phase": "P38_cache_replay", "rows": rows, "all_three_attempted": len(rows) == 3,
              "all_matched": all(r["status"] == "matched" for r in rows),
              "verification_api_requests": sum(r["verification_api_requests"] for r in rows),
              "model_calls": 0, "final_evaluator_invocations": 0, "reserved_scenarios_read": 0,
              "wall_seconds": time.monotonic() - started,
              "source_sha256": {p: sha(root / p) for p in ("scripts/audit_projected_replay.py", "reports/P38_comparison.json")},
              "limits": ["Posthoc replay of fixed requested actions is not a fresh model trial or a formal correctness proof.",
                         "Cached read verification calls are additional audit cost, not execution savings.",
                         "A replay mismatch may reflect external or hidden state; failed traces are retained."]}
    write_json(out / "summary.json", result); write_json(target, result)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--storage-root", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    args = parser.parse_args(); run(args.storage_root, args.repo_root)
