"""Prepare one pinned development image only after the frozen P3 plan completes."""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
P3_SHA = "ce33553f6b3db418a6356a0a9a0b97ce6162773866ee3e36dffa0d93cc298722"
P3_PLAN = "configs/P3_development_plan_v01.json"
GIB = 1024**3


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def completed_trials(storage, plan, expected_plan_sha):
    """A valid unresolved result is complete; missing evaluation or cost is not."""
    proof = []
    for trial in plan["trials"]:
        status_path = storage / "records/p3_plan_runs/P3_development_plan_v01" / trial["trial_id"] / "status.json"
        if not status_path.exists():
            raise ValueError(f"{trial['trial_id']}: missing execution record")
        status = read(status_path)
        if (status.get("status") != "execution_completed"
                or status.get("audit_errors") != []
                or status.get("plan_sha256") != expected_plan_sha):
            raise ValueError(f"{trial['trial_id']}: execution/audit/plan incomplete")
        run = (storage / status["run_record"]).resolve()
        if not run.is_relative_to((storage / "records/p3").resolve()):
            raise ValueError("Run record escapes the P3 directory")
        summary = read(run / "summary.json")
        if (not summary.get("container_removed") or summary.get("usage_complete") is not True
                or summary.get("finalization_error") or not summary.get("artifact_frozen_at")):
            raise ValueError(f"{trial['trial_id']}: finalization or accounting incomplete")
        evaluation = read(run / "final_evaluation_summary.json")
        if (evaluation.get("evaluation_status") != "completed"
                or evaluation.get("infra_failure") is not False
                or type(evaluation.get("resolved")) is not bool):
            raise ValueError(f"{trial['trial_id']}: independent evaluation incomplete")
        artifact = sha(run / "final.patch")
        if any(item.get("artifact_sha256") != artifact for item in (status, summary, evaluation)):
            raise ValueError(f"{trial['trial_id']}: final artifact changed")
        if summary.get("instance_id") != trial["task"] or summary.get("strategy") != trial["strategy"]:
            raise ValueError("Recorded task or strategy differs from the frozen plan")
        proof.append({"trial_id": trial["trial_id"], "run": status["run_record"],
                      "artifact_sha256": artifact, "resolved": evaluation["resolved"]})
    return proof


def require_p3_complete(storage):
    path = storage / P3_PLAN
    if sha(path) != P3_SHA:
        raise ValueError("Expected frozen P3 plan is missing or changed")
    plan = read(path)
    if [t["trial_id"] for t in plan["trials"]] != ["P3-01", "P3-02", "P3-03", "P3-04"]:
        raise ValueError("Expected all four frozen P3 trials")
    return completed_trials(storage, plan, P3_SHA)


def free_space(storage, docker_root):
    command = [str(storage / ".tools/bin/colima"), "ssh", "--profile", "harness-e0",
               "--", "sudo", "-n", "df", "-B1", "--output=avail", docker_root]
    result = subprocess.run(command, capture_output=True, text=True, timeout=30, check=True)
    available = result.stdout.strip().splitlines()[-1].strip()
    if not available.isdecimal():
        raise ValueError("Cannot establish free storage inside the research VM")
    return {"host_free_bytes": shutil.disk_usage(storage).free, "vm_free_bytes": int(available)}


def check_space(space):
    if space["host_free_bytes"] < 20 * GIB or space["vm_free_bytes"] < 15 * GIB:
        raise ValueError("Free storage is below the frozen preparation threshold")


def validate_image(image, plan, manifest):
    attrs = image.attrs
    if plan["image"] not in attrs.get("RepoDigests", []):
        raise ValueError("Pulled image does not match the pinned repository digest")
    target_digest = plan["image"].split("@", 1)[1]
    descriptor = attrs.get("Descriptor")
    if descriptor is not None and (
        descriptor.get("digest") != target_digest
        or descriptor.get("mediaType") not in (
            "application/vnd.oci.image.manifest.v1+json",
            "application/vnd.docker.distribution.manifest.v2+json",
        )
    ):
        raise ValueError("Local image descriptor differs from the pinned single-platform manifest")
    if image.id == manifest["config"]["digest"]:
        identity_kind = "configuration_digest"
    elif descriptor is not None and image.id == target_digest:
        # Observed with this engine's containerd image store. Bind the local
        # target to the immutable manifest, rather than treating its ID as a
        # configuration digest or accepting any ID with a plausible tag.
        identity_kind = "manifest_digest_with_matching_descriptor"
    else:
        raise ValueError("Image ID is neither the pinned configuration nor the verified manifest")
    if attrs.get("Architecture") != "amd64" or attrs.get("Os") != "linux":
        raise ValueError("Unexpected image platform")
    return {"local_image_id": image.id, "identity_kind": identity_kind,
            "manifest_digest": target_digest,
            "manifest_configuration_digest": manifest["config"]["digest"],
            "descriptor": descriptor}


