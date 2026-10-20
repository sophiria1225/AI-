"""Offline official evaluation; raw details remain local, never sent to a model."""
import argparse
import hashlib
import json
import os
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--appworld-root", type=Path, required=True)
    parser.add_argument("--trial", type=Path, required=True)
    args = parser.parse_args()
    os.environ["APPWORLD_ROOT"] = str(args.appworld_root.resolve())
    summary_path = args.trial / "summary.json"
    summary = json.loads(summary_path.read_text())
    if (args.trial / "evaluation.json").exists():
        raise RuntimeError("evaluation already frozen")
    if summary["evaluation"] != "not_run" or not summary["finished_at"]:
        raise RuntimeError("execution is not frozen")
    db_root = args.appworld_root / "experiments/outputs" / summary["run_id"] / summary["task_id"] / "dbs"
    dbs = {str(p.relative_to(db_root)): hashlib.sha256(p.read_bytes()).hexdigest()
           for p in sorted(db_root.rglob("*")) if p.is_file()}
    if not dbs:
        raise RuntimeError("no frozen output database")
    from appworld.evaluator import evaluate_task
    result = evaluate_task(task_id=summary["task_id"], experiment_name=summary["run_id"],
                           suppress_errors=True, save_report=False)
    (args.trial / "evaluation_private.json").write_text(
        json.dumps(result.to_dict(), ensure_ascii=False, indent=2) + "\n")
    public = {"run_id": summary["run_id"], "task_id": summary["task_id"],
              "official_success": bool(result.success),
              "pass_count": result.pass_count, "fail_count": result.fail_count,
              "execution_summary_sha256": hashlib.sha256(summary_path.read_bytes()).hexdigest(),
              "frozen_database_hashes": dbs,
              "evaluation_returned_to_model": False}
    (args.trial / "evaluation.json").write_text(
        json.dumps(public, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({k: v for k, v in public.items() if k != "frozen_database_hashes"}))


if __name__ == "__main__":
    main()
