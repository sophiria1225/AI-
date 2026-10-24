"""Check a closed paper's public files and recompute its reported comparisons.

Standard library only. This checks published records, not private raw receipts,
the truth of evaluator judgments, PDF layout, or scientific novelty.
"""
import argparse
from collections import Counter
import hashlib
from itertools import combinations, product
import json
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FOLDER = 'papers/202610_letter/execution_evidence_focus'
PUBLIC_ROOTS = {'papers', 'scripts', 'reports', 'configs', 'materials', 'docs', 'tests'}


def public_path(root, name):
    path = PurePosixPath(name)
    if (not isinstance(name, str) or path.is_absolute() or not path.parts
            or path.parts[0] not in PUBLIC_ROOTS or '..' in path.parts):
        raise ValueError('public_relative_path_required')
    result = root.joinpath(*path.parts)
    if not result.resolve().is_relative_to(root.resolve()):
        raise ValueError('outside_public_checkout')
    current = root
    for part in path.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError('public_file_symlink_not_supported')
    return result


def digest(path):
    if not path.is_file() or path.stat().st_size > 64 * 1024 * 1024:
        raise ValueError('missing_or_oversized_public_file:' + path.name)
    result = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()


def read(path):
    if path.stat().st_size > 16 * 1024 * 1024:
        raise ValueError('oversized_public_JSON')
    return json.loads(path.read_text())


def count(value):
    if type(value) is not int or value < 0:
        raise ValueError('nonnegative_integer_required')
    return value


def whole_task(rows):
    """Keep every planned row; missing costs and unknown usage are distinct."""
    if len({r['run_id'] for r in rows}) != len(rows):
        raise ValueError('duplicate_condition')
    measured = [r for r in rows if type(r.get('known_total_tokens')) is int]
    known = sum(count(r['known_total_tokens']) for r in measured)
    usage_rows = [r for r in rows if type(r.get('unknown_usage_calls')) is int]
    unknown = sum(count(r['unknown_usage_calls']) for r in usage_rows)
    full_known = len(measured) == len(usage_rows) == len(rows) and unknown == 0
    evaluated = [r for r in rows if r.get('record_status') == 'evaluated']
    if any(type(r.get('success')) is not bool for r in evaluated):
        raise ValueError('evaluated_success_missing')
    def total(key):
        values = [r[key] for r in rows if type(r.get(key)) is int]
        return sum(map(count, values)) if len(values) == len(rows) else None
    return dict(planned_rows=len(rows), evaluated=len(evaluated),
        success=sum(r['success'] for r in evaluated),
        failed=sum(not r['success'] for r in evaluated),
        unevaluated=len(rows)-len(evaluated), known_logical_tokens=known,
        unknown_usage_calls=unknown, rows_without_usage_count=len(rows)-len(usage_rows),
        rows_without_token_count=len(rows)-len(measured),
        full_logical_tokens=known if full_known else None,
        model_calls=total('model_calls'), api_requests=total('api_requests'))


def action_comparisons(rows, structures):
    """Cross products remain dependent comparisons, never independent tasks."""
    if len({r['id'] for r in rows}) != len(rows):
        raise ValueError('duplicate_execution_id')
    if len({r['id'] for r in structures}) != len(structures):
        raise ValueError('duplicate_structure_id')
    syntax = {r['id']: r['structure'] for r in structures}
    if set(syntax) != {r['id'] for r in rows}:
        raise ValueError('structure_execution_cohorts_differ')
    cases = sorted({r['case'] for r in rows})
    output = []
    for left, right in combinations(cases, 2):
        pairs = list(product([r for r in rows if r['case'] == left],
                             [r for r in rows if r['case'] == right]))
        eligible = [(a, b) for a, b in pairs if
                    a['structured_submissions'] > 0 and b['structured_submissions'] > 0
                    and a['suffix_saved_programs'] > 0 and b['suffix_saved_programs'] > 0]
        output.append(dict(left=left, right=right, pairs=len(pairs),
            independent_samples=False, comparable_executed_pairs=len(eligible),
            unavailable_pairs=len(pairs)-len(eligible),
            public_output_equal=sum(syntax[a['id']]['public_output_sha256'] ==
                                    syntax[b['id']]['public_output_sha256'] for a,b in pairs),
            syntax_equal=sum(syntax[a['id']]['syntax_actions_sha256'] ==
                             syntax[b['id']]['syntax_actions_sha256'] for a,b in eligible),
            request_sequence_equal=sum(a['suffix_request_sequence_sha256'] ==
                                       b['suffix_request_sequence_sha256'] for a,b in eligible),
            public_execution_result_equal=sum(a['suffix_execution_evidence_sha256'] ==
                                              b['suffix_execution_evidence_sha256'] for a,b in eligible),
            both_without_structured_calls=sum(a['structured_submissions'] ==
                                             b['structured_submissions'] == 0 for a,b in pairs)))
    return output


