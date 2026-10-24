"""Summarize the closed P98 public records, retaining all comparison units."""
import argparse
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path

from recorded_action_agreement import compare_runs, summarize_pairs

FLAGS = ('equal_public_without_completed_submission', 'different_syntax_same_nonempty_API')


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def summarize(report):
    if report['status'] != 'complete' or len(report['rows']) != 24 or len(report['pairs']) != 60:
        raise ValueError('all_twenty_four_runs_and_sixty_pairs_required')
    runs = {r['run_id']: r for r in report['rows']}
    if len(runs) != 24 or compare_runs(report['rows']) != report['pairs']:
        raise ValueError('public_comparison_recalculation_differs')
    slots = [s for p in report['pairs'] for s in p['rows']]
    matching = [s for s in slots if s['prior_API_prefix_equal'] is True]
    if (summarize_pairs(slots) != report['all_aligned']
            or summarize_pairs(matching) != report['matched_prior_API_prefix']):
        raise ValueError('all_comparison_totals_required')
    inventory = []; patterns = []; task_summary = []
    for r in report['rows']:
        for c in r['calls']:
            inventory.append(dict(run_id=r['run_id'], task_id=r['task_id'],
                time_visibility=r['time_visibility'], repetition=r['repetition'],
                call_id=c['call_id'], ordinal=c['ordinal'], known_total_tokens=c['known_total_tokens'],
                API_requests=c['API_requests'], response_status=c['response']['status'],
                submitted_tool_calls=c['submitted_tool_calls'], completed_submission=c['completed_submission'],
                execution_kinds=c['execution_kinds']))
    for flag in FLAGS:
        for matched_only in (False, True):
            locations = set(); by_task = Counter()
            for p in report['pairs']:
                for s in p['rows']:
                    if s[flag] and (not matched_only or s['prior_API_prefix_equal'] is True):
                        by_task[p['task_id']] += 1
                        locations.update((p[side], s['ordinal']) for side in ('left', 'right'))
            selected = [(runs[r], runs[r]['calls'][i - 1]) for r, i in sorted(locations)]
            kinds = Counter()
            for _, c in selected: kinds.update(c['execution_kinds'])
            patterns.append(dict(pattern=flag, matched_prior_API_prefix_only=matched_only,
                dependent_comparison_slots=sum(by_task.values()), by_task=dict(by_task),
                distinct_recorded_calls=len(locations), distinct_runs=len({r for r, _ in locations}),
                distinct_known_tasks=len({r['task_id'] for r, _ in selected}),
                execution_kinds=dict(kinds),
                tool_submission_counts=dict(Counter(str(c['submitted_tool_calls']) for _, c in selected)),
                locations=[dict(run_id=r, ordinal=i, call_id=runs[r]['calls'][i - 1]['call_id']) for r, i in sorted(locations)],
                calls_are_not_independent_tasks=True))
    for task in dict.fromkeys(r['task_id'] for r in report['rows']):
        selected = [s for p in report['pairs'] if p['task_id'] == task for s in p['rows']]
        task_summary.append(dict(task_id=task, all_aligned=summarize_pairs(selected),
            matched_prior_API_prefix=summarize_pairs([s for s in selected if s['prior_API_prefix_equal'] is True])))
    if (len(inventory) != report['original_model_attempts']
            or sum(c['known_total_tokens'] or 0 for c in inventory) != report['original_known_tokens']
            or sum(c['known_total_tokens'] is None for c in inventory) != report['original_unknown_usage_calls']
            or sum(c['API_requests'] for c in inventory) != report['original_API_requests']):
        raise ValueError('all_original_costs_required')
    return dict(patterns=patterns, by_task=task_summary, all_aligned=report['all_aligned'],
        matched_prior_API_prefix=report['matched_prior_API_prefix'],
        total_recorded_calls=len(inventory),
        unknown_response_calls=sum(c['response_status'] == 'unknown_response' for c in inventory),
        no_structured_tool_calls=sum(c['response_status'] == 'no_structured_tool_calls' for c in inventory),
        structured_but_not_completed_calls=sum(c['response_status'] == 'structured_calls' and not c['completed_submission'] for c in inventory),
        completed_submission_calls=sum(c['completed_submission'] for c in inventory),
        independent_known_tasks=4, condition_pairs_independent=False), inventory


def csv_write(path, rows):
    with path.open('x', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0])); writer.writeheader()
        writer.writerows({k: json.dumps(v, sort_keys=True) if isinstance(v, (dict, list)) else v for k, v in r.items()} for r in rows)


def build(root):
    path = root / 'reports/P98_recorded_action_agreement.json'; report = json.loads(path.read_text())
    for rel, expected in report['source_sha256'].items():
        if sha(root / rel) != expected: raise ValueError('original_P98_source_changed:' + rel)
    summary, inventory = summarize(report)
    target = root / 'materials/20261024_p98_results'; target.mkdir(exist_ok=False)
    summary.update(source_sha256=sha(path), summarizer_sha256=sha(Path(__file__)),
                   new_model_generations=0, new_API_requests=0, new_evaluations=0, raw_record_reads=0)
    with (target / 'summary.json').open('x') as stream:
        json.dump(summary, stream, ensure_ascii=False, indent=2); stream.write('\n')
    keys = ('run_id', 'task_id', 'time_visibility', 'repetition', 'success', 'stop_reason',
            'model_calls', 'api_requests', 'known_total_tokens', 'unknown_usage_calls')
    csv_write(target / 'all_24_conditions.csv', [{k: r[k] for k in keys} for r in report['rows']])
    csv_write(target / 'all_426_recorded_calls.csv', inventory)
    csv_write(target / 'all_60_condition_pairs.csv', [{k: v for k, v in p.items() if k != 'rows'} for p in report['pairs']])
    csv_write(target / 'all_1132_aligned_slots.csv', [dict(task_id=p['task_id'], left=p['left'], right=p['right'],
        **{k: s.get(k) for k in ('ordinal', 'status', 'public_equal', 'syntax_equal', 'API_class',
            'nonempty_API_equal', 'API_result_equal', 'public_tool_results_equal', 'prior_API_prefix_equal', *FLAGS)})
        for p in report['pairs'] for s in p['rows']])
    print(json.dumps({k: summary[k] for k in ('total_recorded_calls', 'unknown_response_calls',
        'no_structured_tool_calls', 'structured_but_not_completed_calls', 'completed_submission_calls')}))


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--repo-root', type=Path, default=Path(__file__).resolve().parents[1])
    build(p.parse_args().repo_root.resolve())
