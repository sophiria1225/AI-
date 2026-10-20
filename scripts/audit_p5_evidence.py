"""Audit P5 observation delivery without exporting prompts, code, or reasoning.

This is a retrospective measurement, not a dependency estimator or a stop rule.
Only completed public tool events and their metadata are inspected. Commands are
never executed. Shell syntax flags are descriptive and do not prove coverage.
"""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import re

from jinja2 import StrictUndefined, Template

ROOT = Path(__file__).resolve().parents[1]
TRIALS = ("P5_PRO_PAIR_01", "P5_PRO_SINGLE_01")
TRUNCATION_MARKER = "\n[output truncated]\n"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def describe_operation(operation, captured, template):
    result = operation["result"]
    if captured["output"] != result["output"]:
        raise ValueError("Saved tool result differs from the turn event")
    if captured["exit_code"] != result["returncode"]:
        raise ValueError("Exit code differs between records")
    if not isinstance(result["output"], str):
        raise ValueError("Tool output must be text")
    for key in ("total_bytes", "captured_bytes"):
        if type(captured.get(key)) is not int or captured[key] < 0:
            raise ValueError("Missing/invalid capture size cannot be counted as zero")
    if captured["total_bytes"] < captured["captured_bytes"]:
        raise ValueError("Captured bytes exceed total bytes")
    command, output = operation["command"], result["output"]
    rendered = Template(template, undefined=StrictUndefined).render(output=result)
    # The frozen template has a 10,000-character bound. Check the exact output
    # against its actual renderer rather than assuming every long string loses
    # new source data: the upstream tool may already have inserted a marker.
    middle = output[5000:-5000] if len(output) >= 10000 else ""
    rendered_elision = (
        "<output_head>" in rendered and "<output_tail>" in rendered
        and output[:5000] in rendered and output[-5000:] in rendered
    )
    removed_marker_only = rendered_elision and middle == TRUNCATION_MARKER
    return {
        "record": operation["record"],
        "exit_code": result["returncode"],
        "captured_bytes": captured["captured_bytes"],
        "total_bytes": captured["total_bytes"],
        "capture_shortfall_bytes": captured["total_bytes"] - captured["captured_bytes"],
        "delivered_output_chars": len(output),
        "formatted_observation_chars": len(rendered),
        "upstream_truncation_marker": TRUNCATION_MARKER in output,
        "formatter_elision": rendered_elision,
        "formatter_middle_chars_removed": len(middle) if rendered_elision else 0,
        "formatter_removes_only_upstream_marker": removed_marker_only,
        "formatter_additional_source_chars_removed": (
            0 if removed_marker_only else len(middle)
        ) if rendered_elision else 0,
        "contains_head_or_tail_syntax": bool(
            re.search(r"(?:^|[|;&]\s*)\s*(?:head|tail)\b", command)
        ),
        "contains_grep_syntax": bool(re.search(r"\bgrep\b", command)),
        "empty_output_exit_one_with_grep": (
            not output and result["returncode"] == 1
            and bool(re.search(r"\bgrep\b", command))
        ),
        "contains_tmp_reproduction_write_syntax": bool(
            re.search(r">\s*/tmp/reproduce\.py\b", command)
        ),
    }


def describe_trial(storage, trial):
    directory = storage / "records/pro_pilot" / trial
    sources = {}

    def read(path):
        sources[str(path.relative_to(storage))] = sha(path)
        return json.loads(path.read_text())

    summary = read(directory / "summary.json")
    templates = read(directory / "unit_templates.json")
    events = [read(p) for p in sorted((directory / "artifact_versions").glob("*/turn.json"))]
    if summary["run_id"] != trial or summary["phase"] != "P5":
        raise ValueError("Unexpected trial identity")
    if len(events) != len(summary["calls"]):
        raise ValueError("Cannot audit an incomplete event sequence")
    rows = []
    for number, (event, call) in enumerate(zip(events, summary["calls"]), 1):
        if event["turn"] != number or event["unit"] != call["unit"]:
            raise ValueError("Event/call order or owner differs")
        for operation in event["operations"]:
            record = operation["record"]
            if not re.fullmatch(r"tool_\d{3}", record):
                raise ValueError("Unexpected tool record identifier")
            captured = read(directory / record / "result.json")
            row = describe_operation(
                operation, captured, templates[event["unit"]]["model"]["observation_template"]
            )
            rows.append({"turn": number, "unit": event["unit"], **row})
    flags = (
        "upstream_truncation_marker", "formatter_elision",
        "formatter_removes_only_upstream_marker",
        "contains_head_or_tail_syntax", "contains_grep_syntax",
        "empty_output_exit_one_with_grep", "contains_tmp_reproduction_write_syntax",
    )
    first_tmp = next((r["turn"] for r in rows
                      if r["contains_tmp_reproduction_write_syntax"]), None)
    return {
        "trial": trial, "strategy": summary["strategy"],
        "model_calls": len(summary["calls"]), "tool_operations": len(rows),
        "total_recorded_input_output_tokens": summary["total_recorded_tokens"],
        "artifact_change_boundaries": sum(bool(e["artifact_changed"]) for e in events),
        "accepted_completion_votes": sum(bool(e["completion_vote_accepted"]) for e in events),
        "first_tmp_reproduction_write_turn": first_tmp,
        "flag_counts": {flag: sum(bool(r[flag]) for r in rows) for flag in flags},
        "additional_source_chars_removed_by_formatter": sum(
            r["formatter_additional_source_chars_removed"] for r in rows
        ),
        "capture_shortfall_bytes": sum(r["capture_shortfall_bytes"] for r in rows),
        "rows": rows, "source_sha256": sources,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--storage-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rows = [describe_trial(args.storage_root.resolve(), trial) for trial in TRIALS]
    report = {
        "checked_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "scope": "Retrospective public-operation metadata audit of the two frozen P5 trials",
        "new_model_calls": 0, "commands_executed": 0,
        "private_evaluator_read": False, "reasoning_exported": False,
        "analysis_source_sha256": sha(Path(__file__)),
        "observed_totals": {
            "artifact_change_boundaries": sum(r["artifact_change_boundaries"] for r in rows),
            "formatter_additional_source_chars_removed": sum(
                r["additional_source_chars_removed_by_formatter"] for r in rows
            ),
            "formatter_marker_only_events": sum(
                r["flag_counts"]["formatter_removes_only_upstream_marker"] for r in rows
            ),
        },
        "interpretation_limits": [
            "Zero recorded artifact-change boundaries cannot demonstrate update-ownership conflict.",
            "A head/tail command is not proof that relevant evidence was omitted.",
            "An empty grep result is scoped to that command, not a repository-wide absence claim.",
            "Owner formatting is audited for both runs. The single-agent run has no peer; "
            "differences in formatting alone do not prove different source evidence was delivered.",
            "Neither operation flags nor absence of edits identify the cause of task failure.",
        ],
        "runs": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({r["trial"]: {
        k: r[k] for k in ("model_calls", "tool_operations", "flag_counts",
                         "first_tmp_reproduction_write_turn",
                         "additional_source_chars_removed_by_formatter")
    } for r in rows}, ensure_ascii=False))


if __name__ == "__main__":
    main()
