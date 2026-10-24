"""Once-only, bounded P92 inventory of all five already-known P69 records.

Saved programs are parsed and their receipts checked; never executed. Original
success/failure and P69 opportunities are copied unchanged, not re-evaluated.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import signal
import subprocess
import time

from inspect_public_read_opportunity import read_bound, sha
from read_view_compatibility import check_saved_boundary, inspect_program

PLAN = 'configs/P92_recorded_view_compatibility_v01.json'
RUNS = ['P18_04_ROLES', 'P25_04_GUIDED', 'P29_04_CODE', 'P68_01_EXPORT_NATIVE', 'P68_02_EXPORT_CONTROLLED']
ZERO = ('model_generations', 'environment_api_requests', 'evaluator_calls',
        'saved_code_executions', 'task_databases_read', 'reserved_scenarios_read')
PROGRAM_FILES = {'input_private.json', 'result_private.json', 'wire_private.jsonl'}


def inspect(storage, root):
    began = time.monotonic(); plan = json.loads((root/PLAN).read_text())
    fixed = dict(phase='P92', run_ids=RUNS, max_wall_seconds=120, max_file_bytes=16777216,
        max_programs_per_record=80, max_source_characters=20000, max_ast_nodes=5000,
        max_events_per_record=4000, measured_savings=None, novel_method_claim=False,
        **{k: 0 for k in ZERO})
    if any(plan.get(k) != v for k, v in fixed.items()): raise ValueError('fixed_P92_scope_changed')
    for name, expected in plan['source_sha256'].items():
        if sha(root/name) != expected: raise ValueError('fixed_helper_changed: '+name)
    old = read_bound(root/'reports/P69_export_acquisition_scope.json',
                     plan['source_sha256']['reports/P69_export_acquisition_scope.json'])
    if [r['run_id'] for r in old['rows']] != RUNS: raise ValueError('all_five_original_rows_required')
    if set(plan['program_files']) != set(RUNS): raise ValueError('fixed_record_population_changed')
    rows = []
    for original in old['rows']:
        rid = original['run_id']; folder = storage/'records/context_pilot'/rid
        folder.resolve().relative_to((storage/'records/context_pilot').resolve())
        values = {name: read_bound(folder/name, digest) for name, digest in original['source_sha256'].items()}
        events, spans = values['events.json'], values['spans.json']
        if len(events) > 4000: raise ValueError('event_bound')
        by_id = {e['span_id']: e for e in events}
        if len(by_id) != len(events): raise ValueError('duplicate_event_identity')
        groups = plan['program_files'][rid]
        actual_files = {str(p.relative_to(folder)) for p in (folder/'programs').glob('*/*') if p.is_file() and p.name in PROGRAM_FILES}
        expected_files = {f'programs/{program}/{name}' for program, files in groups.items() for name in files}
        if actual_files != expected_files or len(groups) > 80: raise ValueError('saved_program_file_inventory_changed')
        outer = [e for e in events if e.get('stage') == 'model_tool'
                 and spans[e['span_id']]['action']['name'] == 'run_python']
        if len(outer) != len(groups): raise ValueError('saved_program_count_differs_from_receipts')
        occurrences = Counter(); programs = []
        for event in outer:
            occurrences[event['call']] += 1
            program = event['call']+f'_{occurrences[event["call"]]:02d}'
            files = groups[program]
            if set(files) != PROGRAM_FILES: raise ValueError('all_saved_program_artifacts_required')
            source = read_bound(folder/'programs'/program/'input_private.json', files['input_private.json'])
            expected = read_bound(folder/'programs'/program/'result_private.json', files['result_private.json'])
            path = folder/'programs'/program/'wire_private.jsonl'
            if path.stat().st_size > 16777216 or sha(path) != files['wire_private.jsonl']:
                raise ValueError('saved_wire_changed')
            wire = [json.loads(line) for line in path.read_text().splitlines()]
            boundary = check_saved_boundary(source, expected, wire)
            if boundary['program_index'] != len(programs)+1: raise ValueError('noncontiguous_program_indices')
            parent = spans[event['span_id']]
            if json.loads(parent['action']['arguments'])['code'] != source['code']:
                raise ValueError('parent_code_differs')
            receipts = parent['observation']['api_receipts']
            if len(receipts) != len(wire)-1: raise ValueError('receipt_count_differs')
            sent = 0
            for packet, receipt in zip(wire[:-1], receipts, strict=True):
                sid = receipt['span_id']; api_event = by_id[sid]; action = spans[sid]['action']
                if (api_event.get('stage') != 'python_api' or api_event['call'] != event['call']
                        or action['name'] != packet['app']+'__'+packet['api']
                        or json.loads(action['arguments']) != packet['arguments']
                        or type(api_event['api_request_sent']) is not bool):
                    raise ValueError('saved_request_receipt_mismatch')
                sent += api_event['api_request_sent']
            if sent != boundary['original_api_requests']: raise ValueError('saved_dispatch_count_differs')
            programs.append(dict(program=program, source_sha256=files,
                                 boundary=boundary, syntax=inspect_program(source['code'])))
        rows.append({k: original[k] for k in ('run_id', 'original_official_success', 'show_song_requests',
            'task_fields_preknown_requests', 'same_request_response_preknown_requests', 'source_sha256')}
            | dict(record_format='saved_python_programs' if programs else 'direct_api_without_saved_python',
                   event_stages=dict(sorted(Counter(e.get('stage', 'legacy_no_stage') for e in events).items())),
                   programs=programs, program_count=len(programs),
                   compatible_replay_executed=False, runtime_view_equivalence_established=False))
    return dict(phase='P92', status='complete', checked_at=datetime.now(timezone.utc).isoformat(),
        source_commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip(),
        plan_sha256=sha(root/PLAN), source_sha256=plan['source_sha256'], rows=rows,
        original_records=5, inspected_programs=sum(r['program_count'] for r in rows),
        wall_seconds=time.monotonic()-began, **{k: 0 for k in ZERO}, novel_method_claim=False,
        measured_savings=None, selection=plan['selection'],
        interpretation='Saved structure and syntax only. Full-response compatibility, dynamic liveness, avoided API requests and task improvement are not established.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--storage-root', type=Path, required=True); args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    target = root/'reports/P92_recorded_view_compatibility.json'
    failure = root/'reports/P92_recorded_view_compatibility_failure.json'
    if target.exists() or failure.exists(): raise FileExistsError('preserve_every_P92_inspection')
    def expired(*_): raise TimeoutError('fixed_readonly_deadline')
    previous = signal.signal(signal.SIGALRM, expired); signal.setitimer(signal.ITIMER_REAL, 120)
    began = time.monotonic()
    try:
        result = inspect(args.storage_root.resolve(), root)
        target.write_text(json.dumps(result, indent=2)+'\n')
    except BaseException as error:
        failure.write_text(json.dumps(dict(phase='P92', status='failed_readonly_inspection',
            error_type=type(error).__name__, detail=str(error), wall_seconds=time.monotonic()-began,
            **{k: 0 for k in ZERO}), indent=2)+'\n'); raise
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0); signal.signal(signal.SIGALRM, previous)
    print(json.dumps(dict(records=5, programs=result['inspected_programs'], wall_seconds=result['wall_seconds'],
        rows=[{k: r[k] for k in ('run_id', 'record_format', 'program_count')} for r in result['rows']])))


if __name__ == '__main__': main()
