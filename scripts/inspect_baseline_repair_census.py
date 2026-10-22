"""P50: rejection-time repair coverage in ten fixed, closed development runs.

Native calls share the schema snapshot supplied to their model response;
Python RPC calls observe discovery immediately. Neither path executes requests.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import time

from appworld_native_tools import NativeCatalog
from inspect_appworld_api_schemas import load_public_tools
from request_repair_binding import RepairBinding, RepairNotAdmitted, canonical

ROOT = Path(__file__).resolve().parents[1]
PLAN = 'configs/P50_baseline_repair_census_v01.json'
ZERO = ('model_generations', 'environment_api_requests', 'program_reexecutions',
        'evaluator_calls', 'tokenizer_requests', 'reserved_scenarios_read',
        'proposals_generated', 'repairs_executed')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inspect_events(events, spans, tools, execution_kind):
    if execution_kind not in ('native_calls', 'persistent_python'):
        raise ValueError('unknown execution kind')
    catalog = NativeCatalog(tools)
    schemas = {name: value['function'] for name, value in catalog.catalog.items()}
    previous_call = None
    closed_calls, seen_spans = set(), set()
    supplied = set(catalog.visible)
    rejections, stages = [], Counter()
    for event in events:
        call, span_id = event['call'], event['span_id']
        if span_id in seen_spans or span_id not in spans:
            raise ValueError('duplicate or missing span')
        seen_spans.add(span_id)
        if call != previous_call:
            if call in closed_calls:
                raise ValueError('noncontiguous response group')
            if previous_call is not None:
                closed_calls.add(previous_call)
            supplied = set(catalog.visible)
            previous_call = call
        stage = event.get('stage', 'native_call')
        if ((execution_kind == 'native_calls' and stage != 'native_call')
                or (execution_kind == 'persistent_python' and stage not in ('python_api', 'model_tool'))):
            raise ValueError('source event kind differs')
        stages[stage] += 1
        span = spans[span_id]
        observation = span['observation']
        error = observation.get('format_error') if isinstance(observation, dict) else None
        visible = supplied if execution_kind == 'native_calls' else catalog.visible
        exposed = {name: schemas[name] for name in visible}
        action = span.get('action')
        if error:
            name = action.get('name') if isinstance(action, dict) else None
            record = {'call_id': call, 'span_id': span_id, 'stage': stage,
                'api': name if name in schemas else 'not_a_catalog_api',
                'contract_exposed_at_rejection': name in exposed,
                'api_request_sent': event['api_request_sent'],
                'effects_unknown': event['effects_unknown']}
            if stage == 'model_tool':
                record.update(category='outside_api_repair', admission_reason='outer_model_tool')
            else:
                try:
                    binding = RepairBinding(action, exposed,
                        api_request_sent=event['api_request_sent'],
                        effects_unknown=event['effects_unknown'], format_error=error)
                    packet = binding.packet()
                    empty = packet['drop_allowed_only_for_empty_contract']
                    complete = packet['complete_type_compatible_renaming_exists']
                    category = ('empty_contract_normalization' if empty else
                                'complete_rename_candidate' if complete else 'requires_broader_repair')
                    record.update(category=category,
                        admission_reason='bound_request_and_exposed_contract',
                        packet_characters=len(canonical(packet)),
                        unknown_parameters=len(packet['unknown_parameters']),
                        protected_parameters=len(packet['protected_parameter_names']),
                        admissible_rename_edges=sum(map(len, packet['allowed_rename_targets'].values())))
                except RepairNotAdmitted as exc:
                    record.update(category='not_admitted', admission_reason=str(exc))
            rejections.append(record)
        added = event['new_tools']
        if (type(added) is not list or any(type(n) is not str or n not in schemas for n in added)):
            raise ValueError('invalid recorded discovery')
        catalog.visible.update(added)
    if set(spans) != seen_spans:
        raise ValueError('orphan source spans')
    return {'events_checked': len(events), 'stage_counts': dict(stages),
            'format_rejections': len(rejections),
            'categories': dict(Counter(r['category'] for r in rejections)),
            'rejections': rejections}


def inspect(storage, root):
    started = time.monotonic()
    plan = json.loads((root / PLAN).read_text())
    expected = ([f'P24_{i:02d}_GUIDED' for i in range(1, 7)]
                + [f'P29_{i:02d}_CODE' for i in range(1, 5)])
    if (plan['phase'] != 'P50' or plan['planned_cells'] != 10
            or [c['run_id'] for c in plan['cells']] != expected
            or plan['max_wall_seconds'] != 120 or plan['max_requests'] != 6000
            or plan['max_source_file_bytes'] != 67108864
            or any(plan[k] != 0 for k in ZERO)
            or plan['future_requests_used_to_propose_mapping']
            or plan['new_model_experiment_authorized_by_this_plan']):
        raise ValueError('outside fixed census')
    tools, schema_hashes, _ = load_public_tools(storage / '.runtime/appworld/r18_probe_01/data')
    rows = []
    event_count = 0
    for cell in plan['cells']:
        if time.monotonic() - started > 120:
            raise TimeoutError('census time cap')
        folder = storage / 'records/context_pilot' / cell['run_id']
        records = {}
        for name, digest in cell['source_sha256'].items():
            path = folder / name
            if path.stat().st_size > plan['max_source_file_bytes'] or sha(path) != digest:
                raise ValueError('source changed or exceeds bound')
            records[name] = json.loads(path.read_text())
        provenance = records['provenance.json']
        if (provenance['task_id'] != cell['task_id']
                or provenance['public_schema_hashes'] != schema_hashes
                or records['summary.json']['run_id'] != cell['run_id']
                or records['summary.json']['task_id'] != cell['task_id']):
            raise ValueError('source identity differs')
        for name, digest in provenance['sources'].items():
            if sha(folder / 'source' / name) != digest:
                raise ValueError('original adapter snapshot differs')
        event_count += len(records['events.json'])
        if event_count > plan['max_requests']:
            raise ValueError('event bound exceeded')
        result = inspect_events(records['events.json'], records['spans.json'], tools, cell['execution_kind'])
        rows.append({**cell, **result})
    elapsed = time.monotonic() - started
    if elapsed > 120:
        raise TimeoutError('census time cap')
    groups = {}
    for phase in ('P24', 'P29'):
        selected = [r for r in rows if r['phase'] == phase]
        categories = Counter()
        for row in selected:
            categories.update(row['categories'])
        groups[phase] = {'runs': len(selected), 'events_checked': sum(r['events_checked'] for r in selected),
            'format_rejections': sum(r['format_rejections'] for r in selected),
            'tasks_with_format_rejections': sum(bool(r['format_rejections']) for r in selected),
            'categories': dict(categories),
            'tasks_with_complete_rename_candidate': sum(bool(r['categories'].get('complete_rename_candidate')) for r in selected)}
    return {'phase': 'P50', 'kind': plan['kind'], 'all_planned_cells_accounted': len(rows) == 10,
        'distinct_known_tasks': len({r['task_id'] for r in rows}), 'rows': rows, 'groups': groups,
        'wall_seconds': elapsed, **{k: 0 for k in ZERO},
        'novel_method_established': False, 'quality_preservation_claim': False, 'measured_savings_claim': False,
        'source_sha256': {'plan': sha(root / PLAN), 'script': sha(Path(__file__)),
            'binding': sha(root / 'scripts/request_repair_binding.py')},
        'limits': ['Original development runs, not held-out confirmation or repeated independent trials.',
            'Native same-response schemas and Python sequential discovery use different original rules.',
            'Only format rejections are classified; semantic/API failures and all other work remain outside this census.',
            'No proposals, execution, task-quality comparison or token savings measurement.']}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--storage-root', required=True, type=Path)
    args = parser.parse_args()
    target = ROOT / 'reports/P50_baseline_repair_census.json'
    if target.exists():
        raise FileExistsError('preserve completed census')
    result = inspect(args.storage_root, ROOT)
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'groups': result['groups'], 'wall_seconds': result['wall_seconds']}))
