"""Post-hoc structural diagnosis of frozen outputs. Never executes an agent."""
import argparse
import hashlib
import json
import math
from pathlib import Path


def read(path):
    return json.loads(path.read_text())


def hash_value(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def operations(message):
    """Provider-generated tool-call IDs do not change the requested operation."""
    result = []
    for call in message.get("tool_calls", []):
        function = call.get("function", {})
        arguments = function.get("arguments")
        try:
            arguments = json.loads(arguments)
        except (ValueError, TypeError):
            pass
        result.append({"name": function.get("name"), "arguments": arguments})
    return result


def analyze(directory, reference):
    plan = read(directory / "plan.json")
    usage = read(directory / "usage.json")
    groups = []
    for position, call in enumerate(usage):
        if call["role"] == "agent":
            continue
        if position == 0 or usage[position - 1]["role"] == "agent":
            groups.append([])
        groups[-1].append(call)
    rows = []
    minimum = math.ceil(plan["focus_rollouts"] * plan["focus_threshold"])
    for calls in groups:
        req = read(directory / calls[0]["id"] / "request.json")
        memory = json.loads(req["messages"][-1]["content"])["memory"]
        available = {s["id"] for s in memory["visible_spans"]}
        scores, rescued = dict.fromkeys(available, 0), set()
        valid_json, invalid_refs = 0, 0
        earliest_all = None
        for number, call in enumerate(calls, 1):
            response = read(directory / call["id"] / "response.json")
            tools = response.get("message", {}).get("tool_calls", [])
            if response["status"] != "ok" or len(tools) != 1:
                continue
            function = tools[0].get("function", {})
            if function.get("name") != "submit_selection":
                continue
            try:
                value = json.loads(function["arguments"])
                cited = {sid for step in value["steps"] for sid in step["depends_on"]}
                extra = set(value["rescued"])
            except (KeyError, TypeError, ValueError):
                continue
            valid_json += 1
            invalid_refs += len((cited | extra) - available)
            for sid in cited & available:
                scores[sid] += 1
            rescued |= extra & available
            if available <= {s for s, n in scores.items() if n >= minimum} | rescued:
                if earliest_all is None:
                    earliest_all = number
        forward = {s for s, n in scores.items() if n >= minimum}
        known_kept = forward | rescued
        # This is a monotone lower bound. Missing drafts may retain more spans.
        rows.append({
            "first_call": calls[0]["id"], "calls_observed": len(calls),
            "parseable_drafts": valid_json, "available_spans": len(available),
            "forward_kept_lower_bound": len(forward),
            "additional_rescued_lower_bound": len(rescued - forward),
            "retained_lower_bound_after_ignoring_nonhistory_ids": len(known_kept),
            "nonhistory_reference_count": invalid_refs,
            "already_all_retained": available <= known_kept,
            "earliest_observed_draft_proving_all_retained": earliest_all,
            "later_completed_calls_after_all_retained": sum(
                c["status"] == "ok" for c in calls[earliest_all:]) if earliest_all else 0,
            "scope": "Post-hoc keep-set bound; no claim of an executed optimized agent."
        })
    agent_calls = [c for c in usage if c["role"] == "agent"]
    ref_usage = read(reference / "usage.json")
    ref_agent_calls = [c for c in ref_usage if c["role"] == "agent"]
    comparisons = []
    for index, (left, right) in enumerate(zip(agent_calls, ref_agent_calls), 1):
        lp, rp = directory / left["id"], reference / right["id"]
        left_response, right_response = read(lp / "response.json"), read(rp / "response.json")
        comparisons.append({
            "agent_turn": index,
            "request_equal": hash_value(read(lp / "request.json")) == hash_value(read(rp / "request.json")),
            "public_operations_equal": hash_value(operations(left_response["message"])) ==
                                       hash_value(operations(right_response["message"]))
        })
    return {
        "run_id": directory.name, "reference_run_id": reference.name,
        "planned_rollouts": plan["focus_rollouts"], "retention_minimum": minimum,
        "cycles": rows, "agent_prefix_comparison": comparisons,
        "source_hashes": {
            "usage": hash_value(usage), "reference_usage": hash_value(ref_usage),
            "plan": hash_value(plan),
            "script": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()},
        "limitations": [
            "Invalid IDs are ignored only in this diagnosis; original results and execution are unchanged.",
            "Parse failures are not guessed or repaired; surviving references give only a lower bound.",
            "A matching prefix does not establish deterministic future replay or general algorithm superiority.",
            "No semantic accuracy, target coverage or hidden evaluation content is inspected.",
            "Monotone early termination is an implementation optimization candidate, not a novel research principle."
        ]}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--trial", type=Path, required=True)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = analyze(args.trial, args.reference)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"cycles": result["cycles"], "prefix": result["agent_prefix_comparison"]}))


if __name__ == "__main__":
    main()
