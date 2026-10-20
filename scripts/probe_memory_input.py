"""Isolated memory-generation calibration after the frozen P6 batch finishes.

No AppWorld execution, evaluator, retries or original-record changes.
"""
import argparse
import copy
import datetime
import hashlib
import json
from pathlib import Path
import signal
import subprocess
import time
import urllib.request

from context_preservation import compact, parse_submission, validate_ledger
from local_llama import payload_for
from model_provenance import check_live_model
from run_context_comparison import Inference, BudgetStop, write_json
from watch_pro_comparison import gh_api

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = "sophiria1225/AI-"
ISSUE = 34
MARKER = "<!-- harness-memory-probe:P7_01 -->"
VARIANTS = ("raw", "quarantine", "execution_tag")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def transform(messages, variant):
    if variant not in VARIANTS:
        raise ValueError("unknown input variant")
    result = copy.deepcopy(messages)
    body = json.loads(result[-1]["content"])
    invalid_ids = set()
    for span in body["memory"]["visible_spans"]:
        action = span.get("action") or {}
        observation = span.get("observation") or {}
        if "format_error" not in observation or action.get("name") != "appworld_api":
            continue
        try:
            json.loads(action["arguments"])
        except (ValueError, TypeError, KeyError):
            invalid_ids.add(span["id"])
            if variant == "quarantine":
                span.pop("assistant", None)
                span.pop("action", None)
                span["unexecuted_output_archive_id"] = span["id"]
            elif variant == "execution_tag":
                span["runtime_execution"] = {
                    "action_dispatched": False, "reason": "invalid_tool_arguments"}
    if variant != "raw":
        result[-1]["content"] = compact(body)
    return result, invalid_ids


def outcome(message, messages, invalid_ids):
    memory = json.loads(messages[-1]["content"])["memory"]
    allowed = {s["id"] for s in memory["visible_spans"]}
    allowed |= {s for i in memory.get("working_ledger", {}).get("items", [])
                for s in i["source_ids"]}
    try:
        ledger = validate_ledger(parse_submission(message, "submit_ledger"), allowed)
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        return {"schema_valid": False, "error_type": type(exc).__name__,
                "items": None, "done_items": None, "done_only_unexecuted_sources": None}
    return {
        "schema_valid": True, "error_type": None,
        "items": len(ledger["items"]),
        "done_items": sum(i["status"] == "done" for i in ledger["items"]),
        # An indicator, not a semantic truth label: acknowledging an error can
        # legitimately be done. Blinded semantic review is still required.
        "done_only_unexecuted_sources": sum(
            i["status"] == "done" and set(i["source_ids"]) <= invalid_ids
            for i in ledger["items"]),
    }


def public_body(rows, status, known_total=None, unknown_usage_calls=0):
    labels = {"raw": "原入力", "quarantine": "未実行の生成文を参照へ退避",
              "execution_tag": "原入力＋未実行の実行記録"}
    lines = [MARKER, "P7：同じ保存入力に対する記憶生成の校正", "",
             "| 表現 | 種 | 形式・参照 | 項目 | done | 未実行参照だけのdone | 既知トークン |",
             "|---|---:|---|---:|---:|---:|---:|"]
    for row in rows:
        valid = "適合" if row["schema_valid"] else "不適合"
        values = [str(row[k]) if row[k] is not None else "—"
                  for k in ("items", "done_items", "done_only_unexecuted_sources")]
        lines.append(f"| {labels[row['variant']]} | {int(row['seed'])} | {valid} | "
                     f"{' | '.join(values)} | {int(row['known_tokens']):,} |")
    statuses = {"waiting": "前のP6バッチの終了待ち", "running": "実行中",
                "complete": "予定9呼び出しが終了", "prerequisite_failed": "P6の状態を確認するため保留",
                "runtime_error": "実行エラーで停止", "budget_stop": "予算上限で停止"}
    if known_total is not None:
        lines += ["", f"既知費用 {int(known_total):,} トークン、使用量不明 {int(unknown_usage_calls)} 呼び出し。"]
    lines += ["", statuses[status],
              "形式適合やdone項目数は正しさではありません。未実行参照だけのdoneも、誤りの自動判定ではありません。",
              "課題の実行・最終評価・新手法の検証は行いません。原試行の再試行ではなく、同じ保存入力への記憶生成だけを比較します。",
              "使用量不明が生じたら停止し、下限費用と不明回数を記録します。自動再試行しません。"]
    return "\n".join(lines) + "\n"


def prepare(plan, storage, out):
    source = storage / "records/context_pilot" / plan["source_run_id"]
    request_path = source / plan["source_call_id"] / "request.json"
    if sha(request_path) != plan["source_request_sha256"]:
        raise RuntimeError("source request changed")
    if sha(source / "plan.json") != plan["source_plan_sha256"]:
        raise RuntimeError("source execution plan changed")
    request = json.loads(request_path.read_text())
    config = json.loads((source / "plan.json").read_text())
    config.update(seed=plan["first_seed"], max_calls=len(plan["order"]),
                  max_total_tokens=plan["max_total_tokens"], max_wall_seconds=plan["max_wall_seconds"])
    runtime = json.loads((storage / ".runtime/model_server.json").read_text())
    with urllib.request.urlopen(config["model"]["base_url"] + "/props", timeout=10) as response:
        props = json.load(response)
    check_live_model(config["model_selection"], runtime, props, root=storage,
                     expected_ctx=config["model"]["num_ctx"], expected_cache=("q8_0", "q8_0"))
    cfg = dict(config["model"], seed=plan["first_seed"], temperature=config["agent_temperature"],
               num_predict=config["max_output_tokens"])
    if payload_for(cfg, request["messages"], request["tools"]) != request:
        raise RuntimeError("raw first-seed payload is not identical to source")
    write_json(out / "provenance.json", {"source_request_sha256": sha(request_path),
                                       "runtime": runtime, "props": props, "config": config})
    return request, config


