"""Pure scheduling only for a caller-authenticated, frozen full12 reservation.

No reservation file is read and no candidate is selected or approved here.
The caller must authenticate the original reservation bytes and their ordered
task_ids before supplying metadata. A claimed source hash alone is not proof.
Validation compares a proposed schedule against that trusted caller input.

This is NOT a launch protocol: candidate eligibility and closed evidence,
model/protocol/budget/source freezes, unseen-task initial-state provision,
preflight, execution namespace, 24-slot audit/reporting and finite server lease
remain separate prerequisites. In particular, no P29 source_run, known-task
budget or reserved_scenarios_read=0 compatibility claim is manufactured.
"""
from copy import deepcopy
import math
import re


SCENARIOS = 12
CELLS = 24
COUNT_BUDGETS = ('max_calls', 'max_total_tokens', 'max_api_requests')
TIME_BUDGETS = ('max_wall_seconds', 'max_setup_seconds', 'max_cleanup_seconds',
                'max_idle_wait_seconds', 'max_evaluation_seconds')


def _require(condition, label):
    if not condition:
        # Keep caller identifiers/values out of error messages.
        raise ValueError(label)


def _reservation(value):
    _require(type(value) is dict and set(value) == {'status', 'source_sha256', 'task_ids'},
             'explicit_reservation_metadata_required')
    _require(value['status'] == 'frozen' and type(value['status']) is str, 'frozen_reservation_required')
    h = value['source_sha256']
    _require(type(h) is str and re.fullmatch('[0-9a-f]{64}', h) is not None, 'original_reservation_hash_required')
    ids = value['task_ids']
    _require(type(ids) is list and len(ids) == SCENARIOS, 'full12_required_no_subset')
    scenarios = []
    for task_id in ids:
        _require(type(task_id) is str and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*_1', task_id) is not None,
                 'variant1_task_id_required')
        scenario, variant = task_id.rsplit('_', 1)
        _require(variant == '1', 'variant1_only')
        scenarios.append(scenario)
    _require(len(set(ids)) == SCENARIOS and len(set(scenarios)) == SCENARIOS,
             'twelve_distinct_reserved_scenarios_required')
    return list(ids), scenarios


def _methods(baseline, candidate):
    for label in (baseline, candidate):
        _require(type(label) is str and re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{0,79}', label) is not None,
                 'unambiguous_method_label_required')
    _require(baseline.casefold() != candidate.casefold(), 'two_distinct_method_labels_required')
    _require(baseline.casefold() != 'candidate' and candidate.casefold() != 'baseline',
             'method_label_conflicts_with_arm_role')
    return {'baseline': baseline, 'candidate': candidate}


def _budgets(value):
    _require(type(value) is dict and set(value) == set(COUNT_BUDGETS + TIME_BUDGETS),
             'complete_explicit_budget_vector_required')
    for key in COUNT_BUDGETS:
        _require(type(value[key]) is int and value[key] > 0, 'positive_integer_count_budget_required')
    for key in TIME_BUDGETS:
        amount = value[key]
        _require(type(amount) in (int, float) and amount > 0, 'positive_finite_time_budget_required')
        try:
            finite = math.isfinite(amount * CELLS)
        except OverflowError:
            finite = False
        _require(finite, 'finite_whole_schedule_time_budget_required')
    try:
        total_finite = math.isfinite(sum(value[key] for key in TIME_BUDGETS) * CELLS)
    except OverflowError:
        total_finite = False
    _require(total_finite, 'finite_combined_schedule_time_budget_required')
    return deepcopy(value)


def build_schedule(reservation, *, baseline, candidate, seed, budgets):
    """Return all24 ordered cells; one shared explicit budget vector, no results.

    Reservation metadata must have exactly status='frozen', source_sha256 and
    the original ordered task_ids list of twelve distinct variant1 tasks.
    Budgets are caller-selected positive limits, identical for both methods
    and all scenarios. This function does not choose or assess those limits.
    """
    ids, scenarios = _reservation(reservation)
    methods = _methods(baseline, candidate)
    _require(type(seed) is int and seed >= 0, 'single_explicit_nonnegative_seed_required')
    limits = _budgets(budgets)
    cells = []
    for index, (task_id, scenario) in enumerate(zip(ids, scenarios), 1):
        roles = ('baseline', 'candidate') if index % 2 else ('candidate', 'baseline')
        for role in roles:
            cells.append(dict(slot=len(cells)+1, scenario_ordinal=index, scenario_id=scenario,
                              task_id=task_id, variant=1, arm_role=role, method=methods[role],
                              seed=seed, budgets=deepcopy(limits)))
    return dict(scope='schedule_preparation_only', reservation_source_sha256=reservation['source_sha256'],
                reserved_task_ids=ids, scenario_count=SCENARIOS, planned_cells=CELLS, methods=methods,
                seed=seed, budgets=limits, cells=cells)


def _same_typed(left, right):
    if type(left) is not type(right):
        return False
    if type(right) is dict:
        return set(left) == set(right) and all(_same_typed(left[k], right[k]) for k in right)
    if type(right) is list:
        return len(left) == len(right) and all(_same_typed(a, b) for a, b in zip(left, right))
    return left == right


def validate_schedule(schedule, reservation, *, baseline, candidate, seed, budgets):
    """Reject replacements, omissions, reordering and any unapproved additions.

    The external reservation/method/seed/budget arguments are the authority;
    the proposed schedule cannot redefine them. True means schedule structure
    matches only, not scientific eligibility or launch authorization.
    """
    expected = build_schedule(reservation, baseline=baseline, candidate=candidate, seed=seed, budgets=budgets)
    _require(_same_typed(schedule, expected), 'schedule_differs_from_full_frozen_caller_inputs')
    return True