PROBE = r'''
import json, pathlib, platform, subprocess, sys
def call(*args):
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=30)
        return {"exit_code": r.returncode, "stdout": r.stdout.strip(), "stderr": r.stderr.strip()}
    except subprocess.TimeoutExpired as e:
        def text(v):
            return v.decode(errors="replace") if isinstance(v, bytes) else (v or "")
        return {"exit_code": None, "stdout": text(e.stdout).strip(),
                "stderr": text(e.stderr).strip(), "timed_out": True}
    except OSError as e:
        return {"exit_code": None, "stdout": "", "stderr": repr(e), "process_start_failed": True}
roots = [p for p in ("/app", "/testbed") if pathlib.Path(p, ".git").exists()]
result = {"python": platform.python_version(), "machine": platform.machine(), "roots": roots}
if len(roots) == 1:
    root = roots[0]
    result["head"] = call("git", "-C", root, "rev-parse", "HEAD")
    result["status"] = call("git", "-C", root, "status", "--porcelain")
    result["refs"] = call("git", "-C", root, "for-each-ref", "--format=%(refname) %(objectname)")
    result["stash"] = call("git", "-C", root, "stash", "list")
    result["task_id_commit_probe"] = call("git", "-C", root, "cat-file", "-e", sys.argv[1] + "^{commit}")
    code = result["task_id_commit_probe"]["exit_code"]
    result["task_id_commit_present"] = (code == 0) if code in (0, 128) else None
    result["unreachable"] = call("git", "-C", root, "fsck", "--connectivity-only", "--no-reflogs", "--unreachable")
    result["private_locations_present"] = [p for p in ("/solution", "/tests/test_patch.patch", "/tests/config.json")
                                          if pathlib.Path(p).exists()]
    result["rootfs_apparent_bytes"] = call("du", "--apparent-size", "-s", "-x", "--block-size=1", "/")
print(json.dumps(result))
'''


def validate_probe(probe, plan):
    if len(probe.get("roots", [])) != 1 or probe.get("machine") != "x86_64":
        raise ValueError("Probe did not identify the intended amd64 repository")
    for key in ("head", "status", "refs", "stash", "unreachable"):
        if probe[key]["exit_code"] != 0:
            raise ValueError(f"Repository probe failed: {key}")
    if probe["head"]["stdout"] != plan["base_commit"]:
        raise ValueError("Image base commit differs from selected task")
    if probe["status"]["stdout"] or probe["stash"]["stdout"]:
        raise ValueError("Image contains unexpected changes or stashes")
    if (type(probe.get("task_id_commit_present")) is not bool
            or probe["task_id_commit_probe"]["exit_code"] not in (0, 128)):
        raise ValueError("Cannot determine whether the task commit is present")
    if probe["task_id_commit_present"] or probe["private_locations_present"]:
        raise ValueError("Potential solution/evaluator exposure in the image")
    if probe["unreachable"]["stdout"]:
        raise ValueError("Unreachable Git objects require inspection before model use")
    # A cap-dropped root cannot necessarily enumerate OS cache directories.
    # Preserve du's result as incomplete, and measure a full uncompressed
    # export through the external Docker controller without widening caps.


def measure_export(chunks, deadline, limit=16 * GIB):
    total = 0
    for chunk in chunks:
        total += len(chunk)
        if total > limit:
            raise ValueError("Root filesystem export exceeded measurement limit")
        if time.monotonic() > deadline:
            raise TimeoutError("Root filesystem export exceeded probe deadline")
    if total == 0:
        raise ValueError("Root filesystem export was empty")
    return total


