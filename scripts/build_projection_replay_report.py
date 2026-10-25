"""Publish bounded P124 aggregates from closed records; never replay programs.

Only explicit numeric/boolean/hash fields are exported. Private programs,
returned values, identifiers, namespace names and prompts are never copied.
"""
import argparse
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path


POLICIES = ('eager_cached', 'automatic_projection_cached')
COUNTS = ('logical_requests', 'saved_backend_responses',
          'ordinary_complete_cache_hits', 'projection_hits', 'control_requests',
          'control_request_bytes', 'control_reply_bytes', 'snapshot_controls')
HASHES = ('boundary_sha256', 'stdout_sha256', 'error_sha256')
CHECKS = ('status', 'stdout', 'stdout_truncated', 'error',
          'declared_complete', 'unknown_effects')
ZERO_COUNTS = ('environment_API_requests', 'model_calls', 'tokenizer_calls', 'evaluator_calls')


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def valid_hash(value, size=64):
    return (type(value) is str and len(value) == size
            and all(character in '0123456789abcdef' for character in value))


def number(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def read(path, label, sources):
    path = Path(path)
    require(path.is_file() and not path.is_symlink()
            and path.stat().st_size <= 32 * 1024 * 1024, 'bounded_regular_record_required')
    data = path.read_bytes()
    sources[label] = sha(data)
    value = json.loads(data)
    require(type(value) is dict, 'record_object_required')
    return value


def build_report(private_root, start_path, end_path, manifest_path, prepare_attempt_path):
    root, sources = Path(private_root), {}
    summary = read(root / 'summary.json', 'summary', sources)
    manifest = read(root / 'input_manifest_private.json', 'copied_input_manifest', sources)
    original = read(manifest_path, 'frozen_input_manifest', sources)
    start = read(start_path, 'execution_start', sources)
    end = read(end_path, 'execution_end', sources)
    preparation = read(prepare_attempt_path, 'earlier_prepare_attempt', sources)
    require(preparation.get('command_kind') == 'prepare-only'
            and preparation.get('status') == 'failed'
            and preparation.get('manifest_created') is False
            and preparation.get('historical_records_changed') is False
            and valid_hash(preparation.get('source_head'), 40)
            and all(type(preparation.get(k)) is int and preparation[k] == 0
                    for k in ('generated_programs', 'model_calls', 'environment_API_requests')),
            'recorded_nonexecuting_preparation_failure_required')
    require(manifest == original and sources['copied_input_manifest'] == sources['frozen_input_manifest'],
            'manifest_copy_differs')
    require(summary.get('phase') == manifest.get('phase') == 'P124'
            and summary.get('kind') == manifest.get('kind') == 'fixed_saved_response_prefix_replay',
            'fixed_P124_scope_required')
    require(summary.get('all_20_programs_match') is True
            and summary.get('implementation_unchanged_at_end') is True
            and end.get('status') == 'complete' and end.get('all_20_programs_match') is True,
            'closed_successful_replay_required')
    require(all(type(summary.get(k)) is int and summary[k] == 20 for k in (
        'attempted_generated_programs', 'completed_generated_programs', 'compared_generated_programs')),
        'all_twenty_attempts_required')
    require(all(type(summary.get(k)) is int and summary[k] == 0
                and type(manifest.get(k)) is int and manifest[k] == 0 for k in ZERO_COUNTS),
            'zero_environment_and_inference_work_required')
    require(summary.get('live_environment_counterfactual_proved') is False
            and summary.get('task_quality_or_total_token_savings_established') is False
            and summary.get('private_result_api_requests_meaning') == 'simulated_saved_backend_responses_only',
            'replay_scope_disclaimer_required')
    require(summary.get('input_manifest_sha256') == start.get('manifest_sha256')
            == sources['frozen_input_manifest'] and end.get('summary_sha256') == sources['summary'],
            'execution_record_hash_binding_differs')
    require(valid_hash(start.get('source_head'), 40)
            and start['source_head'] == end.get('source_head'), 'execution_head_differs')
    require(valid_hash(start.get('wrapper_sha256')), 'wrapper_hash_required')
    require(start.get('maximum_generated_programs') == manifest.get('total_generated_programs') == 20
            and start.get('maximum_seconds') == manifest.get('total_seconds') == 600
            and manifest.get('program_seconds') == 30
            and manifest.get('policies') == list(POLICIES)
            and len(manifest.get('programs', [])) == 10, 'fixed_finite_plan_differs')
    ci = start.get('ci')
    require(type(ci) is list and len(ci) == 2 and {r.get('event') for r in ci} == {'push', 'pull_request'}
            and all(r.get('head_sha') == start['source_head'] and r.get('status') == 'completed'
                    and r.get('conclusion') == 'success' for r in ci), 'matching_successful_CI_required')
    require(number(summary.get('wall_seconds')), 'finite_replay_wall_required')
    started, finished = datetime.fromisoformat(start['started_at']), datetime.fromisoformat(end['finished_at'])
    require(started.tzinfo is not None and finished.tzinfo is not None and finished >= started,
            'ordered_timezone_aware_execution_times_required')
    rows = summary.get('programs')
    require(type(rows) is list and len(rows) == 20, 'all_program_rows_required')
    public_rows, arms = [], {}
    for policy in POLICIES:
        selected = [row for row in rows if row.get('policy') == policy]
        require([r.get('program_number') for r in selected] == list(range(1, 11)),
                'ordered_ten_programs_per_policy_required')
        session = read(root / policy / 'session/session_private.json', policy + '_session', sources)
        require(session.get('status') == 'closed' and session.get('container_removed') is True
                and session.get('oom_killed') is False
                and type(session.get('container_exit_code')) is int and session['container_exit_code'] == 0
                and session.get('projection_policy') == policy, 'clean_closed_session_required')
        controls = session.get('controls')
        require(type(controls) is dict and controls and all(v is True for v in controls.values()),
                'all_container_controls_required')
        require(valid_hash(session.get('trusted_bootstrap_sha256'))
                and number(session.get('cleanup_wall_seconds')), 'session_measurements_required')
        session_rows = session.get('programs')
        require(type(session_rows) is list and len(session_rows) == 10, 'ten_session_programs_required')
        expected_checks = set(CHECKS) | ({'paired_boundary', 'paired_stdout_error'} if policy == POLICIES[1] else set())
        for row, execution in zip(selected, session_rows):
            require(type(row.get('checks')) is dict and set(row['checks']) == expected_checks
                    and all(v is True for v in row['checks'].values()), 'all_observable_checks_required')
            require(all(type(row.get(k)) is int and row[k] >= 0 for k in COUNTS)
                    and all(valid_hash(row.get(k)) for k in HASHES)
                    and number(row.get('wall_seconds')), 'bounded_program_aggregates_required')
            require(row['logical_requests'] == row['saved_backend_responses']
                    + row['ordinary_complete_cache_hits'] + row['projection_hits'], 'logical_action_conservation_failed')
            require(row['snapshot_controls'] == 1, 'one_boundary_control_required')
            require(execution.get('program_index') == row['program_number']
                    and execution.get('status') == 'ok' and execution.get('session_usable') is True
                    and execution.get('api_requests') == row['saved_backend_responses']
                    and number(execution.get('wall_seconds')), 'session_summary_accounting_differs')
            public_rows.append({k: row[k] for k in ('policy', 'program_number', 'checks') + COUNTS + HASHES + ('wall_seconds',)})
        arms[policy] = {k: sum(row[k] for row in selected) for k in COUNTS}
        arms[policy].update(programs=10, all_checks_match=True,
            program_wall_seconds_sum=sum(row['wall_seconds'] for row in selected),
            cleanup_wall_seconds=session['cleanup_wall_seconds'],
            container_removed=True, container_controls_passed=len(controls),
            trusted_bootstrap_sha256=session['trusted_bootstrap_sha256'])
    paired = {policy: [r for r in public_rows if r['policy'] == policy] for policy in POLICIES}
    require(all(all(left[k] == right[k] for k in HASHES + ('logical_requests',))
                for left, right in zip(paired[POLICIES[0]], paired[POLICIES[1]])),
            'paired_boundary_stdout_error_or_request_count_differs')
    require(arms[POLICIES[0]]['projection_hits'] == 0, 'control_must_not_project')
    base, candidate = (arms[p]['saved_backend_responses'] for p in POLICIES)
    require(base > 0, 'positive_reference_response_count_required')
    manifests = {}
    for name in ('private_files', 'schema_files', 'implementation_files'):
        binding = manifest.get(name)
        require(type(binding) is dict and binding and all(valid_hash(v) for v in binding.values()),
                'hash_manifest_required')
        manifests[name] = {'count': len(binding), 'mapping_sha256': sha(
            json.dumps(binding, sort_keys=True, separators=(',', ':')).encode())}
    return {
        'phase': 'P124', 'kind': 'closed_saved_response_prefix_replay_report',
        'all_20_programs_match': True, 'programs_per_policy': 10,
        'attempted_generated_programs': 20, 'completed_generated_programs': 20,
        'compared_generated_programs': 20, 'paired_boundaries_matched': 10,
        'arms': arms, 'programs': public_rows,
        'saved_backend_response_reduction': {'net_count': base - candidate,
            'baseline_count': base, 'candidate_count': candidate,
            'fraction': (base - candidate) / base, 'percent': 100 * (base - candidate) / base,
            'partial_hit_count_is_not_net_savings': True},
        'replay_wall_seconds': summary['wall_seconds'],
        'wrapper_timestamp_elapsed_seconds': (finished - started).total_seconds(),
        'started_at': start['started_at'], 'finished_at': end['finished_at'],
        'execution_source_head': start['source_head'], 'execution_wrapper_sha256': start['wrapper_sha256'],
        'matching_push_and_pull_request_CI': True, 'implementation_unchanged_at_end': True,
        'input_manifest_sha256': sources['frozen_input_manifest'],
        'source_summary_sha256': sources['summary'], 'manifest_inventory': manifests,
        'source_sha256': sources, 'report_builder_sha256': sha(Path(__file__).read_bytes()),
        'earlier_preparation_failure': {
            'count': 1, 'source_head': preparation['source_head'], 'command_kind': 'prepare-only',
            'reason_category': 'nonexistent_historical_provenance_file_assumed',
            'generated_programs': 0, 'model_calls': 0, 'environment_API_requests': 0,
            'manifest_created': False, 'historical_records_changed': False,
            'replay_execution_started': False,
        },
        'replay_execution_count': 1,
        **{key: 0 for key in ZERO_COUNTS},
        'live_environment_counterfactual_proved': False,
        'task_quality_or_total_token_savings_established': False,
        'timing_speedup_claimed': False, 'novelty_established': False,
        'independent_review': 'pending_separate_review',
        'scope_limits': [
            'One exposed closed prefix, fixed saved actions and responses; not a whole-task online comparison.',
            'Saved backend responses are simulated response consumption, never environment API dispatch.',
            'Boundary checks cover the recorded plain value/type snapshots and selected full dict roots, not arbitrary identity or alias graphs.',
            'Omitted full responses are not inserted into the candidate complete cache.',
            'Program/control time includes replay instrumentation; fixed policy order and one run do not establish speed.',
            'Control bytes describe interpreter-host traffic, not model input tokens.',
            'Task selection mistakes in the saved programs are preserved, not corrected or independently evaluated.',
            'Private input values, programs, prompts, resource IDs and namespace names are not published.',
        ],
    }


def main():
    parser = argparse.ArgumentParser()
    for name in ('private-root', 'start', 'end', 'manifest', 'prepare-attempt', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    result = build_report(args.private_root, args.start, args.end, args.manifest, args.prepare_attempt)
    with args.output.open('x') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps({'phase': 'P124', 'reported_programs': result['compared_generated_programs'],
                      'net_saved_backend_responses': result['saved_backend_response_reduction']['net_count'],
                      'additional_model_or_environment_calls': 0}))


if __name__ == '__main__':
    main()
