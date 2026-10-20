"""Read frozen call metadata; export counts, hashes and structural errors only."""
import argparse
import hashlib
import json
from pathlib import Path

from summarize_context_pilot import summarize_trial


def read(path):
    return json.loads(path.read_text())


def audit_trial(directory):
    result = summarize_trial(directory)
    usage = read(directory / "usage.json")
    records = read(directory / "compressions.json") if (directory / "compressions.json").exists() else []
    groups = []
    for call in usage:
        if call["role"] == "agent":
            continue
        # Consecutive non-agent calls belong to one compression attempt.
        position = usage.index(call)
        if position == 0 or usage[position - 1]["role"] == "agent":
            groups.append([])
        groups[-1].append(call)
    cycles = []
    for index, calls in enumerate(groups):
        request = read(directory / calls[0]["id"] / "request.json")
        memory = json.loads(request["messages"][-1]["content"])["memory"]
        available = [s["id"] for s in memory["visible_spans"]]
        event = records[index] if index < len(records) else None
        errors = {"unparseable_arguments": 0, "unavailable_references": 0,
                  "duplicate_reference_lists": 0}
        for call in calls:
            response = read(directory / call["id"] / "response.json")
            if response["status"] != "ok" or call["role"] != "focus":
                continue
            for tool in response.get("message", {}).get("tool_calls", []):
                try:
                    value = json.loads(tool["function"]["arguments"])
                except (ValueError, KeyError, TypeError):
                    errors["unparseable_arguments"] += 1
                    continue
                reference_lists = [step.get("depends_on", []) for step in value.get("steps", [])
                                   if isinstance(step, dict)] + [value.get("rescued", [])]
                for refs in reference_lists:
                    if not isinstance(refs, list) or any(type(s) is not str for s in refs):
                        continue
                    errors["unavailable_references"] += len(set(refs) - set(available))
                    errors["duplicate_reference_lists"] += int(len(refs) != len(set(refs)))
        cycles.append({
            "index": index + 1, "first_call": calls[0]["id"],
            "calls": len(calls), "input_span_count": len(available),
            "recorded": event is not None,
            "status": event["status"] if event else "missing_event",
            "recorded_before_matches_request": event["visible_before"] == available if event else None,
            "output_span_count": len(event["visible_after"]) if event else None,
            "selection_removed_spans": len(set(available) - set(event["visible_after"])) if event else None,
            "known_tokens": sum(c["input_tokens"] + c["output_tokens"]
                                for c in calls if c["status"] == "ok"),
            "unknown_usage_calls": sum(c["status"] != "ok" for c in calls),
            "wall_seconds": sum(c["wall_seconds"] for c in calls),
            "length_stops": sum(c.get("finish_reason") == "length" for c in calls),
            "structural_errors": errors,
        })
    result["compression_audit"] = cycles
    result["call_seconds_by_role"] = {
        role: sum(c["wall_seconds"] for c in usage if c["role"] == role)
        for role in sorted({c["role"] for c in usage})}
    result["runtime_artifact_findings"] = {
        "before_snapshot_mismatches": sum(c["recorded_before_matches_request"] is False for c in cycles),
        "missing_compression_records": sum(not c["recorded"] for c in cycles)}
    result["audit_scope"] = ("Structural call and memory metadata only. No reasoning, task text, "
                             "evaluator content or semantic target-correctness inspection.")
    result["audit_script_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--trial", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = audit_trial(args.trial)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"run": result["run_id"], "audit_errors": result["audit_errors"],
                      "artifact_findings": result["runtime_artifact_findings"]}))


if __name__ == "__main__":
    main()
