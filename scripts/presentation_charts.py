"""Charts generated from the committed, aggregate research records."""
import csv
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.ticker import FuncFormatter
import numpy as np

NAVY, TEAL, AMBER, RED = "#17304D", "#087F8C", "#C18A30", "#B84D4D"


def generate(root, out, font_path):
    out = Path(out)
    figdir = out/"figures"
    figdir.mkdir(parents=True, exist_ok=True)
    font_manager.fontManager.addfont(str(font_path))
    plt.rcParams.update({
        "font.family": font_manager.FontProperties(fname=str(font_path)).get_name(),
        "font.size": 14, "axes.labelsize": 14, "axes.titlesize": 15,
        "axes.spines.top": False, "axes.spines.right": False,
        "axes.edgecolor": "#CED5DE", "text.color": NAVY,
        "axes.labelcolor": NAVY, "xtick.color": NAVY, "ytick.color": NAVY,
        "axes.axisbelow": True, "grid.color": "#E4E9EF", "svg.fonttype": "path",
        "pdf.fonttype": 42, "savefig.facecolor": "white",
    })
    paths = ["reports/P3_measurements.json", "reports/P3_timeline.json",
             "reports/P4_pro_measurements.json", "reports/P4_pro_public_failure_observations.json"]
    sources = {p: json.loads((root/p).read_text()) for p in paths}
    p3 = sources[paths[0]]["runs"]
    times = {r["record"]: r for r in sources[paths[1]]["runs"]}
    ordered = sorted(p3, key=lambda r: (r["task"], r["strategy"] != "single"))
    p4 = sources[paths[2]]["runs"][0]
    m4 = p4["measurements"]
    assert len(ordered) == 4 and not m4["errors"]
    assert m4["evaluation"]["evaluation_status"] == "completed"
    rows = []
    for r in ordered:
        t = times[r["record"]]
        rows.append({
            "task": r["task"], "strategy": r["strategy"],
            "calls": t["calls"], "input_tokens": t["input_tokens"],
            "output_tokens": t["output_tokens"], "total_tokens": r["known_total_tokens"],
            "cached_input_tokens": t["known_cached_input_tokens"],
            "cache_fraction_input": t["cached_fraction_of_input"],
            "wall_seconds": r["wall_seconds"], "resolved": r["evaluation"]["resolved"],
            "stop_reason": r["stop_reason"], "source_record": r["record"],
        })
    with (out/"P3_data.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0])
        writer.writeheader(); writer.writerows(rows)
    with (out/"P4_timeline.csv").open("w", newline="") as f:
        columns = ["turn", "input_tokens", "output_tokens", "cached_input_tokens",
                   "cumulative_input_output_tokens", "artifact_changed"]
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        writer.writeheader(); writer.writerows(p4["timeline"]["timeline"])
    manifest = {p: hashlib.sha256((root/p).read_bytes()).hexdigest() for p in paths}
    (out/"data_sources.json").write_text(json.dumps({
        "cutoff": "P4_PRO_01 final evaluation completed on 2026-10-20",
        "source_sha256": manifest, "P3": rows,
        "P4": {"measurements": m4, "timeline": p4["timeline"]["timeline"]},
        "limits": ["All observations are development observations.",
                   "Each task/strategy has one run; no statistical equivalence or causal efficiency claim.",
                   "P3 and P4 differ in task, budget and runtime; they are not pooled."]
    }, ensure_ascii=False, indent=2)+"\n")

    def save(fig, name):
        for ext in ("png", "svg", "pdf"):
            fig.savefig(figdir/f"{name}.{ext}", dpi=200, bbox_inches=None)
        plt.close(fig)

    # Zero-origin bars and exact labels; no invented error bars for one-run data.
    fig, ax = plt.subplots(figsize=(11.5, 4.2))
    fig.subplots_adjust(left=.17, right=.95, top=.92, bottom=.18)
    ys = [3.25, 2.55, 1.25, .55]
    for y, r in zip(ys, rows):
        c = TEAL if r["strategy"] == "single" else NAVY
        ax.barh(y, r["total_tokens"]/1000, height=.46, color=c)
        ax.text(r["total_tokens"]/1000+3, y, f'{r["total_tokens"]:,}',
                va="center", fontsize=13, color=c)
    ax.set_yticks(ys, ["15380 単一", "15380 2担当", "15957 単一", "15957 2担当"])
    ax.set_xlim(0, 325); ax.set_ylim(0, 4)
    ax.set_xlabel("全入力＋出力（千トークン）")
    ax.axvline(300, color=AMBER, linestyle="--", lw=1.5)
    ax.text(299, 3.82, "上限 300k", ha="right", color=AMBER, fontsize=12)
    ax.grid(axis="x"); save(fig, "p3_tokens")

    fig, axes = plt.subplots(1, 2, figsize=(11.5, 4.2))
    fig.subplots_adjust(left=.07, right=.97, top=.82, bottom=.20, wspace=.27)
    labels = ["15380\n単一", "15380\n2担当", "15957\n単一", "15957\n2担当"]
    colors = [TEAL, NAVY, TEAL, NAVY]
    for ax, vals, title, lim, suffix in [
        (axes[0], [r["wall_seconds"]/60 for r in rows], "課題実行の実時間", 45, "分"),
        (axes[1], [100*r["cache_fraction_input"] for r in rows], "入力のうちキャッシュ対象", 110, "%"),
    ]:
        ax.bar(range(4), vals, width=.60, color=colors)
        ax.set_xticks(range(4), labels, fontsize=12)
        ax.set_ylim(0, lim); ax.set_title(title, pad=15)
        ax.set_ylabel(suffix); ax.grid(axis="y")
        for k, v in enumerate(vals):
            ax.text(k, v+lim*.025, f"{v:.1f}{suffix}", ha="center", fontsize=12)
    save(fig, "p3_time_cache")

    fig, ax = plt.subplots(figsize=(11.5, 4.2))
    fig.subplots_adjust(left=.10, right=.97, top=.91, bottom=.18)
    timeline = p4["timeline"]["timeline"]
    x = [0]+[r["turn"] for r in timeline]
    y = [0]+[r["cumulative_input_output_tokens"]/1000 for r in timeline]
    ax.fill_between(x, y, color=TEAL, alpha=.12)
    ax.plot(x, y, color=TEAL, lw=2.6)
    ax.axhline(600, color=AMBER, linestyle="--", lw=1.5)
    ax.axvline(32, color=NAVY, linestyle=":", lw=1.3)
    ax.scatter([32,38], [429.153,586.166], color=[NAVY,RED], zorder=5, s=40)
    ax.annotate("32回目：一時的な再現確認\n累積 429,153", xy=(32,429.153),
                xytext=(12,490), fontsize=13, color=NAVY,
                arrowprops={"arrowstyle":"->", "color":NAVY})
    ax.annotate("38回目：予算停止\n586,166 / 修正パッチなし", xy=(38,586.166),
                xytext=(23,110), fontsize=13, color=RED,
                bbox={"facecolor":"white","edgecolor":"none","alpha":.9,"pad":3},
                arrowprops={"arrowstyle":"->", "color":RED})
    ax.text(2,613,"総予算 600,000",color=AMBER,fontsize=12)
    ax.set_xlim(0,40); ax.set_ylim(0,660)
    ax.set_xlabel("LLM呼び出しの通算回数")
    ax.set_ylabel("累積 入力＋出力（千トークン）")
    ax.grid(); save(fig, "p4_timeline")

    # A rectangular composition avoids exaggerating a tiny output slice.
    fig, ax = plt.subplots(figsize=(11.5, 2.1))
    fig.subplots_adjust(left=.05, right=.98, top=.88, bottom=.30)
    vals = [m4["cached_input_tokens"], m4["input_tokens"]-m4["cached_input_tokens"], m4["output_tokens"]]
    left = 0
    for v,c,label in zip(vals,[TEAL,NAVY,AMBER],["キャッシュ対象の入力","その他の入力","出力"]):
        ax.barh([0], [v/1000], left=left/1000, height=.35, color=c, label=label)
        left += v
    ax.set_xlim(0,600);ax.set_ylim(-.6,.6);ax.set_yticks([])
    ax.set_xlabel("全入力＋出力（千トークン）")
    ax.legend(loc="upper center", bbox_to_anchor=(.5,1.35), ncol=3, frameon=False,fontsize=13)
    ax.grid(axis="x"); save(fig,"p4_composition")
    return rows, p4
