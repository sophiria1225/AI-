"""Compare all four P18/P25 development cases after both batches finish.

Reuse the P24 accounting checks without changing the frozen execution code.
No partial result inspection and no model or environment calls.
"""
import argparse
import json
from pathlib import Path

from compare_generic_guidance import compare, digest, check_execution_measurement


def comparison(values):
    base, guided = values[:2]
    if (base['phase'], guided['phase']) != ('P18', 'P25'):
        raise ValueError('only the fixed P18/P25 comparison is supported')
    if any(len(plan['run_order']) != 4 for plan in (base, guided)):
        raise ValueError('all four original cases are required')
    report = compare(*values)
    report['limitations'][0] = 'Four already observed development scenarios, one seed per arm.'
    return report


def analyze(repo, storage):
    # Do not open result tables until all four trials in both runs are complete.
    statuses = [storage/'records/context_pilot'/f'{p}_batch_v01/status.json'
                for p in ('P18', 'P25')]
    if any(json.loads(p.read_text())['status'] != 'complete' for p in statuses):
        raise ValueError('wait for both full batches to finish')
    paths = [repo/p for p in (
        'configs/P18_additional_baseline_v01.json', 'configs/P25_guidance_transfer_v01.json',
        'reports/P18_additional_baseline_summary.json', 'reports/P25_guidance_transfer_summary.json',
        'reports/P18_budget_diagnostics.json', 'reports/P25_budget_diagnostics.json')]
    values = [json.loads(p.read_text()) for p in paths]
    bp, gp, bs, gs, bb, gb = values
    sources = {str(p.relative_to(repo)): digest(p) for p in paths}
    for plan, summary, budget, path in ((bp,bs,bb,paths[0]), (gp,gs,gb,paths[1])):
        if summary['plan_sha256'] != digest(path):
            raise ValueError('plan digest mismatch')
        if budget['phase'] != plan['phase'] or any(
                b['source_sha256']['plan.json'] != digest(path) for b in budget['trials']):
            raise ValueError('budget diagnosis is not bound to the fixed plan')
        measurements = {m['run_id']: m for m in summary['trials']}
        for _, _, rid in plan['run_order']:
            for kind in ('execution', 'boundary'):
                p = repo/'reports'/f'{rid}_{kind}_audit.json'
                audit = json.loads(p.read_text())
                if audit['run_id'] != rid or audit['audit_errors']:
                    raise ValueError('technical audit mismatch')
                if kind == 'execution':
                    if audit['dispatch_audit_errors'] or audit['history_audit_errors']:
                        raise ValueError('dispatch or history audit failure')
                    check_execution_measurement(audit, measurements[rid],
                        storage/'records/context_pilot'/rid)
                sources[str(p.relative_to(repo))] = digest(p)
    report = comparison(values)
    report.update(kind='P18_P25_paired_development_comparison', source_hashes=sources,
        script_sha256=digest(Path(__file__)),
        dependency_sha256=digest(Path(__file__).with_name('compare_generic_guidance.py')),
        additional_model_calls=0, environment_calls=0)
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--repo-root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--storage-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError('preserve the existing comparison')
    report = analyze(args.repo_root, args.storage_root)
    with args.output.open('x') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    print(json.dumps({k:report[k] for k in ('outcome_counts','totals','exact_total_token_delta')}))


if __name__ == '__main__':
    main()
