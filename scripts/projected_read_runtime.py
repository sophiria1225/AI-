"""Connect explicit field reads to the existing budgeted, discovered API channel.

No changes to PersistentApiPython or the frozen P29/P33 adapters. One RPC still
produces exactly one accountable row, whether fetched, reused or rejected.
"""
from collections import Counter
import copy
import json
import time

from container_api_python import ApiChannel
from field_read_contract import (CONTRACT_ID, TARGET, READ_ONLY_APIS, FieldReadCache,
                                 ReadContext, canonical, project, required_fields,
                                 target_identity)

ARMS = ("none_keep", "exact_keep", "contract_keep")

INSTALL = '''def read_fields(app, api, fields, **arguments):
    return call_api("_harness", "read_fields", target_app=app, target_api=api,
                    fields=fields, arguments=arguments)
'''

GUIDE = '''
An additional read_fields(app, api, fields, **arguments) function is now available
in Python. It supports spotify.show_song only. It returns a dictionary containing
exactly the requested top-level fields, equivalent to calling that API and then
selecting those fields. Discover the original API normally before using it.
Choose fields from the task's requirements; do not omit information you need.
Use call_api unchanged when you need the full response or any other API.
Eligible prior results may be reused within this task and state; otherwise the
normal API is called. Backend calls consume the same task API limit. Reading
fields does not certify that the task or its output is complete.
'''


def make_conversation(prefix):
    from handoff_factors import handoff_conversation, split_turns
    from native_conversation import NativeConversation, recover_turn
    base, _ = handoff_conversation(prefix["conversation_private"], prefix["public_task"], "full_keep", 8)
    messages = base.messages()
    view = NativeConversation(messages[0]["content"] + GUIDE, prefix["public_task"])
    for turn in split_turns(messages):
        view.append(turn[0], recover_turn(turn))
    return view


class ProjectedReadRuntime:
    def __init__(self, mode, *, execution_scope, verified_contract):
        self.cache = FieldReadCache(mode, verified_contract=verified_contract)
        self.scope = execution_scope
        self.revision = 0
        self.counts = Counter()
        self.installation = None

    def context(self):
        return ReadContext(self.scope, str(self.revision), CONTRACT_ID)

    def observed_sent(self, api, arguments, *, success, value=None):
        # A channel dispatch is synchronous: no other cache lookup can interleave
        # with this backend call. Invalidate on return, including failures with
        # unknown effects, before any subsequent request can run.
        if api not in READ_ONLY_APIS:
            self.revision += 1
            self.cache.invalidate()
            self.counts["invalidations"] += 1
        elif success:
            self.cache.observe(api, arguments, value, self.context())

    def seed(self, events, spans):
        from analyze_structured_reuse import decode
        for event in events:
            if not event["api_request_sent"]:
                continue
            span = spans[event["span_id"]]
            ok, value = decode(span["observation"])
            self.observed_sent(span["action"]["name"], json.loads(span["action"]["arguments"]),
                               success=ok, value=value)

    def install(self, session, storage, folder, catalog):
        if self.installation is not None:
            raise ValueError("helper already installed")
        start = time.monotonic()
        channel = ApiChannel(catalog, None, 0, lambda: False)
        result = session.run(INSTALL, [], channel, storage_root=storage,
                             record_dir=folder, timeout=30)
        if (result["status"] != "ok" or result["stdout"] or result["api_requests"]
                or channel.rows or not result["session_usable"]):
            raise ValueError("field helper installation failed")
        self.installation = {"wall_seconds": time.monotonic() - start,
                             "model_calls": 0, "api_requests": 0,
                             "program_index": result["program_index"]}
        return self.installation

    def program(self, session):
        def run(source, observations, channel, **options):
            if self.installation is None:
                raise ValueError("field helper not installed")
            return session.run(source, observations, FieldChannel(channel, self), **options)
        return run

    def summary(self):
        return {"mode": self.cache.mode, "counts": dict(self.counts),
                "installation": self.installation, "bounds_rejected": self.cache.bounds_rejected,
                "revision_changes": self.revision}


