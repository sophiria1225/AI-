"""Build aggregate P144 artifacts once from closed audited records; no inference."""
import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from receipt_reasoning_history import require
from whole_task_state_update_p144 import MODES, PLAN, run_order, cell_id, summarize, validate_plan

ROOT = Path(__file__).resolve().parents[1]
DESTINATION = 'materials/20261028_p144_results'


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def json_new(path, value):
    with path.open('x') as f:
        json.dump(value, f, ensure_ascii=False, indent=2, allow_nan=False)
        f.write('\n')


def csv_new(path, rows, fields):
    with path.open('x', newline='') as f:
        writer=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore')
        writer.writeheader(); writer.writerows(rows)


def build(root):
    audit_path=root/'reports/P144_comparison.json'
    session_path=root/'reports/P144_server_session.json'
    plan=read(root/PLAN)
    validate_plan(plan)
    require(all(sha(root/name)==expected for name,expected in plan['source_sha256'].items()),
            'fixed_P144_reporting_sources_changed')
    audit, session=read(audit_path),read(session_path)
    expected=[cell_id(n,m) for n,m in run_order()]
    require(audit['phase']==session['phase']=='P144' and audit['batch_status'] in ('complete','stopped')
        and audit['owned_processes_absent'] is True and type(audit['audit_errors']) is list
        and session['status']=='stopped' and session['owned_processes_absent'] is True
        and session['audit_source_sha256']==sha(audit_path)
        and audit['plan_sha256']==sha(root/PLAN)
        and [r['run_id'] for r in audit['rows']]==expected,'closed_fixed_P144_records_required')
    summary=summarize(audit['rows'],audit['audit_errors'])
    require(all(audit[k]==v for k,v in summary.items()),'closed_descriptive_recalculation_mismatch')
    target=root/DESTINATION
    target.mkdir(parents=True,exist_ok=False)
    fields=['run_id','task_id','model_seed','object_timing_mode','checkpoint_representation_mode','record_status','success','stop_reason',
        'model_calls','known_total_tokens','unknown_usage_calls','input_tokens','output_tokens',
        'cached_input_tokens','api_requests','checkpoint_installations',
        'object_prompt_offers','object_prompt_dispatched_focus_calls','object_prompt_known_focus_calls',
        'object_prompt_unknown_focus_calls','delta_envelope_contract_failed','delta_envelope_accounting_complete',
        'decision_differences_from_threshold','decision_differences_from_exposure',
        'actual_decision_differences_from_threshold','actual_decision_differences_from_exposure',
        'delta_installations','fragment_count','actual_delta_actor_calls',
        'actual_delta_known_actor_calls','actual_delta_unknown_actor_calls',
        'update_prompt_offers','update_prompt_dispatched_focus_calls','update_prompt_known_focus_calls',
        'update_prompt_unknown_focus_calls','update_installations','state_changed_installations',
        'old_items_changed_installations','kept_old_items','updated_old_items','deleted_old_items',
        'added_items','changed_old_items','actual_update_actor_calls','actual_update_known_actor_calls',
        'actual_update_unknown_actor_calls','actual_changed_old_actor_calls','actual_changed_old_known_actor_calls',
        'actual_changed_old_unknown_actor_calls','state_update_contract_failed','state_update_accounting_complete',
        'checkpoint_representation_contract_failed','checkpoint_representation_accounting_complete',
        'prefix_exposure_contract_failed','prefix_exposure_accounting_complete','wall_seconds','full_wall_seconds']
    rows=[{k:r.get(k) for k in fields} for r in audit['rows']]
    csv_new(target/'conditions.csv',rows,fields)
    calls=[]
    for r in audit['rows']:
        for c in r.get('request_checks',[]):
            calls.append(dict(run_id=r['run_id'],task_id=r['task_id'],model_seed=r['model_seed'],
                object_timing_mode=r['object_timing_mode'],
                checkpoint_representation_mode=r['checkpoint_representation_mode'],**c))
    csv_new(target/'model_calls.csv',calls,['run_id','task_id','model_seed','object_timing_mode','checkpoint_representation_mode','call_id',
        'role','status','input_tokens','output_tokens','cached_input_tokens','finish_reason',
        'request_sha256','response_sha256'])
    pairs=[p for c in summary['comparisons'] for p in c['pairs']]
    csv_new(target/'pairs.csv',pairs,['task_id','baseline','candidate','baseline_success','candidate_success',
        'both_evaluated','both_usage_known','success_lost','both_successful',
        'candidate_minus_baseline_tokens','candidate_prompt_known_focus_calls',
        'candidate_changed_view_known_actor_calls','candidate_changed_old_items','strict_prefix_match','canonical_prefix_match',
        'actual_intervention'])
    summary.update(phase='P144',created_at=datetime.now(timezone.utc).isoformat(),
        conditions=rows, all_model_roles_included=True, cached_input_deducted=False,
        added_model_calls=0,added_environment_API_requests=0,added_evaluations=0,
        manuscript_written=False, source_sha256={str(p.relative_to(root)):sha(p)
            for p in (audit_path,session_path,root/PLAN,Path(__file__))})
    json_new(target/'summary.json',summary)
    (target/'README.md').write_text(
        '# P144: bounded state-update comparison on four known tasks\n\n'
        'All twelve planned cells remain in [conditions.csv](conditions.csv), including '
        'failures, unknown usage and incomplete cells. [Pairs](pairs.csv) retains all '
        'four task pairs for each of three comparisons. [Model calls](model_calls.csv) '
        'includes every saved actor and focus attempt. [Summary](summary.json) preserves '
        'the fixed development criteria.\n\n'
        'Recursive replacement, explicit object append, and explicit state update use '
        'the same 8192-token first/repeat threshold, maximum two opportunities and '
        '1800 work seconds per cell. Given the same archive and prior state, the first '
        'focus packet and second user-reference construction are common, while the '
        'second system instruction differs. Actual cross-run identity is separately audited. '
        'The update arm explicitly keeps, updates or deletes every old field item '
        'exactly once, then adds items. The host applies this atomically within the '
        'same materialized-state limits. An invalid proposal preserves the current '
        'view and retains known paid cost; there is no repair retry.\n\n'
        'This post-P143 development comparison fixes seed257 on all four known tasks. '
        'It does not pool earlier cohorts or use the reserved twelve tasks. The seed '
        'and work budget differ from P143; cross-phase outcomes do not identify a '
        'representation effect. The execution order is rotated, not randomized.\n\n'
        'Known logical input plus output includes cached input, paid rejected summaries '
        'and failed calls with known usage. Unknown or missing values remain null. '
        'An exact pairwise total requires all eight cells of that comparison evaluated '
        'with known usage; overall eligibility requires all twelve. Empty common-success '
        'groups have null differences. Lower incomplete known subtotals are not savings.\n\n'
        'Update must beat both recursive and append controls without any paired success '
        'loss, lowering both all-task and nonempty common-success cost. Accepted old-item '
        'change must alter the materialized state and reach a known actor on a common-success '
        'task. Mere keep/add or net-unchanged delete/add is not such exposure. Strict and '
        'validated transport-ID canonical prefix identity are separate. The intervention '
        'is the representation-plus-prompt bundle; no component-isolated effect is claimed.\n\n'
        'Typed updates and host merging overlap existing memory systems. This comparison '
        'alone establishes neither novelty, semantic fidelity, general quality preservation '
        'nor scientific adoption. All audit errors remain visible.\n')
    files=sorted(p for p in target.iterdir() if p.is_file())
    json_new(target/'build_manifest.json',dict(phase='P144',status='complete',
        source_sha256=summary['source_sha256'],
        artifact_sha256={p.name:sha(p) for p in files},
        additional_model_calls=0,additional_API_requests=0,additional_evaluations=0))
    return summary


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo-root',type=Path,default=ROOT)
    args=parser.parse_args()
    result=build(args.repo_root.resolve())
    print({k:result[k] for k in ('planned_rows','development_gate_met')})
