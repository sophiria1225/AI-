"""Freeze a small, reproducible Pro public-review pool before reading task text."""
import argparse
import hashlib
import json
from pathlib import Path

from prepare_pro_public_inputs import PUBLIC_COLUMNS, GENERATOR_TEXT_COLUMNS

ROOT = Path(__file__).resolve().parents[1]


def digest(data):
    return hashlib.sha256(data).hexdigest()


def rank(plan, kind, identifier):
    return digest(("\0".join((plan["seed"], plan["dataset_revision"], kind, identifier))).encode())


def select(raw, plan, exposure):
    if digest(raw) != plan["public_inputs_sha256"]:
        raise ValueError("Public input file differs from the fixed plan")
    entry = next(d for d in exposure["datasets"] if d["dataset"] == plan["dataset"])
    excluded = set(entry["exclude_repositories_from_untouched_confirmation"])
    rows = [json.loads(line) for line in raw.decode().splitlines()]
    if any(set(row) != set(PUBLIC_COLUMNS) for row in rows):
        raise ValueError("Input columns must match the public-only allowlist")
    if any(any(not isinstance(row[key], str) for key in PUBLIC_COLUMNS) for row in rows):
        raise ValueError("Unexpected public field type")
    if any(row["repo"] in excluded for row in rows):
        raise ValueError("Recorded exposed repository reached the screening input")
    if any(row["version"] != "2.0.0" for row in rows):
        raise ValueError("Mixed dataset versions")
    if len({row["instance_id"] for row in rows}) != len(rows):
        raise ValueError("Duplicate task IDs")
    if len(rows) != plan["expected_rows"]:
        raise ValueError("Unexpected number of source rows")
    repositories = sorted({row["repo"] for row in rows}, key=lambda r: rank(plan, "repo", r))
    if len(repositories) != plan["expected_repositories"]:
        raise ValueError("Unexpected number of repositories")
    count, per_repository = plan["repository_count"], plan["per_repository"]
    if type(count) is not int or not 0 < count < len(repositories):
        raise ValueError("Keep at least one repository outside this bounded review")
    if type(per_repository) is not int or per_repository < 1:
        raise ValueError("Invalid per-repository count")
    selected_repositories = repositories[:count]
    candidates = []
    for repo in selected_repositories:
        ranked = sorted((r for r in rows if r["repo"] == repo),
                        key=lambda r: rank(plan, "task", r["instance_id"]))
        if len(ranked) < per_repository:
            raise ValueError("Not enough tasks to fill the frozen pool")
        for row in ranked[:per_repository]:
            public_text = {k: row[k] for k in GENERATOR_TEXT_COLUMNS}
            candidates.append({
                "repo": repo, "instance_id": row["instance_id"],
                "base_commit": row["base_commit"], "repo_language": row["repo_language"],
                "rank_sha256": rank(plan, "task", row["instance_id"]),
                "public_text_sha256": digest(json.dumps(
                    public_text, ensure_ascii=False, sort_keys=True).encode()),
                "role": "development_public_review_only",
            })
    return {
        "repository_order": [{"repo": repo, "rank_sha256": rank(plan, "repo", repo)}
                             for repo in repositories],
        "review_repositories": selected_repositories,
        "repositories_not_reviewed_in_this_plan": repositories[count:],
        "candidates": candidates,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--public-inputs", type=Path, required=True)
    args = parser.parse_args()
    plan_path = ROOT / "configs/pro_public_task_screen_v01.json"
    plan = json.loads(plan_path.read_text())
    exposure_raw = (ROOT / plan["exposure_registry"]).read_bytes()
    if digest(exposure_raw) != plan["exposure_registry_sha256"]:
        raise ValueError("Exposure registry changed since the plan was frozen")
    result = select(args.public_inputs.read_bytes(), plan, json.loads(exposure_raw))
    report = {
        "scope": "Bounded public review, not a model experiment or confirmation split",
        "plan_sha256": digest(plan_path.read_bytes()),
        "selection_source_sha256": digest(Path(__file__).read_bytes()),
        **result,
        "model_runs": 0,
        "selection_uses_gold_or_model_results": False,
    }
    target = ROOT / "reports/pro_public_task_candidates_v01.json"
    content = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if target.exists() and target.read_text() != content:
        raise ValueError("Refusing to overwrite a different frozen candidate pool")
    target.write_text(content)
    print(json.dumps({
        "candidates": len(result["candidates"]),
        "review_repositories": result["review_repositories"],
        "repositories_not_reviewed_in_this_plan": result["repositories_not_reviewed_in_this_plan"],
    }))


if __name__ == "__main__":
    main()
