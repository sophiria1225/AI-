"""Fixed no-model replay of explicit membership requests on known public data."""
import argparse
from collections import Counter
from dataclasses import replace
from pathlib import Path
import signal
import subprocess
import time

from diagnose_p24_public_traces import read as public_rows
from membership_evidence import EvidenceScope, MembershipEvidence
from run_handoff_factors import ROOT, read, sha
from run_context_comparison import write_json

PLAN = 'configs/P60_membership_evidence_v01.json'
CONDITIONS = ['no_evidence', 'one_relation', 'complete_union',
              'rows_without_terminal_evidence', 'changed_epoch', 'changed_principal']


def run(storage):
    began = time.monotonic(); plan = read(ROOT / PLAN)
    if (plan['source_run'] != 'P24_02_GUIDED' or plan['scenarios'] != CONDITIONS
            or plan['relations'] != ['roommate', 'coworker'] or plan['max_wall_seconds'] != 60
            or plan['max_rows'] != 4096 or plan['max_pages'] != 128
            or plan['expected_membership_requests_per_scenario'] != 26
            or any(plan[k] for k in ('model_calls', 'tokenizer_requests',
                                    'environment_api_requests', 'evaluator_calls', 'reserved_scenarios_read'))):
        raise ValueError('fixed scope or finite limits changed')
    source_report = ROOT / plan['source_report']
    if sha(source_report) != plan['source_report_sha256']:
        raise ValueError('fixed P59 report changed')
    evidence = read(source_report)
    folder = storage / 'records/context_pilot' / plan['source_run']
    data = storage / '.runtime/appworld/r18_probe_01/data'
    for name, digest in evidence['source_sha256'].items():
        path = ROOT / name if name.startswith('reports/') else data / name if name.startswith('api_docs/') else folder / name
        if sha(path) != digest: raise ValueError('known source changed: ' + name)
    installed = storage / '.runtime/appworld/venv/lib/python3.12/site-packages/appworld'
    for name, digest in plan['installed_public_source_sha256'].items():
        if sha(installed / name) != digest: raise ValueError('public adapter source changed')
    rows, _ = public_rows(storage, 'P24', 2)
    pages = [r for r in rows if r['name'] == 'phone__search_contacts'
             and r['args'].get('relationship') in plan['relations']]
    if (len(pages) != 2 or [r['args']['relationship'] for r in pages] != plan['relations']
            or any(r['args'].get('query') or r['args'].get('page_index', 0) != 0
                   or r['args'].get('page_limit') != 20 or not isinstance(r['data'], list)
                   or len(r['data']) >= 20 for r in pages)):
        raise ValueError('fixed observed relation pages differ')
    subjects = [v['sender']['email'] for r in rows
                if r['name'] == 'venmo__show_received_payment_requests' for v in r['data']]
    if len(subjects) != 26: raise ValueError('preserve all 26 observed-request subjects')
    ordinary = {v['email'] for r in pages for v in r['data'] if v['email'] is not None}
    reference = [email in ordinary for email in subjects]
    scope = EvidenceScope('phone.contacts', 'frozen-P24-02-principal', 'frozen-observations', sha(ROOT / PLAN))
    conditions = []
    for label in plan['scenarios']:
        cache = MembershipEvidence(scope, tuple(plan['relations']), max_rows=4096, max_pages=128)
        selected_pages = [] if label == 'no_evidence' else pages[:1] if label == 'one_relation' else pages
        for r in selected_pages:
            cache.observe_page(scope=scope, relation=r['args']['relationship'], page_index=0,
                page_limit=20, records=r['data'], terminal=label != 'rows_without_terminal_evidence',
                receipt_id=r['id'])
        requested_scope = replace(scope, epoch='changed') if label == 'changed_epoch' else (
            replace(scope, principal='different') if label == 'changed_principal' else scope)
        answers = [cache.lookup(email, requested_scope) for email in subjects]
        counts = Counter(a.reason for a in answers)
        conditions.append({'condition': label, 'membership_requests': len(answers),
            'positive': sum(a.value is True for a in answers),
            'negative': sum(a.value is False for a in answers),
            'unknown': sum(a.value is None for a in answers), 'reasons': dict(counts),
            'known_answers_disagree_with_ordinary_complete_union': sum(
                a.value is not None and a.value != ref for a, ref in zip(answers, reference)),
            'complete_union_compared': label == 'complete_union', 'cache': cache.summary()})
    errors = []
    for row in conditions:
        if row['known_answers_disagree_with_ordinary_complete_union']:
            errors.append(row['condition'] + ': known answer mismatch')
        if row['condition'] in ('no_evidence', 'changed_epoch', 'changed_principal') and row['unknown'] != 26:
            errors.append(row['condition'] + ': unsupported evidence accepted')
        if row['condition'] in ('one_relation', 'rows_without_terminal_evidence') and row['negative']:
            errors.append(row['condition'] + ': incomplete absence accepted')
        if row['condition'] == 'complete_union' and row['unknown']:
            errors.append('complete_union: known coverage not used')
    return {'phase': 'P60', 'status': 'complete', 'rows': conditions, 'audit_errors': errors,
        'known_tasks': 1, 'scenarios': len(conditions), 'membership_requests': 26 * len(conditions),
        'ordinary_complete_union_positive': sum(reference), 'ordinary_complete_union_negative': len(reference) - sum(reference),
        'git_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True, cwd=ROOT).strip(),
        'plan_sha256': sha(ROOT / PLAN), 'source_report_sha256': sha(source_report),
        'source_sha256': evidence['source_sha256'],
        'installed_public_source_sha256': plan['installed_public_source_sha256'],
        'implementation_sha256': {name: sha(ROOT / name) for name in (
            'scripts/membership_evidence.py', 'scripts/probe_membership_evidence.py',
            'tests/test_membership_evidence.py', 'scripts/diagnose_p24_public_traces.py')},
        'wall_seconds': time.monotonic() - began, 'model_calls': 0, 'tokenizer_requests': 0,
        'environment_api_requests': 0, 'evaluator_calls': 0, 'database_reads': 0, 'reserved_scenarios_read': 0,
        'scope': plan['scope'], 'runtime_epoch_monitoring_implemented': False,
        'live_llm_interface_installed': False,
        'limits': ['One frozen known trace and analyst-supplied predicate; 156 control requests are not tasks.',
            'Terminal evidence is justified only for this fixed empty-query adapter over frozen observations.',
            'No original API call was skipped or replaced; full-response requests remain outside this interface.',
            'No task-quality, whole-work saving or additional value beyond an ordinary set join measured.']}


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--storage-root', type=Path, required=True); args = p.parse_args()
    signal.alarm(60)
    target = ROOT / 'reports/P60_membership_evidence.json'
    if target.exists(): raise FileExistsError('preserve original result')
    result = run(args.storage_root); write_json(target, result)
    print({k: result[k] for k in ('status', 'scenarios', 'membership_requests', 'audit_errors', 'wall_seconds')})
