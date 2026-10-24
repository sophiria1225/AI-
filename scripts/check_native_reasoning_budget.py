"""Run fixed upstream and four synthetic native sampler checks without a model."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import time

from run_handoff_factors import ROOT, read, sha
from run_context_comparison import write_json

PROVENANCE = 'reports/P73_renderer_build.json'
SOURCE_FILES = ('tests/test-reasoning-budget.cpp', 'common/reasoning-budget.h',
                'common/reasoning-budget.cpp', 'common/unicode.h', 'common/unicode.cpp')


def run(storage, output, root=ROOT):
    provenance = read(root / PROVENANCE)
    source = storage / provenance['source_tree_relative']
    if sha(storage / provenance['source_archive_relative']) != provenance['source_archive_sha256']:
        raise ValueError('fixed_source_archive_changed')
    for name, expected in provenance['header_sha256'].items():
        if sha(source / name) != expected: raise ValueError('fixed_header_changed:' + name)
    for name, expected in provenance['library_sha256'].items():
        if sha(storage / name) != expected: raise ValueError('fixed_library_changed:' + name)
    budget_scope = read(root / 'reports/output_budget_backend_scope_20261024.json')
    for item in budget_scope['files']:
        if sha(source / item['path']) != item['sha256']:
            raise ValueError('reviewed_budget_source_changed:' + item['path'])
    output.mkdir(parents=True, exist_ok=False)
    lib = storage / '.runtime/llama.cpp/b11669/llama-b11669'
    compiler = subprocess.check_output(['/usr/bin/clang++', '--version'], text=True)
    result = dict(phase='native_reasoning_budget_synthetic_check', status='running',
        started_at=datetime.now(timezone.utc).isoformat(), source_commit=provenance['runtime_commit'],
        source_archive_sha256=provenance['source_archive_sha256'], compiler_version=compiler,
        source_sha256={name: sha(source / name) for name in SOURCE_FILES},
        repo_source_sha256={name: sha(root / name) for name in (PROVENANCE,
            'reports/output_budget_backend_scope_20261024.json',
            'scripts/probe_native_reasoning_budget.cpp', 'scripts/check_native_reasoning_budget.py')},
        library_sha256=provenance['library_sha256'], stages=[],
        live_server_contacted=False, experimental_records_read=False, model_forward_passes=0,
        model_generations=0, vocabulary_loads=0, tokenizations=0, environment_api_requests=0,
        task_evaluations=0, actual_P88_usage_or_outcomes_inferred=False)
    started = time.monotonic()
    try:
        for name, cpp in [('upstream', source / 'tests/test-reasoning-budget.cpp'),
                          ('fixed_2048', root / 'scripts/probe_native_reasoning_budget.cpp')]:
            executable = output / name
            command = ['/usr/bin/clang++', '-std=c++17', '-O2']
            for directory in ('common', 'include', 'ggml/include'):
                command += ['-I', str(source / directory)]
            command += [str(cpp), '-L', str(lib), '-Wl,-rpath,' + str(lib),
                        '-lllama-common', '-lllama', '-lggml', '-lggml-base', '-o', str(executable)]
            for mode, args, timeout in [('compile', command, 60), ('execute', [str(executable)], 10)]:
                began = time.monotonic()
                process = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
                log = output / (name + '_' + mode + '.log')
                log.write_text(process.stdout + process.stderr)
                result['stages'].append(dict(name=name, mode=mode, exit_code=process.returncode,
                    wall_seconds=time.monotonic()-began, command=args, log_sha256=sha(log)))
                write_json(output / 'status.json', result)
                if process.returncode:
                    raise RuntimeError('native_check_stopped_preserve_attempt:' + name + ':' + mode)
                if mode == 'execute':
                    if name == 'upstream':
                        if 'OK (12 tests passed)' not in process.stdout or 'Testing UTF-8 boundary detection... OK' not in process.stdout:
                            raise ValueError('complete_upstream_test_markers_required')
                        result['upstream_sampler_cases_passed'] = 12
                        result['upstream_utf8_helper_passed'] = True
                    else:
                        parsed = json.loads(process.stdout)
                        if len(parsed['synthetic_cases']) != 4:
                            raise ValueError('all_four_fixed_synthetic_cases_required')
                        result['fixed_2048_probe'] = parsed
                    result[name + '_binary_sha256'] = sha(executable)
        result['status'] = 'complete'
    except Exception as error:
        result.update(status='failed', error_type=type(error).__name__)
        (output / 'error.txt').write_text(str(error))
        raise
    finally:
        result['wall_seconds'] = time.monotonic()-started
        result['finished_at'] = datetime.now(timezone.utc).isoformat()
        write_json(output / 'status.json', result)
    print({k: result[k] for k in ('status', 'wall_seconds', 'upstream_sampler_cases_passed', 'model_generations')})
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--storage-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(); run(args.storage_root.resolve(), args.output.resolve())
