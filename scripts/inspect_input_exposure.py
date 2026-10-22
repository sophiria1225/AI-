"""P43: fixed four-input accounting; no generation, tool execution or evaluation."""
import argparse
from collections import Counter
import datetime as dt
import hashlib
import json
from pathlib import Path
import subprocess
import time

from code_agent_interface import CODE_TOOLS
from documentation_exposure import views
from handoff_factors import split_turns
from input_exposure_accounting import (COMPONENTS, cumulative_inputs, match_receipt_text,
                                       receipt_group, token_increments)
from later_handoff_sources import prepare_later_sources
from local_llama import count_input
from native_conversation import recover_turn
from probe_inference_cache import live_identity
from run_context_comparison import write_json
from run_handoff_factors import ROOT, sha

RUNS = tuple(f'P29_{i:02d}_CODE' for i in range(1, 5))
SOURCES = ('scripts/input_exposure_accounting.py', 'scripts/inspect_input_exposure.py',
           'tests/test_input_exposure_accounting.py',
           'docs/experiments/P43_input_exposure_accounting.md',
           'scripts/serve_research_model.py', 'scripts/probe_inference_cache.py',
           'scripts/model_provenance.py', 'scripts/local_llama.py')


def read(path):
    return json.loads(path.read_text())


def prepare(storage, root):
    previous_path = root / 'reports/P42_documentation_exposure.json'
    previous = read(previous_path)
    if (previous['status'] != 'complete' or previous['additional_generation_design_gate']
            or tuple(row['source_run'] for row in previous['rows']) != RUNS):
        raise ValueError('require the complete original P42 cohort and decision')
    for name, value in previous['source_sha256'].items():
        if sha(root / name) != value:
            raise ValueError('P42 source changed: ' + name)
    _, original, _, _, prepared = prepare_later_sources(storage, root)
    if tuple(item['source_run'] for item in prepared) != RUNS:
        raise ValueError('all four original boundaries required')
    rows, inputs = [], []
    for item, prior in zip(prepared, previous['rows'], strict=True):
        prefix = item['prefix']
        proposed, selection = views(prefix)
        if (selection != prior['selection']
                or item['boundary_manifest_sha256'] != prior['boundary_manifest_sha256']):
            raise ValueError('P42 boundary or selection changed')
        conversation = proposed['full_keep']
        messages, formatting = conversation.for_model(original['observation_page_characters'])
        saved = storage / 'records/context_pilot/P42_documentation_exposure_v01' / (
            item['source_run'] + '_full_keep_private.json')
        if (sha(saved) != prior['views']['full_keep']['input_sha256'] or read(saved) != messages
                or formatting != {'text_fallback_turns': 0, 'paged_spans': 0}):
            raise ValueError('fixed rendered input changed or is unsupported')
        events = {event['span_id']: event for event in prefix['events']}
        if len(events) != len(prefix['events']):
            raise ValueError('duplicate recorded event')
        groups, outputs = {}, []
        candidates = {row['span_id']: row for row in prior['selection']['checks']}
        for number, turn in enumerate(split_turns(conversation.messages()), 1):
            for span in recover_turn(turn):
                if span['action']['name'] != 'run_python':
                    raise ValueError('unexpected outer tool in fixed cohort')
                sid, obs = span['id'], span['observation']
                group, docs = receipt_group(obs, prefix['spans'], events)
                if (sid not in events or events[sid]['stage'] != 'model_tool'
                        or any(events[r['span_id']]['call'] != events[sid]['call']
                               for r in obs['api_receipts'])):
                    raise ValueError('inner and outer receipt call mismatch')
                groups[sid] = group
                outputs.append({'span_id': sid, 'turn': number, 'receipt_group': group,
                    'api_receipts': len(obs['api_receipts']), 'documentation_receipts': len(docs),
                    'p42_candidate': sid in candidates,
                    'p42_reason': candidates.get(sid, {}).get('reason'),
                    'latest_turn': number == 8, **match_receipt_text(obs['stdout'], docs)})
        cases = cumulative_inputs(messages, CODE_TOOLS, groups)
        rows.append({'source_run': item['source_run'],
                     'boundary_manifest_sha256': item['boundary_manifest_sha256'],
                     'p42_input_sha256': sha(saved),
                     'p42_full_input_tokens': prior['views']['full_keep']['input_tokens'],
                     'outputs': outputs, 'receipt_groups': dict(Counter(groups.values())),
                     'p42_candidates_accounted': sum(o['p42_candidate'] for o in outputs)})
        inputs.append(cases)
    if sum(len(r['outputs']) for r in rows) != 32 or sum(r['p42_candidates_accounted'] for r in rows) != 23:
        raise ValueError('original output cohort is incomplete')
    return original, rows, inputs


