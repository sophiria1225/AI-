"""Exercise public documentation calls and malformed rejection, without inference."""
import argparse
import hashlib
import json
from pathlib import Path

from appworld_native_tools import NativeCatalog, dispatch_native_calls
from inspect_appworld_api_schemas import load_public_tools
from run_context_comparison import Bridge, write_json


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--storage-root", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    storage = args.storage_root.resolve()
    appworld = storage / ".runtime/appworld/r18_probe_01"
    run_id = "P8_NATIVE_BRIDGE_01"
    if (appworld / "experiments/outputs" / run_id).exists():
        raise FileExistsError("do not overwrite a previous world")
    out = storage / "records/native_controls" / run_id
    out.mkdir(parents=True, exist_ok=False)
    tools, sources, _ = load_public_tools(appworld / "data")
    catalog = NativeCatalog(tools)
    first_app = sorted({n.split("__")[0] for n in catalog.catalog}
                       - {"supervisor", "api_docs"})[0]
    task = "07b42fd_1"
    message = {"tool_calls": [
        {"function": {"name": "api_docs__show_app_descriptions", "arguments": "{}"}},
        {"function": {"name": "api_docs__show_api_descriptions",
                      "arguments": json.dumps({"app_name": first_app})}},
        {"function": {"name": "supervisor__complete_task", "arguments": "{"}},
    ]}
    bridge = Bridge(storage / ".runtime/appworld/venv/bin/python", appworld, out)
    recorded, error = [], None
    try:
        result = bridge.request({"op": "init", "task_id": task, "experiment": run_id, "seed": 42})
        if not result["ok"] or result["result"]["ground_truth_loaded"]:
            raise RuntimeError("public environment preflight failed")
        dispatch_native_calls(
            message, catalog, bridge, lambda sid, offset: None, remaining_api_calls=2,
            on_record=recorded.append)
        if (len(recorded) != 3 or sum(r["api_request_sent"] for r in recorded) != 2
                or any("observation" not in r["observation"] for r in recorded[:2])
                or any(r["observation"].get("declared_complete") for r in recorded)
                or "format_error" not in recorded[2]["observation"]):
            raise RuntimeError("unexpected dispatch results")
    except Exception as exc:
        error = type(exc).__name__
        write_json(out / "error_private.json", {"type": error, "message": str(exc)})
    finally:
        bridge.close()
        write_json(out / "observations_private.json", recorded)
    report = {
        "run_id": run_id, "passed": error is None, "error": error,
        "api_requests": sum(r["api_request_sent"] for r in recorded),
        "recorded_items": len(recorded),
        "malformed_completion_dispatched": any(
            r["api_request_sent"] and r["action"]["name"] == "supervisor__complete_task"
            for r in recorded),
        "new_public_schemas": sum(len(r["new_tools"]) for r in recorded),
        "inference_calls": 0, "evaluator_used": False, "ground_truth_loaded": False,
        "source_hashes": {name: hashlib.sha256(
            Path(__file__).with_name(name).read_bytes()).hexdigest()
            for name in ("calibrate_native_bridge.py", "appworld_native_tools.py", "appworld_bridge.py")},
        "public_schema_hashes": sources,
        "observations_sha256": hashlib.sha256(
            (out / "observations_private.json").read_bytes()).hexdigest(),
        "scope": "Public documentation only; no requested task mutation, agent score or new method.",
    }
    write_json(out / "summary.json", report)
    write_json(args.report, report)
    print(json.dumps({k: v for k, v in report.items() if not k.endswith("hashes")}))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
