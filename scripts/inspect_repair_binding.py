"""Build P49 packets from rejection-time information only; no proposals or APIs."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import time

from appworld_native_tools import NativeCatalog
from diagnose_contract_comparison import require_closed
from later_handoff_sources import prepare_later_sources
from request_repair_binding import RepairBinding, RepairNotAdmitted, canonical
from run_handoff_factors import ROOT, read, sha

PLAN = 'configs/P49_repair_binding_v01.json'


def inspect(storage, root):
    started = time.monotonic()
    plan = read(root / PLAN)
    zero = ('model_generations', 'environment_api_requests', 'program_reexecutions',
            'evaluator_calls', 'tokenizer_requests', 'reserved_scenarios_read')
    if (plan['phase'] != 'P49' or plan['source_phase'] != 'P48'
            or plan['planned_cells'] != 12 or plan['max_wall_seconds'] != 120
            or any(plan[k] != 0 for k in zero)
            or plan['max_packet_characters'] != 16000
            or plan['max_private_binding_characters'] != 65536
            or plan['max_fields_per_request_or_contract'] != 128
            or plan['proposal_attempts_per_binding'] != 1
            or plan['source_request_values_may_change']
            or plan['future_request_used_to_propose_mapping']):
        raise ValueError('outside fixed binding inspection')
    report_path = root / 'reports/P47_comparison.json'
    scope_path = root / 'reports/P48_repair_scope.json'
    report, scope = read(report_path), read(scope_path)
    if not scope['all_planned_cells_accounted'] or sha(report_path) != scope['source_sha256']['comparison']:
        raise ValueError('source inspection changed')
    base = storage / 'records/context_pilot'
    status = base / 'P47_batch_v01/status.json'
    require_closed(report, read(status))
    if sha(status) != report['source_sha256']['batch_status']:
        raise ValueError('closed batch changed')
    _, _, tools, schemas, _ = prepare_later_sources(storage, root)
    expected = {(r['run_id'], r['span_id']) for r in scope['rejections']}
    found = set(); rows = []; bindings = []; packets = []
    scope_rows = {r['run_id']: r for r in scope['rows']}
    private = base / 'P49_repair_binding_v01'
    if private.exists(): raise FileExistsError('preserve previous packet inspection')
    for cell in report['rows']:
        if time.monotonic() - started > plan['max_wall_seconds']: raise TimeoutError('inspection cap')
        row = {k: cell[k] for k in ('run_id', 'task_id', 'arm', 'record_status')}
        if cell['record_status'] == 'not_run_after_stop':
            rows.append(row); continue
        folder = base / cell['run_id']
        for name, digest in scope_rows[cell['run_id']]['source_sha256'].items():
            if sha(folder / name) != digest: raise ValueError('P48 program source changed')
        names = ('events.json', 'spans.json', 'prefix_events.json')
        for name in names:
            if sha(folder / name) != cell['source_sha256'][name]:
                raise ValueError('P47 request source changed')
        events, spans, prefix = [read(folder / n) for n in names]
        catalog = NativeCatalog(tools)
        for event in prefix: catalog.visible.update(event['new_tools'])
        count = 0
        for event in events:
            if event['stage'] != 'python_api': continue
            span = spans[event['span_id']]
            error = span['observation'].get('format_error')
            if error:
                key = (cell['run_id'], event['span_id'])
                if key not in expected or key in found: raise ValueError('source rejection coverage changed')
                found.add(key); count += 1
                exposed = {name: schemas[name] for name in catalog.visible}
                flags = {'api_request_sent': event['api_request_sent'],
                         'effects_unknown': event['effects_unknown'], 'format_error': error}
                record = {**{k: cell[k] for k in ('run_id', 'task_id', 'arm')},
                    'call_id': event['call'], 'span_id': event['span_id'],
                    'api': span['action']['name'] if span['action']['name'] in schemas else 'unlisted_api',
                    'proposal_generated': False, 'api_dispatched': False}
                at = time.perf_counter()
                try:
                    binding = RepairBinding(span['action'], exposed, **flags)
                    packet = binding.packet(); payload = canonical(packet)
                    record.update(admitted=True, admission_reason='bound_request_and_exposed_contract',
                        packet_characters=len(payload),
                        packet_sha256=hashlib.sha256(payload.encode()).hexdigest(),
                        unknown_parameters=len(packet['unknown_parameters']),
                        protected_parameters=len(packet['protected_parameter_names']),
                        admissible_rename_edges=sum(map(len, packet['allowed_rename_targets'].values())),
                        complete_type_compatible_renaming_exists=packet['complete_type_compatible_renaming_exists'],
                        empty_contract_normalization_candidate=packet['drop_allowed_only_for_empty_contract'])
                    packets.append((f'{cell["run_id"]}_{event["span_id"]}.json', payload))
                except RepairNotAdmitted as exc:
                    record.update(admitted=False, admission_reason=str(exc))
                record['construction_seconds'] = time.perf_counter() - at
                bindings.append(record)
            catalog.visible.update(event['new_tools'])
        row.update(rejections_checked=count)
        rows.append(row)
    if found != expected: raise ValueError('missing source rejection')
    elapsed = time.monotonic() - started
    if elapsed > plan['max_wall_seconds']: raise TimeoutError('inspection cap')
    private.mkdir()
    for name, payload in packets: (private / name).write_text(payload + '\n')
    admitted = [r for r in bindings if r['admitted']]
    totals = {'rejections_checked': len(bindings), 'bindings_admitted': len(admitted),
        'bindings_refused': len(bindings) - len(admitted),
        'empty_contract_normalization_candidates': sum(r['empty_contract_normalization_candidate'] for r in admitted),
        'complete_rename_candidates': sum(r['complete_type_compatible_renaming_exists'] for r in admitted),
        'requires_broader_repair': sum(not r['empty_contract_normalization_candidate']
            and not r['complete_type_compatible_renaming_exists'] for r in admitted),
        'packet_characters': sum(r['packet_characters'] for r in admitted),
        'construction_seconds': sum(r['construction_seconds'] for r in bindings)}
    return {'phase': 'P49', 'kind': 'passive_binding_applicability_inspection',
        'all_planned_cells_accounted': len(rows) == 12, 'rows': rows, 'bindings': bindings,
        'totals': totals, 'wall_seconds': elapsed, **{key: 0 for key in zero},
        'proposals_generated': 0, 'proposals_derived_from_later_requests': 0,
        'repairs_executed': 0, 'novel_method_established': False,
        'quality_preservation_claim': False, 'measured_savings_claim': False,
        'source_sha256': {'plan': sha(root / PLAN), 'comparison': sha(report_path),
            'scope_inspection': sha(scope_path), 'script': sha(Path(__file__)),
            'binding': sha(root / 'scripts/request_repair_binding.py')},
        'limits': ['Graph feasibility preserves value transport and supported scalar constraints only, not intended meaning.',
            'Protected parameter names do not imply their existing values are semantically correct.',
            'No mapping was generated or executed, and no live Python frame was resumed.',
            'Packet characters are not token savings; admission and fallback overhead require a separate comparison.',
            'Same known tasks and repeated arms are not independent scenarios.']}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--storage-root', type=Path, required=True)
    parser.add_argument('--repo-root', type=Path, default=ROOT)
    args = parser.parse_args()
    target = args.repo_root / 'reports/P49_repair_binding.json'
    if target.exists(): raise FileExistsError('preserve completed inspection')
    result = inspect(args.storage_root, args.repo_root)
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(result['totals']))
