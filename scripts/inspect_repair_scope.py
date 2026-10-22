"""Inspect P47 rejection scope without executing programs or exporting values.

Static call sites are not runtime continuations. Observed later argument edits
are hindsight diagnostics, never an available repair policy or saved cost.
"""
import argparse
import ast
from collections import Counter
import json
from pathlib import Path
import time

from appworld_native_tools import NativeCatalog
from contract_feedback import UNKNOWN_PARAMETER
from diagnose_contract_comparison import require_closed
from later_handoff_sources import prepare_later_sources
from run_handoff_factors import ROOT, read, sha

PLAN = 'configs/P48_repair_scope_v01.json'


def value_key(value):
    # JSON distinguishes bool/int and container structure; never export this key.
    return type(value).__name__, json.dumps(value, sort_keys=True, ensure_ascii=False,
                                           separators=(',', ':'), allow_nan=False)


def argument_changes(before, after):
    if type(before) is not dict or type(after) is not dict:
        raise ValueError('argument objects required')
    common = before.keys() & after.keys()
    removed = before.keys() - after.keys()
    added = after.keys() - before.keys()
    equal = sum(value_key(before[k]) == value_key(after[k]) for k in common)
    return {
        'same_name_unchanged_values': equal,
        'same_name_changed_values': len(common) - equal,
        'removed_parameter_count': len(removed),
        'added_parameter_count': len(added),
        'removed_to_added_equal_type_edges': sum(type(before[a]) is type(after[b])
                                               for a in removed for b in added),
        'removed_to_added_equal_value_edges': sum(value_key(before[a]) == value_key(after[b])
                                                for a in removed for b in added),
        'removed_value_types': dict(Counter(type(before[k]).__name__ for k in sorted(removed))),
        'added_value_types': dict(Counter(type(after[k]).__name__ for k in sorted(added))),
        'semantic_equivalence_verified': False,
    }


def call_shape(code, api):
    """Return only syntax counts; do not evaluate expressions or infer liveness."""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return {'parsed': False, 'literal_matching_sites': None,
                'runtime_resume_point_identified': False}
    parents = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
             and isinstance(n.func, ast.Name) and n.func.id == 'call_api']
    literal = lambda n: bool(n.args and isinstance(n.args[0], ast.Constant)
                             and isinstance(n.args[0].value, str))
    matching = [n for n in calls if literal(n) and n.args[0].value == api]
    groups = {
        'loop': (ast.For, ast.AsyncFor, ast.While, ast.ListComp, ast.SetComp,
                 ast.DictComp, ast.GeneratorExp),
        'branch': (ast.If, ast.IfExp, ast.Match),
        'function': (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda),
        'exception': (ast.Try, ast.TryStar),
        'context_manager': (ast.With, ast.AsyncWith),
    }
    counts = Counter()
    for node in matching:
        ancestors = []
        while node in parents:
            node = parents[node]; ancestors.append(node)
        for label, types in groups.items():
            counts[label] += any(isinstance(parent, types) for parent in ancestors)
    # Alias calls and arbitrary reflective behavior are not resolved by this
    # deliberately syntactic inspection. No uniqueness/execution guarantee.
    return {
        'parsed': True,
        'direct_call_api_sites': len(calls),
        'dynamic_name_direct_call_sites': sum(not literal(n) for n in calls),
        'literal_matching_sites': len(matching),
        'matching_site_context_counts': {k: counts[k] for k in groups},
        'matching_argument_load_names': sum(len({n.id for arg in [*call.args[1:], *(k.value for k in call.keywords)]
            for n in ast.walk(arg) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)})
            for call in matching),
        'runtime_resume_point_identified': False,
        'alias_or_reflective_calls_resolved': False,
    }


