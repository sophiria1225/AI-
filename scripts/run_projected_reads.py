"""P38: bounded three-arm mechanism-use check on one declared development task."""
import argparse
import datetime
import json
from pathlib import Path
import signal
import subprocess
import sys
import time

from analyze_handoff_factors import trial_row
from appworld_native_tools import NativeCatalog
from code_agent_interface import CODE_TOOLS
from field_read_contract import verify_public_implementation
from handoff_factors import replay_environment
from later_handoff_sources import prepare_later_sources
from local_llama import count_input
from persistent_api_python import PersistentApiPython
from projected_read_runtime import ARMS, ProjectedReadRuntime, make_conversation
from recorded_python_replay import replay_programs
from run_context_comparison import Bridge, write_json
from run_handoff_factors import ROOT, read, sha, run_branch
from run_output_views import model_ready


def sources(storage, root):
    prior, source_plan, tools, schemas, prepared = prepare_later_sources(storage, root)
    plan = read(root / "configs/P38_projected_reads_v01.json")
    if (plan["phase"] != "P38" or plan["arms"] != list(ARMS)
            or plan["source_runs"] != ["P29_04_CODE"]):
        raise ValueError("outside the projected-read mechanism check")
    for key in ("max_calls", "max_total_tokens", "max_wall_seconds", "max_setup_seconds",
                "boundary_after_model_calls", "recent_complete_turns"):
        if prior[key] != plan[key]: raise ValueError("budget or boundary changed")
    selected = [item for item in prepared if item["source_run"] in plan["source_runs"]]
    if len(selected) != 1: raise ValueError("unexpected source task count")
    if not read(root / "reports/P37_field_contract.json")["all_twelve_reviewed"]:
        raise ValueError("P37 not closed")
    return plan, source_plan, tools, schemas, selected[0]


def frozen_hashes(root):
    paths = list((root / "scripts").glob("*.py"))
    paths += [root / p for p in ("configs/P38_projected_reads_v01.json",
              "configs/P29_stateful_code_v01.json", "configs/python_export_image_v01.json",
              "docs/experiments/P38_projected_runtime.md", "reports/P37_field_contract.json",
              "tests/test_projected_read_runtime.py")]
    return {str(p.relative_to(root)): sha(p) for p in sorted(paths)}


def check_transport(storage, root, output, verified):
    # This is an explicit synthetic integration test. It never calls AppWorld or
    # uses task IDs, task values, labels, or an evaluator.
    sys.path.insert(0, str(root / "tests"))
    from test_projected_read_runtime import FixtureBridge, catalog
    from container_api_python import ApiChannel
    code = '''library = call_api("spotify", "show_song_library", access_token="fixture")
print(read_fields("spotify", "show_song", ["title", "artists"], song_id=7))
'''
    rows = []
    for mode in ("none", "exact", "contract"):
        folder = output / ("transport_" + mode); folder.mkdir()
        session = PersistentApiPython(storage, folder / "python_session")
        c = catalog(); backend = FixtureBridge()
        runtime = ProjectedReadRuntime(mode, execution_scope="fixture", verified_contract=verified)
        try:
            runtime.install(session, storage, folder / "install", c)
            channel = ApiChannel(c, backend, 10)
            result = runtime.program(session)(code, [], channel, storage_root=storage,
                                               record_dir=folder / "run", timeout=30)
            expected = 1 if mode == "contract" else 2
            if (result["status"] != "ok" or result["api_requests"] != expected
                    or len(backend.calls) != expected or len(channel.rows) != 2):
                raise ValueError("synthetic transport/accounting mismatch")
            rows.append({"mode": mode, "fixture_dispatches": expected,
                         "stdout_sha256": __import__("hashlib").sha256(result["stdout"].encode()).hexdigest(),
                         "status": result["status"]})
        finally:
            session.close()
            if rows and rows[-1]["mode"] == mode:
                rows[-1]["container_removed"] = session.state["container_removed"]
    if len({row["stdout_sha256"] for row in rows}) != 1:
        raise ValueError("projection output differs between modes")
    return rows