def verify(root, folder_name=DEFAULT_FOLDER):
    folder = public_path(root, folder_name)
    manifest = read(folder / 'build_manifest.json')
    bindings = dict(manifest['source_sha256'])
    for name, expected in manifest['generated_sha256'].items():
        full = folder_name + '/' + name
        if full in bindings and bindings[full] != expected:
            raise ValueError('conflicting_binding')
        bindings[full] = expected
    if not 1 <= len(bindings) <= 2048:
        raise ValueError('binding_count_outside_bound')
    for name, expected in bindings.items():
        if digest(public_path(root, name)) != expected:
            raise ValueError('public_file_changed:' + name)
    layout, review = (read(folder / n) for n in ('layout.json', 'visual_review.json'))
    pdf_hash = digest(folder / 'draft.pdf')
    if not all(x['pdf_sha256'] == pdf_hash for x in (manifest, layout, review)):
        raise ValueError('PDF_links_disagree')
    if digest(folder / 'visual_review.json') != manifest['visual_review_sha256']:
        raise ValueError('visual_review_changed')
    if (layout['pages'] != manifest['pages'] or layout['body_pages'] != manifest['body_pages']
            or review['pages'] != list(range(1, layout['pages']+1))
            or layout['visual_reviewed_pages'] != review['pages']):
        raise ValueError('page_records_disagree')
    sources = ('reports/P82_comparison.json', 'reports/P93_public_action_structure.json',
               'reports/P94_saved_action_execution.json',
               'materials/20261024_p94_results/comparison.json')
    if any(name not in bindings for name in sources):
        raise ValueError('required_closed_reports_not_bound')
    p82, p93, p94, comparison = (read(public_path(root,n)) for n in sources)
    if p82['audit_errors'] or p94['status'] != 'complete' or p93['status'] != 'complete':
        raise ValueError('closed_reports_required')
    rows = p82['rows']
    dimensions = [(r['task_id'], r['repetition'], r['time_visibility']) for r in rows]
    tasks = sorted({r['task_id'] for r in rows})
    if (len(tasks) != 4 or Counter(dimensions) != Counter(product(tasks,(1,2),
            ('measured','not_exposed','late_half'))) or len(rows) != p82['planned_rows']):
        raise ValueError('all_24_factorial_cells_required')
    executions = p94['conditions']
    case_counts = Counter(r['case'] for r in executions)
    if len(executions) != 18 or len(case_counts) != 6 or set(case_counts.values()) != {3}:
        raise ValueError('all_18_execution_cells_required')
    if not all(r['status'] == 'complete' and r['public_prefix_matched'] for r in executions):
        raise ValueError('completed_matched_prefixes_required')
    recomputed = action_comparisons(executions,p93['rows'])
    stored = {frozenset((p['left'],p['right'])):p for p in comparison['cross']}
    if len(stored) != 15 or len(comparison['cross']) != 15:
        raise ValueError('all_15_cross_comparisons_required')
    shared = ('pairs','independent_samples','comparable_executed_pairs','unavailable_pairs',
              'request_sequence_equal','public_execution_result_equal','both_without_structured_calls')
    for row in recomputed:
        saved = stored[frozenset((row['left'],row['right']))]
        if any(row[k] != saved[k] for k in shared):
            raise ValueError('stored_execution_comparison_disagrees')
    prefix_api = sum(count(r['prefix_api_requests']) for r in executions)
    next_api = sum(count(r['suffix_api_requests']) for r in executions)
    programs = sum(count(r['saved_program_executions']) for r in executions)
    if (prefix_api + next_api != p94['environment_api_requests']
            or prefix_api + next_api != comparison['total_api_requests']
            or programs != p94['saved_program_executions']
            or programs != comparison['total_program_executions']):
        raise ValueError('execution_cost_totals_disagree')
    return dict(status='verified_published_files_and_arithmetic',
        manifest_sha256=digest(folder/'build_manifest.json'), checked_bindings=len(bindings),
        pdf_sha256=pdf_hash, recorded_pages=layout['pages'], P82=whole_task(rows),
        P82_by_policy={p:whole_task([r for r in rows if r['time_visibility']==p])
                      for p in ('measured','not_exposed','late_half')},
        independent_tasks=4, P94=dict(conditions=len(executions),
            saved_contexts=1, prefix_api_requests=prefix_api, next_api_requests=next_api,
            total_api_requests=prefix_api+next_api, total_program_executions=programs,
            all_15_cross_comparisons=recomputed),
        scope='Public bytes and arithmetic only; no private receipts, evaluator replay, '
              'PDF layout reinspection, literature assessment, or scientific sufficiency check.',
        new_model_generations=0, new_environment_api_requests=0, new_evaluations=0)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo-root', type=Path, default=ROOT)
    parser.add_argument('--folder', default=DEFAULT_FOLDER)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = verify(args.repo_root.resolve(), args.folder)
    rendered = json.dumps(result,ensure_ascii=False,indent=2)+'\n'
    if args.output:
        with args.output.open('x') as output:
            output.write(rendered)
        print(json.dumps({k:result[k] for k in ('status','checked_bindings','pdf_sha256')}))
    else:
        print(rendered,end='')
