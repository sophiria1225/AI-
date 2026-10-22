"""P44 fixed four-boundary input-only check of a restricted print recognizer."""
import argparse
import datetime as dt
from pathlib import Path
import time

from code_agent_interface import CODE_TOOLS
from documentation_print_origin import build_origin_view
from inspect_input_exposure import SOURCES as P43_SOURCES, check_resume, frozen_sources, prepare as prepare_p43
from later_handoff_sources import prepare_later_sources
from local_llama import count_input
from probe_inference_cache import live_identity
from run_context_comparison import write_json
from run_handoff_factors import ROOT, read, sha

SOURCES = ('scripts/documentation_print_origin.py', 'scripts/inspect_documentation_origin.py',
           'tests/test_documentation_print_origin.py', 'docs/experiments/P44_documentation_origin.md')


def prepare(storage, root):
    original, p43_rows, _ = prepare_p43(storage, root)
    _, _, _, _, items = prepare_later_sources(storage, root)
    rows, prepared = [], []
    for item, prior in zip(items, p43_rows, strict=True):
        views, meta = build_origin_view(item)
        outputs = {}
        for name, conversation in views.items():
            messages, formatting = conversation.for_model(original['observation_page_characters'])
            if formatting != {'text_fallback_turns': 0, 'paged_spans': 0}:
                raise ValueError('paging or fallback differs from the fixed input')
            outputs[name] = messages
        source = storage / 'records/context_pilot/P42_documentation_exposure_v01' / (
            item['source_run'] + '_full_keep_private.json')
        if read(source) != outputs['full_keep'] or sha(source) != prior['p42_input_sha256']:
            raise ValueError('full comparison input differs from P42')
        rows.append({'source_run': item['source_run'],
                     'boundary_manifest_sha256': item['boundary_manifest_sha256'],
                     'p42_full_input_tokens': prior['p42_full_input_tokens'], 'selection': meta})
        prepared.append(outputs)
    if len(rows) != 4 or sum(r['selection']['candidate_outputs'] for r in rows) != 23:
        raise ValueError('all four boundaries and 23 candidates required')
    return original, rows, prepared


def run(root, storage):
    folder = storage / 'records/context_pilot/P44_documentation_origin_v01'
    target = root / 'reports/P44_documentation_origin.json'
    if folder.exists() or target.exists():
        raise FileExistsError('preserve the original inspection, including any failure')
    original, rows, prepared = prepare(storage, root)
    sources = dict.fromkeys((*SOURCES, *P43_SOURCES,
                           *read(root / 'reports/P42_documentation_exposure.json')['source_sha256']))
    commit = frozen_sources(root, sources)
    folder.mkdir(parents=True)
    began = time.monotonic()
    result = {'phase': 'P44', 'status': 'running', 'git_commit': commit,
              'source_sha256': {p: sha(root / p) for p in sources}, 'rows': rows,
              'started_at': dt.datetime.now(dt.timezone.utc).isoformat(),
              'input_count_requests': 0, 'failed_input_count_requests': 0,
              'model_generations': 0, 'environment_api_requests': 0, 'python_replay_programs': 0,
              'evaluator_calls': 0, 'reserved_scenarios_read': 0,
              'novel_method_claim': False, 'quality_preservation_claim': False,
              'end_to_end_savings_claim': False}
    try:
        result['research_resume'] = check_resume(storage)
        identity, end = live_identity(storage, original, 360)
        result.update(model_identity=identity, server_lease_end=end)
        for row, outputs in zip(rows, prepared, strict=True):
            row['views'] = {}
            for name, messages in outputs.items():
                if (storage / '.runtime/P44.stop').exists():
                    raise InterruptedError('explicit P44 stop')
                remaining = 300 - (time.monotonic() - began)
                if remaining <= 0:
                    raise TimeoutError('P44 inspection deadline')
                path = folder / f'{row["source_run"]}_{name}_private.json'
                write_json(path, messages)
                cfg = {**original['model'], 'temperature': original['agent_temperature'],
                       'seed': original['seed'] + 8, 'num_predict': original['max_output_tokens'],
                       'cache_prompt': False}
                result['input_count_requests'] += 1
                try:
                    count = count_input(cfg, messages, CODE_TOOLS, timeout=min(30, remaining))
                except Exception:
                    result['failed_input_count_requests'] += 1
                    raise
                row['views'][name] = {**count, 'input_sha256': sha(path)}
                write_json(folder / 'status.json', result)
            full = row['views']['full_keep']['input_tokens']
            if full != row['p42_full_input_tokens']:
                raise ValueError('full input token count differs from P42')
            row['input_tokens_removed'] = full - row['views']['documentation_origin_keep']['input_tokens']
            row['development_cost_gate_met'] = row['input_tokens_removed'] >= 1000
        result.update(status='complete', all_four_boundaries_counted=True,
                      additional_generation_design_gate=sum(r['development_cost_gate_met'] for r in rows) >= 2)
    except Exception as error:
        result.update(status='failed', error_type=type(error).__name__)
        (folder / 'error_private.txt').write_text(str(error))
        raise
    finally:
        result.update(wall_seconds=time.monotonic() - began,
                      finished_at=dt.datetime.now(dt.timezone.utc).isoformat())
        write_json(folder / 'status.json', result)
        write_json(target, result)
    print({k: result[k] for k in ('status', 'input_count_requests', 'model_generations', 'additional_generation_design_gate')})


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--repo-root', type=Path, default=ROOT)
    parser.add_argument('--storage-root', type=Path, required=True)
    args = parser.parse_args()
    run(args.repo_root.resolve(), args.storage_root.resolve())
