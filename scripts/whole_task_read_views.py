"""P107 development pilot: the same explicit read interface in two policies."""
import copy
import json

from api_error_comparison import initial_conversation as original_conversation
from budget_observation import notification
from protocol_stable_history import StableReferenceConversation
from whole_task_tool_choice import worker_config as ordinary_worker_config

POLICIES = ('eager_cached', 'coalesced_cached')
ERROR_POLICY = 'error_exception'
TASK_ID = '6104387_1'
GUIDE = '''
An additional task-local helper is available:
read_view("spotify", "show_song", song_id=...) returns a read-only Mapping.
Prefer this helper when you need fields of a song. Other API calls continue
through call_api, which returns the complete ordinary value. This helper does
not choose the required data, select songs, or verify completion for you.
Read fields with view["field"]. A view is not a dict; dict(view) obtains a full
ordinary copy. Printing, iterating, serializing or otherwise inspecting the
whole view can obtain the full value. Do not modify a view. Views can be kept
in variables and containers between programs. Deleting the last reference can
release an unneeded future request. Prefer printing the facts needed for the
next decision, as with ordinary API values.
The harness may reuse previously observed information or defer a full request.
Unknown fields and intervening operations may require a full API request and
can still fail. Every actually sent request counts. Outstanding deferred reads
reserve API capacity; the resource notice separates spent, pending and available
requests. A reservation is not a completed request or proof of task success.
'''


def initial_conversation(original, public_task):
    previous=original_conversation(original,public_task)
    return StableReferenceConversation(previous.messages()[0]['content']+GUIDE,public_task)


def cell_id(number,policy):
    if type(number) is not int or number!=1 or policy not in POLICIES:
        raise ValueError('fixed_P107_policy_required')
    return 'BOC_P107_01_'+policy.upper()


def config_for(original,plan,task_id,policy):
    if task_id != TASK_ID or policy not in POLICIES:
        raise ValueError('one_known_P107_task_and_fixed_policy_required')
    config=ordinary_worker_config(original,plan,task_id,'error_exception',cell_id(1,policy),'auto')
    config['read_view_policy']=policy
    if config['max_api_requests'] != 80:
        raise ValueError('existing_known_task_API_limit_required')
    return config


def read_view_notification(messages,state,requests):
    expected={'limit','spent','pending','available','stopped'}
    if (type(requests) is not dict or set(requests)!=expected
            or any(type(requests[k]) is not int for k in expected-{'stopped'})
            or requests['stopped'] is not False
            or min(requests[k] for k in expected-{'stopped'})<0
            or requests['spent']+requests['pending']+requests['available'] != requests['limit']
            or requests['spent'] != state['used']['api_calls']
            or requests['limit']-requests['spent'] != state['remaining']['api_calls']):
        raise ValueError('consistent_live_read_view_budget_required')
    supplied,visible=notification(messages,state,'not_exposed')
    supplied.append({'role':'user','content':'<read_view_api_budget_v1>\n'+
        json.dumps(requests,sort_keys=True,separators=(',',':'))+'\n</read_view_api_budget_v1>'})
    return supplied,visible


def run_order():return [(1,p) for p in POLICIES]


def make_notification(messages,state,policy,*,wall_limit):
    if policy not in POLICIES or state['used']['api_calls']!=0:
        raise ValueError('initial_read_view_preflight_only')
    return read_view_notification(messages,state,dict(limit=80,spent=0,pending=0,available=80,stopped=False))


def summarize(rows,errors):
    if len(rows)!=2 or [r['read_view_policy'] for r in rows]!=list(POLICIES):
        raise ValueError('both_fixed_P107_slots_required')
    known=all(r.get('record_status')=='evaluated' and r.get('unknown_usage_calls')==0
              and type(r.get('known_total_tokens')) is int for r in rows) and not errors
    both_success=known and all(r['success'] is True for r in rows)
    tokens=(rows[1]['known_total_tokens']-rows[0]['known_total_tokens']) if known else None
    apis=(rows[1]['api_requests']-rows[0]['api_requests']) if known else None
    return dict(planned_rows=2,independent_tasks=1,repetitions=1,
        all_two_complete_with_known_usage=known,both_successful=both_success,
        coalesced_minus_eager_tokens=tokens,coalesced_minus_eager_API_requests=apis,
        successful_task_token_reduction=bool(both_success and tokens<0),
        successful_task_API_reduction=bool(both_success and apis<0),
        development_gate_met=bool(both_success and tokens<0),
        novel_method_claim=False,general_quality_preservation_claim=False,
        interpretation='One posthoc-selected known task, one run per policy with the same explicit interface. '
        'Known usage and both independently successful tasks are required for a successful-task cost comparison. '
        'API and token differences remain separate; no general quality or novelty claim.')


def fixed_parameters():
    return dict(phase='budget_observation_connection',experiment='P107',batch_id='P107_batch_v01',
        source_plan='configs/P29_stateful_code_v01.json',source_runs=['P29_04_CODE'],
        read_view_policies=list(POLICIES),max_calls=80,max_total_tokens=450000,
        max_wall_seconds=1800,max_setup_seconds=120,max_cleanup_seconds=180,
        max_idle_wait_seconds=60,max_evaluation_seconds=180,server_max_lifetime_seconds=9000,
        max_cells=2,max_model_calls=160,max_reserved_tokens=900000,
        max_reserved_environment_api_requests=160,world_seed=42,model_seed=57,
        reserved_scenarios_read=0,novel_method_claim=False,automatic_retries=0,
        history_policy='all_returned_reasoning_from_start',catalog_policy='public_names',
        tool_choice='auto',reasoning_budget_tokens=-1,time_visibility='not_exposed',
        fresh_seed_search=False,threshold_search=False,repetitions=1,
        same_explicit_interface_in_both_policies=True,
        same_ordinary_complete_cache_in_both_policies=True)


def validate_plan(plan):
    for key,value in fixed_parameters().items():
        if type(plan.get(key)) is not type(value) or plan[key]!=value:
            raise ValueError('fixed_P107_parameter_changed:'+key)
    if len(plan.get('known_tasks',[]))!=1 or plan['known_tasks'][0]['task_id']!=TASK_ID:
        raise ValueError('one_previously_known_task_required')
    return plan