def preflight(storage, root):
    plan, source_plan, tools, schemas, item = sources(storage, root)
    identity = model_ready(storage, source_plan)
    verified = verify_public_implementation(storage / ".runtime/appworld/venv/lib/python3.12/site-packages/appworld/apps/spotify")
    output = storage / "records/context_pilot/P38_preflight_v01"
    target = root / "reports/P38_prefix_checks.json"
    if output.exists() or target.exists(): raise FileExistsError("preserve preflight")
    output.mkdir(); started = time.monotonic()
    transports = check_transport(storage, root, output, verified)
    rows = []
    appworld = storage / ".runtime/appworld/r18_probe_01"
    prefix = item["prefix"]; task = item["task_id"]
    for arm in ARMS:
        rid = "P38_PREFIX_V01_" + arm.upper()
        out = output / rid; out.mkdir()
        world = appworld / "experiments/outputs" / rid
        if world.exists(): raise FileExistsError("preserve preflight world")
        bridge = session = None; at = time.monotonic()
        row = {"arm": arm, "status": "not_started", "environment": {}}
        try:
            bridge = Bridge(storage / ".runtime/appworld/venv/bin/python", appworld, out)
            init = bridge.request({"op": "init", "task_id": task, "experiment": rid, "seed": source_plan["seed"]})
            if not init["ok"] or init["result"] != prefix["public_task"] or init["result"]["ground_truth_loaded"]:
                raise ValueError("initial public state differs")
            c = NativeCatalog(tools)
            replay_environment(prefix, c, bridge, world / "tasks" / task / "dbs",
                               deadline=at + plan["max_setup_seconds"], clock=time.monotonic,
                               accounting=row["environment"])
            session = PersistentApiPython(storage, out / "python_session")
            replayed = replay_programs(item["programs"], schemas, session, out / "prefix_programs", storage)
            if len(replayed) != len(item["programs"]) or not all(r["observable_prefix_matches"] for r in replayed):
                raise ValueError("Python prefix differs")
            runtime = ProjectedReadRuntime(arm.removesuffix("_keep"), execution_scope=rid, verified_contract=verified)
            runtime.seed(prefix["events"], prefix["spans"])
            runtime.install(session, storage, out / "helper", c)
            messages, _ = make_conversation(prefix).for_model(source_plan["observation_page_characters"])
            cfg = {**source_plan["model"], "temperature": source_plan["agent_temperature"],
                   "seed": source_plan["seed"] + 8, "num_predict": source_plan["max_output_tokens"]}
            counted = count_input(cfg, messages, CODE_TOOLS)
            if counted["input_tokens"] + cfg["num_predict"] > min(cfg["num_ctx"], plan["max_total_tokens"]):
                raise ValueError("initial input does not fit")
            write_json(out / "input_private.json", messages)
            row.update(status="matched_observable_prefix", replayed_programs=len(replayed),
                       input_tokens=counted["input_tokens"], input_sha256=sha(out / "input_private.json"),
                       helper=runtime.installation)
        except Exception as error:
            row.update(status="failed", error_type=type(error).__name__)
            (out / "error_private.txt").write_text(str(error))
        finally:
            for resource in (session, bridge):
                if resource:
                    try: resource.close()
                    except Exception as error: row.update(status="cleanup_error", error_type=type(error).__name__)
            row["container_removed"] = session.state["container_removed"] if session else None
            row["wall_seconds"] = time.monotonic() - at
            rows.append(row); write_json(out / "summary.json", row)
    matched = all(r["status"] == "matched_observable_prefix" for r in rows)
    result = {"phase": "P38_preflight", "rows": rows, "synthetic_transport": transports,
              "all_three_attempted": len(rows) == 3, "all_observable_prefixes_match": matched,
              "identical_initial_inputs": matched and len({r["input_sha256"] for r in rows}) == 1,
              "source_hashes": frozen_hashes(root), "boundary_sha256": item["boundary_manifest_sha256"],
              "model_identity": identity, "model_calls": 0, "evaluator_invocations": 0,
              "setup_api_requests": sum(r["environment"].get("api_requests", 0) for r in rows),
              "input_count_requests": sum("input_tokens" in r for r in rows),
              "wall_seconds": time.monotonic() - started}
    write_json(output / "summary.json", result); write_json(target, result)
    print(json.dumps({k: v for k, v in result.items() if k not in ("source_hashes", "rows", "model_identity")}))
    return 0 if matched and result["identical_initial_inputs"] else 1


