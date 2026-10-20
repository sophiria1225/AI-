"""Export standalone plots from finished trials; no trajectory text leaves storage."""
import argparse
import csv
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from summarize_context_pilot import summarize_trial


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--storage-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    plan = json.loads(args.plan.read_text())
    schedule = plan.get("prior_run_order", []) + plan["run_order"]
    args.output_dir.mkdir(parents=True, exist_ok=True)
    rows, points, unfinished = [], [], []
    tasks = list(dict.fromkeys(t for t, _, _ in schedule))
    for task, arm, name in schedule:
        trial = args.storage_root / "records/context_pilot" / name
        if not (trial / "summary.json").exists():
            unfinished.append(name)
            continue
        row = summarize_trial(trial)
        if row["audit_errors"]:
            raise ValueError(f"Unaudited measurement: {name}")
        row["task_number"] = tasks.index(task) + 1
        rows.append(row)
        total, turns = 0, 0
        for call in json.loads((trial / "usage.json").read_text()):
            if call["status"] == "ok":
                total += call["input_tokens"] + call["output_tokens"]
            if call["role"] == "agent" and call["status"] == "ok":
                turns += 1
            points.append({"run_id": name, "role": call["role"], "call": call["id"],
                           "completed_agent_calls": turns, "known_cumulative_tokens": total,
                           "usage_known": call["status"] == "ok"})
    if not rows:
        raise ValueError("No finished measurements")
    plt.rcParams.update({"font.family": "Hiragino Sans", "font.size": 10,
                         "axes.spines.top": False, "axes.spines.right": False})
    figure, axes = plt.subplots(1, 2, figsize=(13, 5.8), layout="constrained")
    names = {"full": "全履歴", "focus": "FOCUS再実装", "ledger": "対象台帳"}
    labels = [f"課題{r['task_number']}・{names[r['arm']]}" for r in rows]
    executor = [sum(v["input_tokens"] + v["output_tokens"] for k, v in r["usage_by_role"].items()
                    if k == "agent") / 1000 for r in rows]
    memory = [r["known_total_tokens"] / 1000 - a for r, a in zip(rows, executor)]
    positions = list(range(len(rows)))
    axes[0].barh(positions, executor, color="#245a81", label="作業の実行")
    axes[0].barh(positions, memory, left=executor, color="#c67b32", label="圧縮・台帳生成")
    axes[0].set_yticks(positions, labels)
    axes[0].invert_yaxis()
    axes[0].set_xlabel("既知の総入力＋出力（千トークン）")
    for i, row in enumerate(rows):
        success = (row.get("evaluation") or {}).get("official_success")
        state = "成功" if success is True else ("未達" if success is False else "評価待ち")
        unknown = "＋不明費用" if row["unknown_usage_calls"] else ""
        axes[0].text(row["known_total_tokens"] / 1000 + 1, i,
                     f"{row['known_total_tokens']:,}{unknown}\n{state}", va="center", fontsize=8)
    axes[0].set_xlim(0, max(r["known_total_tokens"] for r in rows) / 1000 * 1.55)
    axes[0].legend(loc="lower right", frameon=False)
    axes[0].set_title("最終状態と全役割の費用")
    for row in rows:
        series = [p for p in points if p["run_id"] == row["run_id"]]
        axes[1].plot([0] + [p["completed_agent_calls"] for p in series],
                     [0] + [p["known_cumulative_tokens"] / 1000 for p in series],
                     marker=".", markersize=4, label=f"課題{row['task_number']}・{names[row['arm']]}")
    axes[1].set_xlabel("完了した実行役の呼び出し数")
    axes[1].set_ylabel("累積既知トークン（千）")
    axes[1].set_title("作業が進む間に費用がどこで増えたか")
    axes[1].legend(frameon=False, fontsize=8)
    figure.suptitle("P6 情報保持方式の導入観察：終了した試行のみ", fontsize=15)
    figure.supxlabel("学習用2課題・各方式1回。費用不明は総額の下限。成功率の一般化・品質維持・新規性は未確定。", fontsize=9)
    for extension in ("png", "svg", "pdf"):
        figure.savefig(args.output_dir / f"cost_and_progress.{extension}", dpi=160,
                       metadata={"Creator": "plot_context_observations.py"})
    plt.close(figure)
    with (args.output_dir / "call_costs.csv").open("w") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(points[0]))
        writer.writeheader()
        writer.writerows(points)
    (args.output_dir / "measurements.json").write_text(json.dumps({
        "finished": rows, "unfinished": unfinished,
        "plan_sha256": hashlib.sha256(args.plan.read_bytes()).hexdigest(),
        "plot_script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "interpretation": "Only completed trials. Interrupted calls remain unknown, not zero."
    }, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"finished": len(rows), "unfinished": len(unfinished)}))


if __name__ == "__main__":
    main()
