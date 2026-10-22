"""Fixed P45 eight-cell continuation comparison on four known development tasks."""
import argparse
import datetime as dt
from pathlib import Path
import signal
import subprocess
import time

from audit_documentation_origin import audit as audit_origin
from budget_signal import digest, snapshot
from code_agent_interface import CODE_TOOLS
from documentation_comparison import ARMS, add_notification, build_condition
from inspect_input_exposure import check_resume, frozen_sources
from later_handoff_sources import prepare_later_sources
from local_llama import count_input
from probe_inference_cache import live_identity
from residual_output_budget import admission
from run_context_comparison import write_json
from run_handoff_factors import ROOT, read, sha, run_branch

PLAN = 'configs/P45_documentation_comparison_v01.json'
PREFLIGHT = 'reports/P45_prefix_checks.json'
ACTIVATION = 'reports/P45_activation_v01.json'


def sources(storage, root):
    prior, original, tools, schemas, prepared = prepare_later_sources(storage, root)
    plan = read(root / PLAN)
    if plan['phase'] != 'P45' or plan['arms'] != list(ARMS):
        raise ValueError('outside the fixed documentation-display comparison')
    for key in ('source_plan', 'source_runs', 'boundary_after_model_calls', 'max_calls',
                'max_total_tokens', 'max_wall_seconds', 'max_setup_seconds', 'recent_complete_turns'):
        if plan[key] != prior[key]:
            raise ValueError('original sources or budgets changed: ' + key)
    if (original['max_output_tokens'] != 4096 or original['model']['num_ctx'] != 65536
            or plan['output_reservation'] != 'residual' or plan['notification'] != 'both'
            or len(prepared) != 4):
        raise ValueError('fixed common controls or cohort changed')
    calibration = read(root / 'reports/P39_calibration_audit.json')
    if (not calibration['all_six_validated'] or calibration['unknown_usage_calls']
            or calibration['source_report_sha256'] != sha(root / 'reports/P39_inference_cache_v02.json')):
        raise ValueError('cache calibration is not closed and audited')
    previous = read(root / 'reports/P33_prefix_checks.json')
    if (not previous['all_four_attempted'] or not previous['all_observable_prefixes_match']
            or [r['boundary_manifest_sha256'] for r in previous['rows']] !=
               [p['boundary_manifest_sha256'] for p in prepared]):
        raise ValueError('restoration evidence does not cover the fixed boundaries')
    report = read(root / 'reports/P44_documentation_origin.json')
    integrity = read(root / 'reports/P44_documentation_origin_integrity.json')
    if (not report['additional_generation_design_gate'] or integrity['errors']
            or integrity['report_sha256'] != sha(root / 'reports/P44_documentation_origin.json')
            or audit_origin(root, storage) != integrity):
        raise ValueError('complete P44 measurements and display audit required')
    return plan, original, tools, schemas, prepared


def frozen_hashes(root):
    paths = list((root / 'scripts').glob('*.py')) + list((root / 'tests').glob('test_*.py'))
    paths += [root / p for p in (PLAN, 'configs/P29_stateful_code_v01.json',
        'configs/P31_handoff_factors_v01.json', 'configs/P32_handoff_factors_v01.json',
        'configs/python_export_image_v01.json', 'docs/experiments/P45_documentation_comparison.md',
        'reports/P39_calibration_audit.json', 'reports/P39_inference_cache_v02.json',
        'reports/P33_prefix_checks.json', 'reports/P44_documentation_origin.json',
        'reports/P44_documentation_origin_integrity.json')]
    return {str(p.relative_to(root)): sha(p) for p in sorted(paths)}


def run_order(prepared):
    return [(number, item, arm) for number, item in enumerate(prepared, 1)
            for arm in (ARMS if number % 2 else ARMS[::-1])]


def cell_id(number, arm):
    if arm not in ARMS:
        raise ValueError('unknown comparison condition')
    return f'P45_{number:02d}_{arm.upper()}'