def activate(root):
    result = read(root / "reports/P38_prefix_checks.json")
    if (not result["all_three_attempted"] or not result["all_observable_prefixes_match"]
            or not result["identical_initial_inputs"] or result["source_hashes"] != frozen_hashes(root)):
        raise ValueError("preflight has not passed for current sources")
    target = root / "reports/P38_activation_v01.json"
    if target.exists(): raise FileExistsError("preserve activation")
    write_json(target, {"source_hashes": frozen_hashes(root), "preflight_sha256": sha(root / "reports/P38_prefix_checks.json"),
                       "boundary_sha256": result["boundary_sha256"], "all_three_frozen_before_inference": True})


def run(storage, root):
    plan, source_plan, tools, schemas, item = sources(storage, root)
    frozen = read(root / "reports/P38_activation_v01.json")
    if (frozen["source_hashes"] != frozen_hashes(root)
            or frozen["preflight_sha256"] != sha(root / "reports/P38_prefix_checks.json")
            or frozen["boundary_sha256"] != item["boundary_manifest_sha256"]):
        raise ValueError("frozen check changed")
    identity = model_ready(storage, source_plan)
    output = storage / "records/context_pilot" / plan["batch_id"]
    output.mkdir(exist_ok=False)
    write_json(output / "plan.json", plan); write_json(output / "activation.json", frozen)
    status = {"phase": "P38", "status": "running", "active": None, "completed": [], "rows": [],
              "model_identity": identity, "started_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
              "git_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()}
    def save():
        status["updated_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        write_json(output / "status.json", status)
    for arm in ARMS:
        rid = "P38_04_" + arm.upper(); status["active"] = rid; save()
        summary = run_branch(storage, root, plan, source_plan, tools, schemas, item, arm, rid)
        if summary["setup"]["status"] != "matched_observable_prefix":
            status.update(status="stopped_setup_mismatch", active=None); save(); return 1
        evaluated = subprocess.run([str(storage / ".runtime/appworld/venv/bin/python"),
                       str(root / "scripts/evaluate_context_trial.py"), "--appworld-root",
                       str(storage / ".runtime/appworld/r18_probe_01"), "--trial",
                       str(storage / "records/context_pilot" / rid)], capture_output=True, text=True, timeout=180)
        (output / (rid + "_evaluation.log")).write_text(evaluated.stdout + evaluated.stderr)
        if evaluated.returncode:
            status.update(status="stopped_evaluation_error", active=None); save(); return 1
        row = trial_row(storage / "records/context_pilot" / rid, source_plan, item["source_run"])
        row["projected_reads"] = summary.get("projected_reads")
        status["rows"].append(row); status["completed"].append(rid); save()
        print(json.dumps({k: row[k] for k in ("run_id", "success", "stop_reason", "model_calls",
                                             "known_total_tokens", "api_requests", "projected_reads")}), flush=True)
    status.update(status="complete", active=None, finished_at=datetime.datetime.now(datetime.timezone.utc).isoformat()); save()
    write_json(root / "reports/P38_comparison.json", {"phase": "P38", "rows": status["rows"],
               "all_three_reviewed": True, "independent_tasks": 1, "reserved_scenarios_read": 0,
               "novel_method_claim": False, "general_quality_preservation_claim": False})
    return 0


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--storage-root", type=Path, required=True)
    p.add_argument("--repo-root", type=Path, default=ROOT)
    p.add_argument("--preflight", action="store_true"); p.add_argument("--activate", action="store_true")
    a = p.parse_args()
    def timeout(*_): raise TimeoutError("bounded local inference timeout")
    signal.signal(signal.SIGALRM, timeout)
    if a.preflight: raise SystemExit(preflight(a.storage_root, a.repo_root))
    if a.activate: activate(a.repo_root)
    else: raise SystemExit(run(a.storage_root, a.repo_root))
