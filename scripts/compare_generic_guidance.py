"""Paired descriptive comparison after BOTH fixed six-task runs have ended.

Uses audited public metadata, not raw model/evaluator bodies. Unknown token
usage prevents an exact token delta; a changed instruction bundle does not
identify a sentence-level mechanism or establish a novel method.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path


MATCHED_KEYS = ('model', 'model_selection', 'task_ids', 'seed', 'agent_temperature',
                'max_calls', 'max_api_requests', 'max_wall_seconds', 'max_total_tokens',
                'max_output_tokens', 'observation_page_characters', 'history_representation',
                'discovery_policy', 'max_checkpoint_new_bytes_per_boundary', 'max_checkpoint_object_bytes')
TOTAL_KEYS = ('model_calls', 'known_total_tokens', 'unknown_usage_calls', 'api_requests',
              'output_limit_finishes', 'execution_wall_seconds')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def arm_rows(plan, summary, budget):
    if summary.get('pending') or summary.get('audit_errors'):
        raise ValueError('execution summary is pending or inconsistent')
    expected = plan['run_order']
    trials = summary['trials']
    if len(trials) != len(expected) or len(budget['trials']) != len(expected):
        raise ValueError('incomplete or additional trials')
    bmap = {t['run_id']: t for t in budget['trials']}
    if len(bmap) != len(expected) or len({t['run_id'] for t in trials}) != len(expected):
        raise ValueError('duplicated run identity')
    result = []
    for (task, arm, rid), m in zip(expected, trials):
        if (m['task_id'], m['arm'], m['run_id']) != (task, arm, rid):
            raise ValueError('task, arm or order mismatch')
        b = bmap[rid]
        if m.get('audit_errors') or not m.get('evaluation'):
            raise ValueError('missing evaluation or trial audit failure')
        if m['evaluation']['evaluation_returned_to_model']:
            raise ValueError('final evaluation was exposed to the model')
        success = m['evaluation']['official_success']
        if type(success) is not bool:
            raise ValueError('success must be a boolean')
        for k in ('model_calls', 'known_total_tokens', 'unknown_usage_calls', 'declared_complete', 'stop_reason', 'wall_seconds'):
            if b[k] != m[k]:
                raise ValueError('budget and measurement disagree: ' + k)
        for k, val in b['limits'].items():
            if plan[k] != val:
                raise ValueError('budget limit differs from fixed plan')
        for key in ('summary', 'usage'):
            if m['source_hashes'][key] != b['source_sha256'][key+'.json']:
                raise ValueError('budget and measurement source mismatch')
        result.append(dict(task_id=task, run_id=rid, success=success,
                           declared_complete=m['declared_complete'], stop_reason=m['stop_reason'],
                           model_calls=m['model_calls'], known_total_tokens=m['known_total_tokens'],
                           unknown_usage_calls=m['unknown_usage_calls'], api_requests=b['api_requests'],
                           output_limit_finishes=b['output_limit_finishes'],
                           execution_wall_seconds=m['wall_seconds']))
    for summary_key, row_key in (('total_model_calls', 'model_calls'),
                                 ('known_total_tokens', 'known_total_tokens'),
                                 ('unknown_usage_calls', 'unknown_usage_calls')):
        if summary[summary_key] != sum(r[row_key] for r in result):
            raise ValueError('summary total disagrees with trial rows')
    return result


def compare(base_plan, guided_plan, base_summary, guided_summary, base_budget, guided_budget):
    for key in MATCHED_KEYS:
        if base_plan[key] != guided_plan[key]:
            raise ValueError('unmatched condition: ' + key)
    base = arm_rows(base_plan, base_summary, base_budget)
    guided = arm_rows(guided_plan, guided_summary, guided_budget)
    if [r['task_id'] for r in base] != [r['task_id'] for r in guided]:
        raise ValueError('unmatched task rows')
    paired = [dict(task_id=b['task_id'], baseline=b, guided=g,
                   outcome=('both_success' if b['success'] and g['success'] else
                            'both_failure' if not b['success'] and not g['success'] else
                            'improved' if g['success'] else 'worsened')) for b, g in zip(base,guided)]
    totals = {}
    for name, rows in (('baseline', base), ('guided', guided)):
        totals[name] = {k: sum(r[k] for r in rows) for k in TOTAL_KEYS}
        totals[name].update(successes=sum(r['success'] for r in rows), trials=len(rows))
        totals[name]['tokens_exact'] = totals[name]['unknown_usage_calls'] == 0
    exact = all(t['tokens_exact'] for t in totals.values())
    return dict(pairs=paired, outcome_counts=dict(Counter(r['outcome'] for r in paired)),
                totals=totals, exact_total_token_delta=(totals['guided']['known_total_tokens']-
                    totals['baseline']['known_total_tokens']) if exact else None,
                matched_condition_keys=list(MATCHED_KEYS),
                limitations=['Six already observed development scenarios, one seed per arm.',
                             'Instruction bundle contrast, not isolated sentence-level attribution.',
                             'Known tokens are lower bounds when a call has unknown usage.',
                             'No novel-method efficacy or confirmatory generalization claim.'])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--repo-root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--storage-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError('preserve the existing comparison')
    # Check both statuses before opening any result table.
    status_paths = [args.storage_root/'records/context_pilot'/f'{phase}_batch_v01/status.json'
                    for phase in ('P22', 'P24')]
    if any(json.loads(p.read_text())['status'] != 'complete' for p in status_paths):
        raise ValueError('wait for both full batches to finish')
    paths = [args.repo_root/p for p in (
        'configs/P22_additional_baseline_v01.json', 'configs/P24_generic_guidance_v01.json',
        'reports/P22_additional_baseline_summary.json', 'reports/P24_guidance_baseline_summary.json',
        'reports/P22_budget_diagnostics.json', 'reports/P24_budget_diagnostics.json')]
    values = [json.loads(p.read_text()) for p in paths]
    bp,gp,bs,gs,bb,gb = values
    sources = {str(p.relative_to(args.repo_root)):digest(p) for p in paths}
    for plan, summary, budget, path in ((bp,bs,bb,paths[0]),(gp,gs,gb,paths[1])):
        if len(plan['run_order']) != 6 or summary['plan_sha256'] != digest(path):
            raise ValueError('not the six fixed runs, or plan digest mismatch')
        if budget['phase'] != plan['phase'] or any(
                b['source_sha256']['plan.json'] != digest(path) for b in budget['trials']):
            raise ValueError('budget diagnosis is not bound to the fixed plan')
        measurements = {m['run_id']:m for m in summary['trials']}
        for _,_,rid in plan['run_order']:
            for kind in ('execution', 'boundary'):
                p = args.repo_root/'reports'/f'{rid}_{kind}_audit.json'
                audit = json.loads(p.read_text())
                if audit['run_id'] != rid or audit['audit_errors']:
                    raise ValueError('technical audit mismatch')
                if kind == 'execution' and (audit['dispatch_audit_errors'] or audit['history_audit_errors']):
                    raise ValueError('dispatch or history audit failure')
                if kind == 'execution' and any(audit[k] != measurements[rid][k] for k in (
                        'source_hashes','evaluation','known_total_tokens','model_calls','unknown_usage_calls')):
                    raise ValueError('execution audit does not match measurement')
                sources[str(p.relative_to(args.repo_root))] = digest(p)
    report = compare(*values)
    report.update(kind='P22_P24_paired_development_comparison', source_hashes=sources,
                  script_sha256=digest(Path(__file__)), additional_model_calls=0, environment_calls=0)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps({k:report[k] for k in ('outcome_counts','totals','exact_total_token_delta')}))


if __name__ == '__main__':
    main()