def rejection_shape(span, event, exposed_schemas):
    name = span['action']['name']
    args = json.loads(span['action']['arguments'])
    if type(args) is not dict:
        raise ValueError('audited API arguments are not an object')
    schema = exposed_schemas.get(name)
    properties = schema.get('parameters', {}).get('properties') if schema else None
    known = type(properties) is dict
    error = span['observation'].get('format_error')
    return {
        'rejection_kind': 'unknown_parameter' if error == UNKNOWN_PARAMETER else 'other_format_rejection',
        'api_request_sent': event['api_request_sent'],
        'effects_unknown': event['effects_unknown'],
        'contract_exposed_at_rejection': known,
        'requested_parameter_count': len(args),
        'requested_value_types': dict(Counter(type(v).__name__ for v in args.values())),
        'allowed_parameter_count': len(properties) if known else None,
        'unknown_parameter_count': len(args.keys() - properties.keys()) if known else None,
        'empty_contract_extra_argument_candidate': bool(known and not properties and args
            and error == UNKNOWN_PARAMETER and not event['api_request_sent'] and not event['effects_unknown']),
        'contract_characters': len(json.dumps(schema, sort_keys=True, ensure_ascii=False)) if known else None,
        'automatic_repair_performed': False,
    }


def inspect(storage, root):
    started = time.monotonic()
    plan = read(root / PLAN)
    zero = ('model_generations', 'environment_api_requests', 'tokenizer_requests',
            'program_reexecutions', 'evaluator_calls', 'reserved_scenarios_read')
    if (plan['phase'] != 'P48' or plan['source_phase'] != 'P47' or plan['planned_cells'] != 12
            or plan['max_wall_seconds'] != 120 or any(plan[k] != 0 for k in zero)):
        raise ValueError('outside fixed passive scope')
    comparison = root / 'reports/P47_comparison.json'
    if sha(comparison) != plan['source_comparison_sha256']:
        raise ValueError('fixed source comparison changed')
    report = read(comparison)
    base = storage / 'records/context_pilot'
    status = base / 'P47_batch_v01/status.json'
    require_closed(report, read(status))
    if sha(status) != report['source_sha256']['batch_status']:
        raise ValueError('closed batch changed since audit')
    _, _, tools, schemas, _ = prepare_later_sources(storage, root)
    rows = []; failures = []
    for cell in report['rows']:
        if time.monotonic() - started > plan['max_wall_seconds']:
            raise TimeoutError('passive inspection time cap')
        row = {k: cell[k] for k in ('run_id', 'task_id', 'arm', 'record_status')}
        if cell['record_status'] == 'not_run_after_stop':
            rows.append(row); continue
        folder = base / cell['run_id']
        names = ('events.json', 'spans.json', 'usage.json', 'prefix_events.json')
        for name in names:
            if sha(folder / name) != cell['source_sha256'][name]:
                raise ValueError('audited input changed: ' + name)
        events, spans, usage, prefix = [read(folder / n) for n in names]
        by_span = {e['span_id']: e for e in events}
        positions = {e['span_id']: i for i, e in enumerate(events)}
        catalog = NativeCatalog(tools)
        for event in prefix: catalog.visible.update(event['new_tools'])
        indices = Counter(); programs = 0; rejected = []; sources = {}
        covered = set()
        for event in events:
            if event['stage'] != 'model_tool': continue
            call_id = event['call']; indices[call_id] += 1
            program = folder / 'programs' / f'{call_id}_{indices[call_id]:02d}'
            if not program.exists(): continue
            for name in ('input_private.json', 'result_private.json', 'wire_private.jsonl'):
                path = program / name; key = str(path.relative_to(folder))
                digest = sha(path)
                if digest != cell['feedback_audit']['source_sha256'].get(key):
                    raise ValueError('audited program changed: ' + key)
                sources[key] = digest
            source = read(program / 'input_private.json')
            outer = spans[event['span_id']]
            if source['code'] != json.loads(outer['action']['arguments'])['code']:
                raise ValueError('program differs from model tool request')
            if source['api_schemas'] != {n: schemas[n] for n in catalog.visible}:
                raise ValueError('program-start catalog differs')
            programs += 1
            for receipt in outer['observation']['api_receipts']:
                sid = receipt['span_id']; inner = by_span[sid]; span = spans[sid]
                if sid in covered: raise ValueError('duplicate internal receipt')
                covered.add(sid)
                if span['observation'].get('format_error'):
                    api = span['action']['name']
                    exposed = {n: schemas[n] for n in catalog.visible}
                    detail = {'run_id': cell['run_id'], 'task_id': cell['task_id'],
                        'arm': cell['arm'], 'call_id': call_id, 'span_id': sid,
                        'api': api if api in schemas else 'unlisted_api',
                        **rejection_shape(span, inner, exposed),
                        'program_characters': len(source['code']),
                        'call_site_shape': call_shape(source['code'], api)}
                    later = [e for e in events[positions[sid] + 1:]
                        if e['stage'] == 'python_api' and e['api_request_sent']
                        and spans[e['span_id']]['action']['name'] == api]
                    first = later[0] if later else None
                    detail['first_later_same_api_dispatch'] = ({'call_id': first['call'],
                        'span_id': first['span_id'], 'same_program_call': first['call'] == call_id,
                        'argument_changes': argument_changes(json.loads(span['action']['arguments']),
                            json.loads(spans[first['span_id']]['action']['arguments']))} if first else None)
                    index = next(i for i, call in enumerate(usage) if call['id'] == call_id)
                    following = usage[index + 1] if index + 1 < len(usage) else None
                    detail['following_model_input_tokens'] = following['input_tokens'] if following else None
                    detail['following_model_usage_status'] = following['status'] if following else None
                    detail['following_cost_is_saved_or_avoidable'] = False
                    rejected.append(detail)
                catalog.visible.update(inner['new_tools'])
        expected = {e['span_id'] for e in events if e['stage'] == 'python_api'}
        if covered != expected:
            raise ValueError('internal request coverage differs')
        row.update(programs_checked=programs, internal_requests_checked=len(covered),
                   rejected_requests=len(rejected), source_sha256=sources)
        rows.append(row); failures.extend(rejected)
    elapsed = time.monotonic() - started
    if elapsed > plan['max_wall_seconds']: raise TimeoutError('passive inspection time cap')
    totals = {
        'programs_checked': sum(r.get('programs_checked', 0) for r in rows),
        'internal_requests_checked': sum(r.get('internal_requests_checked', 0) for r in rows),
        'rejected_requests': len(failures),
        'contract_exposed': sum(f['contract_exposed_at_rejection'] for f in failures),
        'empty_contract_extra_argument_candidates': sum(f['empty_contract_extra_argument_candidate'] for f in failures),
        'later_same_api_dispatches_found': sum(f['first_later_same_api_dispatch'] is not None for f in failures),
        'single_literal_call_site_rejections': sum(f['call_site_shape'].get('literal_matching_sites') == 1 for f in failures),
    }
    return {'phase': 'P48', 'kind': 'posthoc_passive_repair_scope_inspection',
        'all_planned_cells_accounted': len(rows) == 12, 'rows': rows,
        'rejections': failures, 'totals': totals, 'wall_seconds': elapsed,
        **{key: 0 for key in zero}, 'automatic_repairs': 0, 'novel_method_established': False,
        'quality_preservation_claim': False, 'measured_savings_claim': False,
        'source_sha256': {'plan': sha(root / PLAN), 'comparison': sha(comparison),
            'script': sha(Path(__file__)), 'closed_batch_status': sha(status)},
        'limits': ['All twelve planned P47 cells retained; this is posthoc development analysis.',
            'Later argument changes are hindsight observations, not runtime repair knowledge.',
            'Type/value correspondence does not certify semantic equivalence or final success.',
            'Static call sites do not identify dynamic iterations, aliases, or safe continuation points.',
            'Character counts and following model costs are not savings or avoidable-cost bounds.']}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--storage-root', type=Path, required=True)
    parser.add_argument('--repo-root', type=Path, default=ROOT)
    args = parser.parse_args()
    target = args.repo_root / 'reports/P48_repair_scope.json'
    if target.exists(): raise FileExistsError('preserve completed inspection')
    result = inspect(args.storage_root, args.repo_root)
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(result['totals'], ensure_ascii=False))
