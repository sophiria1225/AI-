"""Offline audit of all P54 receipts; never opens a model, world or evaluator."""
import argparse
import json
from pathlib import Path

from probe_ranked_subset_access import (PLAN, ROOT, extract_targets, fixed_access_contract,
                                        read, sha, value_sha, validate_sources)
from probe_prefix_replay import db_hashes
from ranked_subset_read import ReadReceipt, subset_maximum
from run_context_comparison import write_json


def audit(storage):
    plan = read(ROOT / PLAN)
    folder = storage / 'records/context_pilot' / plan['batch_id']
    state = read(folder / 'status.json')
    errors, checks = [], []

    def check(value, label):
        checks.append(label)
        if not value:
            errors.append(label)

    source, provenance, world_root, _ = validate_sources(storage, plan)
    check(read(folder / 'plan.json') == plan, 'fixed plan')
    check(state['status'] == 'complete', 'closed batch')
    check(state['planned'] == plan['arms'] and [r['mode'] for r in state['rows']] == plan['arms']
          and not state['not_attempted'], 'all three planned cases once in order')
    for path, digest in state['source_sha256'].items():
        check(sha(ROOT / path) == digest, 'fixed source ' + path)
    check(all(state[k] == 0 for k in ('model_generations', 'tokenizer_requests', 'evaluator_calls',
                                      'reserved_scenarios_read')), 'no generation tokenization evaluation or reserved access')
    spans = read(source / 'spans.json')
    targets = extract_targets(spans, plan['maximum_target_ids'])
    expected_dbs = {name: item['sha256'] for name, item in read(
        source / 'boundaries/manifests' / (plan['boundary'] + '.json'))['files'].items()
        if name.startswith('dbs/')}
    all_winners = []
    independent_winners = None
    for row in state['rows']:
        mode = row['mode']; case = folder / mode
        check(read(case / 'result.json') == row, 'final case row ' + mode)
        check(row['status'] == 'complete' and row['bridge_exit_code'] == 0, 'case and child closed ' + mode)
        check(row['ground_truth_loaded'] is False, 'ground truth not loaded ' + mode)
        check(read(case / 'target_ids_private.json') == targets
              and row['target_ids_sha256'] == value_sha(targets), 'same public target set ' + mode)
        before = read(case / 'prefix_db_hashes.json')
        check(before == expected_dbs, 'prefix saved DB files ' + mode)
        final_dbs = db_hashes(world_root / 'experiments/outputs' / row['run_id'] / 'tasks' / provenance['task_id'] / 'dbs')
        check(final_dbs == before and row['read_db_files_unchanged'] is True,
              'final DB files and recorded per-read checks ' + mode)
        calls = read(case / 'calls_private.json')
        setup = [c for c in calls if c['stage'] == 'setup']
        lookup = [c for c in calls if c['stage'] == 'lookup']
        check(len(setup) == row['setup_api_requests_attempted'] == 5, 'five setup requests ' + mode)
        for index, entry in enumerate(setup, 1):
            action = spans[f's{index}']['action']
            app, api = action['name'].split('__')
            check(entry['request'] == {'op': 'call', 'call': {'app': app, 'api': api,
                  'args': json.loads(action['arguments'])}} and entry['response']['ok']
                  and entry['response']['result'] == spans[f's{index}']['observation'],
                  f'prefix receipt {mode} {index}')
        check(len(lookup) == row['lookup_api_requests_attempted'] == row['access']['requests_attempted'],
              'lookup request accounting ' + mode)
        check(row['api_requests_attempted'] == len(calls) == len(setup) + len(lookup)
              and len(lookup) <= plan['max_requests_per_arm'], 'all API accounting and cap ' + mode)
        check(sum(len(json.dumps(c['response'], ensure_ascii=False).encode()) for c in lookup)
              == row['lookup_response_utf8_bytes'], 'all returned bytes ' + mode)
        contract = fixed_access_contract(plan['contract'], value_sha(before))
        cursor = 0

        def replay(api, arguments, is_page):
            nonlocal cursor
            entry = lookup[cursor]; cursor += 1
            expected = {'op': 'call', 'call': {'app': 'spotify', 'api': api, 'args': arguments}}
            check(entry['request'] == expected, f'access order and request {mode} {cursor}')
            response = entry['response']
            check(response['ok'] and not response['result']['declared_complete'], f'read response {mode} {cursor}')
            payload = json.loads(response['result']['observation'])
            return ReadReceipt(contract.source_id, contract.snapshot_id, payload if is_page else [payload])

        reproduced = subset_maximum(targets, contract=contract,
            point_read=lambda key: replay('show_song', {'song_id': key}, False),
            page_read=lambda index, size: replay('search_songs',
                {'query': '', 'sort_by': '-like_count', 'page_index': index, 'page_limit': size}, True),
            mode=mode, max_requests=plan['max_requests_per_arm'], page_limit=plan['page_limit'],
            exploratory_pages=plan['exploratory_pages'])
        saved = read(case / 'access_result_private.json')
        check(reproduced == saved and cursor == len(lookup), 'pure receipt replay ' + mode)
        check({k: v for k, v in saved.items() if k != 'winners'} == row['access'], 'public access fields ' + mode)
        check(value_sha(saved['winners']) == row['winners_sha256']
              and len(saved['winners']) == row['winner_count'], 'winner hash and count ' + mode)
        check(len(json.dumps(saved['winners'], ensure_ascii=False).encode()) == row['projected_output_utf8_bytes'],
              'projected result bytes ' + mode)
        all_winners.append(saved['winners'])
        if mode == 'point':
            records = [json.loads(c['response']['result']['observation']) for c in lookup]
            check([r['song_id'] for r in records] == targets, 'point baseline covers every supplied target once')
            maximum = max(r['like_count'] for r in records)
            independent_winners = [{k: r[k] for k in ('song_id', 'like_count', 'title')}
                for r in sorted(records, key=lambda r: r['song_id']) if r['like_count'] == maximum]
        check(row['wall_seconds_including_cleanup'] > 0, 'nonzero whole case time ' + mode)
    check(independent_winners is not None and all(v == independent_winners for v in all_winners),
          'all results equal independent exhaustive calculation including ties')
    check(state['all_completed_outputs_equal'] is True, 'reported result equality')
    check(state['api_requests_attempted'] == sum(r['api_requests_attempted'] for r in state['rows'])
          <= plan['max_total_api_requests'], 'whole batch API allocation')
    check(state['wall_seconds'] >= sum(r['wall_seconds_including_cleanup'] for r in state['rows']),
          'whole batch time includes cases')
    audit_report = {'phase': 'P54', 'audit_errors': errors, 'checks': checks,
        'original_status_sha256': sha(folder / 'status.json'), 'additional_api_requests': 0,
        'additional_model_generations': 0, 'evaluator_calls': 0, 'tokenizer_requests': 0,
        'scope': 'Saved receipts, exact source, counters, final saved DB files, pure replay and independent maximum over exhaustive public reads. Not autonomous task correctness or an independent retest of the API.'}
    write_json(ROOT / 'reports/P54_ranked_subset_access_audit.json', audit_report)
    if errors:
        raise ValueError('audit failed: ' + repr(errors))
    write_json(ROOT / 'reports/P54_ranked_subset_access.json', {**state,
        'original_status_sha256': sha(folder / 'status.json'),
        'audit_report': 'reports/P54_ranked_subset_access_audit.json'})
    print(json.dumps({'checks': len(checks), 'audit_errors': errors,
                      'api_requests': state['api_requests_attempted'], 'wall_seconds': state['wall_seconds']}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--storage-root', type=Path, required=True)
    audit(parser.parse_args().storage_root.resolve())
