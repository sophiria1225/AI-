"""Export aggregate counts and hashes, never prompts, task text or evaluator traces."""
import argparse
import hashlib
import json
from pathlib import Path


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def summarize_trial(directory):
    summary_path = directory / "summary.json"
    summary = json.loads(summary_path.read_text())
    usage_path = directory / "usage.json"
    usage = json.loads(usage_path.read_text()) if usage_path.exists() else []
    errors = []
    known = sum(u["input_tokens"] + u["output_tokens"] for u in usage if u["status"] == "ok")
    if known != summary["known_total_tokens"] or len(usage) != summary["model_calls"]:
        errors.append("summary disagrees with terminal usage")
    for row in usage:
        response = json.loads((directory / row["id"] / "response.json").read_text())
        for key in ("status", "input_tokens", "output_tokens"):
            if row[key] != response[key]:
                errors.append(f"{row['id']}: {key} mismatch")
        if row["status"] == "ok" and row["input_tokens"] != row["predicted_input_tokens"]:
            errors.append(row["id"] + ": preflight input mismatch")
    evaluation = None
    evaluation_path = directory / "evaluation.json"
    if evaluation_path.exists():
        source = json.loads(evaluation_path.read_text())
        if (source["execution_summary_sha256"] != digest(summary_path)
                or source["run_id"] != summary["run_id"]
                or source["task_id"] != summary["task_id"]):
            errors.append("evaluation is not bound to frozen execution")
        evaluation = {k: source[k] for k in (
            "official_success", "pass_count", "fail_count", "evaluation_returned_to_model")}
    result = {k: summary[k] for k in (
        "run_id", "task_id", "arm", "stop_reason", "declared_complete",
        "known_total_tokens", "usage_by_role", "model_calls", "tool_turns",
        "compression_events", "format_errors", "api_bridge_errors", "wall_seconds")}
    result.update(
        evaluation=evaluation, unknown_usage_calls=sum(u["status"] != "ok" for u in usage),
        peak_input_tokens=max((u["input_tokens"] or 0 for u in usage), default=0),
        audit_errors=errors,
        source_hashes={"summary": digest(summary_path),
                       "usage": digest(usage_path) if usage_path.exists() else None,
                       "evaluation": digest(evaluation_path) if evaluation_path.exists() else None})
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--storage-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    config = json.loads(args.plan.read_text())
    trials, pending = [], []
    for task, arm, run_id in config.get("prior_run_order", []) + config["run_order"]:
        directory = args.storage_root / "records/context_pilot" / run_id
        if (directory / "summary.json").exists():
            trials.append(summarize_trial(directory))
        else:
            pending.append(run_id)
    result = {
        "plan_sha256": digest(args.plan), "trials": trials, "pending": pending,
        "total_model_calls": sum(t["model_calls"] for t in trials),
        "known_total_tokens": sum(t["known_total_tokens"] for t in trials),
        "unknown_usage_calls": sum(t["unknown_usage_calls"] for t in trials),
        "audit_errors": sum(len(t["audit_errors"]) for t in trials),
        "scope": (f"{len(config['task_ids'])} development scenarios, one seed per arm; "
                  "no new method, no confirmatory claim."),
        "exclusions": "No task instructions, API response bodies, model reasoning or evaluator details exported.",
    }
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k not in ("trials", "exclusions")}))


if __name__ == "__main__":
    main()
