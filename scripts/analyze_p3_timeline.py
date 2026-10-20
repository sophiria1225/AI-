"""Post-run descriptions of observable work, cache use and artifact versions.

This script never loads prompts, reasoning text or hidden test cases.
It hashes the initial artifact and exports no patch or tool-output text.
The final-artifact suffix is identified retrospectively, not an online stop rule.
"""
import datetime
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def describe_timeline(summary, events, initial_hash):
    calls = summary["calls"]
    if len(calls) != len(events):
        raise ValueError("Not every model call has a completed turn; no exact timeline")
    final_hash = summary["artifact_sha256"]
    cumulative = 0
    cached_total = 0
    unknown_cache_calls = 0
    rows = []
    hashes = [initial_hash]
    for number, (call, event) in enumerate(zip(calls, events), 1):
        if event["turn"] != number or event["unit"] != call["unit"]:
            raise ValueError("Call and turn identities differ")
        input_tokens, output_tokens = call.get("input_tokens"), call.get("output_tokens")
        if (type(input_tokens) is not int or type(output_tokens) is not int
                or min(input_tokens, output_tokens) < 0):
            raise ValueError("Unknown/invalid usage cannot be counted as zero")
        cached = call.get("cached_input_tokens")
        if cached is None:
            unknown_cache_calls += 1
        elif type(cached) is not int or not 0 <= cached <= input_tokens:
            raise ValueError("Cached tokens must be a subset of input tokens")
        else:
            cached_total += cached
        cumulative += input_tokens + output_tokens
        artifact_hash = event["artifact"]["artifact_sha256"]
        hashes.append(artifact_hash)
        rows.append({
            "turn": number, "unit": event["unit"],
            "input_tokens": input_tokens, "output_tokens": output_tokens,
            "cached_input_tokens": cached,
            "cumulative_input_output_tokens": cumulative,
            "model_seconds": call["wall_seconds"],
            "artifact_sha256": artifact_hash,
            "artifact_changed": event["artifact_changed"],
            "completion_vote_accepted": event["completion_vote_accepted"],
            "tool_exit_codes": [operation["result"]["returncode"]
                                for operation in event["operations"]],
        })
    if cumulative != summary["total_recorded_tokens"]:
        raise ValueError("Timeline total differs from the run ledger")
    if hashes[-1] != final_hash:
        raise ValueError("Final artifact differs from the last observed version")
    # A version can appear, disappear, then return. Use the final uninterrupted
    # suffix, not its first appearance, when describing subsequent observations.
    last_different = max((i for i, value in enumerate(hashes) if value != final_hash), default=-1)
    suffix_start = last_different + 1
    later_rows = rows[suffix_start:]
    input_total = sum(row["input_tokens"] for row in rows)
    return {
        "calls": len(rows),
        "input_tokens": input_total,
        "output_tokens": sum(row["output_tokens"] for row in rows),
        "total_input_output_tokens": cumulative,
        "known_cached_input_tokens": cached_total,
        "unknown_cache_calls": unknown_cache_calls,
        "cached_fraction_of_input": cached_total / input_total
        if input_total and not unknown_cache_calls else None,
        "model_seconds": sum(row["model_seconds"] for row in rows),
        "first_final_hash_observation": hashes.index(final_hash),
        "final_hash_uninterrupted_suffix_starts_after_turn": suffix_start,
        "later_model_calls": len(later_rows),
        "later_input_output_tokens": sum(row["input_tokens"] + row["output_tokens"]
                                        for row in later_rows),
        "timeline": rows,
    }


def main():
    import hashlib
    rows, pending, excluded = [], [], []
    for path in sorted((ROOT / "records/p3").glob("*/summary.json")):
        summary = json.loads(path.read_text())
        record = str(path.parent.relative_to(ROOT))
        evaluation_path = path.parent / "final_evaluation_summary.json"
        if ("wall_seconds" not in summary or not summary.get("container_removed")
                or not evaluation_path.exists()):
            pending.append(record)
            continue
        evaluation = json.loads(evaluation_path.read_text())
        if evaluation.get("evaluation_status") != "completed" or evaluation.get("infra_failure"):
            excluded.append({"record": record, "reason": "Independent evaluation incomplete or failed"})
            continue
        try:
            events = [json.loads(p.read_text()) for p in
                      sorted((path.parent / "artifact_versions").glob("*/turn.json"))]
            initial = path.parent / "artifact_versions/initial/final.patch"
            initial_hash = hashlib.sha256(initial.read_bytes()).hexdigest()
            description = describe_timeline(summary, events, initial_hash)
            rows.append({
                "record": record,
                "task": summary["instance_id"], "strategy": summary["strategy"],
                "stop_reason": summary["stop_reason"],
                "resolved": evaluation["resolved"],
                "wall_seconds": summary["wall_seconds"],
                **description,
            })
        except (KeyError, ValueError) as error:
            excluded.append({"record": record, "reason": str(error)})
    report = {
        "at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "scope": "Descriptive, post-run P3 development observations",
        "source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "interpretation": [
            "All input tokens, including cached input, remain in the primary logical-token cost.",
            "The final-hash suffix is known only after completion; it is not an implementable early-stop policy.",
            "Later calls can perform necessary verification or completion coordination; they are not labelled waste.",
            "Version zero is the initial artifact. Only turn boundaries are observed, not temporary changes within a turn.",
            "One slot and sequential worker switching are properties of this runtime, not universal multi-agent latency.",
            "Use audit_p3.py separately; this descriptive report is not a correctness audit or a causal estimate.",
        ],
        "runs": rows, "pending": pending, "excluded": excluded,
    }
    (ROOT / "reports/P3_timeline.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"completed": len(rows), "pending": len(pending), "excluded": len(excluded)}))
    return not excluded


if __name__ == "__main__":
    raise SystemExit(0 if main() else 1)
