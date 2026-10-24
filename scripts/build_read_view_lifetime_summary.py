"""Publish all P108 reservation dispositions beside original P107 task outcomes."""
import argparse
import csv
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path


DISPOSITIONS=('explicit_materialization','conservative_barrier','last_reference_release',
              'separate_complete_response','pending_at_stop')


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def build(root):
    replay_path=root/'reports/P108_read_view_lifetimes.json'
    original_path=root/'reports/P107_comparison.json'
    replay=json.loads(replay_path.read_text());original=json.loads(original_path.read_text())
    if (original['audit_errors'] or replay['source_audit_sha256']!=sha(original_path)
            or len(replay['rows'])!=2 or [r['run_id'] for r in replay['rows']]!=[r['run_id'] for r in original['rows']]):
        raise ValueError('both_original_conditions_and_bound_replay_required')
    target=root/'materials/20261025_p108_results'
    target.mkdir(exist_ok=False)
    rows=[];lifetimes=[]
    for result,source in zip(replay['rows'],original['rows'],strict=True):
        checked=result['status']=='checked'
        row=dict(run_id=source['run_id'],policy=source['read_view_policy'],replay_status=result['status'],
            original_task_success=source.get('success'),original_record_status=source['record_status'],
            original_known_tokens=source.get('known_total_tokens'),original_unknown_usage=source.get('unknown_usage_calls'),
            original_API_requests=source.get('api_requests'),
            replayed_control_requests=result.get('control_requests'),deferred_groups=result.get('deferred_groups'))
        counts=result.get('disposition_counts',{})
        if checked and (set(counts)-set(DISPOSITIONS) or sum(counts.values())!=result['deferred_groups']
                or len(result['lifetimes'])!=result['deferred_groups']
                or result['replayed_API_receipts']!=source['api_requests']):
            raise ValueError('lifetime_and_original_totals_disagree')
        row.update({kind:counts.get(kind,0) if checked else None for kind in DISPOSITIONS})
        rows.append(row)
        lifetimes.extend(dict(run_id=source['run_id'],policy=source['read_view_policy'],**life)
                         for life in result.get('lifetimes',[]))
    with (target/'all_conditions.csv').open('x',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    fields=('run_id','policy','reservation','created_program','created_control','largest_alias_count',
            'disposition','terminal_program','terminal_control','invocation_status')
    with (target/'all_deferred_reservations.csv').open('x',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader();writer.writerows(lifetimes)
    summary=dict(all_conditions=rows,analysis_status=replay['status'],analysis_errors=replay['errors'],
        analysis_wall_seconds=replay['wall_seconds'],all_planned_conditions=2,
        original_independent_tasks=1,original_repetitions_per_policy=1,
        local_field_accesses_not_observed=True,cancellations_are_not_causal_savings=True,
        original_task_success_from_independent_P107_evaluation=True,
        original_worker_summary_evaluation_placeholders_not_used=True,
        new_model_calls=0,new_environment_API_requests=0,new_generated_program_executions=0,new_evaluations=0)
    with (target/'summary.json').open('x') as stream:json.dump(summary,stream,indent=2);stream.write('\n')
    manifest=dict(created_at=datetime.now(timezone.utc).isoformat(),builder_sha256=sha(Path(__file__)),
        replay_sha256=sha(replay_path),original_audit_sha256=sha(original_path),
        public_artifact_sha256={p.name:sha(p) for p in sorted(target.iterdir())},
        reporting_only=True,original_experiment_reexecuted=False)
    with (target/'build_manifest.json').open('x') as stream:json.dump(manifest,stream,indent=2);stream.write('\n')
    print(json.dumps(dict(conditions=2,deferred_reservations=len(lifetimes),analysis_status=replay['status'])))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--repo-root',type=Path,required=True)
    build(p.parse_args().repo_root.resolve())