def check_resume(storage):
    pause = storage / '.runtime/RESEARCH_PAUSED_BY_USER_20261022.json'
    resumed = storage / '.runtime/RESEARCH_RESUMED_BY_USER_20261022.json'
    record = read(resumed)
    if record.get('status') != 'resumed_by_user' or record.get('supersedes_pause_sha256') != sha(pause):
        raise ValueError('require explicit recorded user resumption of this pause')
    return {'resume_sha256': sha(resumed), 'retained_pause_sha256': sha(pause), 'at': record['at']}


def frozen_sources(root, paths):
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip()
    for name in paths:
        committed = subprocess.check_output(['git', 'show', f'{commit}:{name}'], cwd=root)
        if hashlib.sha256(committed).hexdigest() != sha(root / name):
            raise ValueError('commit the fixed implementation before counting: ' + name)
    return commit


def run(storage, root, *, tokens=False):
    storage, root = storage.resolve(), root.resolve()
    name = 'tokens' if tokens else 'structure'
    folder = storage / f'records/context_pilot/P43_input_exposure_{name}_v01'
    target = root / f'reports/P43_input_exposure_{name}.json'
    if folder.exists() or target.exists():
        raise FileExistsError('preserve previous P43 accounting, including failures')
    original, rows, cases = prepare(storage, root)
    paths = SOURCES + tuple(read(root / 'reports/P42_documentation_exposure.json')['source_sha256'])
    sources = {p: sha(root / p) for p in paths}
    commit = frozen_sources(root, paths) if tokens else subprocess.check_output(
        ['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip()
    folder.mkdir(parents=True)
    began = time.monotonic()
    result = {'phase': 'P43', 'mode': name, 'status': 'running', 'rows': rows,
              'started_at': dt.datetime.now(dt.timezone.utc).isoformat(),
              'git_commit': commit, 'source_sha256': sources,
              'p42_report_sha256': sha(root / 'reports/P42_documentation_exposure.json'),
              'component_order': ['envelope', *COMPONENTS],
              'input_count_requests': 0, 'failed_input_count_requests': 0,
              'model_generations': 0, 'environment_api_requests': 0,
              'python_replay_programs': 0, 'evaluator_calls': 0, 'reserved_scenarios_read': 0,
              'new_generation_authorized_by_result': False, 'novel_method_claim': False,
              'quality_preservation_claim': False, 'achievable_savings_claim': False,
              'interpretation': 'Ordered descriptive token differences on fixed inputs; not independent causal effects. Whole-response text matches are not dataflow or proof of irrelevance.'}
    try:
        if tokens:
            result['research_resume'] = check_resume(storage)
            identity, end = live_identity(storage, original, 660)
            result.update(model_identity=identity, server_lease_end=end)
        for row, inputs in zip(rows, cases, strict=True):
            row['cumulative_inputs'] = []
            for case in inputs:
                if (storage / '.runtime/P43.stop').exists():
                    raise InterruptedError('explicit P43 stop')
                if time.monotonic() - began >= 600:
                    raise TimeoutError('P43 accounting deadline')
                path = folder / f'{row["source_run"]}_{case["component"]}_private.json'
                write_json(path, case)
                entry = {'component': case['component'], 'input_sha256': sha(path)}
                row['cumulative_inputs'].append(entry)
                if tokens:
                    cfg = {**original['model'], 'temperature': original['agent_temperature'],
                           'seed': original['seed'] + 8, 'num_predict': original['max_output_tokens'],
                           'cache_prompt': False}
                    result['input_count_requests'] += 1
                    try:
                        entry.update(count_input(cfg, case['messages'], case['tools'],
                                                 timeout=min(30, max(0.001, 600 - (time.monotonic() - began)))))
                    except Exception:
                        result['failed_input_count_requests'] += 1
                        raise
                write_json(folder / 'status.json', result)
            if tokens:
                counts = {r['component']: r['input_tokens'] for r in row['cumulative_inputs']}
                row['ordered_token_increments'] = token_increments(counts)
                if list(counts.values())[-1] != row['p42_full_input_tokens']:
                    raise ValueError('full input token count differs from P42')
        result.update(status='complete', all_four_inputs_accounted=True)
    except Exception as error:
        result.update(status='failed', error_type=type(error).__name__)
        (folder / 'error_private.txt').write_text(str(error))
        raise
    finally:
        result['wall_seconds'] = time.monotonic() - began
        result['finished_at'] = dt.datetime.now(dt.timezone.utc).isoformat()
        write_json(folder / 'status.json', result)
        write_json(target, result)
    print(json.dumps({k: result[k] for k in ('status', 'mode', 'input_count_requests', 'model_generations')}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--repo-root', type=Path, default=ROOT)
    parser.add_argument('--storage-root', type=Path, required=True)
    parser.add_argument('--count-tokens', action='store_true')
    args = parser.parse_args()
    run(args.storage_root, args.repo_root, tokens=args.count_tokens)
