"""Supplemental hash coverage of every P81 pair; never impute missing responses.

Usage completeness, recorded requests, and recorded outputs are distinct. This
descriptive supplement preserves the frozen analysis and does not infer causes.
"""
import argparse
from itertools import combinations
from pathlib import Path

from build_budget_visibility_repetition_report import validated
from compare_budget_visibility_repetitions import compare_traces
from run_context_comparison import write_json
from run_handoff_factors import ROOT, read, sha

FIELDS = ('request_sha256', 'public_output_sha256', 'opaque_message_sha256')


def compare_field(left, right, key):
    a, b = [c[key] for c in left], [c[key] for c in right]
    paired = list(zip(a, b))
    observed = [i for i, (x, y) in enumerate(paired, 1) if x is not None and y is not None]
    differences = [i for i in observed if a[i-1] != b[i-1]]
    prefix = 0
    for x, y in paired:
        if x is None or y is None or x != y:
            break
        prefix += 1
    fully_observed = bool(a and b) and all(v is not None for v in a + b)
    if differences:
        relation = 'observed_difference'
    elif fully_observed and len(a) == len(b):
        relation = 'identical_recorded_sequences'
    elif fully_observed:
        relation = 'different_lengths_identical_common_prefix'
    else:
        relation = 'indeterminate'
    return {'relation': relation, 'call_counts': [len(a), len(b)],
        'fully_observed_sequences': fully_observed,
        'observed_pairs': len(observed), 'unobserved_pairs': len(paired) - len(observed),
        'one_sided_calls': abs(len(a) - len(b)), 'equal_initial_calls': prefix,
        'first_observed_difference': differences[0] if differences else None,
        'missing_hashes': [sum(v is None for v in a), sum(v is None for v in b)]}


def compare_prefixes(left, right):
    fields = {key: compare_field(left['calls'], right['calls'], key) for key in FIELDS}
    i = fields['request_sha256']['first_observed_difference']
    outputs = [fields[k]['first_observed_difference'] for k in FIELDS[1:]]
    first_output = min((x for x in outputs if x is not None), default=None)
    return {'fields': fields,
        'both_returned_output_prefixes_equal_before_first_request_difference':
            all(fields[k]['equal_initial_calls'] >= i - 1 for k in FIELDS[1:]) if i is not None else None,
        'first_observed_returned_output_difference': first_output,
        'recorded_requests_equal_through_first_returned_output_difference':
            fields['request_sha256']['equal_initial_calls'] >= first_output if first_output is not None else None}


def run(storage):
    _, report, stability, _ = validated()
    path = ROOT / 'reports/P81_prefix_coverage.json'
    if path.exists():
        raise FileExistsError('preserve_first_prefix_supplement')
    expected = {(g['task_id'], g['time_visibility'], a, b) for g in report['groups']
                for a, b in combinations(g['run_ids'], 2)}
    actual = [(p['task_id'], p['time_visibility'], *p['run_ids']) for p in stability['pairs']]
    if len(actual) != 24 or len(set(actual)) != 24 or set(actual) != expected:
        raise ValueError('all_exact_dependent_pairs_required')
    rows, notice_sources = [], {}
    for pair in stability['pairs']:
        a, b = [stability['traces'][rid] for rid in pair['run_ids']]
        canonical = compare_traces(a, b)
        if any(pair[k] != v for k, v in canonical.items()):
            raise ValueError('frozen_pair_summary_changed')
        row = {'task_id': pair['task_id'], 'time_visibility': pair['time_visibility'],
            'run_ids': pair['run_ids'], **compare_prefixes(a, b),
            'frozen_both_known_complete': pair['both_known_complete'],
            'first_request_difference_is_current_wall_only':
                pair['first_request_difference_is_current_wall_only']}
        idx = pair['first_request_difference']
        wall = []
        if idx is not None:
            for t in (a, b):
                source = storage / 'records/context_pilot' / t['run_id'] / 'budget_observations.json'
                if sha(source) != t['notices_sha256']:
                    raise ValueError('audited_budget_notice_changed')
                notice_sources[t['run_id']] = sha(source)
                matches = [v for v in read(source) if v['next_call_id'] == f'call_{idx:03d}'
                           and v['model_attempted']]
                if len(matches) != 1:
                    raise ValueError('single_attempted_notice_required')
                value = matches[0]['measured_state']['remaining']['wall_seconds_at_snapshot']
                if type(value) is not int:
                    raise ValueError('integer_wall_observation_required')
                wall.append(value)
        row['wall_seconds_at_first_request_difference'] = wall or None
        row['absolute_wall_difference_seconds'] = abs(wall[1] - wall[0]) if wall else None
        rows.append(row)
    result = {'phase': 'P81_prefix_coverage', 'supplemental_descriptive_analysis': True,
        'dependent_pairs': 24, 'independent_tasks': 4, 'rows': rows,
        'source_sha256': {p: sha(ROOT / p) for p in
            ('reports/P81_repetitions.json', 'reports/P81_trajectory_stability.json',
             'reports/P81_server_session.json')},
        'private_notice_sha256': notice_sources, 'script_sha256': sha(Path(__file__)),
        'unknown_usage_imputed': False, 'missing_response_treated_as_equal': False,
        'private_reasoning_inspected_semantically': False, 'causal_timing_effect_identified': False,
        'model_visible_token_sequences_compared': False,
        'additional_generations': 0, 'additional_api_calls': 0, 'additional_evaluations': 0,
        'interpretation': 'Equality of recorded JSON requests and output hashes is distinct from usage completeness. Equal observed prefixes do not establish equality of missing responses or unattempted continuations.'}
    write_json(path, result)
    print({'pairs': len(rows), 'unknown_usage_imputed': False})
    return result


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--storage-root', type=Path, required=True)
    run(p.parse_args().storage_root)