def preflight(storage, root):
    folder = storage / 'records/context_pilot/P45_preflight_v01'
    target = root / PREFLIGHT
    if folder.exists() or target.exists():
        raise FileExistsError('preserve preflight records, including failures')
    plan, original, _, _, prepared = sources(storage, root)
    hashes = frozen_hashes(root)
    commit = frozen_sources(root, tuple(hashes))
    resume = check_resume(storage)
    identity, end = live_identity(storage, original, 360)
    folder.mkdir(parents=True)
    started = time.monotonic()
    result = {'phase': 'P45_preflight', 'status': 'running', 'rows': [],
              'all_eight_inputs_checked': False, 'model_identity': identity,
              'server_lease_end': end, 'source_hashes': hashes, 'git_commit': commit,
              'research_resume': resume, 'prepared_at': dt.datetime.now(dt.timezone.utc).isoformat(),
              'input_count_requests': 0, 'failed_input_count_requests': 0,
              'model_generations': 0, 'environment_api_requests': 0, 'evaluator_calls': 0,
              'reserved_scenarios_read': 0, 'restoration_evidence_reused': 'reports/P33_prefix_checks.json',
              'restoration_rechecked_before_each_generation': True}
    try:
        for item in prepared:
            config = {**original, **{k: plan[k] for k in ('max_calls', 'max_total_tokens', 'max_wall_seconds')},
                      'max_api_requests': original['api_budget_by_task'][item['task_id']]}
            state = snapshot(config, [], item['prefix']['manifest']['state']['api_requests'], 0, 0)
            row = {'source_run': item['source_run'], 'boundary_manifest_sha256': item['boundary_manifest_sha256'],
                   'conditions': {}}
            result['rows'].append(row)
            for arm in ARMS:
                if (storage / '.runtime/P45.stop').exists():
                    raise InterruptedError('explicit P45 stop')
                remaining = 300 - (time.monotonic() - started)
                if remaining <= 0:
                    raise TimeoutError('preflight deadline')
                conversation, transfer = build_condition(item, arm)
                base, formatting = conversation.for_model(original['observation_page_characters'])
                saved = storage / 'records/context_pilot/P44_documentation_origin_v01' / (
                    item['source_run'] + '_' + arm + '_private.json')
                if read(saved) != base or formatting != {'text_fallback_turns': 0, 'paged_spans': 0}:
                    raise ValueError('base input differs from the audited P44 view')
                supplied = add_notification(base, state)
                path = folder / (item['source_run'] + '_' + arm + '_private.json')
                write_json(path, supplied)
                entry = {'base_messages_sha256': digest(base), 'input_sha256': sha(path),
                         'model_messages_sha256': digest(supplied), 'notification_state': state,
                         'notification_characters': len(supplied[-1]['content']),
                         'transfer': transfer}
                row['conditions'][arm] = entry
                cfg = {**original['model'], 'temperature': original['agent_temperature'],
                       'seed': original['seed'] + 8, 'num_predict': original['max_output_tokens'],
                       'cache_prompt': False}
                result['input_count_requests'] += 1
                try:
                    entry.update(count_input(cfg, supplied, CODE_TOOLS, timeout=min(30, remaining)))
                except Exception:
                    result['failed_input_count_requests'] += 1
                    raise
                entry['admission'] = admission(plan['max_total_tokens'], entry['input_tokens'],
                                               cfg['num_predict'], cfg['num_ctx'], 'residual')
                if not entry['admission']['admitted']:
                    raise ValueError('initial input cannot fit the unchanged budget')
                write_json(folder / 'status.json', result)
        result.update(status='complete', all_eight_inputs_checked=True)
    except Exception as error:
        result.update(status='failed', error_type=type(error).__name__)
        (folder / 'error_private.txt').write_text(str(error))
        raise
    finally:
        result['wall_seconds'] = time.monotonic() - started
        write_json(folder / 'status.json', result)
        write_json(target, result)
    return result


def activate(storage, root):
    target = root / ACTIVATION
    if target.exists():
        raise FileExistsError('preserve activation')
    pre = read(root / PREFLIGHT)
    if (pre['status'] != 'complete' or not pre['all_eight_inputs_checked']
            or pre['input_count_requests'] != 8 or pre['failed_input_count_requests']
            or pre['source_hashes'] != frozen_hashes(root)):
        raise ValueError('preparation is incomplete or stale')
    write_json(target, {'phase': 'P45', 'source_hashes': pre['source_hashes'],
        'preflight_sha256': sha(root / PREFLIGHT), 'research_resume': check_resume(storage),
        'source_boundaries': [r['boundary_manifest_sha256'] for r in pre['rows']],
        'all_eight_conditions_frozen_before_inference': True,
        'activated_at': dt.datetime.now(dt.timezone.utc).isoformat()})


