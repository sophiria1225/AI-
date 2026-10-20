"""Check declared checkpoint artifacts before controlled restore comparisons.

This does not capture a live environment, restore a container, inspect private
test contents, or certify that an adapter declared every writable location.
It is intentionally not connected to the P3/P4/P5 execution paths.
"""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re


COMPONENTS = frozenset({
    "conversations", "task_registry", "budget_ledger",
    "completion_state", "filesystem", "tool_state",
})
RUNTIME_FIELDS = frozenset({
    "model_revision", "inference_settings_sha256", "tool_image",
    "tool_config_sha256", "external_inputs_sha256",
})
BUDGET_FIELDS = frozenset({
    "remaining_tokens", "remaining_calls", "remaining_wall_milliseconds",
})


class ContractError(ValueError):
    pass


def require(condition, reason):
    if not condition:
        raise ContractError(reason)


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def sha(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def object_with_keys(value, keys, label):
    require(isinstance(value, dict) and set(value) == set(keys), label + "_fields")


def roots(value, label):
    require(isinstance(value, list) and len(value) > 0, label + "_empty")
    for entry in value:
        require(isinstance(entry, str), label + "_type")
        p = PurePosixPath(entry)
        require(p.is_absolute() and str(p) == entry and ".." not in p.parts
                and "\\" not in entry and "\0" not in entry, label + "_path")
    require(len(set(value)) == len(value), label + "_duplicate")
    return set(value)


def artifact(root, value, component):
    object_with_keys(value, {"path", "sha256"}, component)
    require(sha(value["sha256"]), component + "_invalid_hash")
    name = value["path"]
    require(isinstance(name, str) and bool(name), component + "_path")
    relative = PurePosixPath(name)
    require(not relative.is_absolute() and relative.parts
            and str(relative) == name and ".." not in relative.parts
            and "\\" not in name and "\0" not in name, component + "_path")
    path = root.joinpath(*relative.parts)
    current = root
    for part in relative.parts:
        current = current / part
        require(not current.is_symlink(), component + "_symlink")
    require(path.is_file(), component + "_missing")
    require(path.resolve().is_relative_to(root), component + "_outside_bundle")
    require(digest(path) == value["sha256"], component + "_content_mismatch")


def validate(manifest, bundle):
    """Validate declared files and compareable metadata; never infer completeness."""
    object_with_keys(manifest, {
        "schema_version", "checkpoint_id", "components", "boundary",
        "writable_roots", "captured_roots", "runtime", "remaining_budget",
        "inference_cache_policy",
    }, "manifest")
    require(type(manifest["schema_version"]) is int and manifest["schema_version"] == 1,
            "schema_version")
    require(isinstance(manifest["checkpoint_id"], str)
            and re.fullmatch(r"[a-zA-Z0-9_.-]{1,128}", manifest["checkpoint_id"]),
            "checkpoint_id")
    object_with_keys(manifest["boundary"], {
        "active_tool_operations", "pending_model_request",
        "usage_complete", "background_processes", "live_external_inputs",
    }, "boundary")
    b = manifest["boundary"]
    require(type(b["active_tool_operations"]) is int and b["active_tool_operations"] == 0,
            "tool_operation_in_flight")
    require(type(b["background_processes"]) is int and b["background_processes"] == 0,
            "background_processes_not_supported")
    require(b["pending_model_request"] is False, "model_request_in_flight")
    require(b["usage_complete"] is True, "unknown_usage")
    require(b["live_external_inputs"] is False, "unfrozen_external_input")
    writable = roots(manifest["writable_roots"], "writable_roots")
    captured = roots(manifest["captured_roots"], "captured_roots")
    require(writable == captured, "filesystem_scope_mismatch")
    require(manifest["inference_cache_policy"] == "clear_before_each_branch",
            "cache_policy_not_matched")
    object_with_keys(manifest["remaining_budget"], BUDGET_FIELDS, "budget")
    require(all(type(v) is int and v >= 0 for v in manifest["remaining_budget"].values()),
            "invalid_remaining_budget")
    object_with_keys(manifest["runtime"], RUNTIME_FIELDS, "runtime")
    for key, value in manifest["runtime"].items():
        require(isinstance(value, str) and bool(value), "runtime_" + key)
        if key.endswith("_sha256"):
            require(sha(value), "runtime_" + key)
    object_with_keys(manifest["components"], COMPONENTS, "components")
    root = Path(bundle).resolve()
    require(root.is_dir(), "bundle_missing")
    for name, entry in manifest["components"].items():
        artifact(root, entry, name)
    paths = [e["path"] for e in manifest["components"].values()]
    require(len(set(paths)) == len(paths), "duplicate_component_path")
    # Paths may differ after restoration; compare contents and semantic metadata.
    return {
        "checkpoint_id": manifest["checkpoint_id"],
        "component_sha256": {k: v["sha256"] for k, v in manifest["components"].items()},
        "writable_roots": sorted(writable),
        "runtime": dict(manifest["runtime"]),
        "remaining_budget": dict(manifest["remaining_budget"]),
        "inference_cache_policy": manifest["inference_cache_policy"],
    }


def compare_restore(original, original_bundle, restored, restored_bundle):
    left = validate(original, original_bundle)
    right = validate(restored, restored_bundle)
    differences = sorted(k for k in left if left[k] != right[k])
    require(not differences, "restore_mismatch:" + ",".join(differences))
    return {
        "declared_artifacts_match": True,
        "checkpoint_id": left["checkpoint_id"],
        "components_checked": len(COMPONENTS),
        "scope": "Declared artifacts and metadata only; live capture and replay unverified.",
        "certifies_live_environment_restoration": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--restored", type=Path)
    args = parser.parse_args()
    try:
        source = json.loads(args.manifest.read_text())
        if args.restored:
            result = compare_restore(source, args.manifest.parent,
                                     json.loads(args.restored.read_text()), args.restored.parent)
        else:
            result = validate(source, args.manifest.parent)
            result = {"declared_artifacts_valid": True,
                      "checkpoint_id": result["checkpoint_id"],
                      "certifies_live_environment_restoration": False}
    except (ContractError, OSError, json.JSONDecodeError) as exc:
        # No artifact contents or raw conversation text is emitted.
        print(json.dumps({"status": "rejected",
                          "reason": str(exc) if isinstance(exc, ContractError)
                          else type(exc).__name__}))
        raise SystemExit(1)
    print(json.dumps({"status": "ok", **result}))


if __name__ == "__main__":
    main()
