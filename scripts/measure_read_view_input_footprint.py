"""P104: once-only offline counts of all six handwritten read-view boundaries."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import time

from inspect_input_exposure import check_resume
from inspect_recorded_action_agreement import sha, verify_ci
from model_provenance import verified_model
from probe_prompt_identity import render_summary
from probe_public_read_views_live import PROGRAMS
from public_display import CODE_TOOLS
from read_view_input_footprint import (POLICIES, REPRESENTATIONS, EXPECTED_API,
                                     reconstruct, compare_boundaries, system_prompt)
from tool_choice_local_llama import payload_for

PLAN = 'configs/P104_read_view_input_footprint_v01.json'
OLD_PLAN = 'configs/public_read_views_live_v01.json'
OLD_REPORT = 'reports/public_read_views_live_results_20261024.json'
ZERO = ('model_generations', 'environment_API_requests', 'saved_code_executions',
        'evaluations', 'task_databases_read', 'reserved_scenarios_read')
FIXED = dict(phase='P104', policies=list(POLICIES), representations=list(REPRESENTATIONS),
    handwritten_programs_per_policy=6, max_renderings=24, max_renderer_seconds=120,
    max_renderer_rss_bytes=2**31, max_wall_seconds=600, max_file_bytes=16777216,
    automatic_retries=0, private_output='records/context_pilot/P104_read_view_input_footprint_v01',
    private_source='records/context_pilot/read_views_public_live_v01',
    source_plan='configs/P29_stateful_code_v01.json',
    runtime_record='records/context_pilot/P80_pipeline_v01/server_runtime.json',
    runtime_commit='620d2225cc436ab0b001e3200e590e3b286ef9ab',
    stop_marker='.runtime/P104.stop', tool_choice='auto', reasoning_budget_tokens=-1,
    seed=70, temperature=1.0, max_output_tokens=4096, cache_prompt=False,
    task_quality_measured=False, observed_LLM_usage=False, novel_method_claim=False,
    **{k: 0 for k in ZERO})


def read(path):
    return json.loads(path.read_text())


def write_new(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')


def private_read(storage, plan, rel):
    path = storage / rel
    path.resolve().relative_to(storage.resolve())
    if (path.is_symlink() or path.stat().st_size > plan['max_file_bytes']
            or sha(path) != plan['private_source_sha256'][rel]):
        raise ValueError('changed_or_unbounded_private_record')
    return read(path)


def guard(storage, plan, deadline):
    if (storage / plan['stop_marker']).exists():
        raise InterruptedError('explicit_P104_stop')
    if time.monotonic() >= deadline:
        raise TimeoutError('finite_P104_deadline')


def render_batch(storage, plan, build, command, model, folder, cases, operation, deadline):
    manifest = folder / 'manifest_private.json'
    write_new(manifest, dict(recorded_server_command=command, model_path=str(model),
                           output_dir=str(folder), cases=cases))
    operation['manifest_sha256'] = sha(manifest)
    started = time.monotonic()
    process = None
    try:
        with (folder / 'renderer_private.log').open('x') as log:
            process = subprocess.Popen([str(storage / build['renderer_relative']), str(manifest)],
                                       stdout=log, stderr=log, start_new_session=True)
        operation.update(pid=process.pid, status='rendering', sampled_peak_rss_bytes=0)
        while process.poll() is None:
            guard(storage, plan, min(deadline, started + plan['max_renderer_seconds']))
            sample = subprocess.run(['ps', '-o', 'rss=', '-p', str(process.pid)],
                                    capture_output=True, text=True, timeout=10)
            if sample.returncode == 0 and sample.stdout.strip():
                operation['sampled_peak_rss_bytes'] = max(operation['sampled_peak_rss_bytes'],
                                                         int(sample.stdout.strip()) * 1024)
                if operation['sampled_peak_rss_bytes'] > plan['max_renderer_rss_bytes']:
                    raise MemoryError('bounded_vocabulary_renderer_RSS')
            time.sleep(.05)
        operation['exit_code'] = process.returncode
        if process.returncode or read(folder / 'renderer_complete.json') != {'renderings': 6, 'decode_calls': 0}:
            raise ValueError('complete_six_renderings_required')
        meta = read(folder / 'renderer_metadata_private.json')
        if (meta['vocabulary_only'] is not True or meta['inference_contexts_created'] != 0
                or meta['decode_calls'] != 0
                or hashlib.sha256(meta['default_template'].encode()).hexdigest() != plan['effective_template_sha256']):
            raise ValueError('fixed_vocabulary_only_renderer_required')
        summaries = []
        for case in cases:
            path = folder / (case['id'] + '_rendered_private.json')
            if path.stat().st_size > plan['max_file_bytes']:
                raise ValueError('bounded_rendered_file_required')
            summaries.append(dict(**render_summary(read(path)), private_rendered_sha256=sha(path)))
        operation.update(status='complete', renderings=6, decode_calls=0,
                         metadata_sha256=sha(folder / 'renderer_metadata_private.json'))
        return summaries
    except BaseException as error:
        operation.update(status='stopped', error_type=type(error).__name__)
        raise
    finally:
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=15)
        operation['owned_process_absent'] = process is None or process.poll() is not None
        operation['wall_seconds'] = time.monotonic() - started


def measure(storage, root, plan, result, output):
    began = time.monotonic()
    deadline = began + plan['max_wall_seconds']
    if any(type(plan.get(k)) is not type(v) or plan[k] != v for k, v in FIXED.items()):
        raise ValueError('fixed_P104_scope_changed')
    guard(storage, plan, deadline)
    # Operational closure only. Never inspect the P101 generation content here.
    pipeline = read(storage / 'records/context_pilot/P101_pipeline_v01/status.json')
    if pipeline.get('status') not in ('complete', 'stopped') or not pipeline.get('server_stopped'):
        raise ValueError('wait_for_P101_owned_server_closure')
    result['research_resume'] = check_resume(storage)
    for rel, expected in plan['source_sha256'].items():
        if sha(root / rel) != expected:
            raise ValueError('fixed_P104_source_changed:' + rel)
    result['source_commit'], result['CI'] = verify_ci(root)
    old, original_plan = read(root / OLD_REPORT), read(root / OLD_PLAN)
    if old['status'] != 'complete' or not old['all_six_observations_equal'] or len(old['conditions']) != 2:
        raise ValueError('closed_two_policy_source_required')
    status_rel = plan['private_source'] + '/status.json'
    if plan['private_source_sha256'][status_rel] != old['private_status_sha256']:
        raise ValueError('original_closed_status_changed')
    private_read(storage, plan, status_rel)
    if [hashlib.sha256(p.encode()).hexdigest() for p in PROGRAMS] != original_plan['program_sha256']:
        raise ValueError('original_six_handwritten_sources_changed')
    task_rel = original_plan['known_public_task']
    if plan['private_source_sha256'][task_rel] != original_plan['known_public_task_sha256']:
        raise ValueError('original_public_task_changed')
    public = private_read(storage, plan, task_rel)
    original = read(root / plan['source_plan'])
    selection_config = read(root / original['model_selection'])
    required_private = {status_rel, task_rel, plan['runtime_record'], selection_config['download_record']}
    for policy in POLICIES:
        prefix = plan['private_source'] + '/' + policy
        required_private.update(prefix + f'/program_{n:02d}/view_program_private.json' for n in range(1, 7))
        required_private.update(prefix + f'/record_{n:02d}_private.json'
                                for n in range(1, sum(EXPECTED_API[policy]) + 1))
    if set(plan['private_source_sha256']) != required_private:
        raise ValueError('exact_closed_private_inventory_required')
    for rel in (original['model_selection'], selection_config['file_manifest']):
        if sha(storage / rel) != sha(root / rel):
            raise ValueError('storage_model_configuration_changed')
    private_read(storage, plan, selection_config['download_record'])
    prompt = system_prompt(original)
    if hashlib.sha256(prompt.encode()).hexdigest() != plan['shared_system_prompt_sha256']:
        raise ValueError('fixed_shared_interface_guidance_changed')
    runtime = private_read(storage, plan, plan['runtime_record'])
    selection, _, model = verified_model(original['model_selection'], root=storage)
    command = runtime['command']
    if (runtime['runtime']['commit'] != plan['runtime_commit'] or runtime['model_revision'] != selection['revision']
            or Path(command[command.index('--model') + 1]) != model):
        raise ValueError('fixed_runtime_and_model_required')
    build = read(root / 'reports/P83_renderer_build.json')
    if (build['exit_code'] != 0 or build['runtime_commit'] != plan['runtime_commit']
            or sha(storage / build['renderer_relative']) != build['renderer_sha256']
            or sha(root / 'scripts/render_fallback_chat.cpp') != build['source_cpp_sha256']):
        raise ValueError('fixed_renderer_binary_required')
    for rel, expected in build['library_sha256'].items():
        if sha(storage / rel) != expected:
            raise ValueError('fixed_renderer_dependency_changed')
    for rel, expected in build['header_sha256'].items():
        if sha(storage / build['source_tree_relative'] / rel) != expected:
            raise ValueError('fixed_renderer_header_changed')
    config = dict(original['model'], seed=plan['seed'], temperature=plan['temperature'],
        num_predict=plan['max_output_tokens'], cache_prompt=plan['cache_prompt'],
        tool_choice=plan['tool_choice'], reasoning_budget_tokens=plan['reasoning_budget_tokens'])
    for policy in POLICIES:
        guard(storage, plan, deadline)
        prefix = plan['private_source'] + '/' + policy
        evidences = [private_read(storage, plan, prefix + f'/program_{n:02d}/view_program_private.json')
                     for n in range(1, 7)]
        api_rows = [private_read(storage, plan, prefix + f'/record_{n:02d}_private.json')
                    for n in range(1, sum(EXPECTED_API[policy]) + 1)]
        condition = next(c for c in old['conditions'] if c['policy'] == policy)
        for representation in REPRESENTATIONS:
            boundaries = reconstruct(policy, representation, PROGRAMS, evidences, api_rows, condition,
                prompt=prompt, public_task=public, page_limit=original['observation_page_characters'])
            folder = output / (policy + '_' + representation)
            folder.mkdir()
            cases = []
            metadata = []
            for boundary in boundaries:
                messages = boundary.pop('messages')
                key = f'{policy}_{representation}_{boundary["number"]:02d}'
                request = folder / (key + '_request_private.json')
                write_new(request, payload_for(config, messages, CODE_TOOLS))
                cases.append(dict(id=key, request_path=str(request)))
                metadata.append(dict(policy=policy, representation=representation, **boundary,
                                     request_sha256=sha(request)))
            operation = dict(policy=policy, representation=representation, status='starting', renderings=0)
            result['operations'].append(operation)
            summaries = render_batch(storage, plan, build, command, model, folder, cases, operation, deadline)
            for meta, summary in zip(metadata, summaries, strict=True):
                target = next(r for r in result['rows'] if r['policy'] == policy
                              and r['representation'] == representation and r['after_program'] == meta['after_program'])
                target.update(meta, **summary, status='complete')
    result.update(comparisons=compare_boundaries(result['rows']), status='complete',
        finished_at=datetime.now(timezone.utc).isoformat(), wall_seconds=time.monotonic() - began,
        source_sha256=plan['source_sha256'], private_source_sha256=plan['private_source_sha256'],
        original_API_requests={'eager': 11, 'deferred': 10}, original_model_generations=0,
        total_observed_LLM_usage=None, task_quality_measured=False,
        content_attribution_is_deployable_policy=False, terminal_boundary_is_actual_next_call=False,
        interpretation='Controlled post-hoc input footprints for six handwritten programs; no generated agent trajectory, no overall task token savings, no quality or novelty claim.')


def main(storage, root):
    plan = read(root / PLAN)
    target = root / 'reports/P104_read_view_input_footprint.json'
    if target.exists():
        raise FileExistsError('preserve_every_P104_attempt')
    output = storage / FIXED['private_output']
    output.mkdir(parents=True, exist_ok=False)
    result = dict(phase='P104', status='starting', plan_sha256=sha(root / PLAN),
        started_at=datetime.now(timezone.utc).isoformat(), operations=[],
        rows=[dict(policy=p, representation=v, after_program=n, status='not_attempted', input_tokens=None)
              for p in POLICIES for v in REPRESENTATIONS for n in range(1, 7)], **{k: 0 for k in ZERO})
    began = time.monotonic()
    def expired(*_):
        raise TimeoutError('finite_P104_wall_deadline')
    signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, FIXED['max_wall_seconds'])
    try:
        measure(storage, root, plan, result, output)
    except BaseException as error:
        result.update(status='stopped', error_type=type(error).__name__, wall_seconds=time.monotonic() - began)
        write_new(output / 'error_private.json', dict(type=type(error).__name__, message=str(error)))
        raise
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        write_new(target, result)
    print(json.dumps({k: result[k] for k in ('status', 'comparisons', 'wall_seconds')}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--storage-root', type=Path, required=True)
    args = parser.parse_args()
    main(args.storage_root.resolve(), Path(__file__).resolve().parents[1])
