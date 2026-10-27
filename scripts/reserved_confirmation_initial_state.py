"""Pure adapter from the full12 schedule to the existing typed init protocol.

This module never initializes a world or reads a task. After the external
protocol/eligibility/source freeze, a caller may supply authenticated receipts
from RecordedBridge and TypedBridgeProcess.close. All twelve references must
be supplied before the private bundle can be accepted. Later cell setup must
match that bundle before constructing the first model input.

The bundle CONTAINS PRIVATE PUBLIC-TASK CONTENT (potentially account details).
It is not a publication artifact. Only whole-record hashes are produced here.
No P29 source_run, prior task body, reserved_scenarios_read=0, model settings or
scientific approval is fabricated. Matching public projections does not prove
database equality, process ownership, freshness or receipt authenticity. The
caller must bind the real request/reply bytes, enforce new output namespaces,
use fresh owned bridge processes, and preserve failed setup/cleanup attempts.
"""
from copy import deepcopy
import hashlib
import json
import math
import re

from public_api_envelope import PROTOCOL, validate_json_value
from reserved_confirmation_schedule import validate_schedule

VERSION = 'reserved_confirmation_initial_state_v1'
PUBLIC_FIELDS = {'instruction', 'supervisor', 'app_descriptions', 'helper_docs',
                 'ground_truth_loaded'}


def _require(ok, label):
    if not ok:
        raise ValueError(label)  # Never include task content or caller values.


def digest(value):
    validate_json_value(value)
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def initialization_requests(schedule, reservation, *, baseline, candidate, seed,
                            budgets, namespace, world_seed):
    """Build init command data only: 12 reference worlds and 24 cell worlds.

    The caller must explicitly budget/authorize reference-world setup and close
    in addition to the cell budgets. This function dispatches none of them.
    """
    validate_schedule(schedule, reservation, baseline=baseline, candidate=candidate,
                      seed=seed, budgets=budgets)
    _require(type(namespace) is str and re.fullmatch('[A-Za-z][A-Za-z0-9_-]{0,59}', namespace),
             'explicit_safe_new_namespace_required')
    _require(type(world_seed) is int and world_seed >= 0, 'explicit_world_seed_required')
    def command(task, suffix):
        return dict(op='init', task_id=task, experiment=namespace+'_'+suffix, seed=world_seed)
    return dict(reference=[command(t, f'REFERENCE_{i:02d}') for i,t in
                           enumerate(schedule['reserved_task_ids'], 1)],
                cells=[command(c['task_id'], f'CELL_{c["slot"]:02d}') for c in schedule['cells']])


def _public(receipt, expected_command, setup_limit):
    # Exact completed RecordedBridge.request schema, not a worker self-report.
    _require(type(receipt) is dict and set(receipt) ==
             {'command', 'raw_request_started', 'response', 'wall_seconds'}, 'completed_init_receipt_required')
    _require(digest(receipt['command']) == digest(expected_command), 'init_command_binding_mismatch')
    _require(receipt['raw_request_started'] is True, 'recorded_init_dispatch_required')
    wall = receipt['wall_seconds']
    _require(type(wall) in (int, float) and math.isfinite(wall) and 0 <= wall <= setup_limit,
             'finite_in_budget_recorded_init_wall_required')
    response = receipt['response']
    _require(type(response) is dict and set(response) == {'ok','result'}
             and response['ok'] is True and type(response['result']) is dict, 'successful_typed_init_required')
    public = deepcopy(response['result'])
    _require(public.pop('api_result_protocol', None) == PROTOCOL, 'typed_init_protocol_required')
    _require(set(public) == PUBLIC_FIELDS and public['ground_truth_loaded'] is False,
             'only_public_initial_projection_required')
    _require(type(public['instruction']) is str and type(public['supervisor']) is dict
             and type(public['helper_docs']) is dict
             and set(public['helper_docs']) == {'api_docs','supervisor'}
             and all(type(v) is dict for v in public['helper_docs'].values()), 'public_initial_shape_required')
    validate_json_value(public)
    return public


