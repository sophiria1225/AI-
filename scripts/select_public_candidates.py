"""Select a bounded public-statement review pool without gold or run results."""
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIELDS = {"repo", "instance_id", "base_commit", "problem_statement",
          "created_at", "version", "environment_setup_commit"}


def select(raw, plan, registry):
    if hashlib.sha256(raw).hexdigest() != plan["public_inputs_sha256"]:
        raise ValueError("Public input file differs from the fixed plan")
    tasks = [json.loads(line) for line in raw.decode().splitlines()]
    if any(set(task) != FIELDS for task in tasks):
        raise ValueError("Input columns must match the public-only allowlist")
    if len({task["instance_id"] for task in tasks}) != len(tasks):
        raise ValueError("Duplicate task IDs")
    excluded = {task["instance_id"] for task in registry["development"]}
    excluded.update(registry["researcher_gold_preview_exposure"])
    candidates = []
    for repository in plan["repositories"]:
        ranked = []
        for task in tasks:
            if task["repo"] != repository or task["instance_id"] in excluded:
                continue
            rank = hashlib.sha256(
                (plan["seed"] + "\0" + plan["dataset_revision"] + "\0"
                 + task["instance_id"]).encode()).hexdigest()
            ranked.append((rank, task))
        for rank, task in sorted(ranked, key=lambda item: item[0])[:plan["per_repository"]]:
            candidates.append({
                "instance_id": task["instance_id"], "repo": task["repo"],
                "base_commit": task["base_commit"], "rank_sha256": rank,
                "problem_statement_sha256": hashlib.sha256(
                    task["problem_statement"].encode()).hexdigest(),
            })
    if len(candidates) != len(plan["repositories"]) * plan["per_repository"]:
        raise ValueError("Not enough unexposed candidates to fill the planned pool")
    return candidates


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--public-inputs", type=Path, default=ROOT / "data/verified_public_inputs.jsonl")
    args = parser.parse_args()
    plan_path = ROOT / "configs/public_task_screen_v01.json"
    plan = json.loads(plan_path.read_text())
    registry_raw = (ROOT / plan["registry_snapshot"]).read_bytes()
    if hashlib.sha256(registry_raw).hexdigest() != plan["registry_sha256"]:
        raise ValueError("Exposure registry differs from the pre-screen snapshot")
    candidates = select(args.public_inputs.read_bytes(), plan, json.loads(registry_raw))
    report = {
        "scope": "Public-statement screening pool; not selected experiments or confirmation data",
        "plan_sha256": hashlib.sha256(plan_path.read_bytes()).hexdigest(),
        "selection_source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "candidates": candidates,
        "gold_read": False, "model_runs": 0,
    }
    destination = ROOT / "reports/public_task_candidates_v01.json"
    content = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if destination.exists() and destination.read_text() != content:
        raise ValueError("Refusing to overwrite a different screening pool")
    destination.write_text(content)
    print(json.dumps({"candidates": len(candidates), "report": str(destination)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
