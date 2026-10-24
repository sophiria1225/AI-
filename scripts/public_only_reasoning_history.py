"""Ordinary no-replay control: keep the archive, omit every prior reasoning field.

P110 receipt validation remains as shared instrumentation. Eligibility never
selects the display in this control, including after failure and for latest turn.
"""
from receipt_reasoning_history import (
    digest, execution_evidence, project as archive_projection, require, strip_reasoning,
)

POLICIES = ('public_only',)


def project(messages, evidence, policy):
    require(policy in POLICIES, 'fixed_public_only_policy_required')
    archive, metadata = archive_projection(messages, evidence, 'full')
    result = strip_reasoning(archive)
    assistants = [m for m in archive if m.get('role') == 'assistant']
    removed = [i for i, m in enumerate(assistants, 1) if 'reasoning_content' in m]
    metadata.update(policy=policy, removed_reasoning_turns=removed,
        retained_reasoning_turns=[i for i in range(1, len(assistants)+1) if i not in removed],
        supplied_reasoning_characters=0,
        removed_reasoning_characters=metadata['original_reasoning_characters'],
        supplied_history_sha256=digest(result), latest_reasoning_preserved=False,
        receipt_eligibility_used_for_selection=False)
    return result, metadata
