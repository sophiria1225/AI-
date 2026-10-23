"""Compile and exercise five synthetic parser inputs, with no model execution."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
SOURCE = 'scripts/reproduce_minimax_parser_boundary.cpp'
BUILD = 'reports/P73_renderer_build.json'
EXPECTED = 'materials/20261024_synthetic_parser_boundary/synthetic_results.json'
COMMIT = '620d2225cc436ab0b001e3200e590e3b286ef9ab'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(storage, output):
    if output.exists():
        raise FileExistsError('preserve_previous_probe_outputs')
    began = time.monotonic()
    build = json.loads((ROOT / BUILD).read_text())
    if build['runtime_commit'] != COMMIT or build['binary_tag'] != 'b11669':
        raise ValueError('fixed_backend_required')
    source_root = storage / build['source_tree_relative']
    libraries = storage / '.runtime/llama.cpp/b11669/llama-b11669'
    for name, expected in build['library_sha256'].items():
        if sha(storage / name) != expected:
            raise ValueError('pinned_library_changed:' + name)
    for name, expected in build['header_sha256'].items():
        if sha(source_root / name) != expected:
            raise ValueError('pinned_header_changed:' + name)
    expected_result = json.loads((ROOT / EXPECTED).read_text())
    if (len(expected_result['cases']) != 5 or not expected_result['synthetic_only']
            or expected_result['uses_real_model_template']
            or any(expected_result[k] != 0 for k in ('model_loads', 'vocabulary_loads',
                'inference_contexts', 'tokenizations', 'sampling_calls', 'environment_calls'))):
        raise ValueError('five_synthetic_cases_only')
    output.mkdir(parents=True, exist_ok=False)
    manifest = dict(created_at=datetime.now(timezone.utc).isoformat(), status='preparing',
        source_sha256=sha(ROOT / SOURCE), wrapper_sha256=sha(Path(__file__)),
        prior_build_report_sha256=sha(ROOT / BUILD), backend_commit=COMMIT,
        library_sha256=build['library_sha256'], header_sha256=build['header_sha256'],
        expected_result_sha256=sha(ROOT / EXPECTED), synthetic_inputs=5, parser_evaluations=10,
        model_loads=0, model_generations=0, tokenizations=0, environment_api_requests=0,
        task_evaluations=0, private_experimental_records_read=False,
        grammar_sampling_test=False, uses_real_model_template=False,
        original_experiments_changed=False, automatic_retries=0, stages=[])
    def save():
        manifest['total_wall_seconds'] = time.monotonic() - began
        (output / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    command = ['/usr/bin/clang++', '-std=c++17', '-O2',
        '-I' + str(source_root / 'common'), '-I' + str(source_root / 'include'),
        '-I' + str(source_root / 'ggml/include'), '-L' + str(libraries), '-Wl,-rpath,' + str(libraries),
        str(ROOT / SOURCE), '-lllama-common', '-lllama', '-lggml', '-o', str(output / 'parser_boundary')]
    try:
        for stage, cmd, timeout in (('compile', command, 60), ('parse',
                [str(output / 'parser_boundary'), str(output / 'synthetic_results.json')], 30)):
            manifest['status'] = stage; save(); start = time.monotonic()
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            (output / (stage + '.log')).write_text(result.stdout + result.stderr)
            manifest['stages'].append(dict(stage=stage, command=cmd, exit_code=result.returncode,
                wall_seconds=time.monotonic() - start))
            save()
            if result.returncode:
                raise RuntimeError('synthetic_probe_stage_failed:' + stage)
        observed = json.loads((output / 'synthetic_results.json').read_text())
        manifest.update(output_sha256=sha(output / 'synthetic_results.json'),
                        binary_sha256=sha(output / 'parser_boundary'),
                        all_results_match_original=observed == expected_result)
        if not manifest['all_results_match_original']:
            raise ValueError('synthetic_parser_behavior_changed')
        manifest['status'] = 'complete'
    except Exception as error:
        manifest.update(status='stopped', error_type=type(error).__name__, error=str(error)); save()
        raise
    save()
    print({k: manifest[k] for k in ('status', 'synthetic_inputs', 'parser_evaluations',
        'all_results_match_original', 'model_generations', 'total_wall_seconds')})
    return manifest


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--storage-root', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    run(a.storage_root.resolve(), a.output.resolve())
