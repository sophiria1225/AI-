"""Public-observation memory baselines, not a new research method.

The FOCUS adaptation follows arXiv:2609.37590v1 §4 and the dual-objective
draft in Appendix A.9. Native function outputs replace the paper's text
parser. Retention uses three citation sets plus the union of rescued spans.
"""
import json
import math


def function(name, description, properties, required):
    return {"type": "function", "function": {
        "name": name, "description": description,
        "parameters": {"type": "object", "properties": properties,
                       "required": required, "additionalProperties": False}}}


STR = {"type": "string"}
IDS = {"type": "array", "items": STR, "uniqueItems": True}
AGENT_TOOLS = [
    function("appworld_api", "Call a documented API in the simulated task world.",
             {"app": STR, "api": STR,
              "args": {"type": "object", "additionalProperties": True}},
             ["app", "api", "args"]),
    function("read_span", "Read one earlier observation/action span by its ID. "
             "Use offset to page through a long span; this does not repeat an API action.",
             {"span_id": STR, "offset": {"type": "integer", "minimum": 0}},
             ["span_id"]),
]
FOCUS_TOOL = function(
    "submit_selection", "Submit a possible continuation and its historical dependencies.",
    {"steps": {"type": "array", "items": {
        "type": "object", "properties": {"plan": STR, "depends_on": IDS},
        "required": ["plan", "depends_on"], "additionalProperties": False}},
     "rescued": IDS, "rescue_reason": STR}, ["steps", "rescued", "rescue_reason"])
LEDGER_TOOL = function(
    "submit_ledger", "Record observed targets, conditions, progress and unresolved scope.",
    {"items": {"type": "array", "items": {
        "type": "object", "properties": {
            "key": STR, "requirement": STR, "status": {
                "type": "string", "enum": ["pending", "done", "uncertain", "excluded"]},
            "source_ids": IDS},
        "required": ["key", "requirement", "status", "source_ids"],
        "additionalProperties": False}},
     "constraints": {"type": "array", "items": STR},
     "unresolved": {"type": "array", "items": STR}},
    ["items", "constraints", "unresolved"])

AGENT_PROMPT = """Complete the user's task in the simulated AppWorld using documented APIs.
Use appworld_api to look up API documentation and then call APIs. All accounts and
operations belong to this simulation. Do not invent API parameters or entity IDs.
When a response is paginated, check remaining pages as needed. Respect all task
conditions and avoid unrelated changes. API errors are observations, not successes.
Call supervisor.complete_task only after the requested work is complete; include
an answer when the task asks for one. An ordinary final message does not finish
the task. You can read earlier spans by ID, including spans removed from working
memory. Re-reading a span does not re-run its action. Memory notes are fallible.
Choose one tool call per response. The supplied task and public API observations
are the only evidence available; no evaluator is accessible."""

FOCUS_PROMPT = """Plan the remaining work from the task and visible interaction spans.
Submit a short possible continuation using submit_selection. For each step, cite
the exact span IDs needed to make its decisions. Then examine every span not
cited in your plan: rescue observations whose loss could repeat a failed action,
break a condition, or lose state needed for correct continuation. Cite rescued
IDs separately and explain the risk briefly. Do not execute tools or claim that
proposed future work has already happened."""

LEDGER_PROMPT = """Update a compact working ledger from the task, previous ledger and
new visible interaction spans. Use submit_ledger. Track individual observed
targets and their identifiers, required actions, pending/done/uncertain/excluded
status, and source span IDs. Preserve conditions, already completed actions and
uncertainty about whether enumeration is complete. Store authentication or API
facts needed for continuation in constraints with source IDs when available.
Do not infer that an unseen target does not exist. A previous ledger can be wrong;
revise it only from supplied observations. This is a memory summary, not an
evaluator, and no correct target list is provided."""


