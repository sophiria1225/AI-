"""Measure syntactic code-prefix availability in closed, malformed arguments.

This is an offline, post-hoc scope check, never an executor or repair policy.
Parsing a prefix does not establish intent, safe effects, or reusable work.
Only public tool arguments are examined; returned reasoning is not interpreted.
"""
import argparse
import ast
from collections import Counter
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import time


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def code_string_prefix(arguments):
    """Decode only an exactly observed initial code string, without invention.

    Restrict to code as the first JSON member. A missing trailing escape or
    unicode escape contributes no invented character. Other malformed escapes
    and literal control characters are refused. Other member orders are outside
    this diagnostic's coverage, not evidence that they contain no useful code.
    """
    start = re.match(r'\s*\{\s*"code"\s*:\s*"', arguments)
    if not start:
        return {'status': 'outside_first_code_string_scope', 'code': None}
    i = start.end()
    boundary = i
    closed = False
    while i < len(arguments):
        char = arguments[i]
        if char == '"':
            closed = True
            break
        if ord(char) < 0x20:
            return {'status': 'literal_control_character', 'code': None}
        if char == '\\':
            if i + 1 == len(arguments):
                break
            escaped = arguments[i + 1]
            if escaped == 'u':
                digits = arguments[i + 2:i + 6]
                if any(x not in '0123456789abcdefABCDEF' for x in digits):
                    return {'status': 'invalid_unicode_escape', 'code': None}
                if len(digits) < 4:
                    break
                i += 6
            elif escaped in '"\\/bfnrt':
                i += 2
            else:
                return {'status': 'invalid_escape', 'code': None}
        else:
            i += 1
        boundary = i
    code = json.loads('"' + arguments[start.end():boundary] + '"')
    return {'status': 'closed_string' if closed else 'open_string_prefix', 'code': code,
            'observed_source_end': boundary, 'string_closed': closed}


def syntactic_prefix(code):
    """Find the longest parseable prefix at an observed physical line break.

    A line break inside a string is not automatically a statement boundary;
    ast.parse must accept the complete prefix. A compound suite can still be
    extended by unseen text, so a successful parse never licenses execution.
    """
    if len(code) > 20000:
        return {'status': 'outside_code_length_scope', 'characters': None}
    boundaries = [i + 1 for i, c in enumerate(code) if c == '\n']
    for boundary in reversed(boundaries):
        try:
            tree = ast.parse(code[:boundary])
        except (SyntaxError, ValueError):
            continue
        if not tree.body:
            continue
        calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)]
        return {'status': 'parseable_observed_line_prefix', 'characters': boundary,
            'lines': code[:boundary].count('\n'), 'top_level_statements': len(tree.body),
            'statement_types': dict(Counter(type(node).__name__ for node in tree.body)),
            'call_expression_nodes': len(calls),
            'direct_call_api_nodes': sum(isinstance(node.func, ast.Name) and node.func.id == 'call_api' for node in calls),
            'prefix_sha256': hashlib.sha256(code[:boundary].encode('utf-8', errors='surrogatepass')).hexdigest(),
            'safe_to_execute_established': False, 'reusable_work_established': False}
    return {'status': 'no_parseable_nonempty_line_prefix', 'characters': 0,
            'safe_to_execute_established': False, 'reusable_work_established': False}


