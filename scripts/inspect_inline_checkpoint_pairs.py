"""Public-only P119 cost decomposition and pre-intervention request checks."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess

from inspect_checkpoint_pair_controls import costs
from plot_receipt_history_results import read, sha, write_new, require, TASKS

PLAN = 'configs/P119_reporting_v01.json'
OUTPUT = 'reports/P119_pair_controls.json'
POLICIES = ('single_checkpoint', 'inline_checkpoint')


def pre_intervention_requests(separate, inline):
    if not all(r['record_status'] in ('evaluated', 'unevaluated') for r in (separate, inline)):
        return {'available': False, 'reason': 'unaccounted_slot', 'positions': []}
    events = [e for e in separate['checkpoint_controls'] if e.get('model_attempted')]
    require(len(events) <= 1, 'one_separate_summary_dispatch_required')
    sequences = [[c for c in r['request_checks'] if c['role'] == 'agent'] for r in (separate, inline)]
    offered = [i for i, c in enumerate(sequences[1]) if c.get('inline_offered')]
    require(len(offered) <= 1, 'one_inline_offer_dispatch_required')
    boundaries = {'separate': events[0]['after_model_calls'] if events else None,
                  'inline': offered[0] if offered else None}
    for policy, boundary in boundaries.items():
        if boundary is not None:
            require(type(boundary) is int and 0 <= boundary <= len(sequences[0 if policy == 'separate' else 1]),
                    'valid_pre_intervention_agent_boundary_required')
    finite = [b for b in boundaries.values() if b is not None]
    planned = min(finite) if finite else max(map(len, sequences))
    positions = []
    for index in range(planned):
        hashes = [seq[index].get('request_sha256') if index < len(seq) else None for seq in sequences]
        present = all(type(h) is str and len(h) == 64 for h in hashes)
        positions.append({'agent_ordinal': index + 1, 'separate_request_sha256': hashes[0],
            'inline_request_sha256': hashes[1], 'comparable': present,
            'same_complete_request_file': hashes[0] == hashes[1] if present else None})
    comparable = [p for p in positions if p['comparable']]
    different = [p['agent_ordinal'] for p in comparable if not p['same_complete_request_file']]
    return {'available': True, 'agent_calls_before_intervention': boundaries,
        'scope': 'before either first intervention dispatch' if finite else 'all realized agent requests; neither intervention dispatched',
        'planned_positions': planned, 'comparable_positions': len(comparable),
        'equal_request_files': sum(p['same_complete_request_file'] for p in comparable),
        'unavailable_positions': planned - len(comparable),
        'first_different_request_ordinal': different[0] if different else None,
        'response_file_hashes_used_as_behavior_labels': False,
        'causal_future_behavior_claim': False, 'positions': positions}


def immediate(row):
    if row['checkpoint_policy'] == 'single_checkpoint':
        events = [e for e in row.get('checkpoint_controls', []) if 'ordinary_next_input_tokens' in e]
        a, b = 'ordinary_next_input_tokens', 'checkpoint_next_input_tokens'
    else:
        events = [e for e in row.get('checkpoint_controls', []) if e['status'] == 'checkpoint_decided']
        a, b = 'ordinary_input_tokens', 'compacted_input_tokens'
    require(len(events) <= 1, 'one_counted_checkpoint_decision_required')
    if not events:
        return None
    before, after = events[0][a], events[0][b]
    require(type(before) is int and type(after) is int and before > 0 and after > 0,
            'positive_next_input_counts_required')
    return {'ordinary_input_tokens': before, 'compacted_input_tokens': after,
            'difference': before - after, 'whole_task_savings_claim': False}


def compare(rows):
    lookup = {(r['task_id'], r['checkpoint_policy']): r for r in rows}
    require(len(rows) == len(lookup) == 8 and
            set(lookup) == {(task, policy) for task in TASKS for policy in POLICIES}, 'all_eight_slots_required')
    pairs = []
    for task in TASKS:
        separate, inline = (lookup[task, policy] for policy in POLICIES)
        s, i = costs(separate), costs(inline)
        if i['accounted']:
            require(i['roles']['focus']['calls'] == 0 and i['roles']['focus']['known_subtotal'] == 0,
                    'inline_arm_must_not_generate_separate_summary')
        actor_known = s['accounted'] and i['accounted'] and all(
            c['roles']['agent']['exact_total'] is not None for c in (s, i))
        actor_delta = i['roles']['agent']['exact_total'] - s['roles']['agent']['exact_total'] if actor_known else None
        summary_cost = s['roles']['focus']['exact_total'] if s['accounted'] else None
        exact = s['exact_total'] is not None and i['exact_total'] is not None
        total_delta = i['exact_total'] - s['exact_total'] if exact else None
        if exact:
            require(total_delta == actor_delta - summary_cost, 'whole_cost_decomposition_mismatch')
        pairs.append({'task_id': task, 'separate_success': separate.get('success'),
            'inline_success': inline.get('success'), 'separate_cost': s, 'inline_cost': i,
            'separate_checkpoint_installed': separate.get('checkpoint_installed'),
            'inline_checkpoint_installed': inline.get('checkpoint_installed'),
            'agent_including_inline_metadata_token_difference': actor_delta,
            'separate_summary_exact_tokens': summary_cost,
            'inline_minus_separate_whole_task_tokens': total_delta,
            'immediate_counted_inputs': {p: immediate(lookup[task, p]) for p in POLICIES},
            'immediate_reduction_is_not_total_savings': True,
            'summary_input_is_not_measured_savings': True,
            'pre_intervention_request_comparison': pre_intervention_requests(separate, inline)})
    return pairs


def run(root, storage, expected_head):
    require(not (root / OUTPUT).exists(), 'preserve_existing_pair_analysis')
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip()
    require(head == expected_head, 'fixed_analysis_head_required')
    from run_whole_task_inline_checkpoint_pipeline import checked_ci
    ci = checked_ci(root, head)
    plan = read(root / PLAN)
    require(plan['analysis'] == 'P119_public_reporting' and plan['planned_conditions'] == 8 and
            plan['model_calls'] == plan['API_requests'] == plan['tokenizer_requests'] == 0,
            'fixed_public_only_analysis_required')
    for rel, digest in plan['source_sha256'].items():
        require(sha(root / rel) == digest, 'fixed_pair_analysis_source_changed:' + rel)
    closed = read(storage / '.runtime/P119_closure_once_end.json')
    audit_path, session_path = root / 'reports/P119_comparison.json', root / 'reports/P119_server_session.json'
    require(sha(audit_path) == closed['audit_sha256'] and sha(session_path) == closed['session_sha256'],
            'original_closed_cohort_required')
    audit, session = read(audit_path), read(session_path)
    start = read(root / 'reports/P119_execution_start_20261025.json')
    require(start['preparation_merge']['head'] == plan['source_implementation_head'] and
            audit['plan_sha256'] == sha(root / 'configs/P119_whole_task_inline_checkpoint_v01.json'),
            'fixed_original_P119_implementation_required')
    require(audit['phase'] == session['phase'] == 'P119' and not audit['audit_errors'] and
            audit['owned_processes_absent'] and session['owned_processes_absent'] and
            session['status'] == 'stopped' and session['audit_source_sha256'] == sha(audit_path),
            'closed_clean_cohort_required')
    result = {'phase': 'P119_public_pair_controls', 'created_at': datetime.now(timezone.utc).isoformat(),
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
