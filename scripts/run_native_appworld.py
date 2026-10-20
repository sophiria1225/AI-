"""Run the public-schema full-history baseline; final evaluation stays separate."""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import signal
import time
import urllib.request

from appworld_native_tools import NativeCatalog, dispatch_native_calls
from context_preservation import AGENT_PROMPT, compact, page_span, render_memory
from inspect_appworld_api_schemas import load_public_tools
from model_provenance import check_live_model
from native_conversation import NativeConversation
from native_boundary_record import snapshot_boundary
from run_context_comparison import Bridge, BudgetStop, Inference, write_json

ROOT = Path(__file__).resolve().parents[1]
NATIVE_PROMPT = AGENT_PROMPT.replace(
    "Use appworld_api to look up API documentation and then call APIs.",
    "Use the supplied app__api functions. Request app descriptions or individual API "
    "documentation through api_docs functions; the requested public schemas become "
    "available on your NEXT response.").replace(
    "Choose one tool call per response.",
    "You may choose multiple independent tool calls per response. They execute in "
    "listed order; do not use an earlier call's unknown result as a later argument. "
    "After declaring task completion, remaining calls are not executed.").replace(
    "Call supervisor.complete_task", "Call supervisor__complete_task")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def messages_for(task, spans, config):
    return [
        {"role": "system", "content": NATIVE_PROMPT},
        {"role": "user", "content": compact({
            "task": task, "memory": json.loads(render_memory(
                spans, list(spans), None, config["observation_page_characters"]))})},
    ]