def inspect(storage, root, output):
    started = time.monotonic()
    if output.exists():
        raise FileExistsError('preserve_first_prefix_diagnosis')
    files = ['reports/P80_comparison.json', 'reports/P81_repetitions.json',
             'reports/P82_comparison.json', 'reports/P82_server_session.json',
             'reports/P81_P83_results_provenance_20261024.json',
             'reports/P82_results_provenance_20261024.json']
    anchor, repeat, late, session, *ledgers = [read(root / name) for name in files]
    for ledger in ledgers:
        for name, digest in ledger['source_sha256'].items():
            if sha(root / name) != digest:
                raise ValueError('bound_source_changed:' + name)
    if (any(x['batch_status'] != 'complete' or x['audit_errors'] for x in (anchor, repeat, late))
            or repeat['anchor_rows'] != anchor['rows']
            or repeat['anchor_sha256'] != sha(root / files[0])
            or session['status'] != 'stopped'
            or session['audit_source_sha256'] != sha(root / files[2])):
        raise ValueError('closed_audited_cohorts_required')
    rows = anchor['rows'] + repeat['rows'] + late['rows']
    if len(rows) != 48 or len({r['run_id'] for r in rows}) != 48:
        raise ValueError('all_48_closed_conditions_required')
    calls, arguments, cells = [], [], []
    for row in rows:
        if row['record_status'] != 'evaluated':
            raise ValueError('evaluated_closed_cell_required')
        folder = storage / 'records/context_pilot' / row['run_id']
        for name in ('summary', 'usage', 'evaluation'):
            if sha(folder / (name + '.json')) != row[name + '_sha256']:
                raise ValueError('audited_cell_changed')
        local = []
        for ordinal, check in enumerate(row['request_checks'], 1):
            call_id = f'call_{ordinal:03d}'
            if check['call_id'] != call_id:
                raise ValueError('original_full_call_order_required')
            path = folder / call_id / 'response.json'
            if sha(path) != check['response_sha256']:
                raise ValueError('audited_response_changed')
            response = read(path)
            if response['status'] != check['status']:
                raise ValueError('audited_response_status_changed')
            known = response['status'] == 'ok'
            item = dict(run_id=row['run_id'], task_id=row['task_id'], call_id=call_id,
                time_visibility=row['time_visibility'], success=row['success'],
                terminal_observed=known, done_reason=response.get('done_reason') if known else None,
                output_tokens=response.get('output_tokens') if known else None,
                response_sha256=check['response_sha256'],
                malformed_arguments=0 if known else None, malformed_code_arguments=0 if known else None)
            if known:
                for index, call in enumerate(response['message'].get('tool_calls') or [], 1):
                    fn = call['function']; raw = fn['arguments']
                    try:
                        json.loads(raw)
                    except ValueError:
                        item['malformed_arguments'] += 1
                        value = dict(run_id=row['run_id'], call_id=call_id, tool_index=index,
                            function_name=fn['name'], finish_reason=response['done_reason'],
                            argument_characters=len(raw), argument_sha256=hashlib.sha256(raw.encode()).hexdigest())
                        if fn['name'] == 'run_python':
                            item['malformed_code_arguments'] += 1
                            extraction = code_string_prefix(raw)
                            value['extraction_status'] = extraction['status']
                            code = extraction.pop('code')
                            value['decoded_prefix_characters'] = None if code is None else len(code)
                            value['syntactic_prefix'] = None if code is None else syntactic_prefix(code)
                        else:
                            value.update(extraction_status='non_code_tool', decoded_prefix_characters=None, syntactic_prefix=None)
                        arguments.append(value)
            local.append(item)
        if (len(local) != row['model_calls']
                or sum(not c['terminal_observed'] for c in local) != row['unknown_usage_calls']):
            raise ValueError('whole_cell_counts_disagree')
        calls.extend(local)
        cells.append(dict(run_id=row['run_id'], task_id=row['task_id'], success=row['success'],
            model_calls=len(local), unknown_usage_calls=sum(not c['terminal_observed'] for c in local),
            length_completions=sum(c['done_reason'] == 'length' for c in local),
            malformed_arguments=sum(c['malformed_arguments'] or 0 for c in local)))
    if len(calls) != 855 or sum(not c['terminal_observed'] for c in calls) != 6:
        raise ValueError('fixed_all_855_attempts_and_six_unknowns_required')
    result = dict(phase='closed_truncated_code_prefix_scope', posthoc=True,
        created_at=datetime.now(timezone.utc).isoformat(), source_sha256={n:sha(root/n) for n in files},
        script_sha256=sha(Path(__file__)), independent_tasks=4, conditions=48, model_attempts=855,
        unknown_usage_calls=6, finish_reason_counts=dict(Counter(c['done_reason'] or 'unobserved' for c in calls)),
        malformed_arguments=arguments, cells=cells, calls=calls,
        extraction_scope='run_python malformed JSON whose first key is code; only fully observed JSON string escapes',
        parse_scope='Longest nonempty ast.parse-accepted prefix ending at an observed newline; at most 20,000 code characters',
        analysis_wall_seconds=time.monotonic()-started, raw_code_published=False,
        private_reasoning_semantically_read=False, new_model_generations=0, input_count_requests=0,
        environment_api_requests=0, generated_programs_executed=0, evaluations=0, reserved_tasks_read=False,
        P84_responses_read=False, safe_partial_execution_established=False,
        avoided_work_or_quality_improvement_measured=False, original_execution_rules_changed=False)
    output.mkdir(parents=True, exist_ok=False)
    with (output/'diagnosis.json').open('x') as f:json.dump(result,f,ensure_ascii=False,indent=2);f.write('\n')
    for name, values in [('all_855_calls.csv',calls),('all_48_conditions.csv',cells)]:
        with (output/name).open('x',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=list(values[0]));writer.writeheader();writer.writerows(values)
    print({k:result[k] for k in ('conditions','model_attempts','unknown_usage_calls','finish_reason_counts','analysis_wall_seconds')})
    print({'malformed_arguments':len(arguments),'syntactic_prefix_statuses':dict(Counter((v['syntactic_prefix'] or {}).get('status',v['extraction_status']) for v in arguments))})
    return result


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('storage-root','repo-root','output'):
        p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();inspect(a.storage_root.resolve(),a.repo_root.resolve(),a.output.resolve())
