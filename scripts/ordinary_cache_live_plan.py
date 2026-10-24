"""Fixed P106 control: cache complete ordinary reads in both policies."""
import hashlib

from coalesced_live_sequences import PROGRAMS


POLICIES = ('eager_cached', 'coalesced_cached')
EXPECTED_API = {'eager_cached':[6, 1, 0, 1, 0, 1, 3],
                'coalesced_cached':[6, 0, 1, 0, 0, 1, 4]}
EXPECTED_PENDING = {'eager_cached':[0, 0, 0, 0, 0, 0, 0],
                    'coalesced_cached':[0, 1, 0, 1, 0, 0, 0]}
EXPECTED_EXACT_REUSES = {'eager_cached':5, 'coalesced_cached':0}
EXPECTED_COALESCED_REUSES = {'eager_cached':0, 'coalesced_cached':4}
EXPECTED_MATERIALIZATION_CACHE_REUSES = {'eager_cached':0, 'coalesced_cached':1}
EXPECTED_ORDINARY_COMPLETE_REUSES = {'eager_cached':1, 'coalesced_cached':0}


def fixed_parameters():
    return dict(phase='P106_ordinary_complete_read_cache', task_id='6104387_1', seed=42,
        policies=list(POLICIES), fresh_world_per_policy=True,
        experiment_prefix='P106_ORDINARY_CACHE_LIVE_V01',
        private_output='records/context_pilot/P106_ordinary_cache_live_v01',
        stop_marker='.runtime/P106.stop', max_task_initializations=2,
        max_python_containers=2, handwritten_programs_per_policy=7,
        max_api_requests_per_policy=20, max_total_api_requests=40,
        active_deadline_seconds=300, program_timeout_seconds=30, bridge_timeout_seconds=30,
        expected_api_requests_per_program=EXPECTED_API,
        expected_pending_after_program=EXPECTED_PENDING,
        expected_exact_reuses=EXPECTED_EXACT_REUSES,
        expected_coalesced_reuses=EXPECTED_COALESCED_REUSES,
        expected_materialization_cache_reuses=EXPECTED_MATERIALIZATION_CACHE_REUSES,
        expected_ordinary_complete_reuses=EXPECTED_ORDINARY_COMPLETE_REUSES,
        model_calls=0, evaluator_calls=0, automatic_retries=0,
        task_quality_measured=False, novel_method_claim=False,
        program_sha256=[hashlib.sha256(s.encode()).hexdigest() for s in PROGRAMS],
        ordinary_complete_cache_enabled_in_both_policies=True)


def validate_plan(plan):
    for key, value in fixed_parameters().items():
        if plan.get(key) != value:
            raise ValueError('fixed_P106_plan_changed:'+key)
    return plan
