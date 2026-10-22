"""Closed P38 cost/use summary; distinguish backend reuse from model KV reuse."""
import argparse
from collections import Counter
from pathlib import Path

from profile_handoff_costs import summarize_calls
from projected_read_runtime import ARMS
from run_handoff_factors import read, sha
from run_context_comparison import write_json

ROOT = Path(__file__).resolve().parents[1]


def run(storage, root):
    report = read(root / "reports/P38_comparison.json")
    status = read(storage / "records/context_pilot/P38_batch_v01/status.json")
    expected = ["P38_04_" + arm.upper() for arm in ARMS]
    if (status["status"] != "complete" or status["completed"] != expected
            or not report["all_three_reviewed"] or [r["run_id"] for r in report["rows"]] != expected):
        raise ValueError("wait for all three closed branches")
    target = root / "reports/P38_runtime_costs.json"
    if target.exists(): raise FileExistsError("preserve cost profile")
    rows = []
    for cell in report["rows"]:
        trial = storage / "records/context_pilot" / cell["run_id"]
        for name in ("usage.json", "summary.json", "events.json", "spans.json"):
            if sha(trial / name) != cell["source_hashes"][name]: raise ValueError("closed record changed")
        usage = read(trial / "usage.json")
        profiled = summarize_calls(usage, lambda cid: read(trial / cid / "response.json"),
                                  lambda cid: read(trial / cid / "request.json"))
        for key in ("known_total_tokens", "unknown_usage_calls"):
            if profiled["totals"][key] != cell[key]: raise ValueError("cost summary differs")
        if profiled["totals"]["calls"] != cell["model_calls"]:
            raise ValueError("model-call summary differs")
        for call in profiled["calls"]:
            call["source_sha256"] = {name: sha(trial / call["call_id"] / name)
                                     for name in ("request.json", "response.json")}
        spans = read(trial / "spans.json"); counts = Counter()
        for event in read(trial / "events.json"):
            if event["stage"] != "python_api": continue
            span = spans[event["span_id"]]; meta = span["observation"].get("field_read")
            counts["backend_requests"] += int(event["api_request_sent"])
            if meta:
                if not event["api_request_sent"]:
                    if meta["source"] not in ("exact", "cross_api"): raise ValueError("unknown hit source")
                    counts[("raw_" if meta["full_api_response"] else "projected_") + meta["source"]] += 1
                else:
                    if meta["source"] != "fetched": raise ValueError("sent request labelled cached")
                    counts["projected_fetched" if meta["projection_success"] else "projected_failed"] += 1
            elif not event["api_request_sent"]:
                counts["rejected"] += 1
        runtime = cell["projected_reads"]
        for key in ("backend_requests", "raw_exact", "projected_exact", "projected_cross_api",
                    "projected_fetched", "projected_failed", "rejected"):
            if counts[key] != runtime["counts"].get(key, 0): raise ValueError("RPC/cache account mismatch: " + key)
        rows.append({"run_id": cell["run_id"], "arm": cell["arm"], "success": cell["success"],
                     "stop_reason": cell["stop_reason"],
                     **profiled, "read_account": dict(counts), "installation": runtime["installation"],
                     "first_call": profiled["calls"][0] if profiled["calls"] else None,
                     "source_sha256": {name: sha(trial / name) for name in
                                       ("usage.json", "summary.json", "events.json", "spans.json")}})
    write_json(target, {"phase": "P38_runtime_costs", "rows": rows, "all_three_profiled": True,
               "source_sha256": {p: sha(root / p) for p in
                                 ("reports/P38_comparison.json", "scripts/profile_projected_reads.py",
                                  "scripts/profile_handoff_costs.py")},
               "model_calls_added": 0, "api_requests_added": 0,
               "limits": ["Unknown-usage calls are not zero; known totals are lower bounds.",
                          "API result caching and model KV-prefix caching are different mechanisms.",
                          "The fixed single-task order does not reset the server KV cache between modes.",
                          "This accounting is descriptive and does not identify a causal latency effect."]})


if __name__ == "__main__":
    p = argparse.ArgumentParser(); p.add_argument("--storage-root", type=Path, required=True)
    p.add_argument("--repo-root", type=Path, default=ROOT); a = p.parse_args(); run(a.storage_root, a.repo_root)
