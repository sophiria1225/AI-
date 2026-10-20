"""A public-schema adapter for a stronger baseline, not a research proposal."""
import copy
import json

from context_preservation import AGENT_TOOLS


class NativeCatalog:
    def __init__(self, public_tools):
        self.catalog = {}
        for tool in public_tools:
            name = tool["function"]["name"]
            parts = name.split("__")
            if (len(parts) != 2 or parts[0] == "admin"
                    or any(not p.isidentifier() or p.startswith("_") for p in parts)
                    or name in self.catalog):
                raise ValueError("invalid or duplicate public API name")
            self.catalog[name] = copy.deepcopy(tool)
        self.visible = {n for n in self.catalog
                        if n.startswith(("api_docs__", "supervisor__"))}

    def tools(self):
        return [copy.deepcopy(self.catalog[n]) for n in sorted(self.visible)] + [
            copy.deepcopy(AGENT_TOOLS[1])]

    def decode(self, function, visible=None):
        name = function.get("name")
        allowed = self.visible if visible is None else visible
        if name != "read_span" and name not in allowed:
            raise ValueError("tool is not in the supplied public schema set")
        arguments = json.loads(function["arguments"])
        if not isinstance(arguments, dict):
            raise ValueError("tool arguments must be a JSON object")
        if name == "read_span":
            if not set(arguments) <= {"span_id", "offset"}:
                raise ValueError("unknown archive parameter")
            if not isinstance(arguments.get("span_id"), str):
                raise ValueError("span_id is required")
            offset = arguments.get("offset", 0)
            if type(offset) is not int or offset < 0:
                raise ValueError("invalid archive offset")
            return {"archive": True, **arguments}
        app, api = name.split("__")
        properties = self.catalog[name]["function"]["parameters"]["properties"]
        if not set(arguments) <= set(properties):
            raise ValueError("unknown API parameter")
        # The simulated API enforces parameter types and required fields.
        # Keep the distributed official schema unchanged, including omissions.
        return {"app": app, "api": api, "args": arguments}

    def expose_requested_document(self, call):
        """Expose public schemas requested by an API or app documentation call.

        This is tool discovery, not a claim that the called operation succeeded.
        It grants no private API or external account access.
        """
        if call.get("app") != "api_docs":
            return []
        args = call.get("args", {})
        if call.get("api") == "show_api_doc":
            names = {f"{args.get('app_name')}__{args.get('api_name')}"}
        elif call.get("api") == "show_api_descriptions":
            names = {n for n in self.catalog if n.startswith(str(args.get("app_name")) + "__")}
        else:
            names = set()
        added = sorted(names & set(self.catalog) - self.visible)
        self.visible.update(added)
        return added


def dispatch_native_calls(message, catalog, bridge, read_archive, *, remaining_api_calls,
                          may_continue=lambda: True, on_record=lambda row: None):
    """Dispatch in recorded order; every rejected/skipped item gets a record."""
    calls = message.get("tool_calls") or []
    if not isinstance(calls, list):
        raise ValueError("tool_calls must be a list")
    if not calls:
        row = {"action": None, "observation": {"format_error": "at least one tool call required"},
               "api_request_sent": False, "new_tools": []}
        on_record(copy.deepcopy(row))
        return [row]
    rows, completed, sent, blocked = [], False, 0, None
    supplied = set(catalog.visible)
    for call in calls:
        function = call.get("function") if isinstance(call, dict) else None
        row = {"action": function, "api_request_sent": False, "new_tools": []}
        if blocked:
            row["observation"] = {"not_executed": blocked}
        elif completed:
            row["observation"] = {"not_executed": "task completion was already declared"}
        elif not may_continue():
            row["observation"] = {"not_executed": "run budget was reached"}
        else:
            try:
                if not isinstance(function, dict):
                    raise ValueError("missing function object")
                decoded = catalog.decode(function, visible=supplied)
            except (ValueError, KeyError, TypeError) as exc:
                row["observation"] = {"format_error": str(exc)}
            else:
                if decoded.pop("archive", False):
                    try:
                        row["observation"] = read_archive(decoded["span_id"], decoded.get("offset", 0))
                    except (ValueError, KeyError, TypeError) as exc:
                        row["observation"] = {"format_error": str(exc)}
                elif sent >= remaining_api_calls:
                    row["observation"] = {"not_executed": "API request budget was reached"}
                else:
                    row["api_request_sent"] = True
                    sent += 1
                    try:
                        # A timeout may follow a side effect. Never label it unexecuted or retry it.
                        response = bridge.request({"op": "call", "call": decoded})
                        if response["ok"]:
                            row["observation"] = response["result"]
                            row["new_tools"] = catalog.expose_requested_document(decoded)
                            completed = bool(response["result"].get("declared_complete"))
                        else:
                            row["observation"] = {"api_error": response["error"]}
                    except Exception as exc:
                        row["observation"] = {"transport_error_type": type(exc).__name__}
                        row["effects_unknown"] = True
                        blocked = "prior API request has unknown effects"
        rows.append(row)
        on_record(copy.deepcopy(row))
    return rows
