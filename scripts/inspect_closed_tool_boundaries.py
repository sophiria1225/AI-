"""Inspect closed P80/P81 response shapes and existing P83 parser controls.

Read-only, post-hoc diagnosis. No generation, tokenization, inference context,
environment execution, semantic reasoning inspection, or argument repair.
"""
import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import tarfile
import time

ROOT = Path(__file__).resolve().parents[1]
BACKEND = '620d2225cc436ab0b001e3200e590e3b286ef9ab'
ARCHIVE_SHA = '1d4a987d9bd048f6e93107e838026438df70fbde237fc0c69c63d600512b4bd9'
FILES = ('reports/P80_comparison.json', 'reports/P81_repetitions.json',
         'reports/P81_fallback_reference_diagnostic.json', 'reports/P83_fallback_prompt.json',
         'reports/P81_P83_results_provenance_20261024.json', 'reports/P73_renderer_build.json',
         'scripts/local_llama.py', 'scripts/native_conversation.py', 'scripts/serve_research_model.py')
BACKEND_FILES = ('common/parsers/minimax-m3.cpp', 'common/chat.cpp',
                 'common/chat-peg-parser.cpp', 'common/sampling.cpp',
                 'tools/server/server-common.cpp', 'tools/server/server-task.h')


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(',', ':')).encode()).hexdigest()


def classify_response(response):
    """Unknown/error completions remain unobservable, never valid empty output."""
    if response.get('status') == 'error':
        return dict(terminal_observed=False, finish_reason=None, output_tokens=None,
                    tool_calls=None, invalid_json_arguments=None, nonobject_arguments=None,
                    fallback_eligible=None)
    if response.get('status') != 'ok' or response.get('done_reason') not in ('stop', 'length', 'tool_calls'):
        raise ValueError('unsupported_saved_response')
    output = response.get('output_tokens')
    if type(output) is not int or output < 0:
        raise ValueError('invalid_known_output_count')
    calls = response['message'].get('tool_calls') or []
    if not isinstance(calls, list):
        raise ValueError('unsupported_tool_list')
    invalid, nonobject = 0, 0
    for call in calls:
        arguments = call['function']['arguments']
        if not isinstance(arguments, str):
            raise ValueError('expected_archived_argument_string')
        try:
            value = json.loads(arguments)
        except ValueError:
            invalid += 1
        else:
            nonobject += not isinstance(value, dict)
    return dict(terminal_observed=True, finish_reason=response['done_reason'], output_tokens=output,
                tool_calls=len(calls), invalid_json_arguments=invalid, nonobject_arguments=nonobject,
                fallback_eligible=bool(invalid + nonobject))