class FieldChannel:
    """Preserves base-channel counters and fatal/completion status for its caller."""
    def __init__(self, base, runtime):
        self.base = base
        self.runtime = runtime

    def __getattr__(self, name):
        return getattr(self.base, name)

    def _check(self, packet):
        if (type(packet) is not dict or set(packet) != {"kind", "id", "app", "api", "arguments"}
                or packet["kind"] != "api" or type(packet["id"]) is not int
                or packet["id"] != self.base.last_id + 1
                or type(packet["arguments"]) is not dict
                or any(type(packet[k]) is not str for k in ("app", "api"))):
            raise ValueError("invalid API RPC request")

    def _rejected(self, packet, message, *, not_executed=False):
        self.base.last_id = packet["id"]
        row = {"action": {"name": packet["app"] + "__" + packet["api"],
                          "arguments": json.dumps(packet["arguments"], allow_nan=False)},
               "api_request_sent": False, "new_tools": [],
               "observation": {"not_executed" if not_executed else "format_error": message}}
        self.base.rows.append(row)
        self.runtime.counts["rejected"] += 1
        return {"id": packet["id"], "ok": False, "error": message}

    def _hit(self, packet, hit, fields):
        self.base.last_id = packet["id"]
        meta = {"requested_fields": list(fields) if fields is not None else None,
                "source": hit.source, "full_api_response": fields is None,
                "contract": CONTRACT_ID, "state_revision": self.runtime.revision}
        self.base.rows.append({
            "action": {"name": TARGET, "arguments": json.dumps(packet["arguments"], allow_nan=False)},
            "api_request_sent": False, "new_tools": [],
            "observation": {"observation": json.dumps(hit.value, allow_nan=False), "field_read": meta}})
        self.runtime.counts["raw_" + hit.source if fields is None else "projected_" + hit.source] += 1
        return {"id": packet["id"], "ok": True, "value": hit.value, "new_schemas": {}}

    def exchange(self, packet):
        self._check(packet)
        explicit = packet["app"] == "_harness"
        original = packet
        fields = None
        if explicit:
            try:
                args = packet["arguments"]
                if (packet["api"] != "read_fields"
                        or set(args) != {"target_app", "target_api", "fields", "arguments"}
                        or args["target_app"] != "spotify" or args["target_api"] != "show_song"
                        or type(args["arguments"]) is not dict):
                    raise ValueError("read_fields supports only spotify.show_song")
                fields = required_fields(args["fields"])
                packet = {**packet, "app": args["target_app"], "api": args["target_api"],
                          "arguments": args["arguments"]}
            except (ValueError, TypeError, KeyError) as error:
                return self._rejected(original, str(error))
        if (self.base.complete or self.base.fatal or self.base.remaining <= 0
                or not self.base.may_continue()):
            return self._rejected(original, "completion, unknown effects or run budget", not_executed=True)
        api = packet["app"] + "__" + packet["api"]
        # Cache hits must obey exactly the same discovered public API validation.
        try:
            action = self.base.catalog.decode({"name": api, "arguments": json.dumps(packet["arguments"], allow_nan=False)})
            if set(action) != {"app", "api", "args"}:
                raise ValueError("only discovered public APIs in Python")
        except (ValueError, TypeError, KeyError) as error:
            return self._rejected(original, str(error))
        cache = self.runtime.cache
        context = self.runtime.context()
        hit = None
        if explicit:
            hit = cache.lookup(api, packet["arguments"], fields, context)
        elif target_identity(api, packet["arguments"]) is not None:
            # Ordinary exact caching also applies to full original API reads in
            # BOTH cache modes; it is not restricted to the new helper.
            if cache._activate(context):
                versions = cache.exact.get(canonical(packet["arguments"]), {})
                if len(versions) == 1:
                    prior = next(iter(versions.values()))
                    if prior:
                        candidate = cache.lookup(api, packet["arguments"], list(prior), context)
                        if candidate is not None and candidate.source == "exact":
                            hit = candidate
        if hit is not None:
            return self._hit(packet, hit, fields)
        reply = self.base.exchange(packet)
        row = self.base.rows[-1]
        if row["api_request_sent"]:
            success = reply.get("ok", False)
            selected = None
            if success and explicit:
                try:
                    selected = project(reply["value"], fields)
                except (ValueError, KeyError):
                    success = False
                    reply = {"id": packet["id"], "ok": False,
                             "error": "requested fields absent or non-dictionary response"}
            self.runtime.observed_sent(api, packet["arguments"], success=success,
                                       value=reply.get("value"))
            self.runtime.counts["backend_requests"] += 1
            if explicit:
                row["observation"]["field_read"] = {
                    "requested_fields": list(fields), "source": "fetched",
                    "full_api_response": False, "projection_success": success}
                self.runtime.counts["projected_fetched" if success else "projected_failed"] += 1
                if success: reply = {**reply, "value": selected}
        return reply
