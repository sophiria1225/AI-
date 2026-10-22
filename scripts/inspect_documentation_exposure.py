"""P42 passive content matching and exact counting on four known boundaries."""
import argparse
import datetime as dt
from pathlib import Path
import subprocess
import time

from code_agent_interface import CODE_TOOLS
from documentation_exposure import views
from later_handoff_sources import prepare_later_sources
from local_llama import count_input
from probe_inference_cache import live_identity
from run_context_comparison import write_json
from run_handoff_factors import ROOT, sha


def run(storage, root):
    _, original, _, _, prepared = prepare_later_sources(storage, root)
    if [p['source_run'] for p in prepared] != [f'P29_{i:02d}_CODE' for i in range(1, 5)]:
        raise ValueError('use all four fixed known development boundaries')
    identity, end = live_identity(storage, original, 900)
    folder = storage / 'records/context_pilot/P42_documentation_exposure_v01'
    target = root / 'reports/P42_documentation_exposure.json'
    if folder.exists() or target.exists(): raise FileExistsError('preserve prior inspection')
    folder.mkdir()
    sources = ('scripts/documentation_exposure.py', 'scripts/inspect_documentation_exposure.py',
               'scripts/later_handoff_sources.py', 'scripts/handoff_output_views.py',
               'scripts/handoff_factors.py', 'scripts/native_conversation.py', 'scripts/local_llama.py',
               'scripts/code_agent_interface.py', 'scripts/probe_inference_cache.py',
               'docs/experiments/P42_documentation_exposure.md', 'tests/test_documentation_exposure.py')
    began = time.monotonic()
    result = {'phase': 'P42', 'status': 'running', 'rows': [], 'input_count_requests': 0,
              'failed_input_count_requests': 0, 'model_generations': 0, 'environment_api_requests': 0,
              'evaluator_calls': 0, 'python_replay_programs': 0, 'reserved_scenarios_read': 0,
              'model_identity': identity, 'server_lease_end': end,
              'source_sha256': {p: sha(root / p) for p in sources},
              'git_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip(),
              'started_at': dt.datetime.now(dt.timezone.utc).isoformat(),
              'quality_preservation_claim': False, 'end_to_end_savings_claim': False, 'novel_method_claim': False}
    try:
        for item in prepared:
            if (storage / '.runtime/P42.stop').exists(): raise InterruptedError('explicit stop')
            proposed, meta = views(item['prefix'])
            row = {'source_run': item['source_run'], 'boundary_manifest_sha256': item['boundary_manifest_sha256'],
                   'selection': meta, 'views': {}}
            result['rows'].append(row)
            for name, conversation in proposed.items():
                messages, formatting = conversation.for_model(original['observation_page_characters'])
                path = folder / (item['source_run'] + '_' + name + '_private.json')
                write_json(path, messages)
                cfg = {**original['model'], 'temperature': original['agent_temperature'],
                       'seed': original['seed'] + 8, 'num_predict': original['max_output_tokens'], 'cache_prompt': False}
                result['input_count_requests'] += 1
                try:
                    count = count_input(cfg, messages, CODE_TOOLS, timeout=30)
                except Exception:
                    result['failed_input_count_requests'] += 1
                    raise
                row['views'][name] = {**count, 'input_sha256': sha(path), 'formatting': formatting}
            full = row['views']['full_keep']['input_tokens']
            row['documentation_input_tokens_removed'] = full - row['views']['documentation_stdout_mask_keep']['input_tokens']
            row['all_stdout_input_tokens_removed'] = full - row['views']['all_stdout_mask_keep']['input_tokens']
            row['development_cost_gate_met'] = row['documentation_input_tokens_removed'] >= 1000
            write_json(folder / 'status.json', result)
        result.update(status='complete', all_four_boundaries_counted=len(result['rows']) == 4,
                      additional_generation_design_gate=sum(r['development_cost_gate_met'] for r in result['rows']) >= 2)
    except Exception as error:
        result.update(status='failed', error_type=type(error).__name__)
        (folder / 'error_private.txt').write_text(str(error))
        raise
    finally:
        result['wall_seconds'] = time.monotonic() - began
        result['finished_at'] = dt.datetime.now(dt.timezone.utc).isoformat()
        write_json(folder / 'status.json', result)
        write_json(target, result)
    print({k: result[k] for k in ('status', 'input_count_requests', 'model_generations', 'additional_generation_design_gate')})
    print([{k: r[k] for k in ('source_run', 'documentation_input_tokens_removed', 'all_stdout_input_tokens_removed')} for r in result['rows']])


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--storage-root', type=Path, required=True)
    p.add_argument('--repo-root', type=Path, default=ROOT); a = p.parse_args()
    run(a.storage_root, a.repo_root)
