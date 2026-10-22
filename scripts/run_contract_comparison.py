"""Fixed P47 twelve-cell display/contract comparison on four known development tasks."""
import argparse
import datetime as dt
from pathlib import Path
import signal
import subprocess
import time

from budget_signal import digest, snapshot
from code_agent_interface import CODE_TOOLS
from documentation_comparison import add_notification
from contract_comparison import ARMS, CONDITIONS, build_condition
from run_documentation_comparison import sources as previous_sources
from inspect_input_exposure import check_resume, frozen_sources
from later_handoff_sources import prepare_later_sources
from local_llama import count_input
from probe_inference_cache import live_identity
from residual_output_budget import admission
from run_context_comparison import write_json
from run_handoff_factors import ROOT, read, sha, run_branch

PLAN = 'configs/P47_contract_comparison_v01.json'
PREFLIGHT = 'reports/P47_prefix_checks.json'
ACTIVATION = 'reports/P47_activation_v01.json'


def sources(storage, root):
    prior, original, tools, schemas, prepared = previous_sources(storage, root)
    plan = read(root / PLAN)
    if (plan['phase'] != 'P47' or plan['arms'] != list(ARMS)
            or plan['max_feedback_characters'] != 16000
            or plan['conditions'] != {key: list(value) for key, value in CONDITIONS.items()}):
        raise ValueError('outside fixed display/contract comparison')
    for key in ('source_plan', 'source_runs', 'boundary_after_model_calls', 'max_calls',
                'max_total_tokens', 'max_wall_seconds', 'max_setup_seconds', 'recent_complete_turns',
                'output_reservation', 'notification'):
        if plan[key] != prior[key]:
            raise ValueError('prior source or common control changed: ' + key)
    probe = read(root / 'reports/P46_contract_feedback.json')
    if (not probe['all_eight_cells_inspected'] or probe['programs_checked'] != 52
            or probe['feedback_candidates'] != 4 or probe['candidate_tasks'] != 3
            or any(probe[k] for k in ('model_calls', 'environment_api_requests', 'evaluator_calls'))
            or probe['source_sha256']['feedback'] != sha(root / 'scripts/contract_feedback.py')):
        raise ValueError('closed passive component probe required')
    return plan, original, tools, schemas, prepared


def frozen_hashes(root):
    paths = list((root / 'scripts').glob('*.py')) + list((root / 'tests').glob('test_*.py'))
    paths += [root / p for p in (PLAN, 'configs/P29_stateful_code_v01.json',
        'configs/P31_handoff_factors_v01.json', 'configs/P32_handoff_factors_v01.json',
        'configs/python_export_image_v01.json', 'docs/experiments/P47_contract_comparison.md',
        'reports/P39_calibration_audit.json', 'reports/P39_inference_cache_v02.json',
        'reports/P33_prefix_checks.json', 'reports/P44_documentation_origin.json',
        'reports/P44_documentation_origin_integrity.json', 'reports/P46_contract_feedback.json')]
    return {str(p.relative_to(root)): sha(p) for p in sorted(paths)}


def run_order(prepared):
    orders = (ARMS, ARMS[1:] + ARMS[:1], ARMS[2:] + ARMS[:2], (ARMS[0], ARMS[2], ARMS[1]))
    if len(prepared) != 4:
        raise ValueError('fixed four-task cohort required')
    return [(number, item, arm) for number, (item, order) in enumerate(zip(prepared, orders, strict=True), 1)
            for arm in order]


def cell_id(number, arm):
    if arm not in ARMS:
        raise ValueError('unknown comparison condition')
    return f'P47_{number:02d}_{arm.upper()}'


def preflight(storage, root):
    folder = storage / 'records/context_pilot/P47_preflight_v01'
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
    result = {'phase': 'P47_preflight', 'status': 'running', 'rows': [],
              'all_twelve_inputs_checked': False, 'model_identity': identity,
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
                if (storage / '.runtime/P47.stop').exists():
                    raise InterruptedError('explicit P47 stop')
                remaining = 300 - (time.monotonic() - started)
                if remaining <= 0:
                    raise TimeoutError('preflight deadline')
                conversation, transfer = build_condition(item, arm)
                base, formatting = conversation.for_model(original['observation_page_characters'])
                saved = storage / 'records/context_pilot/P44_documentation_origin_v01' / (
                    item['source_run'] + '_' + CONDITIONS[arm][0] + '_private.json')
                if read(saved) != base or formatting != {'text_fallback_turns': 0, 'paged_spans': 0}:
                    raise ValueError('base input differs from the audited P44 view')
                supplied = add_notification(base, state)
                path = folder / (item['source_run'] + '_' + CONDITIONS[arm][0] + '_private.json')
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
        result.update(status='complete', all_twelve_inputs_checked=True)
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
    check = read(root / 'reports/P47_runtime_checks.json')
    if (not check['all_checks_passed'] or check['fixture_dispatches'] != 4
            or check['model_calls'] or check['environment_api_requests'] or check['evaluator_calls']
            or len(check['rows']) != 2
            or any(r['programs'] != 4 or not r['container_removed'] for r in check['rows'])
            or any(sha(root / 'scripts' / name) != value for name, value in check['source_sha256'].items())):
        raise ValueError('synthetic execution checks are incomplete or stale')
    if (pre['status'] != 'complete' or not pre['all_twelve_inputs_checked']
            or pre['input_count_requests'] != 12 or pre['failed_input_count_requests']
            or pre['source_hashes'] != frozen_hashes(root)):
        raise ValueError('preparation is incomplete or stale')
    write_json(target, {'phase': 'P47', 'source_hashes': pre['source_hashes'],
        'preflight_sha256': sha(root / PREFLIGHT),
        'runtime_check_sha256': sha(root / 'reports/P47_runtime_checks.json'), 'research_resume': check_resume(storage),
        'source_boundaries': [r['boundary_manifest_sha256'] for r in pre['rows']],
        'all_twelve_conditions_frozen_before_inference': True,
        'activated_at': dt.datetime.now(dt.timezone.utc).isoformat()})


def run(storage, root):
    plan, original, tools, schemas, prepared = sources(storage, root)
    freeze, pre = read(root / ACTIVATION), read(root / PREFLIGHT)
    if (freeze['source_hashes'] != frozen_hashes(root)
            or freeze['preflight_sha256'] != sha(root / PREFLIGHT)
            or freeze['runtime_check_sha256'] != sha(root / 'reports/P47_runtime_checks.json')
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
    state = {'phase': 'P47', 'status': 'running', 'rows': [], 'completed': [], 'active': None,
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
            if (storage / '.runtime/P47.stop').exists():
                raise InterruptedError('explicit P47 stop')
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
    raise TimeoutError('bounded P47 execution interrupted')


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
