"""Wait for P7, run two frozen baselines, evaluate offline and publish aggregate progress."""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

from run_context_comparison import write_json
from watch_context_pilot import collect
from watch_pro_comparison import gh_api

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = "sophiria1225/AI-"
ISSUE = 36
MARKER = "<!-- harness-native-baseline:P8_batch_v01 -->"


def check_frozen(frozen):
    for name, digest in frozen["source_hashes"].items():
        if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != digest:
            raise RuntimeError("frozen source changed: " + name)


def public_body(rows, state):
    states = {
        "waiting": "P7の終了待ち", "running": "実行中", "complete": "2試行の実行・評価処理が終了",
        "prerequisite_failed": "前段の状態を確認するため保留",
        "runtime_error": "実行エラーで停止", "server_lease_too_short": "サーバーの残稼働時間不足で未開始",
    }
    lines = [MARKER, "P8：公開スキーマ・複数操作を使う全履歴基準", "",
             "| 課題 | 状態 | LLM呼出 | API要求 | 既知トークン | 使用量不明 | 独立評価 |",
             "|---|---|---:|---:|---:|---:|---|"]
    for row in rows:
        status = {"pending": "待機", "running": "実行中", "finished": "実行終了",
                  "evaluated": "評価済み", "evaluation_error": "評価要確認"}[row["status"]]
        success = row.get("success")
        if success is not None and type(success) is not bool:
            raise ValueError("invalid public evaluation")
        result = "未確定" if success is None else ("成功" if success else "未達")
        lines.append(f"| {int(row['task_number'])} | {status} | {int(row.get('calls', 0))} | "
                     f"{int(row.get('api_requests', 0))} | "
                     f"{int(row.get('tokens', 0)):,} | {int(row.get('unknown_usage_calls', 0))} | {result} |")
    lines += ["", states[state["status"]],
              "各試行：80 LLM呼び出し・80 API要求・45万トークン・30分以内。未知費用は0とせず、失敗を自動再試行しません。",
              "公式APIスキーマを利用した導入基準で、公式エージェントの完全再現・新手法・品質維持の主張ではありません。",
              "評価は終了後の別プロセスで行い、後続のモデル入力には返しません。",
              "[事前仕様](https://github.com/sophiria1225/AI-/blob/research/appworld-api-calibration-20261021/docs/experiments/P8_native_baseline.md)"]
    return "\n".join(lines) + "\n"


def publish(body, state):
    endpoint = f"repos/{REPOSITORY}/issues/{ISSUE}"
    if state.get("comment_id"):
        endpoint = f"repos/{REPOSITORY}/issues/comments/{int(state['comment_id'])}"
        previous = gh_api(endpoint)
        if (previous.get("issue_url") != f"https://api.github.com/repos/{REPOSITORY}/issues/{ISSUE}"
                or not previous.get("body", "").startswith(MARKER)):
            raise ValueError("unexpected progress destination")
        result = gh_api(endpoint, method="PATCH", payload={"body": body})
    else:
        if gh_api(endpoint)["html_url"] != f"https://github.com/{REPOSITORY}/issues/{ISSUE}":
            raise ValueError("unexpected Issue identity")
        result = gh_api(endpoint + "/comments", method="POST", payload={"body": body})
    state.update(comment_id=result["id"], comment_url=result["html_url"])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--freeze-record", type=Path, required=True)
    parser.add_argument("--storage-root", type=Path, required=True)
    parser.add_argument("--publish", action="store_true")
    args = parser.parse_args()
    storage = args.storage_root.resolve()
    plan = json.loads(args.plan.read_text())
    frozen = json.loads(args.freeze_record.read_text())
    check_frozen(frozen)
    if plan["batch_id"] != "P8_batch_v01" or len(plan["run_order"]) != 2:
        raise ValueError("only the fixed two-trial plan is supported")
    out = storage / "records/context_pilot" / plan["batch_id"]
    out.mkdir(exist_ok=False)
    observer = out / "observer"
    observer.mkdir()
    write_json(out / "plan.json", plan)
    write_json(out / "freeze_record.json", frozen)
    state = {
        "status": "waiting", "started_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "git_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "completed": [], "active": None,
    }
    last_publish, last_signature = 0, None

    def update(force=False):
        nonlocal last_publish, last_signature
        rows = collect(storage, plan["run_order"], observer)
        for row, (_, _, run_id) in zip(rows, plan["run_order"], strict=True):
            trial = storage / "records/context_pilot" / run_id
            source = trial / "summary.json"
            if not source.exists():
                source = trial / "progress.json"
            if source.exists():
                row["api_requests"] = json.loads(source.read_text()).get("api_requests", 0)
        state["rows"] = rows
        body = public_body(rows, state)
        (out / "progress.md").write_text(body)
        signature = (state["status"], state["active"],
                     [(r["status"], r.get("success")) for r in rows])
        if args.publish and (force or signature != last_signature
                             or time.monotonic() - last_publish >= 300):
            try:
                publish(body, state)
                state.pop("publish_error", None)
            except (ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
                state["publish_error"] = type(exc).__name__
            last_publish, last_signature = time.monotonic(), signature
        state["updated_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        write_json(out / "status.json", state)

    update()
    started = time.monotonic()
    while True:
        prerequisite = json.loads(
            (storage / "records/memory_probe" / plan["wait_for_probe"] / "status.json").read_text())
        if prerequisite["status"] == "complete":
            break
        if (prerequisite["status"] not in ("waiting", "running")
                or time.monotonic() - started > plan["max_wait_seconds"]):
            state["status"] = "prerequisite_failed"
            update(True)
            return 1
        update()
        time.sleep(30)
    try:
        check_frozen(frozen)
    except RuntimeError:
        state.update(status="runtime_error", error_type="FrozenSourceChanged")
        update(True)
        return 1
    lease_end = datetime.datetime.fromisoformat(plan["server_lease_end_utc"])
    remaining = (lease_end - datetime.datetime.now(datetime.timezone.utc)).total_seconds()
    if remaining < len(plan["run_order"]) * plan["max_wall_seconds"] + 180:
        state["status"] = "server_lease_too_short"
        update(True)
        return 1
    try:
        state["status"] = "running"
        for task, arm, name in plan["run_order"]:
            if arm != "native_full":
                raise ValueError("unexpected baseline arm")
            check_frozen(frozen)
            state["active"] = name
            update(True)
            command = [
                sys.executable, str(ROOT / "scripts/run_native_appworld.py"),
                "--plan", str(args.plan.absolute()), "--task-id", task, "--run-id", name,
                "--storage-root", str(storage),
                "--appworld-root", str(storage / ".runtime/appworld/r18_probe_01"),
                "--appworld-python", str(storage / ".runtime/appworld/venv/bin/python"),
            ]
            with (out / (name + ".log")).open("w") as stream:
                child = subprocess.Popen(command, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT)
                while child.poll() is None:
                    update()
                    time.sleep(30)
            state["completed"].append({"run_id": name, "exit_code": child.returncode})
            update(True)
            if child.returncode:
                raise RuntimeError("trial failed; no automatic retry")
        state["status"] = "complete"
    except Exception as exc:
        state.update(status="runtime_error", error_type=type(exc).__name__)
        write_json(out / "error_private.json", {"type": type(exc).__name__, "message": str(exc)})
    finally:
        state.update(active=None, finished_at=datetime.datetime.now(datetime.timezone.utc).isoformat())
        update(True)
    return 0 if state["status"] == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
