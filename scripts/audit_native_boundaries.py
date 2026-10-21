"""Verify local boundary files against recorded public execution, without replay.

Output contains counts, categories and whole-file hashes only. DB bytes are hashed,
never interpreted as hidden task truth or returned to an executing agent.
"""
import argparse
import hashlib
import json
from pathlib import Path

from native_boundary_record import verify_boundary
from native_conversation import NativeConversation
from run_native_appworld import system_prompt_for


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_state(state, usage, events, spans, plan, run_id, task_id, visible, arm='native_roles'):
    errors = []
    tokens = sum(row['input_tokens'] + row['output_tokens'] for row in usage if row['status'] == 'ok')
    expected = {'run_id': run_id, 'task_id': task_id, 'arm': arm,
                'model_calls': len(usage), 'known_total_tokens': tokens,
                'api_requests': sum(row['api_request_sent'] for row in events),
                'span_ids': list(spans), 'remaining_tokens': plan['max_total_tokens'] - tokens,
                'declared_complete': any(row['declared_complete'] for row in events),
                'rng_and_process_state_captured': False}
    if visible is not None:
        expected['visible_api_schemas'] = sorted(visible)
    for key, value in expected.items():
        if state.get(key) != value:
            errors.append('boundary state disagrees: ' + key)
    elapsed = state.get('elapsed_wall_seconds')
    if (not isinstance(elapsed, (int, float)) or elapsed < 0
            or state.get('remaining_wall_seconds_before_capture') != max(0, plan['max_wall_seconds'] - elapsed)):
        errors.append('boundary wall accounting disagrees')
    return errors


