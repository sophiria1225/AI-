"""Map the closed P45 records to already-exposed contract feedback, without execution."""
import argparse
import ast
from collections import Counter
import json
from pathlib import Path
import time

from appworld_native_tools import NativeCatalog
from contract_feedback import MODES, UNKNOWN_PARAMETER, canonical, make_feedback
from diagnose_documentation_comparison import require_closed
from later_handoff_sources import prepare_later_sources
from recorded_python_replay import reply_from_receipt
from run_handoff_factors import ROOT, read, sha

PLAN = 'configs/P46_contract_feedback_v01.json'


def schema_lookups(code):
    names = set()
    for node in ast.walk(ast.parse(code)):
        if (isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name)
                and node.value.id == 'api_schemas' and isinstance(node.slice, ast.Constant)
                and isinstance(node.slice.value, str)):
            names.add(node.slice.value)
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name) and node.func.value.id == 'api_schemas'
                and node.func.attr == 'get' and node.args and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)):
            names.add(node.args[0].value)
    return names


def inspect(storage, root):
    started = time.monotonic()
    plan = read(root / PLAN)
    if (plan['phase'] != 'P46' or plan['source_phase'] != 'P45'
            or plan['feedback_modes'] != list(MODES) or plan['model_calls'] != 0
            or plan['environment_api_requests'] != 0 or plan['max_wall_seconds'] != 120):
        raise ValueError('outside fixed passive inspection')
    report_path = root / 'reports/P45_comparison.json'
    report = read(report_path)
    base = storage / 'records/context_pilot'
    state_path = base / 'P45_batch_v01/status.json'
    require_closed(report, read(state_path))
    if sha(state_path) != report['source_sha256']['batch_status']:
        raise ValueError('audited closed status changed')
    _, _, tools, schemas, items = prepare_later_sources(storage, root)
    items = {item['task_id']: item for item in items}
    rows = []; failures = []
    for cell in report['rows']:
        if time.monotonic() - started > plan['max_wall_seconds']:
            raise TimeoutError('bounded offline inspection')
        trial = base / cell['run_id']
        names = ('events.json', 'spans.json', 'usage.json', 'prefix_events.json')
        for name in names:
            if sha(trial / name) != cell['source_sha256'][name]:
                raise ValueError('audited record changed: ' + name)
        events, spans, usage, prefix_events = [read(trial / n) for n in names]
        by_id = {e['span_id']: e for e in events}
        catalog = NativeCatalog(tools)
        for event in prefix_events:
            catalog.visible.update(event['new_tools'])
        count = 0; indices = Counter(); sources = {}; calls = {}
        for event in events:
            if event['stage'] != 'model_tool':
                continue
            call_id = event['call']; indices[call_id] += 1
            folder = trial / 'programs' / f'{call_id}_{indices[call_id]:02d}'
            if not folder.exists():
                continue
            source, result = (read(folder / n) for n in ('input_private.json', 'result_private.json'))
            outer = spans[event['span_id']]
            if source['code'] != json.loads(outer['action']['arguments'])['code']:
                raise ValueError('executed source differs from recorded tool request')
            count += 1
            if (source['program_index'] != len(items[cell['task_id']]['programs']) + count
                    or source['api_schemas'] != {n: schemas[n] for n in catalog.visible}):
                raise ValueError('program-start index or exposed schemas differ')
            wires = [json.loads(line) for line in (folder / 'wire_private.jsonl').read_text().splitlines()]
            packets = [w for w in wires if w['kind'] == 'api']
            refs = outer['observation']['api_receipts']
            if len(packets) != len(refs) or not wires or wires[-1]['kind'] != 'done':
                raise ValueError('wire completion or receipt correspondence differs')
            calls.setdefault(call_id, []).append({'lookups': schema_lookups(source['code']),
                                                  'sent_api': result['api_requests']})
            for packet, ref in zip(packets, refs, strict=True):
                sid = ref['span_id']; inner_event = by_id[sid]; span = spans[sid]
                # This only validates/reconstructs recorded JSON; no API is run.
                reply_from_receipt(packet, span, inner_event, schemas)
                error = span['observation'].get('format_error')
                if error:
                    row = {'action': span['action'], 'observation': span['observation'],
                           'api_request_sent': inner_event['api_request_sent'],
                           'effects_unknown': inner_event['effects_unknown']}
                    exposed = {n: schemas[n] for n in catalog.visible}
                    feedback = {mode: make_feedback(row, exposed, mode, plan['max_feedback_characters'])
                                for mode in MODES}
                    function = span['action']['name']
                    failures.append({'run_id': cell['run_id'], 'task_id': cell['task_id'],
                        'arm': cell['arm'], 'call_id': call_id, 'span_id': sid, 'api': function,
                        'category': 'unknown_parameter' if error == UNKNOWN_PARAMETER else 'other_rejection',
                        'already_exposed': function in exposed,
                        'feedback': {mode: {'available': value is not None,
                            'characters': len(canonical(value)) if value is not None else 0,
                            'schema_sha256': value['schema_sha256'] if value is not None else None,
                            'actual_mode': value['mode'] if value is not None else None}
                            for mode, value in feedback.items()}})
                catalog.visible.update(inner_event['new_tools'])
            for name in ('input_private.json', 'result_private.json', 'wire_private.jsonl'):
                sources[str((folder / name).relative_to(trial))] = sha(folder / name)
        for failure in (f for f in failures if f['run_id'] == cell['run_id']):
            index = next(i for i, c in enumerate(usage) if c['id'] == failure['call_id'])
            following = usage[index + 1] if index + 1 < len(usage) else None
            programs = calls.get(following['id'], []) if following else []
            match = bool(programs) and any(failure['api'] in p['lookups'] for p in programs)
            failure['next_program_contains_schema_lookup_and_sends_no_api'] = match and sum(p['sent_api'] for p in programs) == 0
            failure['following_known_tokens'] = (following['input_tokens'] + following['output_tokens']
                if following and following['status'] == 'ok' else None)
            failure['following_cost_is_claimed_savings'] = False
        selected = [f for f in failures if f['run_id'] == cell['run_id']]
        rows.append({'run_id': cell['run_id'], 'task_id': cell['task_id'], 'arm': cell['arm'],
                     'model_calls': cell['model_calls'], 'programs_checked': count,
                     'rejected_requests': len(selected),
                     'feedback_candidates': sum(f['feedback']['public_schema']['available'] for f in selected),
                     'source_sha256': sources})
    return {'phase': 'P46', 'all_eight_cells_inspected': len(rows) == 8,
            'kind': 'posthoc_implementation_probe', 'rows': rows, 'rejections': failures,
            'programs_checked': sum(r['programs_checked'] for r in rows),
            'rejected_requests': len(failures),
            'feedback_candidates': sum(f['feedback']['public_schema']['available'] for f in failures),
            'candidate_tasks': len({f['task_id'] for f in failures if f['feedback']['public_schema']['available']}),
            'next_call_schema_lookup_syntax_without_api': sum(f['next_program_contains_schema_lookup_and_sends_no_api'] for f in failures),
            'wall_seconds': time.monotonic() - started,
            'model_calls': 0, 'environment_api_requests': 0, 'tokenizer_requests': 0,
            'evaluator_calls': 0, 'reserved_scenarios_read': 0,
            'novel_method_claim': False, 'quality_preservation_claim': False, 'measured_savings_claim': False,
            'source_sha256': {'plan': sha(root / PLAN), 'comparison': sha(report_path),
                'script': sha(Path(__file__)), 'feedback': sha(root / 'scripts/contract_feedback.py')},
            'limits': ['Selected after observing P45 rejection and schema-lookup patterns, not a blind discovery test.',
                       'Character counts are not token savings; subsequent call costs are not saved costs.',
                       'Literal api_schemas lookup syntax does not prove the lookup executed or served a particular decision.',
                       'All eight known-task conditions remain, including the unknown-usage unevaluated cell.',
                       'No hypothetical feedback was sent to a model and no saved program was executed.']}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--storage-root', type=Path, required=True)
    parser.add_argument('--repo-root', type=Path, default=ROOT); args = parser.parse_args()
    target = args.repo_root / 'reports/P46_contract_feedback.json'
    if target.exists(): raise FileExistsError('preserve completed probe')
    result = inspect(args.storage_root, args.repo_root)
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print({k: result[k] for k in ('programs_checked', 'rejected_requests', 'feedback_candidates', 'candidate_tasks')})
