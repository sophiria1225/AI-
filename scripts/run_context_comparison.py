"""Run one predeclared AppWorld memory arm; final evaluation is a separate process."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import selectors
import signal
import subprocess
import sys
import time
import urllib.request

from context_preservation import (
    AGENT_PROMPT, AGENT_TOOLS, FOCUS_PROMPT, FOCUS_TOOL, LEDGER_PROMPT, LEDGER_TOOL,
    compact, page_span, parse_submission, render_memory, select_focus, validate_ledger,
)
from local_llama import count_input, model_call, post
from model_provenance import check_live_model

ROOT = Path(__file__).resolve().parents[1]


def write_json(path, value):
    path = Path(path)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    temporary.replace(path)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class BudgetStop(Exception):
    pass


class Bridge:
    def __init__(self, python, root, output):
        env = os.environ.copy()
        env["APPWORLD_ROOT"] = str(root)
        self.errors = (output / "bridge.stderr").open("w")
        self.process = subprocess.Popen(
            [str(python), str(ROOT / "scripts/appworld_bridge.py")],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.errors,
            text=True, bufsize=1, cwd=root, env=env)
        self.selector = selectors.DefaultSelector()
        self.selector.register(self.process.stdout, selectors.EVENT_READ)

    def request(self, value):
        self.process.stdin.write(compact(value) + "\n")
        self.process.stdin.flush()
        if not self.selector.select(90):
            raise TimeoutError("AppWorld bridge response timed out")
        line = self.process.stdout.readline()
        if not line:
            raise RuntimeError("AppWorld bridge exited")
        return json.loads(line)

    def close(self):
        try:
            if self.process.poll() is None:
                self.request({"op": "close"})
                self.process.wait(timeout=15)
        finally:
            if self.process.poll() is None:
                self.process.terminate()
                self.process.wait(timeout=15)
            self.selector.close()
            self.errors.close()


class Inference:
    def __init__(self, config, output):
        self.config = config
        self.output = output
        self.started = time.monotonic()
        self.calls = []

    @property
    def tokens(self):
        return sum(c["input_tokens"] + c["output_tokens"] for c in self.calls
                   if c["status"] == "ok")

    def call(self, role, messages, tools):
        elapsed = time.monotonic() - self.started
        cfg = dict(self.config["model"])
        cfg["temperature"] = (self.config["draft_temperature"] if role == "focus"
                              else self.config["agent_temperature"])
        # Compression calls must not shift the executor's random seed schedule.
        cfg["seed"] = self.config["seed"] + sum(c["role"] == role for c in self.calls)
        cfg["num_predict"] = self.config["max_output_tokens"]
        predicted = count_input(cfg, messages, tools)["input_tokens"]
        if len(self.calls) >= self.config["max_calls"]:
            raise BudgetStop("call_limit")
        if elapsed >= self.config["max_wall_seconds"]:
            raise BudgetStop("wall_limit")
        if predicted + cfg["num_predict"] > cfg["num_ctx"]:
            raise BudgetStop("context_limit")
        if self.tokens + predicted + cfg["num_predict"] > self.config["max_total_tokens"]:
            raise BudgetStop("token_reservation_limit")
        call_id = f"call_{len(self.calls) + 1:03d}"
        out = self.output / call_id
        out.mkdir()
        response = model_call(cfg, messages, out,
                              self.config["max_wall_seconds"] - elapsed, tools)
        row = {"id": call_id, "role": role, "status": response["status"],
               "input_tokens": response["input_tokens"],
               "output_tokens": response["output_tokens"],
               "cached_input_tokens": response.get("cached_input_tokens"),
               "wall_seconds": response["wall_seconds"],
               "finish_reason": response.get("done_reason"),
               "predicted_input_tokens": predicted}
        self.calls.append(row)
        write_json(self.output / "usage.json", self.calls)
        if response["status"] != "ok":
            raise RuntimeError("model failure; usage unknown, no free retry")
        if response["input_tokens"] != predicted:
            raise RuntimeError("preflight and terminal input counts differ")
        if self.tokens > self.config["max_total_tokens"]:
            raise RuntimeError("terminal usage exceeded reserved budget")
        return response["message"]

    def memory_tokens(self, content):
        result = post(self.config["model"], "/tokenize", {"content": content}, 60)
        tokens = result.get("tokens")
        if not isinstance(tokens, list):
            raise RuntimeError("tokenizer did not return tokens")
        return len(tokens)


def compress(mode, infer, task, spans, selected, ledger, config):
    visible = render_memory(spans, selected, ledger, config["observation_page_characters"])
    user = compact({"task": task, "memory": json.loads(visible)})
    available = list(selected)
    if mode == "focus":
        drafts = []
        for _ in range(config["focus_rollouts"]):
            message = infer.call("focus", [
                {"role": "system", "content": FOCUS_PROMPT},
                {"role": "user", "content": user}], [FOCUS_TOOL])
            drafts.append(parse_submission(message, "submit_selection"))
        keep, detail = select_focus(drafts, available, config["focus_threshold"])
        return keep, None, detail
    if mode == "ledger":
        message = infer.call("ledger", [
            {"role": "system", "content": LEDGER_PROMPT},
            {"role": "user", "content": user}], [LEDGER_TOOL])
        value = parse_submission(message, "submit_ledger")
        previous_sources = {sid for item in (ledger or {}).get("items", [])
                            for sid in item["source_ids"]}
        value = validate_ledger(value, set(available) | previous_sources)
        return available[-config["ledger_recent_spans"]:], value, {
            "items": len(value["items"]), "semantics_verified": False}
    raise ValueError("unknown compression arm")


def run(config, mode, task_id, run_id, storage, appworld_root, python):
    if task_id not in config["task_ids"] or mode not in config["arms"]:
        raise ValueError("task or arm outside predeclared plan")
    if not run_id.replace("_", "").isalnum():
        raise ValueError("unsafe run ID")
    output = storage / "records/context_pilot" / run_id
    output.mkdir(parents=True, exist_ok=False)
    runtime = json.loads((storage / ".runtime/model_server.json").read_text())
    with urllib.request.urlopen(config["model"]["base_url"] + "/props", timeout=10) as r:
        props = json.load(r)
    check_live_model(config["model_selection"], runtime, props, root=storage,
                     expected_ctx=config["model"]["num_ctx"], expected_cache=("q8_0", "q8_0"))
    snapshot = output / "source"
    snapshot.mkdir()
    files = ["context_preservation.py", "appworld_bridge.py",
             "run_context_comparison.py", "local_llama.py", "model_provenance.py"]
    hashes = {}
    for name in files:
        source = ROOT / "scripts" / name
        (snapshot / name).write_bytes(source.read_bytes())
        hashes[name] = sha(source)
    write_json(output / "plan.json", config)
    write_json(output / "provenance.json", {
        "sources": hashes, "runtime": runtime, "props": props,
        "spec_sha256": sha(appworld_root / "data/tasks" / task_id / "specs.json"),
        "python": str(python), "arm": mode, "task_id": task_id})
    infer = Inference(config, output)
    bridge = Bridge(python, appworld_root, output)
    spans, selected, ledger = {}, [], None
    events, compression_events, format_errors, api_errors = [], [], 0, 0
    declared_complete, stop_reason, last_compression_turn = False, "not_started", 0
    try:
        response = bridge.request({"op": "init", "task_id": task_id,
                                   "experiment": run_id, "seed": config["seed"]})
        if not response["ok"]:
            raise RuntimeError(response["error"])
        task = response["result"]
        write_json(output / "public_task.json", task)
        while not declared_complete:
            memory = render_memory(spans, selected, ledger, config["observation_page_characters"])
            if (mode != "full" and len(spans) > last_compression_turn
                    and infer.memory_tokens(memory) > config["compression_trigger_tokens"]):
                before = list(selected)
                before_calls = len(infer.calls)
                before_tokens = infer.tokens
                event = {"turn": len(spans), "visible_before": before}
                try:
                    selected, ledger, detail = compress(
                        mode, infer, task, spans, selected, ledger, config)
                    event.update(status="ok", detail=detail)
                except (ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
                    # A malformed compressor never silently loses evidence.
                    selected = before
                    event.update(status="invalid_keep_original", error=str(error))
                    format_errors += 1
                event.update(visible_after=list(selected),
                             calls=len(infer.calls) - before_calls,
                             tokens=infer.tokens - before_tokens)
                compression_events.append(event)
                last_compression_turn = len(spans)
                memory = render_memory(spans, selected, ledger, config["observation_page_characters"])
                write_json(output / "compressions.json", compression_events)
            message = infer.call("agent", [
                {"role": "system", "content": AGENT_PROMPT},
                {"role": "user", "content": compact({"task": task,
                                                    "memory": json.loads(memory)})}],
                AGENT_TOOLS)
            calls = message.get("tool_calls") or []
            action = None
            try:
                if len(calls) != 1:
                    raise ValueError("choose exactly one tool call")
                action = calls[0]["function"]
                args = json.loads(action["arguments"])
                if action["name"] == "read_span":
                    result = page_span(spans, args["span_id"], args.get("offset", 0),
                                       config["observation_page_characters"])
                elif action["name"] == "appworld_api":
                    response = bridge.request({"op": "call", "call": args})
                    if not response["ok"]:
                        api_errors += 1
                        result = {"api_error": response["error"]}
                    else:
                        result = response["result"]
                        declared_complete = result["declared_complete"]
                else:
                    raise ValueError("unknown tool")
            except (ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
                format_errors += 1
                result = {"format_error": str(error)}
            span_id = f"s{len(spans) + 1}"
            span = {"id": span_id, "assistant": message.get("content") or "",
                    "action": action, "observation": result}
            # Archive is immutable; expose a reversible page rather than silently
            # deleting long API output. Every arm has the same read_span tool.
            spans[span_id] = span
            selected.append(span_id)
            events.append({"turn": len(spans), "call": infer.calls[-1]["id"],
                           "span_id": span_id, "declared_complete": declared_complete})
            write_json(output / "spans.json", spans)
            write_json(output / "events.json", events)
            write_json(output / "progress.json", {
                "arm": mode, "task_id": task_id, "calls": len(infer.calls),
                "tokens": infer.tokens, "turns": len(spans),
                "compressions": len(compression_events)})
        stop_reason = "agent_declared_complete"
    except BudgetStop as error:
        stop_reason = str(error)
    except Exception as error:
        stop_reason = "runtime_error"
        write_json(output / "error.json", {"type": type(error).__name__, "message": str(error)})
    finally:
        try:
            bridge.close()
        except Exception as error:
            stop_reason = "runtime_error"
            write_json(output / "close_error.json", {
                "type": type(error).__name__, "message": str(error)})
        roles = {}
        for call in infer.calls:
            entry = roles.setdefault(call["role"], {"calls": 0, "input_tokens": 0,
                                                    "output_tokens": 0, "unknown_usage": 0})
            entry["calls"] += 1
            if call["status"] == "ok":
                for key in ("input_tokens", "output_tokens"):
                    entry[key] += call[key]
            else:
                entry["unknown_usage"] += 1
        summary = {"run_id": run_id, "task_id": task_id, "arm": mode,
                   "stop_reason": stop_reason, "declared_complete": declared_complete,
                   "final_success": None, "evaluation": "not_run",
                   "known_total_tokens": infer.tokens, "usage_by_role": roles,
                   "model_calls": len(infer.calls), "tool_turns": len(spans),
                   "compression_events": len(compression_events),
                   "format_errors": format_errors, "api_bridge_errors": api_errors,
                   "wall_seconds": time.monotonic() - infer.started,
                   "finished_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                   "source_hashes": hashes}
        write_json(output / "summary.json", summary)
        print(json.dumps(summary, ensure_ascii=False), flush=True)
    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", required=True)
    parser.add_argument("--arm", required=True, choices=["full", "focus", "ledger"])
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--storage-root", required=True, type=Path)
    parser.add_argument("--appworld-root", required=True, type=Path)
    parser.add_argument("--appworld-python", required=True, type=Path)
    args = parser.parse_args()
    def timeout(signum, frame):
        raise TimeoutError("local inference deadline")
    signal.signal(signal.SIGALRM, timeout)
    summary = run(json.loads(Path(args.plan).read_text()), args.arm, args.task_id,
                  args.run_id, args.storage_root.resolve(), args.appworld_root.resolve(),
                  args.appworld_python.resolve())
    return summary["stop_reason"] != "runtime_error"


if __name__ == "__main__":
    raise SystemExit(0 if main() else 1)