def inspect(storage, root=ROOT):
    started = time.monotonic()
    target = root / 'materials/20261024_tool_grammar_boundary'
    if target.exists():
        raise FileExistsError('preserve_first_boundary_diagnosis')
    anchor, cohort, exposure, p83, ledger, build = [read(root / n) for n in FILES[:6]]
    for name, expected in ledger['source_sha256'].items():
        if sha(root / name) != expected:
            raise ValueError('closed_public_source_changed:' + name)
    rows = anchor['rows'] + cohort['rows']
    if (len(rows) != 24 or len({r['run_id'] for r in rows}) != 24
            or anchor['audit_errors'] or cohort['audit_errors']
            or anchor['batch_status'] != 'complete' or cohort['batch_status'] != 'complete'
            or cohort['anchor_rows'] != anchor['rows'] or cohort['anchor_sha256'] != sha(root / FILES[0])
            or exposure['partial_only'] or exposure['closed_cells'] != 24
            or exposure['source_cohort_sha256'] != sha(root / FILES[1])
            or exposure['source_anchor_sha256'] != sha(root / FILES[0])
            or [r['run_id'] for r in exposure['rows']] != [r['run_id'] for r in rows]
            or any(r['record_status'] != 'evaluated' for r in rows)):
        raise ValueError('closed_all_twenty_four_required')
    archive = storage / build['source_archive_relative']
    source_root = storage / build['source_tree_relative']
    if build['runtime_commit'] != BACKEND or build['source_archive_sha256'] != ARCHIVE_SHA or sha(archive) != ARCHIVE_SHA:
        raise ValueError('pinned_backend_archive_changed')
    backend_hashes = {}
    with tarfile.open(archive, 'r:gz') as package:
        for name in BACKEND_FILES:
            member = package.extractfile('llama.cpp-' + BACKEND + '/' + name)
            if member is None or member.read() != (source_root / name).read_bytes():
                raise ValueError('backend_source_not_equal_to_archive:' + name)
            backend_hashes[name] = sha(source_root / name)
    if p83['status'] != 'complete' or p83['completed_renderings'] != 6:
        raise ValueError('all_existing_six_renderings_required')
    controls = []
    folder = storage / 'records/context_pilot/P83_fallback_prompt_v01'
    for identity in p83['planned_inputs']:
        reference = p83['rendered'][identity]
        path = folder / (identity + '_rendered_private.json')
        if sha(path) != reference['private_rendering_sha256']:
            raise ValueError('existing_P83_rendering_changed')
        control = read(path)['session_controls']
        if digest(control) != reference['session_controls_sha256']:
            raise ValueError('existing_P83_controls_changed')
        grammar = control['grammar']
        if not isinstance(grammar, str):
            raise ValueError('grammar_must_be_text')
        controls.append(dict(input_id=identity, format=control['format'],
            grammar_nonempty=bool(grammar), grammar_characters=len(grammar),
            grammar_sha256=hashlib.sha256(grammar.encode()).hexdigest(),
            grammar_lazy=control['grammar_lazy'], trigger_count=len(control['grammar_triggers']),
            preserved_token_count=len(control['preserved_tokens']),
            existing_controls_sha256=reference['session_controls_sha256'],
            existing_rendering_sha256=reference['private_rendering_sha256']))
    if len(controls) != 6:
        raise ValueError('all_six_controls_required')
    calls, cells = [], []
    for row, old_exposure in zip(rows, exposure['rows'], strict=True):
        folder = storage / 'records/context_pilot' / row['run_id']
        for name in ('summary', 'usage', 'evaluation'):
            if sha(folder / (name + '.json')) != row[name + '_sha256']:
                raise ValueError('closed_cell_record_changed')
        selected = []
        for ordinal, check in enumerate(row['request_checks'], 1):
            call_id = check['call_id']
            if call_id != f'call_{ordinal:03d}':
                raise ValueError('all_calls_in_original_order_required')
            for kind in ('request', 'response'):
                if sha(folder / call_id / (kind + '.json')) != check[kind + '_sha256']:
                    raise ValueError('audited_request_or_response_changed')
            request = read(folder / call_id / 'request.json')
            response = read(folder / call_id / 'response.json')
            if response['status'] != check['status']:
                raise ValueError('saved_status_disagrees')
            shape = classify_response(response)
            if (type(request['max_tokens']) is not int or request['max_tokens'] < 1
                    or (shape['terminal_observed'] and shape['output_tokens'] > request['max_tokens'])):
                raise ValueError('invalid_output_cap')
            item = dict(run_id=row['run_id'], task_id=row['task_id'], time_visibility=row['time_visibility'],
                call_id=call_id, ordinal=ordinal, success=row['success'], **shape,
                max_tokens=request['max_tokens'], tools_present=bool(request.get('tools')),
                tool_choice_auto=request.get('tool_choice') == 'auto',
                parallel_tool_calls=request.get('parallel_tool_calls'), stream=request.get('stream'),
                explicit_grammar='grammar' in request, explicit_response_format='response_format' in request,
                explicit_json_schema='json_schema' in request,
                request_sha256=check['request_sha256'], response_sha256=check['response_sha256'])
            selected.append(item)
        if len(selected) != row['model_calls'] or sum(not c['terminal_observed'] for c in selected) != row['unknown_usage_calls']:
            raise ValueError('all_calls_and_unknowns_must_be_retained')
        malformed = [c for c in selected if c['fallback_eligible'] is True]
        cells.append(dict(run_id=row['run_id'], task_id=row['task_id'], time_visibility=row['time_visibility'],
            success=row['success'], model_calls=len(selected), unknown_usage_calls=row['unknown_usage_calls'],
            length_completions=sum(c['finish_reason'] == 'length' for c in selected),
            fallback_eligible_responses=len(malformed),
            fallback_eligible_length_responses=sum(c['finish_reason'] == 'length' for c in malformed),
            first_fallback_eligible_response=malformed[0]['ordinal'] if malformed else None,
            previously_bound_exposed_requests=old_exposure['requests_with_fallback_references'],
            previously_bound_first_exposed_request=old_exposure['first_request_with_fallback_references']))
        calls.extend(selected)
    result = dict(phase='closed_tool_grammar_boundary', posthoc=True,
        created_at=datetime.now(timezone.utc).isoformat(), cells=cells, calls=calls, existing_P83_controls=controls,
        finish_reason_counts=dict(Counter(c['finish_reason'] or 'unobserved' for c in calls)),
        fallback_eligible_responses=sum(c['fallback_eligible'] is True for c in calls),
        invalid_json_argument_count=sum(c['invalid_json_arguments'] or 0 for c in calls if c['terminal_observed']),
        nonobject_argument_count=sum(c['nonobject_arguments'] or 0 for c in calls if c['terminal_observed']),
        independent_tasks=4, condition_count=len(cells), model_attempts=len(calls),
        unknown_usage_calls=sum(not c['terminal_observed'] for c in calls),
        source_sha256={n: sha(root / n) for n in FILES}, script_sha256=sha(Path(__file__)),
        backend_commit=BACKEND, backend_archive_sha256=ARCHIVE_SHA, backend_source_sha256=backend_hashes,
        analysis_wall_seconds=time.monotonic() - started,
        private_record_bytes_read=True, private_reasoning_inspected_semantically=False,
        argument_values_published=False, additional_generations=0, additional_input_count_requests=0,
        environment_api_requests=0, evaluations=0, inference_contexts_created=0,
        P82_records_read=False, original_records_changed=False,
        grammar_applied_at_every_generated_token_verified=False,
        finite_output_cap_forces_syntactic_completion=False,
        malformed_output_causes_task_failure_identified=False, novel_method_claim=False)
    target.mkdir(parents=True, exist_ok=False)
    with (target / 'diagnosis.json').open('x') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2); stream.write('\n')
    for name, values in (('all_429_calls.csv', calls), ('all_24_conditions.csv', cells)):
        with (target / name).open('x', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(values[0])); writer.writeheader(); writer.writerows(values)
    print({k: result[k] for k in ('condition_count', 'model_attempts', 'unknown_usage_calls',
        'finish_reason_counts', 'fallback_eligible_responses', 'invalid_json_argument_count',
        'nonobject_argument_count', 'analysis_wall_seconds')})
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--storage-root', type=Path, required=True)
    args = parser.parse_args()
    inspect(args.storage_root.resolve())
