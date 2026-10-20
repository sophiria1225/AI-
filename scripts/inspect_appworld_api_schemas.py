"""Read public API schema files and count model input; never load task or answers."""
import argparse
import copy
import datetime
import hashlib
import json
from pathlib import Path
import urllib.request

from local_llama import count_input
from model_provenance import check_live_model


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_public_tools(data_root):
    tools, sources, rows = [], {}, []
    for path in sorted((data_root / "api_docs/function_calling").glob("*.json")):
        if path.stem == "admin":
            raise ValueError("admin is not a public tool collection")
        standard_path = data_root / "api_docs/standard" / path.name
        standard = json.loads(standard_path.read_text())
        raw = json.loads(path.read_text())
        group = []
        for item in raw:
            item = copy.deepcopy(item)
            item.pop("canary_string", None)
            name = item["function"]["name"]
            app, api = name.split("__")
            if app != path.stem or api not in standard:
                raise ValueError("tool is outside public standard documentation")
            group.append(item)
        sources[str(path.relative_to(data_root))] = digest(path)
        sources[str(standard_path.relative_to(data_root))] = digest(standard_path)
        rows.append({
            "app": path.stem, "tools": len(group),
            "compact_json_bytes": len(json.dumps(group, ensure_ascii=False).encode()),
            "tools_with_required_field": sum(
                "required" in t["function"]["parameters"] for t in group),
        })
        tools += group
    names = [t["function"]["name"] for t in tools]
    if not tools or len(names) != len(set(names)):
        raise ValueError("empty or duplicated public tool set")
    return tools, sources, rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--storage-root", type=Path, required=True)
    parser.add_argument("--model-plan", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    tools, sources, rows = load_public_tools(args.data_root)
    plan = json.loads(args.model_plan.read_text())
    runtime = json.loads((args.storage_root / ".runtime/model_server.json").read_text())
    with urllib.request.urlopen(plan["model"]["base_url"] + "/props", timeout=10) as response:
        props = json.load(response)
    check_live_model(plan["model_selection"], runtime, props, root=args.storage_root,
                     expected_ctx=plan["model"]["num_ctx"], expected_cache=("q8_0", "q8_0"))
    config = dict(plan["model"], seed=plan["seed"], temperature=plan["agent_temperature"],
                  num_predict=plan["max_output_tokens"])
    # A neutral header, no task instruction, account, evaluator or DB content.
    messages = [{"role": "system", "content": "Use documented APIs to complete a task."},
                {"role": "user", "content": "Inspect the available API tools."}]
    all_count = count_input(config, messages, tools)
    for row in rows:
        subset = [t for t in tools if t["function"]["name"].startswith(row["app"] + "__")]
        row["input_tokens_with_header"] = count_input(config, messages, subset)["input_tokens"]
    output = {
        "checked_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "schema_tools": len(tools), "groups": rows,
        "all_tools_input_tokens": all_count["input_tokens"],
        "context_limit": config["num_ctx"], "output_reservation": config["num_predict"],
        "all_tools_fit_before_task_or_history": (
            all_count["input_tokens"] + config["num_predict"] <= config["num_ctx"]),
        "inference_calls": 0, "task_executions": 0, "answers_loaded": False,
        "counting_calls": 1 + len(rows),
        "model": {k: runtime[k] for k in (
            "model_revision", "model_alias", "quantization", "ctx_size", "cache_type_k", "cache_type_v")},
        "runtime_commit": runtime["runtime"]["commit"],
        "model_plan_sha256": digest(args.model_plan),
        "script_sha256": digest(Path(__file__)),
        "source_hashes": sources,
        "scope": "Public schemas and tokenizer only. No agent quality or reproduction claim.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({k: v for k, v in output.items() if k not in ("groups", "source_hashes")}))


if __name__ == "__main__":
    main()
