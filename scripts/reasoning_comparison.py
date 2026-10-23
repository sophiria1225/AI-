"""P76 ordinary continuation controls differing only in reasoning retention."""
import time

from handoff_factors import split_turns
from inventory_display import InventoryInference, disposition
from native_conversation import NativeConversation, recover_turn
from public_display import CODE_TOOLS, audit_access
from public_display import build_condition as public_condition
from reasoning_history import ReasoningConversation, reasoning_shape, with_recorded_reasoning
from run_handoff_factors import ROOT, read, sha

ARMS = ('public_only', 'reasoning_keep')


def build_history(messages, task, saved_messages, arm):
    if arm not in ARMS or len(saved_messages) != 8:
        raise ValueError('fixed_history_policy_and_eight_response_prefix_required')
    restored = with_recorded_reasoning(messages, saved_messages)
    source = restored if arm == 'reasoning_keep' else messages
    cls = ReasoningConversation if arm == 'reasoning_keep' else NativeConversation
    view = cls(source[0]['content'], task)
    if view.messages() != source[:2]:
        raise ValueError('initial_public_task_or_prompt_changed')
    for turn in split_turns(source):
        view.append(turn[0], recover_turn(turn))
    if view.messages() != source:
        raise ValueError('history_reconstruction_changed_values')
    return view


def prefix_responses(storage, item):
    plan = read(ROOT / 'configs/P75_reasoning_history_v01.json')
    groups = [g for g in plan['groups'] if g['source'] == 'prefix' and g['run_id'] == item['source_run']]
    if len(groups) != 1 or len(groups[0]['calls']) != 8:
        raise ValueError('fixed_P75_prefix_required')
    saved = []
    for index, call in enumerate(groups[0]['calls'], 1):
        if call['call_id'] != f'call_{index:03d}' or call['recorded_status'] != 'ok':
            raise ValueError('fixed_prefix_call_identity_changed')
        path = storage / 'records/context_pilot' / item['source_run'] / call['call_id'] / 'response.json'
        path.resolve().relative_to(storage.resolve())
        if sha(path) != call['files']['response.json']:
            raise ValueError('fixed_prefix_response_changed')
        response = read(path)
        if response['status'] != 'ok': raise ValueError('unknown_prefix_response')
        saved.append(response['message'])
    return saved


def build_condition(item, arm, storage):
    before = time.monotonic()
    public, transfer = public_condition(item, 'full_keep')
    saved = prefix_responses(storage, item)
    view = build_history(public.messages(), item['prefix']['public_task'], saved, arm)
    transfer.update(transfer_wall_seconds=time.monotonic() - before, view_arm=arm,
        history_policy=arm, reasoning_policy_applies_to='prefix_and_every_successful_continuation_response',
        prefix_reasoning_characters_available=sum(reasoning_shape(m)['characters'] for m in saved),
        prefix_reasoning_characters_supplied=sum(reasoning_shape(m)['characters'] for m in view.messages()
                                                 if m.get('role') == 'assistant'),
        one_time_boundary_display_change=False, novel_method_claim=False)
    return view, transfer


def validate_matched_views(item, storage):
    public, _ = build_condition(item, ARMS[0], storage)
    retained, meta = build_condition(item, ARMS[1], storage)
    stripped = [{k: v for k, v in m.items() if k != 'reasoning_content'} for m in retained.messages()]
    if stripped != public.messages() or meta['prefix_reasoning_characters_supplied'] <= 0:
        raise ValueError('ordinary_history_conditions_not_matched')
    return {'all_non_reasoning_fields_equal': True,
            'prefix_reasoning_characters': meta['prefix_reasoning_characters_supplied']}


class ReasoningInference(InventoryInference):
    def __init__(self, config, output, arm):
        if arm not in ARMS: raise ValueError('unknown_reasoning_history_condition')
        super().__init__(config, output, 'full_keep')
        self.arm = arm


def validate_plan(plan):
    expected = {'phase': 'P76', 'batch_id': 'P76_batch_v01', 'source_plan': 'configs/P29_stateful_code_v01.json',
        'source_runs': [f'P29_{n:02d}_CODE' for n in range(1, 5)], 'arms': list(ARMS),
        'boundary_after_model_calls': 8, 'max_calls': 16, 'max_total_tokens': 120000,
        'max_wall_seconds': 480, 'max_setup_seconds': 600, 'recent_complete_turns': 1,
        'output_reservation': 'residual', 'notification': 'both', 'max_feedback_characters': 16000,
        'max_idle_wait_seconds': 60, 'max_evaluation_seconds': 180, 'server_max_lifetime_seconds': 14400,
        'max_cells': 8, 'max_continuation_model_calls': 128, 'max_continuation_reserved_tokens': 960000,
        'reserved_scenarios_read': 0, 'novel_method_claim': False, 'catalog_policy': 'public_names'}
    if any(plan.get(k) != v for k, v in expected.items()):
        raise ValueError('fixed_history_comparison_or_budget_changed')
    for path, expected_hash in plan['source_sha256'].items():
        if sha(ROOT / path) != expected_hash:
            raise ValueError('historical_history_source_changed')
    for name, record in plan['prior_implementation_derivation'].items():
        if sha(ROOT / 'scripts' / name) != record['source_sha256']:
            raise ValueError('historical_runner_changed')