def run(config, task_id, run_id, storage, appworld_root, python):
    expected = {"P8": "native_full", "P10": "native_roles", "P11": "native_roles"}
    phase = config["phase"]
    if (phase not in expected or config["arms"] != [expected.get(phase)]
            or task_id not in config["task_ids"] or not run_id.startswith(phase + "_")
            or not run_id.replace("_", "").isalnum()):
        raise ValueError("outside the fixed native-baseline plan")
    arm = expected[phase]
    world_output = appworld_root / "experiments/outputs" / run_id
    if world_output.exists():
        raise FileExistsError("refusing to replace an existing world")
    out = storage / "records/context_pilot" / run_id
    out.mkdir(parents=True, exist_ok=False)
    write_json(out / "plan.json", config)
    runtime = json.loads((storage / ".runtime/model_server.json").read_text())
    with urllib.request.urlopen(config["model"]["base_url"] + "/props", timeout=10) as response:
        props = json.load(response)
    check_live_model(config["model_selection"], runtime, props, root=storage,
                     expected_ctx=config["model"]["num_ctx"], expected_cache=("q8_0", "q8_0"))
    tools, schema_hashes, _ = load_public_tools(appworld_root / "data")
    catalog = NativeCatalog(tools)
    snapshot = out / "source"
    snapshot.mkdir()
    files = [
        "run_native_appworld.py", "appworld_native_tools.py", "inspect_appworld_api_schemas.py",
        "run_context_comparison.py", "context_preservation.py", "local_llama.py",
        "appworld_bridge.py", "model_provenance.py",
    ]
    if arm == "native_roles":
        files.append("native_conversation.py")
    if phase == "P11":
        files.append("native_boundary_record.py")
    hashes = {}
    for name in files:
        path = ROOT / "scripts" / name
        (snapshot / name).write_bytes(path.read_bytes())
        hashes[name] = sha(path)
    write_json(out / "provenance.json", {
        "sources": hashes, "public_schema_hashes": schema_hashes,
        "runtime": runtime, "props": props, "python": str(python),
        "task_id": task_id, "arm": arm,
        "spec_sha256": sha(appworld_root / "data/tasks" / task_id / "specs.json"),
    })
    infer = Inference(config, out)
    bridge = Bridge(python, appworld_root, out)
    spans, events = {}, []
    api_requests, peak_tools = 0, len(catalog.tools())
    complete, reason = False, "not_started"
    conversation = None
    formatting = {}
    boundaries = []
    capture_attempts, capture_seconds = 0, 0.0

    def capture_files_at_boundary(checkpoint_id):
        dbs = world_output / "tasks" / task_id / "dbs"
        entries = list(dbs.iterdir())
        if not entries or any(not p.is_file() or p.is_symlink() for p in entries):
            raise ValueError("unexpected AppWorld saved DB directory")
        capture_files = {"dbs/" + p.name: p for p in entries}
        for name in ("plan.json", "provenance.json", "public_task.json", "spans.json",
                     "events.json", "usage.json", "conversation_private.json"):
            if (out / name).exists():
                capture_files["harness/" + name] = out / name
        remaining = config["max_checkpoint_object_bytes"] - sum(
            row["new_object_bytes"] for row in boundaries)
        if remaining <= 0:
            raise BudgetStop("checkpoint_storage_limit")
        elapsed = time.monotonic() - infer.started
        state = {"run_id": run_id, "task_id": task_id, "arm": arm,
                 "model_calls": len(infer.calls), "known_total_tokens": infer.tokens,
                 "api_requests": api_requests, "span_ids": list(spans),
                 "visible_api_schemas": sorted(catalog.visible),
                 "declared_complete": complete, "elapsed_wall_seconds": elapsed,
                 "remaining_tokens": config["max_total_tokens"] - infer.tokens,
                 "remaining_wall_seconds_before_capture": max(0, config["max_wall_seconds"] - elapsed),
                 "rng_and_process_state_captured": False}
        saved = snapshot_boundary(out / "boundaries", checkpoint_id, capture_files, state,
                                  min(remaining, config["max_checkpoint_new_bytes_per_boundary"]))
        boundaries.append(saved)
        write_json(out / "boundary_index.json", boundaries)

    def capture(checkpoint_id):
        nonlocal capture_attempts, capture_seconds
        if phase != "P11":
            return
        capture_attempts += 1
        started_capture = time.monotonic()
        try:
            capture_files_at_boundary(checkpoint_id)
        finally:
            capture_seconds += time.monotonic() - started_capture
    try:
        response = bridge.request({"op": "init", "task_id": task_id,
                                   "experiment": run_id, "seed": config["seed"]})
        if not response["ok"]:
            raise RuntimeError(response["error"])
        task = response["result"]
        write_json(out / "public_task.json", task)
        if arm == "native_roles":
            conversation = NativeConversation(NATIVE_PROMPT, task)
            write_json(out / "conversation_private.json", conversation.messages())
        capture("initial")
        while not complete:
            if api_requests >= config["max_api_requests"]:
                raise BudgetStop("api_request_limit")
            supplied_tools = catalog.tools()
            peak_tools = max(peak_tools, len(supplied_tools))
            if conversation is None:
                messages = messages_for(task, spans, config)
            else:
                messages, formatting = conversation.for_model(config["observation_page_characters"])
            message = infer.call("agent", messages, supplied_tools)
            call_id = infer.calls[-1]["id"]
            first = True
            current_spans = []

            def record(row):
                nonlocal api_requests, complete, first
                sid = f"s{len(spans) + 1}"
                spans[sid] = {
                    "id": sid, "assistant": (message.get("content") or "") if first else "",
                    "action": row["action"], "observation": row["observation"]}
                first = False
                current_spans.append(spans[sid])
                api_requests += int(row["api_request_sent"])
                complete = complete or bool(row["observation"].get("declared_complete"))
                events.append({
                    "turn": len(spans), "call": call_id, "span_id": sid,
                    "api_request_sent": row["api_request_sent"], "new_tools": row["new_tools"],
                    "effects_unknown": row.get("effects_unknown", False),
                    "declared_complete": complete})
                # Persist each result before the next operation in the same model response.
                write_json(out / "spans.json", spans)
                write_json(out / "events.json", events)
                write_json(out / "progress.json", {
                    "arm": arm, "task_id": task_id, "calls": len(infer.calls),
                    "tokens": infer.tokens, "turns": len(spans), "compressions": 0,
                    "api_requests": api_requests, "exposed_api_schemas": len(catalog.visible)})

            rows = dispatch_native_calls(
                message, catalog, bridge,
                lambda sid, offset: page_span(
                    spans, sid, offset, config["observation_page_characters"]),
                remaining_api_calls=config["max_api_requests"] - api_requests,
                may_continue=lambda: time.monotonic() - infer.started < config["max_wall_seconds"],
                on_record=record)
            if conversation is not None:
                conversation.append(message, current_spans)
                write_json(out / "conversation_private.json", conversation.messages())
                _, formatting = conversation.for_model(config["observation_page_characters"])
            if any(r.get("effects_unknown") for r in rows):
                raise RuntimeError("API request has unknown effects; no retry")
            capture(call_id)
        reason = "agent_declared_complete"
    except BudgetStop as exc:
        reason = str(exc)
    except Exception as exc:
        reason = "runtime_error"
        write_json(out / "error.json", {"type": type(exc).__name__, "message": str(exc)})
    finally:
        try:
            bridge.close()
        except Exception as exc:
            reason = "runtime_error"
            write_json(out / "close_error.json", {"type": type(exc).__name__, "message": str(exc)})
        known = [c for c in infer.calls if c["status"] == "ok"]
        summary = {
            "run_id": run_id, "task_id": task_id, "arm": arm,
            "stop_reason": reason, "declared_complete": complete,
            "final_success": None, "evaluation": "not_run",
            "known_total_tokens": infer.tokens, "model_calls": len(infer.calls),
            "usage_by_role": {"agent": {
                "calls": len(infer.calls),
                "input_tokens": sum(c["input_tokens"] for c in known),
                "output_tokens": sum(c["output_tokens"] for c in known),
                "unknown_usage": len(infer.calls) - len(known)}},
            "tool_turns": len(spans), "api_requests": api_requests, "compression_events": 0,
            "format_errors": sum("format_error" in s["observation"] for s in spans.values()),
            "api_bridge_errors": sum("api_error" in s["observation"] for s in spans.values()),
            "unknown_effect_requests": sum(e["effects_unknown"] for e in events),
            "peak_supplied_tools": peak_tools,
            "wall_seconds": time.monotonic() - infer.started,
            "finished_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "source_hashes": hashes,
            "history_formatting": formatting,
            "boundary_records": len(boundaries),
            "boundary_capture_attempts": capture_attempts,
            "boundary_capture_seconds": capture_seconds,
            "boundary_new_object_bytes": sum(row["new_object_bytes"] for row in boundaries),
            "boundary_object_bytes_on_disk": sum(p.stat().st_size for p in
                                                  (out / "boundaries/objects").glob("*") if p.is_file()),
        }
        write_json(out / "summary.json", summary)
        print(json.dumps(summary), flush=True)
    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--storage-root", type=Path, required=True)
    parser.add_argument("--appworld-root", type=Path, required=True)
    parser.add_argument("--appworld-python", type=Path, required=True)
    args = parser.parse_args()

    def timeout(_signum, _frame):
        raise TimeoutError("local inference deadline")

    signal.signal(signal.SIGALRM, timeout)
    result = run(json.loads(args.plan.read_text()), args.task_id, args.run_id,
                 args.storage_root.resolve(), args.appworld_root.resolve(),
                 args.appworld_python.absolute())
    return 0 if result["stop_reason"] != "runtime_error" else 1


if __name__ == "__main__":
    raise SystemExit(main())
