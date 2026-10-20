"""Inspect two pinned Flow graph metrics on fixed DAGs, without importing Flow."""
import ast
import collections
import datetime
import hashlib
import json
from pathlib import Path
import statistics
import types

ROOT = Path(__file__).resolve().parents[1]
COMMIT = '1bbfe1e699e6f35d5d422306c9a5bd637da84759'
SOURCE_SHA = 'db07a2b1eeed225c6ae84461be09cadd3ec09b446ea4fc09575b964e83996bd4'


def main():
    source = ROOT/'records/sources/20261020_runtime_reorganization/flow/workflow.py'
    if hashlib.sha256(source.read_bytes()).hexdigest() != SOURCE_SHA:
        raise ValueError('inspected Flow source differs from the pinned hash')
    tree = ast.parse(source.read_text())
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'Workflow')
    names = {'calculate_average_parallelism', 'calculate_dependency_complexity'}
    selected = [n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name in names]
    if len(selected) != 2:
        raise ValueError('expected two inspected methods')
    namespace = {'deque': collections.deque, 'defaultdict': collections.defaultdict}
    exec(compile(ast.fix_missing_locations(ast.Module(body=selected, type_ignores=[])), str(source), 'exec'), namespace)
    rows = []
    graphs = [('chain', [(0, 1), (1, 2), (2, 3)]),
              ('complete_forward_dag', [(i, j) for i in range(4) for j in range(i+1, 4)])]
    for name, edges in graphs:
        tasks = {i: types.SimpleNamespace(prev=[a for a, b in edges if b == i],
                                         next=[b for a, b in edges if a == i]) for i in range(4)}
        degrees = [len(tasks[i].prev)+len(tasks[i].next) for i in range(4)]
        depth = {}
        for i in range(4):
            depth[i] = 1+max((depth[p] for p in tasks[i].prev), default=0)
        widths = list(collections.Counter(depth.values()).values())
        graph = types.SimpleNamespace(nodes=list(tasks), degree=lambda n, d=degrees: d[n])
        obj = types.SimpleNamespace(tasks=tasks, graph=graph, _build_graph=lambda: graph)
        rows.append({'name': name, 'edges': edges, 'edge_count': len(edges), 'total_degrees': degrees,
                     'paper_degree_std': statistics.pstdev(degrees), 'true_layer_widths': widths,
                     'true_average_parallelism': sum(widths)/len(widths),
                     'inspected_code_dependency_complexity': namespace['calculate_dependency_complexity'](obj),
                     'inspected_code_average_parallelism': namespace['calculate_average_parallelism'](obj)})
    record = {'at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'scope': 'two hand-constructed DAG metric controls; no LLM or task-performance reproduction',
              'source_commit': COMMIT, 'source_url': f'https://raw.githubusercontent.com/tmllab/2025_ICLR_FLOW/{COMMIT}/workflow.py',
              'source_sha256': SOURCE_SHA, 'script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'executed_only': sorted(names), 'source_imports_executed': False,
              'paper_exact_code_revision_confirmed': False, 'controls': rows,
              'interpretation': 'Degree variation is not monotonic in edge count. This code revision revisits vertices '
              'with multiple incoming paths in the parallelism loop. These proxies are not direct observations '
              'of true inter-task coupling. This does not invalidate all reported paper results.'}
    (ROOT/'reports/flow_metric_controls.json').write_text(json.dumps(record, indent=2)+'\n')
    print(json.dumps({'controls': rows, 'executed_only': sorted(names)}))


if __name__ == '__main__':
    main()
