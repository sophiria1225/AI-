"""Bounded P6 observer and offline evaluator; updates only AI- Issue 30.

No model calls, retries, parameter changes, Git commits or Issue closing.
"""
import argparse
import datetime
import json
from pathlib import Path
import subprocess
import sys
import time

from watch_pro_comparison import gh_api

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = "sophiria1225/AI-"
ISSUE = 30
MARKER = "<!-- harness-batch:P6_v02 -->"


def public_body(rows, finished=False, marker=MARKER):
    lines = [marker, "P6自動進捗：AppWorldの学習用2課題・3方式・各1回", "",
             "| 課題 | 方式 | 状態 | 呼び出し | 既知トークン | 費用不明の呼出 | 記録済圧縮 | 公式評価 |",
             "|---|---|---|---:|---:|---:|---:|---|"]
    for row in rows:
        arm = {"full": "全履歴", "focus": "防御的圧縮の再実装", "ledger": "対象台帳"}[row["arm"]]
        status = {"pending": "待機", "running": "実行中", "finished": "実行終了",
                  "evaluated": "評価済み", "evaluation_error": "評価要確認"}[row["status"]]
        outcome = row.get("success")
        if outcome is not None and type(outcome) is not bool:
            raise ValueError("Boolean evaluation required")
        outcome_text = "未確定" if outcome is None else ("成功" if outcome else "未達")
        if row.get("stop_reason") in ("wall_limit", "wall_limit_during_count",
                                      "wall_limit_during_model_call"):
            status += "・時間上限"
        elif row.get("stop_reason") == "runtime_error":
            status += "・実行エラー"
        lines.append(f"| {int(row['task_number'])} | {arm} | {status} | "
                     f"{int(row.get('calls', 0))} | {int(row.get('tokens', 0)):,} | "
                     f"{int(row.get('unknown_usage_calls', 0))} | "
                     f"{int(row.get('compressions', 0))} | {outcome_text} |")
    lines += ["", "実行・圧縮・台帳作成の全呼び出しを計上。公式評価は実行終了後の別プロセスで行い、モデルへ返しません。",
              "費用不明の呼び出しがある行では、既知トークンは総費用の下限です。実行中の呼び出しは完了後に反映します。",
              "各実行は最大80呼び出し・45万トークン・30分。基盤異常を自動再試行しません。",
              "導入用の少数観察で、新規性・品質維持・一般的な費用削減を確定する実験ではありません。",
              "[固定仕様](https://github.com/sophiria1225/AI-/blob/research/context-preservation-20261021/docs/experiments/P6_context_preservation.md)",
              "[PR #31](https://github.com/sophiria1225/AI-/pull/31)"]
    if finished:
        lines += ["", "このバッチの自動監視を終了しました。未完了・評価要確認は成功に含めません。"]
    return "\n".join(lines) + "\n"


def publish(body, state, marker=MARKER):
    endpoint = f"repos/{REPOSITORY}/issues/{ISSUE}"
    if state.get("comment_id"):
        endpoint = f"repos/{REPOSITORY}/issues/comments/{int(state['comment_id'])}"
        existing = gh_api(endpoint)
        if (existing.get("issue_url") != f"https://api.github.com/repos/{REPOSITORY}/issues/{ISSUE}"
                or not existing.get("body", "").startswith(marker)):
            raise ValueError("progress comment is outside authorized Issue or marker")
        result = gh_api(endpoint, method="PATCH", payload={"body": body})
    else:
        issue = gh_api(endpoint)
        if issue["html_url"] != f"https://github.com/{REPOSITORY}/issues/{ISSUE}":
            raise ValueError("unexpected Issue identity")
        result = gh_api(endpoint + "/comments", method="POST", payload={"body": body})
    state.update(comment_id=result["id"], comment_url=result["html_url"])