def compact(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def parse_submission(message, expected):
    calls = message.get("tool_calls") or []
    if len(calls) != 1 or calls[0].get("function", {}).get("name") != expected:
        raise ValueError("exactly one expected function call required")
    args = json.loads(calls[0]["function"]["arguments"])
    if not isinstance(args, dict):
        raise ValueError("function arguments must be an object")
    return args


def checked_ids(values, allowed):
    if (not isinstance(values, list) or any(type(x) is not str for x in values)
            or len(values) != len(set(values)) or not set(values) <= set(allowed)):
        raise ValueError("invalid, duplicated or unavailable source ID")
    return set(values)


def select_focus(drafts, available, threshold=0.3):
    if not drafts or not 0 < threshold <= 1:
        raise ValueError("drafts and a valid retention threshold are required")
    scores = dict.fromkeys(available, 0)
    rescued = set()
    for draft in drafts:
        if not isinstance(draft.get("steps"), list):
            raise ValueError("missing plan steps")
        cited = set()
        for step in draft["steps"]:
            if not isinstance(step.get("plan"), str):
                raise ValueError("missing plan")
            cited |= checked_ids(step.get("depends_on"), available)
        for span_id in cited:
            scores[span_id] += 1
        rescued |= checked_ids(draft.get("rescued"), available)
    minimum = math.ceil(threshold * len(drafts))
    keep = {s for s, count in scores.items() if count >= minimum} | rescued
    return [s for s in available if s in keep], {"citation_counts": scores,
                                               "rescued": sorted(rescued)}


def validate_ledger(value, allowed):
    if not isinstance(value.get("items"), list):
        raise ValueError("missing ledger items")
    keys = []
    for item in value["items"]:
        if not isinstance(item.get("key"), str) or not item["key"]:
            raise ValueError("ledger item requires a key")
        if not isinstance(item.get("requirement"), str):
            raise ValueError("ledger item requires a requirement")
        if item.get("status") not in ("pending", "done", "uncertain", "excluded"):
            raise ValueError("invalid ledger status")
        if not checked_ids(item.get("source_ids"), allowed):
            raise ValueError("a ledger entry needs visible provenance")
        keys.append(item["key"])
    if len(set(keys)) != len(keys):
        raise ValueError("duplicate ledger key")
    for field in ("constraints", "unresolved"):
        if not isinstance(value.get(field), list) or any(
                not isinstance(x, str) for x in value[field]):
            raise ValueError("invalid ledger field: " + field)
    return value


def page_span(spans, span_id, offset=0, limit=24000):
    if type(offset) is not int or offset < 0 or span_id not in spans:
        raise ValueError("invalid span page")
    text = compact(spans[span_id])
    end = min(len(text), offset + limit)
    return {"span_id": span_id, "offset": offset, "total_characters": len(text),
            "text": text[offset:end],
            "next_offset": end if end < len(text) else None}


def render_memory(spans, selected, ledger=None, page_limit=24000):
    # Archive IDs reveal no hidden outcome and are available in every arm.
    visible = []
    for key in selected:
        span = spans[key]
        visible.append(span if len(compact(span)) <= page_limit else
                       {"id": key, "first_page": page_span(spans, key, 0, page_limit)})
    result = {"available_archive_ids": list(spans),
              "visible_spans": visible}
    if ledger is not None:
        result["working_ledger"] = ledger
    return compact(result)


def validate_api_request(value, docs):
    app, api, args = (value.get(k) for k in ("app", "api", "args"))
    if app == "admin" or app not in docs or api not in docs[app]:
        raise ValueError("API is not in public task documentation")
    if not isinstance(args, dict):
        raise ValueError("API args must be an object")
    parameters = {p["name"] for p in docs[app][api]["parameters"]}
    if not set(args) <= parameters:
        raise ValueError("unknown API parameters")
    # Names must also be Python identifiers because the trusted bridge emits a
    # literal invocation. User content is passed only through repr(args).
    if any(not x.isidentifier() or x.startswith("_") for x in (app, api)):
        raise ValueError("invalid public API name")
    return app, api, args


def api_code(value, docs):
    app, api, args = validate_api_request(value, docs)
    return f"print(apis.{app}.{api}(**{args!r}))"
