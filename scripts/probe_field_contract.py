"""Fixed projected-read protocol over all closed P33 records; no live calls."""
import argparse
from collections import Counter
import copy
import hashlib
import json
from pathlib import Path
import time

from analyze_structured_reuse import decode
from diagnose_handoff_programs import require_complete
from field_read_contract import (CONTRACT_ID, SOURCE, TARGET, READ_ONLY_APIS,
                                 FieldReadCache, ReadContext, canonical, project,
                                 verify_public_implementation)

ROOT = Path(__file__).resolve().parents[1]
DEMAND = ("title", "artists")


def read(path): return json.loads(path.read_text())
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def write(path, obj): path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n")


def process(events, spans, caches, scope, revision=0, *, measure):
    counts = Counter()
    outcomes = []
    for index, event in enumerate(events):
        if not event["api_request_sent"]:
            counts["unsent_events"] += 1
            continue
        span = spans[event["span_id"]]
        api = span["action"]["name"]
        arguments = json.loads(span["action"]["arguments"])
        counts["sent_requests"] += 1
        if api not in READ_ONLY_APIS:
            revision += 1
            for cache in caches.values(): cache.invalidate()
            counts["invalidations"] += 1
            continue
        context = ReadContext(scope, str(revision), CONTRACT_ID)
        if api == TARGET and measure:
            row = {"event_index": index, "modes": {}}
            # Cache selection uses only the request and the earlier observations.
            # The current reply is exposed through fetch only when there is a miss.
            for mode, cache in caches.items():
                fetched = 0
                def fetch(name, args):
                    nonlocal fetched
                    if name != api or canonical(args) != canonical(arguments):
                        raise AssertionError("request changed")
                    fetched += 1
                    ok, value = decode(span["observation"])
                    if not ok: raise RuntimeError("recorded API error")
                    return copy.deepcopy(value)
                failure = None
                try:
                    result = cache.read_fields(api, arguments, DEMAND, context, fetch)
                    actual = ("value", canonical(result.value))
                    source = result.source
                except (KeyError, ValueError, RuntimeError) as error:
                    actual = ("error", type(error).__name__)
                    failure = type(error).__name__
                    source = "error"
                # Posthoc audit, never inserted into a cache that hit.
                try:
                    ok, value = decode(span["observation"])
                    if not ok: raise RuntimeError("recorded API error")
                    expected = ("value", canonical(project(value, DEMAND)))
                except (KeyError, ValueError, RuntimeError) as error:
                    expected = ("error", type(error).__name__)
                row["modes"][mode] = {"source": source, "backend_fetches": fetched,
                                      "projection_matches_record": actual == expected,
                                      "error_class": failure}
                counts[mode + "_backend_fetches"] += fetched
                counts[mode + "_" + source] += 1
                counts[mode + "_mismatches"] += int(actual != expected)
            counts["projected_requests"] += 1
            outcomes.append(row)
        else:
            ok, value = decode(span["observation"])
            if ok:
                for cache in caches.values(): cache.observe(api, arguments, value, context)
                if api == SOURCE: counts["source_observations"] += 1
            else:
                counts["read_errors"] += 1
    return revision, dict(counts), outcomes


def run(storage, root):
    comparison = read(root / "reports/P33_comparison.json")
    recorded = {r["run_id"]: r for r in read(root / "reports/P36_structured_reuse.json")["rows"]}
    plan = read(root / "configs/P33_output_views_v01.json")
    require_complete(comparison, read(storage / "records/context_pilot" / plan["batch_id"] / "status.json"), "P33")
    directory = storage / "records/context_pilot/P37_field_contract_v01"
    target = root / "reports/P37_field_contract.json"
    if directory.exists() or target.exists(): raise FileExistsError("preserve prior probe")
    verified = verify_public_implementation(storage / ".runtime/appworld/venv/lib/python3.12/site-packages/appworld/apps/spotify")
    files = ("scripts/field_read_contract.py", "scripts/probe_field_contract.py",
             "docs/experiments/P37_field_contract.md", "reports/P33_comparison.json",
             "reports/P36_structured_reuse.json")
    sources = {name: sha(root / name) for name in files}
    directory.mkdir()
    write(directory / "source_sha256.json", sources)
    started = time.monotonic()
    rows = []
    for cell in comparison["rows"]:
        trial = storage / "records/context_pilot" / cell["run_id"]
        for name in ("events.json", "spans.json", "source_identity.json"):
            if sha(trial / name) != cell["source_hashes"][name]: raise ValueError("closed source changed")
        for name in ("prefix_events.json", "prefix_spans.json"):
            if sha(trial / name) != recorded[cell["run_id"]]["source_sha256"][name]:
                raise ValueError("closed prefix changed")
        caches = {mode: FieldReadCache(mode, verified_contract=verified)
                  for mode in ("none", "exact", "contract")}
        revision, prefix, _ = process(read(trial / "prefix_events.json"), read(trial / "prefix_spans.json"),
                                      caches, cell["run_id"], measure=False)
        _, counts, outcomes = process(read(trial / "events.json"), read(trial / "spans.json"),
                                      caches, cell["run_id"], revision, measure=True)
        row = {key: cell[key] for key in ("run_id", "task_id", "arm")}
        row.update(prefix_counts=prefix, counts=counts, outcomes=outcomes,
                   bounded_values={mode: cache.bounds_rejected for mode, cache in caches.items()},
                   source_sha256={name: sha(trial / name) for name in
                                  ("events.json", "spans.json", "prefix_events.json", "prefix_spans.json")})
        rows.append(row)
        print(json.dumps({"run_id": row["run_id"], "counts": counts}), flush=True)
    result = {"phase": "P37_field_contract", "all_twelve_reviewed": len(rows) == 12,
              "demand_fields": list(DEMAND), "rows": rows, "source_sha256": sources,
              "public_implementation_verified": True, "contract_id": verified,
              "wall_seconds": time.monotonic() - started,
              "model_calls": 0, "live_api_requests": 0, "final_evaluator_invocations": 0,
              "reserved_scenarios_read": 0, "original_program_semantics_preserved": False,
              "end_to_end_savings_measured": False, "novel_method_claim": False,
              "limits": ["Fixed title/artists requests are a new auxiliary protocol, not original agent demand.",
                         "The original task programs, their outputs, completion and future choices were not replayed.",
                         "Unknown sent operations, including unverified GETs, invalidate all cache entries.",
                         "No writes or exogenous updates occur during the fixed audited read segments.",
                         "A cache hit is checked against the recorded reply afterwards and is not seeded with that reply.",
                         "Pinned app files do not independently certify every framework dependency or an external service."]}
    write(directory / "summary.json", result)
    write(target, result)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--storage-root", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    args = parser.parse_args()
    run(args.storage_root, args.repo_root)