def probe_image(client, plan, name, record):
    task_commit = re.search(r"-([0-9a-f]{40})(?:-|$)", plan["instance_id"]).group(1)
    container = client.containers.create(
        image=plan["image"], name=name, entrypoint=[],
        command=["python3", "-c", PROBE, task_commit], network_mode="none",
        user="root", cap_drop=["ALL"], security_opt=["no-new-privileges:true"],
        mem_limit="4g", nano_cpus=1_000_000_000, pids_limit=256,
        labels={"harness_research": "pro_environment_calibration"},
    )
    peak, samples = None, 0
    started = time.monotonic()
    runtime = {"container_id": container.id, "status": "error"}
    try:
        container.reload()
        host = container.attrs["HostConfig"]
        if (container.attrs.get("Mounts") or host.get("Privileged") or host.get("CapAdd")
                or host["NetworkMode"] != "none"):
            raise ValueError("Unexpected probe isolation")
        container.start()
        while True:
            container.reload()
            if not container.attrs["State"]["Running"]:
                break
            if time.monotonic() - started > 120:
                raise TimeoutError("Probe exceeded 120 seconds")
            stats = container.stats(stream=False)
            usage = stats.get("memory_stats", {}).get("usage")
            if isinstance(usage, int) and usage > 0:
                peak = max(peak or 0, usage)
                samples += 1
            time.sleep(1)
        raw = container.logs(stdout=True, stderr=False)
        (record / "probe.stdout.json").write_bytes(raw)
        (record / "probe.stderr.txt").write_bytes(container.logs(stdout=False, stderr=True))
        if container.attrs["State"]["ExitCode"] != 0:
            raise ValueError("Probe process failed; raw logs retained")
        probe = json.loads(raw)
        validate_probe(probe, plan)
        stream = container.export(chunk_size=1024**2)
        try:
            export_bytes = measure_export(stream, started + 120)
        finally:
            stream.close()
        size = probe["rootfs_apparent_bytes"]
        size_match = re.fullmatch(r"([1-9][0-9]*)\s+/", size.get("stdout", ""))
        visible_bytes = int(size_match[1]) if size_match else None
        complete_size = size.get("exit_code") == 0 and visible_bytes is not None
        runtime["status"] = "passed"
        return {"status": "passed", "python": probe["python"], "machine": probe["machine"],
                "repository_path": probe["roots"][0], "base_commit": probe["head"]["stdout"],
                "rootfs_visible_apparent_bytes": visible_bytes,
                "rootfs_apparent_measurement_complete": complete_size,
                "rootfs_apparent_bytes": visible_bytes if complete_size else None,
                "uncompressed_rootfs_tar_bytes": export_bytes,
                "export_note": "Stream counted and discarded; includes tar headers/padding; not physical disk allocation",
                "stdout_sha256": hashlib.sha256(raw).hexdigest(),
                "sampled_peak_cgroup_memory_bytes": peak, "memory_samples": samples,
                "wall_seconds": time.monotonic() - started,
                "scope": "Bounded history/location probes; not a proof against all possible data leakage"}
    finally:
        # Remove only the exact container created by this invocation.
        runtime.update(wall_seconds=time.monotonic() - started,
                       sampled_peak_cgroup_memory_bytes=peak, memory_samples=samples)
        try:
            container.remove(force=True)
            runtime["container_removed"] = True
        except Exception as error:
            runtime.update(status="error", cleanup_error=repr(error))
            raise
        finally:
            (record / "probe_runtime.json").write_text(json.dumps(runtime, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--storage-root", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9_-]+", args.run_id):
        raise ValueError("Invalid local run identifier")
    storage = args.storage_root.resolve()
    plan_path = ROOT / "configs/pro_environment_feasibility_v01.json"
    plan = read(plan_path)
    manifest = read(ROOT / "reports/pro_candidate_image_manifest.json")
    record = storage / "records/pro_environment" / args.run_id
    record.mkdir(parents=True, exist_ok=False)
    (record / "plan.json").write_bytes(plan_path.read_bytes())
    (record / "prepare_pro_environment.py").write_bytes(Path(__file__).read_bytes())
    result = {"started_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
              "status": "error", "plan_sha256": sha(plan_path),
              "source_sha256": sha(Path(__file__)), "image": plan["image"],
              "model_calls": 0, "reference_or_hidden_tests_read": False}
    started = time.monotonic()
    try:
        result["p3_completion"] = require_p3_complete(storage)
        import docker
        client = docker.from_env(timeout=180)
        if client.containers.list():
            raise ValueError("Another container workload is still running")
        docker_root = client.info()["DockerRootDir"]
        result["space_before"] = free_space(storage, docker_root)
        check_space(result["space_before"])
        repository, digest = plan["image"].split("@", 1)
        with (record / "pull_events.jsonl").open("x") as events:
            for event in client.api.pull(repository, tag=digest, platform="linux/amd64",
                                         stream=True, decode=True):
                events.write(json.dumps(event) + "\n")
                events.flush()
                if event.get("error"):
                    raise RuntimeError("Image pull failed; event retained")
                if time.monotonic() - started > 900:
                    raise TimeoutError("Image preparation exceeded 900 seconds")
        image = client.images.get(plan["image"])
        result["image_identity"] = validate_image(image, plan, manifest)
        result["image_id"] = image.id
        # Engine/storage implementations do not necessarily report unpacked
        # snapshot bytes here. Preserve the raw field and measure separately.
        result["docker_inspect_reported_size_bytes"] = image.attrs["Size"]
        result["space_after_pull"] = free_space(storage, docker_root)
        check_space(result["space_after_pull"])
        result["probe"] = probe_image(client, plan, "harness_pro_probe_" + args.run_id, record)
        result["space_after_probe"] = free_space(storage, docker_root)
        result["status"] = "completed"
    except Exception as error:
        result["error"] = repr(error)
    finally:
        result["wall_seconds"] = time.monotonic() - started
        (record / "summary.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
        print(json.dumps(result, ensure_ascii=False))
    return result["status"] == "completed"


if __name__ == "__main__":
    raise SystemExit(0 if main() else 1)
