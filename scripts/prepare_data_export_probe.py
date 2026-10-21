"""Prepare and freeze an export diagnostic without model/environment calls."""
import argparse
import ast
import json
from pathlib import Path

from data_export_probe import extract_case, inputs, schedule, sha

ROOT = Path(__file__).resolve().parents[1]


def local_dependencies(entries):
    found, queue = set(), list(entries)
    while queue:
        path = queue.pop()
        if path in found:
            continue
        found.add(path)
        for node in ast.walk(ast.parse((ROOT/path).read_text())):
            modules = ([node.module] if isinstance(node, ast.ImportFrom) else
                       [n.name for n in node.names] if isinstance(node, ast.Import) else [])
            for module in modules:
                candidate = 'scripts/' + (module or '').split('.')[0] + '.py'
                if (ROOT/candidate).is_file():
                    queue.append(candidate)
    return sorted(found)


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--storage-root', type=Path, required=True)
    p.add_argument('--plan', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    plan = json.loads(a.plan.read_text())
    order = schedule(plan)
    status = json.loads((a.storage_root/'records/context_pilot/P18_batch_v01/status.json').read_text())
    if status['status'] != 'complete':
        raise ValueError('P18 must finish before P20 preparation')
    case, manifest = extract_case(a.storage_root/'records/context_pilot'/plan['source_run'])
    # Independently check exact common input bytes; mechanism instructions may differ.
    if inputs(case, 'literal_csv')[0][1] != inputs(case, 'data_program')[0][1]:
        raise ValueError('data inputs differ')
    out = a.storage_root/plan['input_root']
    out.mkdir(parents=True, exist_ok=False)
    (out/'input.json').write_text(json.dumps(case, ensure_ascii=False, indent=2)+'\n')
    manifest['input_sha256'] = sha(out/'input.json')
    (out/'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n')
    paths = local_dependencies(['scripts/prepare_data_export_probe.py', 'scripts/run_data_export_probe.py',
                                'scripts/data_python.py', 'scripts/evaluate_data_export_probe_v02.py',
                                'scripts/audit_export_generation.py'])
    paths += [plan['model_matches'], 'configs/models/minimax_m3_iq4_selection.json']
    frozen = {'phase': plan['phase'], 'plan_sha256': sha(a.plan), 'input_sha256': manifest['input_sha256'],
              'input_manifest_sha256': sha(out/'manifest.json'),
              'source_hashes': {path: sha(ROOT/path) for path in paths}, 'schedule': order,
              'model_calls': 0, 'environment_requests': 0, 'reserved_task_reads': 0,
              'scope': plan['scope']}
    with a.output.open('x') as f:
        json.dump(frozen, f, ensure_ascii=False, indent=2)
        f.write('\n')
    print(json.dumps({'observations': len(case['observations']), 'source_files': len(paths),
                      'model_calls': 0, 'plan_sha256': frozen['plan_sha256']}))
