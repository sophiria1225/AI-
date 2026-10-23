"""Separate logical tokens, cache counters and observed time in closed pairs."""
from pathlib import Path

from run_context_comparison import write_json
from run_handoff_factors import ROOT, read, sha

SOURCES = {
    'reports/P64_public_name_audit.json': '8c5dac74fcb69c59b89df936270b5bed8ab00db0abef10feca15f07faebfd283',
    'reports/P66_completion_audit.json': 'f8864e42c0b627f6ffc5dc10636c78573050236beb2b1811115c1248030ca990',
    'reports/P68_completion_audit.json': '36fc231b04efb84758c44c3969c61c0179912114ee1c3feef7c95bc74da4a980',
}


def metrics(row):
    total, inp, out, cached = (row[k] for k in (
        'known_total_tokens', 'input_tokens', 'output_tokens', 'cached_input_tokens'))
    if (row['unknown_usage_calls'] or total != inp + out or not 0 <= cached <= inp
            or not 0 <= row['wall_seconds'] <= row['full_wall_seconds']):
        raise ValueError('known and internally consistent costs required')
    return {'logical_tokens': total, 'cached_input_tokens': cached,
        'input_tokens_minus_cached_counter': inp - cached, 'output_tokens': out,
        'execution_wall_seconds': row['wall_seconds'], 'full_condition_wall_seconds': row['full_wall_seconds']}


def summarize(root=ROOT):
    if any(sha(root / path) != digest for path, digest in SOURCES.items()):
        raise ValueError('closed source changed')
    prior, controlled, export = [read(root / path) for path in SOURCES]
    if any(r['audit_errors'] or not r['server_stopped'] for r in (prior, controlled, export)):
        raise ValueError('closed audited comparisons required')
    rows = []
    baseline = {r['run_id']: r for r in prior['rows']}
    pairs = []
    for row in controlled['rows']:
        reference = baseline[row['baseline_comparison']['reference_run']]
        if row['baseline_comparison']['reference_known_tokens'] != reference['known_total_tokens']:
            raise ValueError('reference cost mismatch')
        pairs.append(('photo_' + row['arm'], reference, row))
    if [r['run_id'] for r in export['rows']] != ['P68_01_EXPORT_NATIVE', 'P68_02_EXPORT_CONTROLLED']:
        raise ValueError('fixed export pair changed')
    pairs.append(('export', *export['rows']))
    for label, reference, current in pairs:
        old, new = metrics(reference), metrics(current)
        difference = {k: new[k] - old[k] for k in old}
        if difference['logical_tokens'] != sum(difference[k] for k in (
                'cached_input_tokens', 'input_tokens_minus_cached_counter', 'output_tokens')):
            raise ValueError('token decomposition differs')
        rows.append({'label': label, 'reference_run': reference['run_id'], 'controlled_run': current['run_id'],
            'reference_success': reference['official_success'], 'controlled_success': current['official_success'],
            'reference': old, 'controlled': new, 'controlled_minus_reference': difference,
            'logical_reduction_fraction': (old['logical_tokens'] - new['logical_tokens']) / old['logical_tokens'],
            'wall_difference_is_causal_speedup_estimate': False})
    return {'source_sha256': SOURCES, 'summarizer_sha256': sha(Path(__file__)), 'rows': rows,
        'new_model_calls': 0, 'new_api_requests': 0, 'new_evaluator_calls': 0,
        'limits': ['Two photo interfaces share one known task; export is a separate known task.',
            'Input minus cache counter is a token count, not measured FLOPs, energy or monetary price.',
            'Full condition time contains setup, execution and cleanup, but not separately shared server load or evaluator time.',
            'One execution per condition at different times; observed wall differences do not estimate a general causal speedup.',
            'No cost conversion coefficient is assumed and no outcome is relabeled.']}


if __name__ == '__main__':
    target = ROOT / 'reports/letter_cost_metric_scope_20261023.json'
    if target.exists(): raise FileExistsError('preserve prior derivation')
    result = summarize(); write_json(target, result)
    for row in result['rows']:
        print(row['label'], row['controlled_minus_reference'])