def collect(storage, schedule, observer):
    rows = []
    tasks = list(dict.fromkeys(row[0] for row in schedule))
    for task, arm, run_id in schedule:
        directory = storage / "records/context_pilot" / run_id
        row = {"task_number": tasks.index(task) + 1, "arm": arm, "status": "pending"}
        progress = directory / "progress.json"
        if progress.exists():
            value = json.loads(progress.read_text())
            row.update(status="running", calls=value["calls"], tokens=value["tokens"],
                       compressions=value["compressions"])
        usage = directory / "usage.json"
        if usage.exists():
            calls = json.loads(usage.read_text())
            row.update(status="running", calls=len(calls),
                       tokens=sum(c["input_tokens"] + c["output_tokens"]
                                  for c in calls if c["status"] == "ok"),
                       unknown_usage_calls=sum(c["status"] != "ok" for c in calls))
        compression_path = directory / "compressions.json"
        if compression_path.exists():
            row["compressions"] = len(json.loads(compression_path.read_text()))
        summary = directory / "summary.json"
        if summary.exists():
            value = json.loads(summary.read_text())
            row.update(status="finished", calls=value["model_calls"],
                       tokens=value["known_total_tokens"], compressions=value["compression_events"],
                       stop_reason=value["stop_reason"],
                       unknown_usage_calls=sum(r["unknown_usage"]
                                               for r in value["usage_by_role"].values()))
            evaluation = directory / "evaluation.json"
            failure = observer / (run_id + "_evaluation_error.json")
            if not evaluation.exists() and not failure.exists():
                command = [str(storage / ".runtime/appworld/venv/bin/python"),
                           str(ROOT / "scripts/evaluate_context_trial.py"),
                           "--appworld-root", str(storage / ".runtime/appworld/r18_probe_01"),
                           "--trial", str(directory)]
                try:
                    with (observer / (run_id + "_evaluation.log")).open("w") as stream:
                        result = subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT,
                                                timeout=180)
                    if result.returncode:
                        failure.write_text(json.dumps({"exit_code": result.returncode}) + "\n")
                except subprocess.TimeoutExpired:
                    failure.write_text(json.dumps({"timeout": True}) + "\n")
            if evaluation.exists():
                row.update(status="evaluated", success=json.loads(
                    evaluation.read_text())["official_success"])
            elif failure.exists():
                row["status"] = "evaluation_error"
        rows.append(row)
    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--storage-root", type=Path, required=True)
    parser.add_argument("--batch-id", default="P6_batch_v02")
    parser.add_argument("--publish", action="store_true")
    args = parser.parse_args()
    storage = args.storage_root.resolve()
    if not args.batch_id.startswith("P6_") or not args.batch_id.replace("_", "").isalnum():
        raise ValueError("expected a safe P6 batch ID")
    batch = storage / "records/context_pilot" / args.batch_id
    plan = json.loads((batch / "plan.json").read_text())
    schedule = plan.get("prior_run_order", []) + plan["run_order"]
    marker = f"<!-- harness-batch:{args.batch_id} -->"
    observer = batch / "observer"
    observer.mkdir(exist_ok=False)
    state = {"status": "running"}
    started, last_publish, last_signature = time.monotonic(), 0, None
    while True:
        try:
            batch_state = json.loads((batch / "status.json").read_text())
        except json.JSONDecodeError:
            time.sleep(1)
            continue
        rows = collect(storage, schedule, observer)
        finished = (batch_state["status"] != "running"
                    or time.monotonic() - started > 14400)
        signature = [(r["status"], r.get("success")) for r in rows]
        body = public_body(rows, finished, marker)
        (observer / "progress.md").write_text(body)
        if args.publish and (signature != last_signature or finished
                             or time.monotonic() - last_publish > 300):
            try:
                publish(body, state, marker)
                state.pop("publish_error", None)
            except (ValueError, RuntimeError, subprocess.TimeoutExpired) as error:
                state["publish_error"] = type(error).__name__
            last_publish, last_signature = time.monotonic(), signature
        state.update(rows=rows, at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                     status="finished" if finished else "running")
        (observer / "summary.json").write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n")
        if finished:
            break
        time.sleep(30)
    print(json.dumps(state, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
