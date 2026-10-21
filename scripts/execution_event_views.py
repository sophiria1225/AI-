"""Experimental consumer views of recorded tool events, not semantic verification.

Only a runtime receipt can establish that an API request was not dispatched.
A tool error string or a model-authored claim cannot establish this condition.
The original archive remains immutable; callers must use this projection for
archive reads too if they promise that a consumer cannot see rejected text.
"""
import copy

VARIANTS = ("raw", "execution_tag", "quarantine", "role_split")
CONSUMERS = ("memory", "repair")


def rejected_before_dispatch(span, receipt):
    """Do not conflate transport errors, API errors, archive reads or rejection."""
    if not isinstance(receipt, dict):
        return False
    if receipt.get("span_id") != span.get("id"):
        raise ValueError("receipt does not belong to span")
    if (receipt.get("api_request_sent") is not False
            or receipt.get("effects_unknown") is not False):
        return False
    action = span.get("action") or {}
    name = action.get("name")
    if not isinstance(name, str) or name == "read_span":
        return False
    observation = span.get("observation")
    return (isinstance(observation, dict)
            and ("format_error" in observation or "not_executed" in observation))


def project_span(span, receipt, *, variant, consumer):
    if variant not in VARIANTS or consumer not in CONSUMERS:
        raise ValueError("unknown variant or consumer")
    output = copy.deepcopy(span)
    rejected = rejected_before_dispatch(span, receipt)
    if variant == "raw" or not rejected:
        return output
    hide = variant == "quarantine" or (variant == "role_split" and consumer == "memory")
    output["runtime_execution"] = {
        "api_request_sent": False, "effects_unknown": False,
        "scope": "This request was rejected before API dispatch. This says nothing "
                 "about prior state or the correctness of the requested arguments."}
    if hide:
        output.pop("assistant", None)
        output.pop("action", None)
        output["unexecuted_output_archive_id"] = span["id"]
    return output


def project_spans(spans, receipts, *, variant, consumer):
    if set(receipts) - set(spans):
        raise ValueError("receipt refers to unavailable span")
    return {sid: project_span(span, receipts.get(sid), variant=variant, consumer=consumer)
            for sid, span in spans.items()}
