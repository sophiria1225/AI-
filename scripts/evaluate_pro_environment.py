"""Calibrate a V2 verifier in fresh containers without displaying private inputs."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import datetime
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import tarfile
import time
import urllib.request

from prepare_pro_environment import ROOT, read, require_p3_complete, sha, validate_image

PRIVATE_FILES = (
    "tests/test.sh", "tests/run_script.sh", "tests/parser.py",
    "tests/config.json", "tests/test_patch.patch", "solution/gold_patch.diff",
)
MAX_FILE_BYTES = 20 * 1024**2
MAX_LOG_BYTES = 100 * 1024**2


def validate_private_paths(paths):
    if tuple(paths) != PRIVATE_FILES:
        raise ValueError("Private verifier file allowlist differs from the fixed contract")
    for path in paths:
        parsed = PurePosixPath(path)
        if parsed.is_absolute() or ".." in parsed.parts:
            raise ValueError("Unsafe archive member path")


def private_bundle(storage, plan):
    validate_private_paths(plan["evaluation_isolation"]["private_files"])
    if not re.fullmatch(r"[0-9a-f]{40}", plan["official_code_revision"]):
        raise ValueError("Invalid official source revision")
    if not re.fullmatch(r"[A-Za-z0-9_-]+", plan["instance_id"]):
        raise ValueError("Invalid task ID")
    target = storage / "private_eval/pro_v2_control" / plan["official_code_revision"] / plan["instance_id"]
    manifest_path = target / "manifest.json"
    if manifest_path.exists():
        manifest = read(manifest_path)
        if manifest["code_revision"] != plan["official_code_revision"] or manifest["task"] != plan["instance_id"]:
            raise ValueError("Existing private verifier belongs to another task")
        if [f["path"] for f in manifest["files"]] != list(PRIVATE_FILES):
            raise ValueError("Existing private verifier has an unexpected file set")
        if any(sha(target / f["path"]) != f["sha256"] for f in manifest["files"]):
            raise ValueError("Private verifier file changed")
        return target, manifest
    target.mkdir(parents=True, exist_ok=False)
    revision = plan["official_code_revision"]
    result = subprocess.run(
        ["gh", "api", "--method", "GET",
         f"repos/scaleapi/SWE-bench_Pro-os/git/trees/{revision}?recursive=1"],
        capture_output=True, timeout=60, check=True,
    )
    (target / "source_tree.json").write_bytes(result.stdout)
    tree = json.loads(result.stdout)
    if tree.get("truncated"):
        raise ValueError("Official source tree was truncated")
    entries = {f["path"]: f for f in tree["tree"] if f["type"] == "blob"}

    def fetch(relative):
        path = f"v2/tasks/{plan['instance_id']}/{relative}"
        entry = entries[path]
        if entry.get("size", MAX_FILE_BYTES + 1) > MAX_FILE_BYTES:
            raise ValueError("Private input exceeds the retained-file limit")
        url = f"https://raw.githubusercontent.com/scaleapi/SWE-bench_Pro-os/{revision}/{path}"
        with urllib.request.urlopen(url, timeout=60) as response:
            raw = response.read(MAX_FILE_BYTES + 1)
        if len(raw) > MAX_FILE_BYTES:
            raise ValueError("Private input exceeds the retained-file limit")
        blob = hashlib.sha1(f"blob {len(raw)}\0".encode() + raw).hexdigest()
        if blob != entry["sha"]:
            raise ValueError("Private input differs from the versioned Git blob")
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("xb") as output:
            output.write(raw)
        return {"path": relative, "bytes": len(raw),
                "git_blob_sha": blob, "sha256": hashlib.sha256(raw).hexdigest()}

    with ThreadPoolExecutor(max_workers=4) as workers:
        files = list(workers.map(fetch, PRIVATE_FILES))
    manifest = {"task": plan["instance_id"], "code_revision": revision,
                "source_tree_sha256": hashlib.sha256(result.stdout).hexdigest(),
                "files": files, "private_contents_displayed": False}
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    return target, manifest


def make_archive(bundle, plan, phase, repository_path):
    if phase not in ("negative_control", "reference_control"):
        raise ValueError("Unknown verifier phase")
    if repository_path not in ("/app", "/testbed"):
        raise ValueError("Unexpected repository location")
    if not re.fullmatch(r"[0-9a-f]{40}", plan["base_commit"]):
        raise ValueError("Invalid base commit")
    script = (
        "set -eu\n"
        f"cd {repository_path}\n"
        f"test \"$(git rev-parse HEAD)\" = '{plan['base_commit']}'\n"
        "mkdir -p /logs/verifier\n"
    )
    if phase == "reference_control":
        script += "git apply --check /solution/gold_patch.diff\ngit apply /solution/gold_patch.diff\n"
    script += "exec bash /tests/test.sh\n"
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as archive:
        directories = ["tests", "research", "logs", "logs/verifier"]
        if phase == "reference_control":
            directories.append("solution")
        for directory in directories:
            info = tarfile.TarInfo(directory)
            info.type, info.mode = tarfile.DIRTYPE, 0o755
            archive.addfile(info)
        entries = [(name, (bundle / name).read_bytes()) for name in PRIVATE_FILES
                   if phase == "reference_control" or not name.startswith("solution/")]
        entries.append(("research/run.sh", script.encode()))
        for name, raw in entries:
            # Entries are constructed from the constant allowlist and our own script.
            info = tarfile.TarInfo(name)
            info.size, info.uid, info.gid = len(raw), 0, 0
            info.mode = 0o755 if name.endswith((".sh", ".py")) else 0o644
            archive.addfile(info, io.BytesIO(raw))
    return buffer.getvalue()


def reward_from_archive(raw):
    if len(raw) > 1024**2:
        raise ValueError("Unexpectedly large reward archive")
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:*") as archive:
        members = archive.getmembers()
        if len(members) != 1 or not members[0].isfile() or members[0].name != "reward.txt":
            raise ValueError("Unexpected reward archive members")
        if members[0].size > 100:
            raise ValueError("Reward is not a scalar")
        text = archive.extractfile(members[0]).read().decode().strip()
    if text not in ("0", "0.0", "1", "1.0"):
        raise ValueError("Reward is missing or not binary")
    return float(text)


def save_logs(container, destination):
    total = 0
    with destination.open("xb") as output:
        for chunk in container.logs(stream=True, stdout=True, stderr=True):
            total += len(chunk)
            if total > MAX_LOG_BYTES:
                raise ValueError("Verifier logs exceed retention limit; prefix retained")
            output.write(chunk)
    return {"bytes": total, "sha256": sha(destination)}


def evaluate(client, plan, bundle, phase, repository_path, record):
    name = "harness_pro_" + phase + "_" + record.parent.name
    container = client.containers.create(
        image=plan["image"], name=name, entrypoint=[], command=["bash", "/research/run.sh"],
        user="root", network_mode="bridge", cap_drop=["ALL"],
        security_opt=["no-new-privileges:true"], mem_limit="4g", nano_cpus=1_000_000_000,
        pids_limit=256, labels={"harness_research": "pro_verifier_calibration"},
    )
    result = {"container_id": container.id, "status": "error", "reward": None,
              "sampled_peak_cgroup_memory_bytes": None, "memory_samples": 0}
    started = time.monotonic()
    try:
        container.reload()
        host = container.attrs["HostConfig"]
        if (container.attrs.get("Mounts") or host.get("Privileged") or host.get("CapAdd")
                or host["NetworkMode"] != "bridge"):
            raise ValueError("Unexpected verifier isolation")
        archive = make_archive(bundle, plan, phase, repository_path)
        if not container.put_archive("/", archive):
            raise ValueError("Could not copy verifier into its isolated container")
        container.start()
        timeout = next(p["timeout_seconds"] for p in plan["phases"] if p["id"] == phase)
        while True:
            container.reload()
            if not container.attrs["State"]["Running"]:
                break
            if time.monotonic() - started > timeout:
                container.kill()
                container.wait(timeout=30)
                result["status"] = "timeout"
                break
            stats = container.stats(stream=False)
            memory = stats.get("memory_stats", {}).get("usage")
            if isinstance(memory, int) and memory > 0:
                result["sampled_peak_cgroup_memory_bytes"] = max(
                    result["sampled_peak_cgroup_memory_bytes"] or 0, memory)
                result["memory_samples"] += 1
            result["last_sampled_cpu_total_usage_ns"] = stats.get("cpu_stats", {}).get("cpu_usage", {}).get("total_usage")
            time.sleep(2)
        container.reload()
        result["exit_code"] = container.attrs["State"]["ExitCode"]
        result["oom_killed"] = container.attrs["State"].get("OOMKilled")
        result["logs"] = save_logs(container, record / "verifier.log")
        if result["status"] == "timeout":
            return result
        if result["exit_code"] != 0 or result["oom_killed"]:
            raise ValueError("Verifier process failed; private raw log retained")
        stream, _ = container.get_archive("/logs/verifier/reward.txt")
        data = bytearray()
        for chunk in stream:
            data.extend(chunk)
            if len(data) > 1024**2:
                raise ValueError("Reward archive exceeds limit")
        result["reward"] = reward_from_archive(bytes(data))
        expected = 0.0 if phase == "negative_control" else 1.0
        result["expected_outcome_observed"] = result["reward"] == expected
        result["status"] = "completed"
    except Exception as error:
        result["error"] = repr(error)
    finally:
        result["wall_seconds"] = time.monotonic() - started
        try:
            container.remove(force=True)
            result["container_removed"] = True
        except Exception as error:
            result["status"] = "error"
            result["cleanup_error"] = repr(error)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--storage-root", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--phase", choices=["negative_control", "reference_control"], required=True)
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9_-]+", args.run_id):
        raise ValueError("Invalid run identifier")
    storage = args.storage_root.resolve()
    run = storage / "records/pro_environment" / args.run_id
    plan = read(run / "plan.json")
    preparation = read(run / "summary.json")
    if (preparation["status"] != "completed" or preparation.get("probe", {}).get("status") != "passed"
            or preparation["plan_sha256"] != sha(run / "plan.json")):
        raise ValueError("Preparation did not complete with this frozen plan")
    if sha(ROOT / "configs/pro_environment_feasibility_v01.json") != preparation["plan_sha256"]:
        raise ValueError("Source plan changed since preparation")
    if args.phase == "reference_control":
        prior = read(run / "negative_control/summary.json")
        if prior.get("status") != "completed" or prior.get("expected_outcome_observed") is not True:
            raise ValueError("Negative control has not passed")
    record = run / args.phase
    record.mkdir(exist_ok=False)
    (record / "evaluate_pro_environment.py").write_bytes(Path(__file__).read_bytes())
    result = {"started_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
              "phase": args.phase, "status": "error", "source_sha256": sha(Path(__file__)),
              "plan_sha256": preparation["plan_sha256"], "image": plan["image"],
              "model_calls": 0, "private_contents_displayed": False}
    started = time.monotonic()
    try:
        result["p3_completion"] = require_p3_complete(storage)
        import docker
        client = docker.from_env(timeout=180)
        if client.containers.list():
            raise ValueError("Another container workload is still running")
        validate_image(client.images.get(plan["image"]), plan, read(ROOT / "reports/pro_candidate_image_manifest.json"))
        bundle, manifest = private_bundle(storage, plan)
        result["private_manifest_sha256"] = sha(bundle / "manifest.json")
        result["private_file_count"] = len(manifest["files"])
        result.update(evaluate(client, plan, bundle, args.phase,
                               preparation["probe"]["repository_path"], record))
    except Exception as error:
        result["error"] = repr(error)
    finally:
        result["total_wall_seconds"] = time.monotonic() - started
        (record / "summary.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
        print(json.dumps(result, ensure_ascii=False))
    return result["status"] == "completed" and result.get("expected_outcome_observed") is True


if __name__ == "__main__":
    raise SystemExit(0 if main() else 1)
