"""Closed P118 public-only paired cost decomposition and pre-summary request hashes."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess

from plot_receipt_history_results import read, sha, write_new, require, TASKS

PLAN = 'configs/P118_pair_controls_v01.json'
OUTPUT = 'reports/P118_pair_controls.json'
POLICIES = ('full', 'single_checkpoint')


def costs(row):
    if row['record_status'] not in ('evaluated', 'unevaluated'):
        return {'accounted': False, 'known_subtotal': None, 'exact_total': None,
                'unknown_usage': None, 'roles': None}
    roles = row['usage_by_role']
    require(set(roles) == {'agent', 'focus'}, 'both_roles_required')
    result = {}
    for name, usage in roles.items():
        require(all(type(usage[k]) is int and usage[k] >= 0
                    for k in ('calls', 'unknown_usage', 'input_tokens', 'output_tokens')),
                'nonnegative_role_accounting_required')
        require(usage['unknown_usage'] <= usage['calls'], 'invalid_unknown_count')
        subtotal = usage['input_tokens'] + usage['output_tokens']
        result[name] = {**usage, 'known_subtotal': subtotal,
                        'exact_total': subtotal if usage['unknown_usage'] == 0 else None}
    known = sum(r['known_subtotal'] for r in result.values())
    unknown = sum(r['unknown_usage'] for r in result.values())
    require(known == row['known_total_tokens'] and unknown == row['unknown_usage_calls'] and
            sum(r['calls'] for r in result.values()) == row['model_calls'], 'role_total_mismatch')
    return {'accounted': True, 'known_subtotal': known,
            'exact_total': known if unknown == 0 else None,
            'unknown_usage': unknown, 'roles': result}


def pre_summary_requests(full, checkpoint):
    if not all(r['record_status'] in ('evaluated', 'unevaluated') for r in (full, checkpoint)):
        return {'available': False, 'reason': 'unaccounted_slot', 'positions': []}
    events = [e for e in checkpoint['checkpoint_controls'] if e.get('model_attempted')]
    require(len(events) <= 1, 'at_most_one_summary_opportunity')
    sequences = [[c for c in r['request_checks'] if c['role'] == 'agent'] for r in (full, checkpoint)]
    boundary = events[0]['after_model_calls'] if events else None
    if boundary is not None:
        require(type(boundary) is int and boundary >= 0 and
                boundary <= len(sequences[1]), 'invalid_pre_summary_boundary')
        planned = boundary
    else:
        planned = max(map(len, sequences))
    positions = []
    for index in range(planned):
        hashes = [seq[index].get('request_sha256') if index < len(seq) else None for seq in sequences]
        present = all(type(h) is str and len(h) == 64 for h in hashes)
        positions.append({'agent_ordinal': index + 1, 'full_request_sha256': hashes[0],
                          'checkpoint_request_sha256': hashes[1],
                          'comparable': present, 'same_complete_request_file': hashes[0] == hashes[1] if present else None})
    comparable = [p for p in positions if p['comparable']]
    different = [p['agent_ordinal'] for p in comparable if not p['same_complete_request_file']]
    return {'available': True, 'summary_was_attempted': bool(events),
            'pre_summary_agent_calls': boundary,
            'scope': 'before the summary request' if events else 'all realized agent requests; no summary request was dispatched',
            'planned_positions': planned, 'comparable_positions': len(comparable),
            'equal_request_files': sum(p['same_complete_request_file'] for p in comparable),
            'unavailable_positions': planned - len(comparable),
            'first_different_request_ordinal': different[0] if different else None,
            'response_file_hashes_used_as_behavior_labels': False,
            'causal_future_behavior_claim': False, 'positions': positions}


def compare(rows):
    lookup = {(r['task_id'], r['checkpoint_policy']): r for r in rows}
    require(len(rows) == len(lookup) == 8 and
            set(lookup) == {(task, policy) for task in TASKS for policy in POLICIES}, 'all_eight_slots_required')
    pairs = []
    for task in TASKS:
        full, checkpoint = (lookup[task, policy] for policy in POLICIES)
        f, c = costs(full), costs(checkpoint)
        if f['accounted']:
            require(f['roles']['focus']['calls'] == 0, 'full_arm_must_not_generate_summary')
        exact = f['exact_total'] is not None and c['exact_total'] is not None
        agent_delta = (c['roles']['agent']['exact_total'] - f['roles']['agent']['exact_total']) if exact else None
        summary_cost = c['roles']['focus']['exact_total'] if c['accounted'] else None
        total_delta = c['exact_total'] - f['exact_total'] if exact else None
        if exact:
            require(total_delta == agent_delta + summary_cost, 'whole_cost_decomposition_mismatch')
        controls = [e for e in checkpoint.get('checkpoint_controls', []) if e['status'] != 'below_trigger_or_recent_only']
        require(len(controls) <= 1, 'one_opportunity_required')
        control = controls[0] if controls else None
        before = control.get('ordinary_next_input_tokens') if control else None
        after = control.get('checkpoint_next_input_tokens') if control else None
        pairs.append({'task_id': task, 'full_success': full.get('success'),
            'checkpoint_success': checkpoint.get('success'), 'full_cost': f, 'checkpoint_cost': c,
            'control_status': control['status'] if control else None,
            'checkpoint_installed': checkpoint.get('checkpoint_installed'),
            'agent_token_difference': agent_delta, 'summary_exact_tokens': summary_cost,
            'whole_task_token_difference': total_delta,
            'immediate_counted_input_reduction': before - after
                if type(before) is int and type(after) is int else None,
            'immediate_reduction_is_not_total_savings': True,
            'pre_summary_request_comparison': pre_summary_requests(full, checkpoint)})
    return pairs


def run(root, storage, expected_head):
    require(not (root / OUTPUT).exists(), 'preserve_existing_pair_analysis')
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip()
    require(head == expected_head, 'fixed_analysis_head_required')
    from run_whole_task_single_checkpoint_pipeline import checked_ci
    ci = checked_ci(root, head)
    plan = read(root / PLAN)
    require(plan['analysis'] == 'P118_public_pair_controls' and plan['planned_conditions'] == 8 and
            plan['model_calls'] == plan['API_requests'] == plan['tokenizer_requests'] == 0,
            'fixed_public_only_analysis_required')
    for rel, digest in plan['source_sha256'].items():
        require(sha(root / rel) == digest, 'fixed_pair_analysis_source_changed:' + rel)
    closed = read(storage / '.runtime/P118_closure_once_end.json')
    audit_path, session_path = root / 'reports/P118_comparison.json', root / 'reports/P118_server_session.json'
    require(sha(audit_path) == closed['audit_sha256'] and sha(session_path) == closed['session_sha256'],
            'original_closed_cohort_required')
    audit, session = read(audit_path), read(session_path)
    start = read(root / 'reports/P118_execution_start_20261025.json')
    require(start['preparation_merge']['head'] == plan['source_implementation_head'] and
            audit['plan_sha256'] == sha(root / 'configs/P118_whole_task_single_checkpoint_v01.json'),
            'fixed_original_P118_implementation_required')
    require(audit['phase'] == session['phase'] == 'P118' and not audit['audit_errors'] and
            audit['owned_processes_absent'] and session['owned_processes_absent'] and
            session['status'] == 'stopped' and session['audit_source_sha256'] == sha(audit_path),
            'closed_clean_cohort_required')
    result = {'phase': 'P118_public_pair_controls', 'created_at': datetime.now(timezone.utc).isoformat(),
        'git_commit': head, 'ci': ci, 'source_audit_sha256': sha(audit_path),
        'source_session_sha256': sha(session_path), 'plan_sha256': sha(root / PLAN),
        'pairs': compare(audit['rows']), 'ordinary_control_criteria_met': audit['development_gate_met'],
        'all_four_tasks_retained': True, 'unknown_usage_imputed': False,
        'private_histories_or_summary_text_read': False, 'additional_model_calls': 0,
        'additional_API_requests': 0, 'additional_tokenizer_requests': 0,
        'additional_evaluations': 0, 'manuscript_changed': False,
        'causal_future_behavior_claim': False, 'novel_method_claim': False}
    write_new(root / OUTPUT, result)
    print(json.dumps({'phase': result['phase'], 'pairs': len(result['pairs']), 'additional_model_calls': 0}))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--repo-root', type=Path, required=True)
    parser.add_argument('--storage-root', type=Path, required=True)
    parser.add_argument('--expected-head', required=True)
    args = parser.parse_args()
    run(args.repo_root.resolve(), args.storage_root.resolve(), args.expected_head)