def run(storage, root):
    plan, original, tools, schemas, prepared = sources(storage, root)
    freeze, pre = read(root / ACTIVATION), read(root / PREFLIGHT)
    if (freeze['source_hashes'] != frozen_hashes(root)
            or freeze['preflight_sha256'] != sha(root / PREFLIGHT)
            or freeze['source_boundaries'] != [p['boundary_manifest_sha256'] for p in prepared]
            or freeze['research_resume'] != check_resume(storage)):
        raise ValueError('frozen experiment or resumption changed')
    order = run_order(prepared)
    max_cell_seconds = plan['max_setup_seconds'] + plan['max_wall_seconds'] + 180 + 60
    identity, end = live_identity(storage, original, len(order) * max_cell_seconds)
    if identity != pre['model_identity']:
        raise ValueError('prepared server identity changed')
    folder = storage / 'records/context_pilot' / plan['batch_id']
    folder.mkdir(exist_ok=False)
    write_json(folder / 'frozen_plan.json', plan)
    write_json(folder / 'activation.json', freeze)
    write_json(folder / 'preflight.json', pre)
    state = {'phase': 'P45', 'status': 'running', 'rows': [], 'completed': [], 'active': None,
             'planned': [cell_id(n, arm) for n, _, arm in order],
             'started_at': dt.datetime.now(dt.timezone.utc).isoformat(), 'model_identity': identity,
             'server_lease_end': end, 'reserved_scenarios_read': 0,
             'git_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip()}
    def save():
        state['updated_at'] = dt.datetime.now(dt.timezone.utc).isoformat()
        write_json(folder / 'status.json', state)
    try:
        save()
        for number, item, arm in order:
            if (storage / '.runtime/P45.stop').exists():
                raise InterruptedError('explicit P45 stop')
            current, _ = live_identity(storage, original, max_cell_seconds)
            if current != identity:
                raise ValueError('same idle inference runtime required')
            rid = cell_id(number, arm)
            state['active'] = rid; save()
            signal.alarm(max_cell_seconds)
            result = run_branch(storage, root, plan, original, tools, schemas, item, arm, rid)
            row = {k: result[k] for k in ('run_id', 'task_id', 'arm', 'stop_reason', 'model_calls',
                'known_total_tokens', 'unknown_usage_calls', 'api_requests', 'prefix_api_requests', 'wall_seconds')}
            state['rows'].append(row); save()
            if (result['setup']['status'] != 'matched_observable_prefix'
                    or result['unknown_usage_calls'] or result['unknown_effect_requests']
                    or result['stop_reason'] in ('runtime_error', 'cleanup_error', 'setup_failure')):
                raise ValueError('unknown usage/effects, restoration, cache policy or runtime failure')
            evaluated = subprocess.run([str(storage / '.runtime/appworld/venv/bin/python'),
                str(root / 'scripts/evaluate_context_trial.py'), '--appworld-root',
                str(storage / '.runtime/appworld/r18_probe_01'), '--trial',
                str(storage / 'records/context_pilot' / rid)], capture_output=True, text=True, timeout=180)
            (folder / (rid + '_evaluation.log')).write_text(evaluated.stdout + evaluated.stderr)
            if evaluated.returncode:
                raise ValueError('independent evaluation failed')
            row['success'] = read(storage / 'records/context_pilot' / rid / 'evaluation.json')['official_success']
            state['completed'].append(rid); save()
            signal.alarm(0)
            print({k: row[k] for k in ('run_id', 'stop_reason', 'model_calls', 'known_total_tokens', 'success')}, flush=True)
        state.update(status='complete', active=None, finished_at=dt.datetime.now(dt.timezone.utc).isoformat())
    except Exception as error:
        state.update(status='stopped', error_type=type(error).__name__,
                     finished_at=dt.datetime.now(dt.timezone.utc).isoformat())
        (folder / 'error_private.txt').write_text(str(error))
    finally:
        signal.alarm(0)
        state['not_run'] = [rid for rid in state['planned'] if rid not in {r['run_id'] for r in state['rows']}
                            and rid != state['active']]
        state['unevaluated'] = [r['run_id'] for r in state['rows'] if r['run_id'] not in state['completed']]
        save()
    return 0 if state['status'] == 'complete' else 1


def interrupt(*_):
    raise TimeoutError('bounded P45 execution interrupted')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--storage-root', type=Path, required=True)
    parser.add_argument('--repo-root', type=Path, default=ROOT)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--preflight', action='store_true'); modes.add_argument('--activate', action='store_true')
    args = parser.parse_args()
    signal.signal(signal.SIGALRM, interrupt); signal.signal(signal.SIGTERM, interrupt)
    if args.preflight:
        result = preflight(args.storage_root, args.repo_root)
        print({k: result[k] for k in ('status', 'input_count_requests', 'failed_input_count_requests')})
    elif args.activate:
        activate(args.storage_root, args.repo_root)
    else:
        raise SystemExit(run(args.storage_root, args.repo_root))
