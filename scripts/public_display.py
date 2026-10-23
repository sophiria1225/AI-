"""P71: existing display controls under a common ordinary public-name policy.

No new information-selection algorithm. Only the permission wording and tool
description change in every arm; old actions, receipts and display rules stay
intact. Public-name admission still validates registered names and arguments.
"""
from collections import Counter
import copy
import json
import time

from code_agent_interface import CODE_TOOLS as LEGACY_CODE_TOOLS
from handoff_factors import split_turns
from inventory_display import ARMS, InventoryInference, disposition
from inventory_display import build_condition as legacy_build_condition
from inventory_display import validate_matched_views as legacy_validate_matched_views
from native_conversation import NativeConversation, recover_turn
from public_name_catalog import PublicNameCatalog
from run_handoff_factors import ROOT, sha

CAPABILITY_CHANGES = (
    ('calls one discovered public API', 'calls one registered public API by its exact name'),
    ('Initially only\napi_docs and supervisor APIs are available. Discover APIs with',
     'Exact names of registered public APIs may be called before reading their\n'
     'documentation. Unregistered or private APIs are unavailable. Initially\n'
     'only api_docs and supervisor definitions are visible. Discover APIs with'),
    ('After discovery, you may use the API within the same program.',
     'Documentation is optional when you already know the exact public API name\n'
     'and its arguments; it is available when you need details.'),
)
CODE_TOOLS = copy.deepcopy(LEGACY_CODE_TOOLS)
if CODE_TOOLS[0]['function']['description'].count('discovered simulated APIs') != 1:
    raise ValueError('legacy tool description changed')
CODE_TOOLS[0]['function']['description'] = CODE_TOOLS[0]['function']['description'].replace(
    'discovered simulated APIs', 'registered public simulated APIs')


def capability_prompt(original):
    for before, after in CAPABILITY_CHANGES:
        if original.count(before) != 1:
            raise ValueError('legacy capability wording changed')
        original = original.replace(before, after)
    return original


def build_condition(item, arm):
    before = time.monotonic()
    legacy, transfer = legacy_build_condition(item, arm)
    messages = legacy.messages()
    view = NativeConversation(capability_prompt(messages[0]['content']), item['prefix']['public_task'])
    for turn in split_turns(messages):
        view.append(turn[0], recover_turn(turn))
    transfer.update(transfer_wall_seconds=time.monotonic()-before,
                    catalog_policy='public_names', capability_wording='P64_named_same_in_all_arms')
    return view, transfer


def validate_matched_views(item):
    matched = legacy_validate_matched_views(item)
    for arm in ARMS:
        old = legacy_build_condition(item, arm)[0].messages()
        new = build_condition(item, arm)[0].messages()
        if old[1:] != new[1:] or new[0]['content'] != capability_prompt(old[0]['content']):
            raise ValueError('permission wording changed recorded actions or data')
    return matched


def validate_plan(plan):
    expected = {'phase': 'P71', 'batch_id': 'P71_batch_v01', 'catalog_policy': 'public_names',
        'source_plan': 'configs/P29_stateful_code_v01.json',
        'source_runs': [f'P29_{n:02d}_CODE' for n in range(1,5)],
        'arms': list(ARMS), 'boundary_after_model_calls': 8, 'max_calls': 16,
        'max_total_tokens': 120000, 'max_wall_seconds': 480, 'max_setup_seconds': 600,
        'recent_complete_turns': 1, 'output_reservation': 'residual', 'notification': 'both',
        'max_feedback_characters': 16000, 'max_idle_wait_seconds': 60, 'max_evaluation_seconds': 180,
        'server_max_lifetime_seconds': 21600, 'max_cells': 12, 'max_continuation_model_calls': 192,
        'max_continuation_reserved_tokens': 1440000, 'reserved_scenarios_read': 0, 'novel_method_claim': False,
        'source_comparison': 'reports/P55_comparison.json'}
    if any(plan.get(k) != v for k,v in expected.items()):
        raise ValueError('fixed public-display cohort or budget changed')
    if sha(ROOT / plan['source_comparison']) != plan['source_comparison_sha256']:
        raise ValueError('historical P55 report changed')
    for name, record in plan['prior_implementation_derivation'].items():
        if sha(ROOT/'scripts'/name) != record['source_sha256']:
            raise ValueError('historical P55 implementation changed')


def audit_access(events, spans, tools, prefix_visible):
    """Check all inner requests without executing code or dispatching APIs."""
    catalog = PublicNameCatalog(tools)
    if not set(prefix_visible) <= set(catalog.catalog):
        raise ValueError('unregistered prefix schema')
    catalog.visible = set(prefix_visible)
    counts = Counter(); unseen = Counter(); completed = blocked = False
    for event in events:
        if event['stage'] != 'python_api':
            if event['api_request_sent'] or event['new_tools']:
                raise ValueError('API dispatched or schema exposed outside the Python channel')
            continue
        span = spans[event['span_id']]; action = span['action']; observation = span['observation']
        try:
            decoded = catalog.decode(action)
            valid = set(decoded) == {'app', 'api', 'args'}
        except (ValueError, TypeError, KeyError, json.JSONDecodeError):
            valid = False
        if event['api_request_sent']:
            if not valid or completed or blocked:
                raise ValueError('sent request violates public-name policy, completion or known effects')
            counts[action['name']] += 1
            if action['name'] not in catalog.visible:
                unseen[action['name']] += 1
            completed |= bool(observation.get('declared_complete'))
            blocked |= bool(event.get('effects_unknown'))
        elif 'format_error' in observation and valid:
            raise ValueError('valid public-name request rejected as a format error')
        expected_new = []
        if event['api_request_sent'] and not event.get('effects_unknown') and 'api_error' not in observation:
            expected_new = catalog.expose_requested_document(decoded)
        if event['new_tools'] != expected_new:
            raise ValueError('schema exposure differs from the recorded documentation request')
    return {'catalog_policy': 'public_names', 'sent_api_requests': sum(counts.values()),
        'api_counts': dict(sorted(counts.items())),
        'sent_before_documentation_exposure': dict(sorted(unseen.items())),
        'additional_api_requests': 0, 'code_programs_reexecuted': 0}
