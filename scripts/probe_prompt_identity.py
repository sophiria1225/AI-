"""Bounded offline reconstruction of all P66/P68 executed request pairs."""
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
from model_provenance import verified_model
from probe_notice_calibration import confirmed_ci
from prompt_identity import PAIR_RUNS, renamed_request, selected_requests
from run_context_comparison import write_json
from run_handoff_factors import ROOT, read, sha

PLAN = 'configs/P73_prompt_identity_v01.json'
AUDITS = ('reports/P64_public_name_audit.json', 'reports/P66_completion_audit.json',
          'reports/P68_completion_audit.json')
CODE = tuple(sorted({str(p.relative_to(ROOT)) for p in (
    list((ROOT / 'scripts').glob('*.py')) + list((ROOT / 'scripts').glob('*.cpp'))
    + list((ROOT / 'tests').glob('test_*.py')) + list((ROOT / 'configs').rglob('*.json'))
)} | set(AUDITS) | {'reports/P66_identity_differences.json', 'reports/P73_renderer_build.json',
                  'docs/experiments/P73_prompt_identity.md'}))


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def verify_sources(storage, plan):
    if (plan['phase'] != 'P73' or plan['pair_runs'] != [list(p) for p in PAIR_RUNS]
            or (plan['pairs'], plan['recorded_inputs'], plan['calibration_inputs'], plan['max_renderings']) != (33, 66, 3, 69)
            or plan['max_wall_seconds'] != 180 or plan['max_sampled_rss_bytes'] != 2**31
            or plan['calibration_reference'] != ['P66_01_PHOTO_DOCUMENTED', 'call_013']
            or plan['negative_control_suffix'] != '\nP73 rendering negative-control sentinel.'):
        raise ValueError('fixed scope or budget changed')
    for path, expected in plan['source_sha256'].items():
        if sha(ROOT / path) != expected: raise ValueError('closed source changed: ' + path)
    build = read(ROOT / 'reports/P73_renderer_build.json')
    if (sha(ROOT / 'scripts/render_saved_chat.cpp') != build['source_cpp_sha256']
            or sha(storage / build['renderer_relative']) != build['renderer_sha256']
            or sha(storage / build['source_archive_relative']) != build['source_archive_sha256']
            or build['runtime_commit'] != plan['runtime_commit'] or build['exit_code'] != 0):
        raise ValueError('renderer, build or source archive changed')
    for path, expected in build['library_sha256'].items():
        if sha(storage / path) != expected: raise ValueError('runtime library changed')
    for path, expected in build['header_sha256'].items():
        if sha(storage / build['source_tree_relative'] / path) != expected:
            raise ValueError('compiled header changed')
    selection, _, model = verified_model(plan['model_selection'], root=storage)
    if sha(ROOT / plan['model_selection']) != sha(storage / plan['model_selection']):
        raise ValueError('model selection changed')
    commands = []
    for folder, expected in plan['server_initial_sha256'].items():
        path = storage / 'records/context_pilot' / folder / 'server_initial.json'
        if sha(path) != expected: raise ValueError('original command record changed')
        state = read(path)
        if (state['runtime']['commit'] != plan['runtime_commit']
                or state['model_revision'] != selection['revision']):
            raise ValueError('original runtime or model differs')
        commands.append(state['command'])
    if (any(c != commands[0] for c in commands[1:])
            or Path(commands[0][commands[0].index('--model') + 1]) != model):
        raise ValueError('recorded server commands or model path differ')
    pairs = selected_requests([read(ROOT / path) for path in AUDITS])
    for pair in pairs:
        for row in pair:
            for name in ('request', 'response'):
                path = storage / 'records/context_pilot' / row['run_id'] / row['call_id'] / (name + '.json')
                if path.stat().st_size > plan['max_input_file_bytes'] or sha(path) != row[name + '_sha256']:
                    raise ValueError('audited saved model record changed')
    return build, model, commands[0], pairs


class Interrupted(BaseException):
    pass


def interrupted(*_):
    raise Interrupted('explicit interruption')


def render_summary(value):
    return {
        'input_tokens': value['input_tokens'],
        'prompt_sha256': hashlib.sha256(value['prompt'].encode()).hexdigest(),
        'tokens_sha256': digest(value['tokens']),
        'session_controls_sha256': digest(value['session_controls']),
        'parsed_non_message_parameters_sha256': digest(value['parsed_non_message_parameters']),
    }