def audit(trial, appworld_root, allow_running=False):
    if not (trial / 'summary.json').exists() and not allow_running:
        raise ValueError('trial is running; request an explicitly partial audit')
    index = read(trial / 'boundary_index.json')  # Only published, immutable points.
    usage = read(trial / 'usage.json') if (trial / 'usage.json').exists() else []
    events = read(trial / 'events.json') if (trial / 'events.json').exists() else []
    spans = read(trial / 'spans.json') if (trial / 'spans.json').exists() else {}
    plan, provenance = read(trial / 'plan.json'), read(trial / 'provenance.json')
    if plan['phase'] not in ('P11', 'P12', 'P13', 'P14', 'P18', 'P19', 'P22', 'P23', 'P24', 'P25', 'P26', 'P27', 'P28'):
        raise ValueError('requires a boundary-recorded native trial')
    sources = ['run_native_appworld.py', 'native_conversation.py', 'native_boundary_record.py']
    if plan['phase'] in ('P27','P28'):
        sources += ['run_code_appworld.py', 'code_agent_interface.py', 'container_api_python.py']
    if plan['phase'] == 'P28':
        sources += ['run_code_control_appworld.py', 'code_runtime_prompts.py']
    if plan['phase'] == 'P23':
        sources += ['native_compute_session.py', 'native_data_compute.py', 'container_data_python.py']
    if plan['phase'] == 'P12':
        sources += ['run_native_recent.py', 'native_recent_window.py', 'native_memory_view.py']
    if plan['phase'] in ('P13', 'P14', 'P19'):
        sources += ['run_native_generated.py', 'native_focus_memory.py', 'native_memory_view.py']
    if plan['phase'] in ('P14', 'P19'):
        sources.append('native_ledger_memory.py')
    if plan['phase'] == 'P19':
        sources += ['aligned_ledger_memory.py', 'ledger_contract.py']
    for name in sources:
        if sha(Path(__file__).parent / name) != provenance['sources'][name]:
            raise ValueError('use the frozen boundary/history implementation for this audit')
    if plan['phase'] in ('P27','P28'):
        from run_code_appworld import code_system_prompt
        prompt = code_system_prompt()
        if plan['phase'] == 'P28':
            from code_runtime_prompts import control_system_prompt
            prompt = control_system_prompt(plan)
    else:
        prompt = system_prompt_for(plan)
    conversation = NativeConversation(prompt, read(trial / 'public_task.json'))
    initial_visible = None
    if usage:
        initial_visible = {tool['function']['name'] for tool in read(
            trial / usage[0]['id'] / 'request.json')['tools']} - {'read_span', 'compute_data'}
    if plan['phase'] in ('P27','P28'):
        from inspect_appworld_api_schemas import load_public_tools
        from appworld_native_tools import NativeCatalog
        initial_visible = NativeCatalog(load_public_tools(appworld_root/'data')[0]).visible
    errors, rows, seen_objects, prior_dbs = [], [], set(), None
    reconstructed_calls = 0
    expected_boundaries = [0] + [i for i, call in enumerate(usage, 1) if call['role'] == 'agent']
    for position, entry in enumerate(index):
        cid = entry['id']
        count = 0 if cid == 'initial' else int(cid.removeprefix('call_'))
        if ((position == 0 and cid != 'initial') or position >= len(expected_boundaries)
                or count != expected_boundaries[position]):
            errors.append('published boundary sequence is not contiguous')
        path = trial / 'boundaries/manifests' / (cid + '.json')
        if sha(path) != entry['manifest_sha256']:
            errors.append(cid + ': manifest differs from published index')
        manifest = read(path)
        verified = verify_boundary(trial / 'boundaries', cid)

        def captured(name, default=None):
            metadata = manifest['files'].get('harness/' + name)
            return default if metadata is None else read(trial / 'boundaries/objects' / metadata['sha256'])

        prefix_usage = usage[:count]
        prefix_ids = {row['id'] for row in prefix_usage}
        prefix_events = [row for row in events if row['call'] in prefix_ids]
        prefix_spans = {row['span_id']: spans[row['span_id']] for row in prefix_events}
        if count and (len(prefix_usage) != count or any(row['status'] != 'ok' for row in prefix_usage)):
            errors.append(cid + ': boundary includes unknown model usage')
        for name, expected in [('usage.json', prefix_usage), ('events.json', prefix_events),
                               ('spans.json', prefix_spans)]:
            default = {} if name == 'spans.json' else []
            if captured(name, default) != expected:
                errors.append(cid + ': captured execution prefix differs: ' + name)
        if plan['phase'] == 'P23':
            all_compute = read(trial/'compute_records.json') if (trial/'compute_records.json').exists() else []
            prefix_compute = [r for r in all_compute if r['call_id'] in prefix_ids]
            if captured('compute_records.json', []) != prefix_compute:
                errors.append(cid + ': captured computation records differ')
            state_compute = manifest['state'].get('ordinary_compute', {})
            if (state_compute.get('attempts') != len(prefix_compute)
                    or state_compute.get('executions') != sum(r['execution_started'] for r in prefix_compute)
                    or abs(state_compute.get('wall_seconds', -1) - sum(r['wall_seconds'] for r in prefix_compute)) > 1e-8):
                errors.append(cid + ': captured computation costs differ')
        for name in ('plan.json', 'provenance.json', 'public_task.json'):
            if manifest['files']['harness/' + name]['sha256'] != sha(trial / name):
                errors.append(cid + ': immutable harness input differs: ' + name)
        while reconstructed_calls < count:
            call_id = usage[reconstructed_calls]['id']
            if usage[reconstructed_calls]['role'] == 'agent':
                response = read(trial / call_id / 'response.json')['message']
                call_spans = [spans[row['span_id']] for row in events if row['call'] == call_id
                              and row.get('stage', 'model_tool') == 'model_tool']
                conversation.append(response, call_spans)
            reconstructed_calls += 1
        if captured('conversation_private.json') != conversation.messages():
            errors.append(cid + ': captured conversation differs from actual responses/results')
        visible = None if initial_visible is None else initial_visible | {
            name for row in prefix_events for name in row['new_tools']}
        errors += [cid + ': ' + error for error in check_state(
            manifest['state'], prefix_usage, prefix_events, prefix_spans, plan,
            trial.name, provenance['task_id'], visible, plan['arms'][0])]
        unique_objects = {row['sha256']: row['bytes'] for row in manifest['files'].values()}
        new_bytes = sum(size for digest, size in unique_objects.items() if digest not in seen_objects)
        if new_bytes != entry['new_object_bytes'] or new_bytes != manifest['new_object_bytes']:
            errors.append(cid + ': deduplicated object accounting differs')
        seen_objects.update(unique_objects)
        dbs = {name: row['sha256'] for name, row in manifest['files'].items() if name.startswith('dbs/')}
        if not dbs:
            errors.append(cid + ': DB change files are missing')
        changed = None if prior_dbs is None else sum(dbs.get(n) != prior_dbs.get(n) for n in set(dbs) | set(prior_dbs))
        prior_dbs = dbs
        rows.append({'checkpoint_id': cid, 'model_calls': count,
                     'api_requests': manifest['state']['api_requests'],
                     'known_total_tokens': manifest['state']['known_total_tokens'],
                     'files_verified': verified['files_verified'], 'db_files': len(dbs),
                     'changed_db_files_since_prior': changed, 'new_object_bytes': new_bytes,
                     'capture_wall_seconds': entry['wall_seconds'], 'manifest_sha256': sha(path)})
    finished = (trial / 'summary.json').exists()
    final_db_match = None
    if finished:
        summary = read(trial / 'summary.json')
        if len(index) != summary['boundary_records']:
            errors.append('summary boundary count differs')
        if summary['stop_reason'] == 'agent_declared_complete':
            if len(index) != len(expected_boundaries):
                errors.append('completed execution is missing boundary records')
            output_dbs = appworld_root / 'experiments/outputs' / trial.name / 'tasks' / provenance['task_id'] / 'dbs'
            actual = {'dbs/' + p.name: sha(p) for p in output_dbs.iterdir() if p.is_file()}
            final_db_match = actual == prior_dbs
            if not final_db_match:
                errors.append('final captured DB files differ from submitted environment state')
    return {'run_id': trial.name, 'status': 'finished' if finished else 'partial',
            'boundary_records': rows, 'audit_errors': errors, 'final_db_files_match': final_db_match,
            'model_calls_by_auditor': 0, 'environment_operations': 0, 'final_evaluations': 0,
            'scope': 'Byte integrity, actual execution prefix, budget and final DB-file correspondence. '
                     'No full process restore or causal state-equivalence claim.'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--trial', type=Path, required=True)
    parser.add_argument('--appworld-root', type=Path, required=True)
    parser.add_argument('--allow-running', action='store_true')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.trial, args.appworld_root, args.allow_running)
    result['auditor_sha256'] = sha(Path(__file__))
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'run_id': result['run_id'], 'status': result['status'],
                      'boundaries': len(result['boundary_records']), 'audit_errors': result['audit_errors']}))
