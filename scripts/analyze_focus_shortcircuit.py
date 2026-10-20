"""Offline analysis of redundant FOCUS drafts; not a new runtime or cost result.

Only prove the current retention set cannot change when it is already all
available spans. The runtime's invalid-output fallback also keeps that set.
No saved trial is edited and no unseen model output is assumed to be valid.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path

from context_preservation import checked_ids, parse_submission, select_focus


def all_retained_certificate(drafts, available, total_drafts, threshold):
    if (not drafts or len(drafts) > total_drafts or total_drafts < 1
            or not 0 < threshold <= 1):
        raise ValueError('invalid planned draft count or threshold')
    required = math.ceil(threshold * total_drafts)
    counts = dict.fromkeys(available, 0)
    rescued = set()
    for draft in drafts:
        # Reuse the baseline's structural validation, without changing its IDs.
        select_focus([draft], available, 1)
        cited = set()
        for step in draft['steps']:
            cited |= checked_ids(step['depends_on'], available)
        for sid in cited:
            counts[sid] += 1
        rescued |= checked_ids(draft['rescued'], available)
    established = {sid for sid, n in counts.items() if n >= required} | rescued
    return set(available) <= established


def analyze(directory):
    read = lambda path: json.loads(path.read_text())
    digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    summary = read(directory / 'summary.json')
    if summary['arm'] != 'focus':
        raise ValueError('only a completed FOCUS trial can be analyzed')
    baseline = Path(__file__).parent / 'context_preservation.py'
    saved_baseline = directory / 'source/context_preservation.py'
    if digest(baseline) != digest(saved_baseline):
        raise ValueError('analysis retention rules differ from the saved baseline')
    plan = read(directory / 'plan.json')
    usage = read(directory / 'usage.json')
    records = read(directory / 'compressions.json')
    groups = []
    for index, call in enumerate(usage):
        if call['role'] != 'focus':
            continue
        if index == 0 or usage[index - 1]['role'] != 'focus':
            groups.append([])
        groups[-1].append(call)
    cycles = []
    for index, calls in enumerate(groups):
        memory = json.loads(read(directory / calls[0]['id'] / 'request.json')['messages'][-1]['content'])['memory']
        available = [span['id'] for span in memory['visible_spans']]
        drafts, at, stopped = [], None, None
        for position, call in enumerate(calls):
            response = read(directory / call['id'] / 'response.json')
            if response['status'] != 'ok':
                stopped = 'unknown_response'
                break
            try:
                draft = parse_submission(response['message'], 'submit_selection')
                drafts.append(draft)
                certified = all_retained_certificate(
                    drafts, available, plan['focus_rollouts'], plan['focus_threshold'])
            except (ValueError, TypeError, KeyError, AttributeError):
                stopped = 'invalid_draft_before_certificate'
                break
            if certified:
                at = position + 1
                break
        later = calls[at:] if at is not None else []
        event = records[index] if index < len(records) else None
        if at is not None and event and event['visible_after'] != available:
            raise ValueError('certificate contradicts the recorded retention outcome')
        cycles.append({
            'cycle': index + 1, 'input_spans': len(available),
            'recorded_draft_calls': len(calls), 'certificate_after_draft': at,
            'prefix_blocker': stopped,
            'later_recorded_calls': len(later),
            'later_calls_known_tokens': sum(c['input_tokens'] + c['output_tokens']
                                            for c in later if c['status'] == 'ok'),
            'later_unknown_usage_calls': sum(c['status'] != 'ok' for c in later),
            'later_recorded_call_seconds': sum(c['wall_seconds'] for c in later),
            'recorded_selection_matches_certificate': (
                event['visible_after'] == available if at is not None and event else None),
            'call_hashes': [{
                'id': call['id'],
                'request_sha256': digest(directory / call['id'] / 'request.json'),
                'response_sha256': digest(directory / call['id'] / 'response.json'),
            } for call in calls],
        })
    return {'run_id': summary['run_id'], 'planned_drafts_per_cycle': plan['focus_rollouts'],
            'threshold': plan['focus_threshold'],
            'required_citation_count': math.ceil(plan['focus_threshold'] * plan['focus_rollouts']),
            'cycles': cycles,
            'source_hashes': {name: digest(directory / name) for name in (
                'summary.json', 'plan.json', 'usage.json', 'compressions.json')},
            'retention_module_sha256': digest(baseline),
            'scope': 'Certificate concerns one retention decision only. Later measured call '
                     'costs are candidates for omission, not measured end-to-end savings. '
                     'Future seeds, numerical cache effects, new actions and final success '
                     'are not reproduced. Invalid prefixes are never silently repaired.'}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--trial', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = analyze(args.trial)
    result['script_sha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    result.update(inference_calls=0, environment_actions=0)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'run': result['run_id'], 'certified_cycles': sum(
        row['certificate_after_draft'] is not None for row in result['cycles']),
        'later_recorded_calls': sum(row['later_recorded_calls'] for row in result['cycles'])}))


if __name__ == '__main__':
    main()