def bind_reference_initial_states(schedule, reservation, receipts, *, baseline,
                                  candidate, seed, budgets, namespace, world_seed):
    """Bind all12 caller-authenticated fresh initialization and cleanup records.

    The returned private bundle is a future preflight input, not an executable
    plan. Its digest must be authenticated/frozen externally before cell use.
    """
    requests = initialization_requests(schedule, reservation, baseline=baseline,
        candidate=candidate, seed=seed, budgets=budgets, namespace=namespace, world_seed=world_seed)
    _require(type(receipts) is list and len(receipts) == 12, 'all12_initial_reference_records_required')
    references = []
    for slot, (record, command) in enumerate(zip(receipts, requests['reference']), 1):
        _require(type(record) is dict and set(record) == {'initialization','cleanup'},
                 'reference_init_and_cleanup_required')
        _require(type(record['cleanup']) is dict and record['cleanup'] ==
                 {'process_stopped':True,'graceful':True,'transport_failed':False}
                 and all(type(v) is bool for v in record['cleanup'].values()),
                 'reference_bridge_cleanly_closed_required')
        public = _public(record['initialization'], command, budgets['max_setup_seconds'])
        references.append(dict(scenario_ordinal=slot, task_id=command['task_id'],
            initialization_command_sha256=digest(command), recorded_setup_sha256=digest(record),
            initial_public_task_sha256=digest(public), public_task=public))
    return dict(version=VERSION, scope='private_initial_state_binding_only',
        schedule_sha256=digest(schedule), reservation_source_sha256=reservation['source_sha256'],
        namespace=namespace, world_seed=world_seed, references=references)


def confirm_cell_initial_state(schedule, reservation, bundle, cell_slot, receipt, *,
                               expected_bundle_sha256, baseline, candidate, seed,
                               budgets, namespace, world_seed):
    """Return the unchanged public projection only after fresh cell-init equality.

    expected_bundle_sha256 is an external authority, not read from the bundle.
    No authentication or launch permission is inferred from this matching hash.
    """
    requests = initialization_requests(schedule, reservation, baseline=baseline,
        candidate=candidate, seed=seed, budgets=budgets, namespace=namespace, world_seed=world_seed)
    _require(type(expected_bundle_sha256) is str and
             re.fullmatch('[a-f0-9]{64}', expected_bundle_sha256), 'authenticated_bundle_digest_required')
    _require(digest(bundle) == expected_bundle_sha256, 'frozen_private_bundle_changed')
    _require(type(bundle) is dict and set(bundle) == {'version','scope','schedule_sha256',
        'reservation_source_sha256','namespace','world_seed','references'} and
        bundle['version'] == VERSION and bundle['scope'] == 'private_initial_state_binding_only' and
        bundle['schedule_sha256'] == digest(schedule) and
        bundle['reservation_source_sha256'] == reservation['source_sha256'] and
        bundle['namespace'] == namespace and type(bundle['world_seed']) is int and
        bundle['world_seed'] == world_seed, 'initial_bundle_authority_mismatch')
    refs = bundle['references']
    _require(type(refs) is list and len(refs) == 12, 'all12_bound_references_required')
    for n, (ref, command) in enumerate(zip(refs, requests['reference']), 1):
        _require(type(ref) is dict and set(ref) == {'scenario_ordinal','task_id',
            'initialization_command_sha256','recorded_setup_sha256','initial_public_task_sha256','public_task'} and
            type(ref['scenario_ordinal']) is int and ref['scenario_ordinal'] == n and
            ref['task_id'] == command['task_id'] and ref['initialization_command_sha256'] == digest(command)
            and ref['initial_public_task_sha256'] == digest(ref['public_task']) and
            type(ref['recorded_setup_sha256']) is str and re.fullmatch('[a-f0-9]{64}',ref['recorded_setup_sha256']),
            'ordered_reference_binding_mismatch')
    _require(type(cell_slot) is int and 1 <= cell_slot <= 24, 'planned_cell_slot_required')
    public = _public(receipt, requests['cells'][cell_slot-1], budgets['max_setup_seconds'])
    reference = refs[schedule['cells'][cell_slot-1]['scenario_ordinal']-1]
    _require(digest(public) == reference['initial_public_task_sha256'], 'paired_initial_public_state_changed')
    return public
