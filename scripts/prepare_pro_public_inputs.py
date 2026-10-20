"""Download one fixed Pro file privately and project only public screening inputs."""
import argparse
from collections import Counter
import datetime
import hashlib
import json
from pathlib import Path
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
PUBLIC_COLUMNS = ("repo", "instance_id", "base_commit", "problem_statement",
                  "requirements", "interface", "repo_language", "docker_image", "version")
GENERATOR_TEXT_COLUMNS = ("problem_statement", "requirements", "interface")


def validate_plan(plan, exposure):
    if tuple(plan["public_columns"]) != PUBLIC_COLUMNS:
        raise ValueError("Public-column allowlist changed; refusing projection")
    if tuple(plan["generator_text_columns"]) != GENERATOR_TEXT_COLUMNS:
        raise ValueError("Generator-text contract changed")
    entry = next(d for d in exposure["datasets"] if d["dataset"] == plan["dataset"])
    required = set(entry["exclude_repositories_from_untouched_confirmation"])
    if not required <= set(plan["screening_excluded_repositories"]):
        raise ValueError("Screening exclusion would ignore recorded gold exposure")


def screen_projected_rows(rows, excluded):
    selected, removed, seen = [], Counter(), set()
    for row in rows:
        if set(row) != set(PUBLIC_COLUMNS):
            raise ValueError("Unexpected columns reached public projection")
        if any(not isinstance(row[key], str) for key in PUBLIC_COLUMNS):
            raise ValueError("Unexpected public field type")
        if row["instance_id"] in seen:
            raise ValueError("Duplicate task ID")
        seen.add(row["instance_id"])
        if row["version"] != "2.0.0":
            raise ValueError("Mixed dataset versions")
        if row["repo"] in excluded:
            removed[row["repo"]] += 1
        else:
            selected.append(row)
    return selected, dict(removed)


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--storage-root", type=Path, default=ROOT)
    args = parser.parse_args()
    plan_path = ROOT / "configs/pro_v2_data_source.json"
    plan = json.loads(plan_path.read_text())
    exposure_path = ROOT / "configs/benchmark_exposure_registry.json"
    exposure = json.loads(exposure_path.read_text())
    validate_plan(plan, exposure)
    target = args.storage_root / plan["private_file"]
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        partial = target.with_suffix(".parquet.partial")
        with partial.open("xb") as out, urllib.request.urlopen(plan["download_url"], timeout=60) as response:
            for chunk in iter(lambda: response.read(1024 * 1024), b""):
                out.write(chunk)
        if partial.stat().st_size != plan["size"] or sha256(partial) != plan["sha256"]:
            raise ValueError("Downloaded file failed size/SHA verification; partial retained")
        partial.rename(target)
    if target.stat().st_size != plan["size"] or sha256(target) != plan["sha256"]:
        raise ValueError("Private file no longer matches the pinned source")
    import pyarrow.parquet as pq
    # Project inside the reader, before any row becomes a Python dict.
    table = pq.read_table(target, columns=list(PUBLIC_COLUMNS))
    rows, excluded = screen_projected_rows(
        table.to_pylist(), set(plan["screening_excluded_repositories"]))
    content = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)
    public = args.storage_root / plan["public_file"]
    public.parent.mkdir(parents=True, exist_ok=True)
    if public.exists() and public.read_text() != content:
        raise ValueError("Refusing to overwrite different public screening inputs")
    public.write_text(content)
    report = {
        "prepared_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "scope": "Public screening pool, not a full official evaluation split",
        "dataset_revision": plan["revision"],
        "plan_sha256": sha256(plan_path),
        "exposure_registry_sha256": sha256(exposure_path),
        "script_sha256": sha256(Path(__file__)),
        "private_file_sha256": sha256(target),
        "private_file_bytes": target.stat().st_size,
        "source_rows": table.num_rows, "screening_rows": len(rows),
        "excluded_rows_by_repository": excluded,
        "screening_repository_counts": dict(Counter(row["repo"] for row in rows)),
        "public_columns": list(PUBLIC_COLUMNS),
        "generator_text_columns": list(GENERATOR_TEXT_COLUMNS),
        "public_file": plan["public_file"], "public_file_sha256": sha256(public),
        "public_file_bytes": public.stat().st_size,
        "private_values_displayed": False, "model_calls": 0, "images_downloaded": 0,
    }
    (ROOT / "reports/pro_v2_public_projection.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({k: report[k] for k in [
        "source_rows", "screening_rows", "excluded_rows_by_repository",
        "screening_repository_counts", "private_file_bytes", "public_file_bytes"]}))


if __name__ == "__main__":
    main()
