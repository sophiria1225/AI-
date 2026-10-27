"""Build aggregate P140 artifacts once from closed audited records; no inference."""
import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from receipt_reasoning_history import require
from whole_task_checkpoint_delta_envelope_p140 import MODES, PLAN, run_order, cell_id, summarize, validate_plan

ROOT = Path(__file__).resolve().parents[1]
DESTINATION = 'materials/20261028_p140_results'


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
    audit_path=root/'reports/P140_comparison.json'
    session_path=root/'reports/P140_server_session.json'
    plan=read(root/PLAN)
    validate_plan(plan)
    require(all(sha(root/name)==expected for name,expected in plan['source_sha256'].items()),
            'fixed_P140_reporting_sources_changed')
    audit, session=read(audit_path),read(session_path)
    expected=[cell_id(n,m) for n,m in run_order()]
    require(audit['phase']==session['phase']=='P140' and audit['batch_status'] in ('complete','stopped')
        and audit['owned_processes_absent'] is True and not audit['audit_errors']
        and session['status']=='stopped' and session['owned_processes_absent'] is True
        and session['audit_source_sha256']==sha(audit_path)
        and audit['plan_sha256']==sha(root/PLAN)
        and [r['run_id'] for r in audit['rows']]==expected,'closed_fixed_P140_records_required')
    summary=summarize(audit['rows'],audit['audit_errors'])
    require(all(audit[k]==v for k,v in summary.items()),'closed_gate_recalculation_mismatch')
    target=root/DESTINATION
    target.mkdir(parents=True,exist_ok=False)
    fields=['run_id','task_id','checkpoint_representation_mode','record_status','success','stop_reason',
        'model_calls','known_total_tokens','unknown_usage_calls','input_tokens','output_tokens',
        'cached_input_tokens','api_requests','checkpoint_installations',
        'object_prompt_offers','object_prompt_dispatched_focus_calls','object_prompt_known_focus_calls',
        'object_prompt_unknown_focus_calls','delta_envelope_contract_failed','delta_envelope_accounting_complete',
        'decision_differences_from_threshold','decision_differences_from_exposure',
        'actual_decision_differences_from_threshold','actual_decision_differences_from_exposure',
        'delta_installations','fragment_count','actual_delta_actor_calls',
        'actual_delta_known_actor_calls','actual_delta_unknown_actor_calls',
        'checkpoint_representation_contract_failed','checkpoint_representation_accounting_complete',
        'prefix_exposure_contract_failed','prefix_exposure_accounting_complete','wall_seconds','full_wall_seconds']
    rows=[{k:r.get(k) for k in fields} for r in audit['rows']]
    csv_new(target/'conditions.csv',rows,fields)
    calls=[]
    for r in audit['rows']:
        for c in r.get('request_checks',[]):
            calls.append(dict(run_id=r['run_id'],task_id=r['task_id'],
                checkpoint_representation_mode=r['checkpoint_representation_mode'],**c))
    csv_new(target/'model_calls.csv',calls,['run_id','task_id','checkpoint_representation_mode','call_id',
        'role','status','input_tokens','output_tokens','cached_input_tokens','finish_reason',
        'request_sha256','response_sha256'])
    pairs=[p for c in summary['comparisons'] for p in c['pairs']]
    csv_new(target/'pairs.csv',pairs,['task_id','baseline','candidate','baseline_success','candidate_success',
        'both_evaluated','both_usage_known','success_lost','both_successful',
        'candidate_minus_baseline_tokens','candidate_object_prompt_known_focus_calls',
        'candidate_delta_known_actor_calls','representation_prefix_match','canonical_representation_prefix_match','actual_intervention'])
    summary.update(phase='P140',created_at=datetime.now(timezone.utc).isoformat(),
        conditions=rows, all_model_roles_included=True, cached_input_deducted=False,
        added_model_calls=0,added_environment_API_requests=0,added_evaluations=0,
        manuscript_written=False, source_sha256={str(p.relative_to(root)):sha(p)
            for p in (audit_path,session_path,root/PLAN,Path(__file__))})
    json_new(target/'summary.json',summary)
    (target/'README.md').write_text(
        '# P140: explicit object output for second delta summaries\n\n'
        'All twelve planned cells remain in [conditions.csv](conditions.csv). '
        'The [summary](summary.json) preserves two independent comparisons: the candidate '
        'versus the threshold-recursive control and versus unchanged exposure-delta. '
        '[Pairs](pairs.csv) retain all eight pairs; [model calls](model_calls.csv) include '
        'all actor and focus attempts.\n\n'
        'Only the eligible second delta focus system instruction is clarified. Parser, '
        'fragment limits, initial inputs, maximum two opportunities and shared budgets '
        'stay fixed. This known-task seed57 development question was chosen after P139 '
        'closed diagnostics; no old outcome is replaced or pooled. All failures, unknowns, '
        'missing cells and inactive/mismatched prefixes remain. Whole-job logical IO '
        'includes cached input, paid rejected summaries and failures. Exact all/common '
        'differences remain null unless all four pairs are known; empty common groups '
        'remain null.\n\n'
        'Strict prefix evidence is reported alongside validated transport-ID canonical '
        'evidence. Canonical identity changes protocol identifiers only; it does not '
        'establish semantic fidelity, hidden-state identity, general causal attribution, '
        'novelty or independent replication. Scientific adoption requires both gates.\n')
    files=sorted(p for p in target.iterdir() if p.is_file())
    json_new(target/'build_manifest.json',dict(phase='P140',status='complete',
        source_sha256=summary['source_sha256'],
        artifact_sha256={p.name:sha(p) for p in files},
        additional_model_calls=0,additional_API_requests=0,additional_evaluations=0))
    return summary


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo-root',type=Path,default=ROOT)
    args=parser.parse_args()
    result=build(args.repo_root.resolve())
    print({k:result[k] for k in ('planned_rows','primary_utility_gate_met','development_gate_met')})
