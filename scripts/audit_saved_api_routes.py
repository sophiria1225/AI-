"""Audit representation changes on saved actions without replaying side effects."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

from appworld_native_tools import NativeCatalog
from context_preservation import validate_api_request
from inspect_appworld_api_schemas import load_public_tools


def audit_trial(trial, tools, standard):
    spans_path = trial / "spans.json"
    spans = json.loads(spans_path.read_text())
    all_tools = NativeCatalog(tools)
    all_tools.visible = set(all_tools.catalog)
    discovered = NativeCatalog(tools)
    counts = Counter()
    for span in spans.values():
        action = span.get("action") or {}
        if action.get("name") == "read_span":
            counts["archive_requests"] += 1
            continue
        if action.get("name") != "appworld_api":
            counts["missing_or_other_action"] += 1
            continue
        counts["generic_api_actions"] += 1
        try:
            args = json.loads(action["arguments"])
            if not isinstance(args, dict):
                raise ValueError("not an object")
        except (KeyError, ValueError, TypeError):
            counts["malformed_original_arguments"] += 1
            continue
        original_ok, native_ok = False, False
        try:
            app, api, body = validate_api_request(args, standard)
            original_ok = True
        except (ValueError, TypeError, KeyError):
            pass
        function = {"name": f"{args.get('app')}__{args.get('api')}",
                    "arguments": json.dumps(args.get("args"))}
        try:
            decoded = all_tools.decode(function)
            native_ok = True
        except (ValueError, TypeError, KeyError):
            decoded = None
        if original_ok and native_ok:
            counts["same_decoded_request"] += int(
                decoded == {"app": app, "api": api, "args": body})
            counts["different_decoded_request"] += int(
                decoded != {"app": app, "api": api, "args": body})
        elif original_ok != native_ok:
            counts["validation_disagrees"] += 1
        else:
            counts["both_reject_arguments"] += 1
        if original_ok:
            if function["name"] not in discovered.visible:
                counts["would_need_additional_tool_discovery"] += 1
            # Match the candidate adapter's public-documentation request rule.
            if not {"api_error", "format_error"} & set(span.get("observation", {})):
                discovered.expose_requested_document(args)
    return {
        "run_id": trial.name, "counts": dict(counts),
        "spans_sha256": hashlib.sha256(spans_path.read_bytes()).hexdigest(),
        "api_requests_sent": 0, "inference_calls": 0,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--storage-root", type=Path, required=True)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--same-trials-as", type=Path)
    args = parser.parse_args()
    tools, sources, _ = load_public_tools(args.data_root)
    standard = {
        p.stem: json.loads(p.read_text())
        for p in (args.data_root / "api_docs/standard").glob("*.json") if p.stem != "admin"}
    plan = json.loads(args.plan.read_text())
    schedule = plan.get("prior_run_order", []) + plan["run_order"]
    fixed_trials = None
    if args.same_trials_as:
        fixed_trials = {r["run_id"]: r["spans_sha256"]
                        for r in json.loads(args.same_trials_as.read_text())["trials"]}
    rows, pending = [], []
    for _, _, name in schedule:
        if fixed_trials is not None and name not in fixed_trials:
            continue
        trial = args.storage_root / "records/context_pilot" / name
        if (trial / "summary.json").exists():
            if fixed_trials is not None and hashlib.sha256(
                    (trial / "spans.json").read_bytes()).hexdigest() != fixed_trials[name]:
                raise ValueError("original saved actions changed")
            rows.append(audit_trial(trial, tools, standard))
        else:
            pending.append(name)
    report = {
        "trials": rows, "pending": pending, "public_schema_hashes": sources,
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "adapter_sha256": hashlib.sha256(
            Path(__file__).with_name("appworld_native_tools.py").read_bytes()).hexdigest(),
        "scope": "Saved argument mapping only. Extra tool discovery can change trajectories; "
                 "this does not establish stronger agent quality or identical future behavior.",
    }
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"trials": rows, "pending": pending}))


if __name__ == "__main__":
    main()