def run(storage, head, ci_ids):
    preflight_started = time.monotonic()
    if (subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip() != head
            or subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True).strip()):
        raise ValueError('exact clean committed execution tree required')
    if subprocess.check_output(['git', 'remote', 'get-url', 'origin'], cwd=ROOT, text=True).strip() not in (
            'https://github.com/sophiria1225/AI-', 'https://github.com/sophiria1225/AI-.git'):
        raise ValueError('repository scope differs')
    ci = confirmed_ci(head, ci_ids)
    plan = read(ROOT / PLAN)
    output = storage / 'records/context_pilot' / plan['batch_id']
    public = ROOT / 'reports/P73_prompt_identity.json'
    if output.exists() or public.exists(): raise FileExistsError('preserve every prior batch and failure')
    # These are source checks, not reconstruction or tokenization.
    build, model, command, pairs = verify_sources(storage, plan)
    resume = check_resume(storage)
    if (storage / '.runtime/P73.stop').exists(): raise Interrupted('P73 stop file')
    output.mkdir(parents=True)
    cases = [{'id': row['run_id'] + '_' + row['call_id'], 'request_path': str(
        storage / 'records/context_pilot' / row['run_id'] / row['call_id'] / 'request.json')}
        for pair in pairs for row in pair]
    cases += [{'id': name, 'request_path': str(output / (name + '_request_private.json'))}
              for name in ('P73_UNCHANGED', 'P73_RENAMED_IDS', 'P73_CHANGED_CONTENT')]
    hashes = {p: sha(ROOT / p) for p in CODE}
    report = {'phase': 'P73', 'status': 'started', 'git_commit': head, 'ci': ci,
        'started_at': datetime.now(timezone.utc).isoformat(), 'code_sha256': hashes,
        'source_plan_sha256': sha(ROOT / PLAN), 'research_resume': resume,
        'model_generations': 0, 'inference_contexts_created': 0, 'environment_api_requests': 0,
        'evaluator_calls': 0, 'reserved_scenarios_read': 0, 'hidden_test_details_read': False,
        'original_criteria_changed': False, 'pairs': [], 'calibrations': {},
        'planned_saved_inputs': 66, 'planned_calibration_inputs': 3,
        'planned_input_ids': [c['id'] for c in cases],
        'preflight_wall_seconds': time.monotonic() - preflight_started,
        'sampled_peak_rss_bytes': 0, 'renderer_exit_code': None}
    started = time.monotonic(); process = None; contents = {}; bindings = {}
    def save():
        report['wall_seconds'] = time.monotonic() - started
        write_json(output / 'status.json', report); write_json(public, report)
    try:
        save()
        for pair in pairs:
            for row in pair:
                identity = row['run_id'] + '_' + row['call_id']
                path = storage / 'records/context_pilot' / row['run_id'] / row['call_id'] / 'request.json'
                value = read(path)
                _, count = renamed_request(value)
                contents[identity] = value; bindings[identity] = count
        reference = '_'.join(plan['calibration_reference'])
        rename, count = renamed_request(contents[reference])
        if count == 0: raise ValueError('fixed ID calibration has no historical bindings')
        negative = json.loads(json.dumps(contents[reference]))
        if negative['messages'][0]['role'] != 'system' or not isinstance(negative['messages'][0]['content'], str):
            raise ValueError('fixed negative-control system message absent')
        negative['messages'][0]['content'] += plan['negative_control_suffix']
        for name, value in [('P73_UNCHANGED', contents[reference]), ('P73_RENAMED_IDS', rename), ('P73_CHANGED_CONTENT', negative)]:
            path = output / (name + '_request_private.json'); write_json(path, value)
        manifest = {'recorded_server_command': command, 'model_path': str(model),
                    'output_dir': str(output), 'cases': cases}
        write_json(output / 'render_manifest_private.json', manifest)
        environment = {k: v for k, v in os.environ.items() if not k.startswith('LLAMA_')}
        report['removed_environment_variable_names'] = sorted(set(os.environ) - set(environment))
        with (output / 'renderer_private.log').open('w') as log:
            process = subprocess.Popen([str(storage / build['renderer_relative']), str(output / 'render_manifest_private.json')],
                stdout=log, stderr=log, env=environment, start_new_session=True)
            while process.poll() is None:
                check_resume(storage)
                if (storage / '.runtime/P73.stop').exists(): raise Interrupted('P73 stop file')
                if time.monotonic() - started >= plan['max_wall_seconds']: raise TimeoutError('fixed offline deadline')
                measured = subprocess.run(['ps', '-o', 'rss=', '-p', str(process.pid)], capture_output=True, text=True)
                if measured.stdout.strip():
                    rss = int(measured.stdout.strip()) * 1024
                    report['sampled_peak_rss_bytes'] = max(report['sampled_peak_rss_bytes'], rss)
                    if rss > plan['max_sampled_rss_bytes']: raise MemoryError('fixed resident-memory cap')
                time.sleep(0.25)
            report['renderer_exit_code'] = process.returncode
        if process.returncode: raise ValueError('offline renderer failed; preserve partial outputs')
        if read(output / 'renderer_complete.json') != {'renderings': 69, 'decode_calls': 0}:
            raise ValueError('renderer completion ledger differs')
        metadata = read(output / 'renderer_metadata_private.json')
        if (not metadata['vocabulary_only'] or metadata['inference_contexts_created'] or metadata['decode_calls']
                or hashlib.sha256(metadata['default_template'].encode()).hexdigest() != plan['template_sha256']):
            raise ValueError('template or vocabulary-only execution differs')
        rendered = {c['id']: read(output / (c['id'] + '_rendered_private.json')) for c in cases}
        for index, pair in enumerate(pairs, 1):
            ids = [r['run_id'] + '_' + r['call_id'] for r in pair]
            values = [rendered[i] for i in ids]
            if any(v['input_tokens'] != r['input_tokens'] or len(v['tokens']) != v['input_tokens']
                   or v['id'] != i or v['media_files'] != 0 for v, r, i in zip(values, pair, ids, strict=True)):
                raise ValueError('historical measured input-token count differs')
            report['pairs'].append({'index': index, 'reference_run': pair[0]['run_id'], 'controlled_run': pair[1]['run_id'],
                'call_id': pair[0]['call_id'], 'historical_input_counts_match': True,
                'raw_requests_equal': contents[ids[0]] == contents[ids[1]],
                'bound_id_renamed_requests_equal': renamed_request(contents[ids[0]])[0] == renamed_request(contents[ids[1]])[0],
                'historical_tool_bindings': [bindings[i] for i in ids],
                'equal': {k: values[0][k] == values[1][k] for k in (
                    'prompt', 'tokens', 'session_controls', 'parsed_non_message_parameters')},
                'rendered': [render_summary(v) for v in values],
                'source_sha256': [{k: r[k] for k in ('request_sha256', 'response_sha256')} for r in pair],
                'private_rendering_sha256': [sha(output / (i + '_rendered_private.json')) for i in ids]})
        base = rendered[reference]
        for identity in ('P73_UNCHANGED', 'P73_RENAMED_IDS', 'P73_CHANGED_CONTENT'):
            value = rendered[identity]
            report['calibrations'][identity] = {'equal': {k: base[k] == value[k] for k in (
                'prompt', 'tokens', 'session_controls', 'parsed_non_message_parameters')},
                'rendered': render_summary(value),
                'source_sha256': sha(output / (identity + '_request_private.json')),
                'private_rendering_sha256': sha(output / (identity + '_rendered_private.json'))}
        if (not all(report['calibrations']['P73_UNCHANGED']['equal'].values())
                or any(report['calibrations']['P73_CHANGED_CONTENT']['equal'][k] for k in ('prompt', 'tokens'))):
            raise ValueError('fixed rendering calibration failed')
        if any(sha(ROOT / p) != h for p, h in hashes.items()): raise ValueError('frozen implementation changed')
        verify_sources(storage, plan)
        if time.monotonic() - started >= plan['max_wall_seconds']:
            raise TimeoutError('fixed offline deadline including analysis')
        report.update(status='complete', original_sources_unchanged=True,
            all_33_pairs_accounted=True, all_historical_input_counts_match=True,
            all_pair_prompts_equal=all(p['equal']['prompt'] for p in report['pairs']),
            all_pair_token_sequences_equal=all(p['equal']['tokens'] for p in report['pairs']),
            all_pair_controls_equal=all(p['equal']['session_controls'] and p['equal']['parsed_non_message_parameters'] for p in report['pairs']),
            renderer_metadata_sha256=sha(output / 'renderer_metadata_private.json'))
    except (Exception, Interrupted) as error:
        report.update(status='stopped', error_type=type(error).__name__)
        (output / 'error_private.txt').write_text(str(error))
    finally:
        if process is not None and process.poll() is None:
            process.terminate()
            try: process.wait(timeout=5)
            except subprocess.TimeoutExpired: process.kill(); process.wait(timeout=5)
        if process is not None: report['renderer_exit_code'] = process.returncode
        completed = [c['id'] for c in cases if (output / (c['id'] + '_rendered_private.json')).exists()]
        attempted = [c['id'] for c in cases if (output / (c['id'] + '_started.json')).exists()]
        report['rendering_attempts'] = len(attempted)
        report['attempted_without_complete_rendering'] = [i for i in attempted if i not in completed]
        report['rendered_input_files'] = len(completed)
        report['not_rendered'] = [c['id'] for c in cases if c['id'] not in completed]
        report['unaccounted_pair_indices'] = list(range(len(report['pairs']) + 1, 34))
        report['finished_at'] = datetime.now(timezone.utc).isoformat()
        save()
    print({k: report.get(k) for k in ('status', 'rendered_input_files', 'wall_seconds',
          'all_pair_prompts_equal', 'all_pair_token_sequences_equal', 'all_pair_controls_equal')})
    return 0 if report['status'] == 'complete' else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--storage-root', type=Path, required=True)
    parser.add_argument('--expected-commit', required=True); parser.add_argument('--push-ci', type=int, required=True)
    parser.add_argument('--pr-ci', type=int, required=True); args = parser.parse_args()
    signal.signal(signal.SIGTERM, interrupted); signal.signal(signal.SIGINT, interrupted)
    raise SystemExit(run(args.storage_root, args.expected_commit, [args.push_ci, args.pr_ci]))