def publish(body, state):
    endpoint = f"repos/{REPOSITORY}/issues/{ISSUE}"
    if state.get("comment_id"):
        endpoint = f"repos/{REPOSITORY}/issues/comments/{int(state['comment_id'])}"
        existing = gh_api(endpoint)
        if (existing.get("issue_url") != f"https://api.github.com/repos/{REPOSITORY}/issues/{ISSUE}"
                or not existing.get("body", "").startswith(MARKER)):
            raise ValueError("unexpected progress comment")
        result = gh_api(endpoint, method="PATCH", payload={"body": body})
    else:
        issue = gh_api(endpoint)
        if issue["html_url"] != f"https://github.com/{REPOSITORY}/issues/{ISSUE}":
            raise ValueError("unexpected Issue identity")
        result = gh_api(endpoint + "/comments", method="POST", payload={"body": body})
    state.update(comment_id=result["id"], comment_url=result["html_url"])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--storage-root", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--freeze-record", type=Path, required=True)
    parser.add_argument("--publish", action="store_true")
    args = parser.parse_args()
    storage = args.storage_root.resolve()
    plan = json.loads(args.plan.read_text())
    if plan["run_id"] != "P7_01" or sorted(plan["order"]) != sorted(VARIANTS * 3):
        raise ValueError("expected the fixed nine-call P7_01 plan")
    frozen = json.loads(args.freeze_record.read_text())
    for path, digest in frozen["source_hashes"].items():
        if sha(ROOT / path) != digest:
            raise RuntimeError("probe source changed: " + path)
    out = storage / "records/memory_probe" / plan["run_id"]
    out.mkdir(parents=True, exist_ok=False)
    write_json(out / "plan.json", plan)
    write_json(out / "freeze_record.json", frozen)
    for path in frozen["source_hashes"]:
        target = out / "source" / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / path).read_bytes())
    state = {"status": "waiting", "started_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
             "freeze_record_sha256": sha(args.freeze_record),
             "git_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()}
    rows = []

    def update():
        write_json(out / "status.json", state)
        body = public_body(rows, state["status"], state.get("known_total_tokens"),
                           state.get("unknown_usage_calls", 0))
        (out / "progress.md").write_text(body)
        if args.publish:
            try:
                publish(body, state)
                state.pop("publish_error", None)
            except (RuntimeError, ValueError, subprocess.TimeoutExpired) as exc:
                state["publish_error"] = type(exc).__name__
            write_json(out / "status.json", state)

    update()
    wait_start = time.monotonic()
    while True:
        try:
            prerequisite = json.loads((storage / "records/context_pilot" /
                                       plan["wait_for_batch"] / "status.json").read_text())
        except json.JSONDecodeError:
            time.sleep(1)
            continue
        if prerequisite["status"] == "complete":
            break
        if (prerequisite["status"] != "running"
                or time.monotonic() - wait_start > plan["max_wait_seconds"]):
            state["status"] = "prerequisite_failed"
            update()
            return 1
        time.sleep(30)
    # Recheck after waiting: do not silently run edited source.
    for path, digest in frozen["source_hashes"].items():
        if sha(ROOT / path) != digest:
            state["status"] = "runtime_error"
            state["error_type"] = "FrozenSourceChanged"
            update()
            return 1
    try:
        request, config = prepare(plan, storage, out)
    except Exception as exc:
        state.update(status="runtime_error", error_type=type(exc).__name__)
        write_json(out / "error_private.json", {"type": type(exc).__name__, "message": str(exc)})
        update()
        return 1
    infer = Inference(config, out)
    state["status"] = "running"
    update()
    try:
        for variant in plan["order"]:
            messages, invalid = transform(request["messages"], variant)
            if len(invalid) != plan["expected_unexecuted_spans"]:
                raise RuntimeError("unexpected input scope")
            seed = config["seed"] + sum(c["role"] == variant for c in infer.calls)
            before = infer.tokens
            message = infer.call(variant, messages, request["tools"])
            row = dict(variant=variant, seed=seed, call_id=infer.calls[-1]["id"],
                       known_tokens=infer.tokens - before,
                       **outcome(message, messages, invalid))
            rows.append(row)
            write_json(out / "results.json", rows)
            state.update(completed_calls=len(infer.calls), known_total_tokens=infer.tokens,
                         unknown_usage_calls=0)
            update()
        state["status"] = "complete"
    except BudgetStop as exc:
        state.update(status="budget_stop", stop_reason=str(exc))
    except Exception as exc:
        state.update(status="runtime_error", error_type=type(exc).__name__)
        write_json(out / "error_private.json", {"type": type(exc).__name__, "message": str(exc)})
    finally:
        state.update(known_total_tokens=infer.tokens,
                     unknown_usage_calls=sum(c["status"] != "ok" for c in infer.calls),
                     finished_at=datetime.datetime.now(datetime.timezone.utc).isoformat())
        update()
        write_json(out / "summary.json", {**state, "results": rows})
    return 0 if state["status"] == "complete" else 1


def timeout(_signum, _frame):
    raise TimeoutError("model call timed out")


if __name__ == "__main__":
    signal.signal(signal.SIGALRM, timeout)
    raise SystemExit(main())
