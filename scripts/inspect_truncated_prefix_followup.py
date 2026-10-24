"""Inspect the observed API call shapes and later code without executing it.

This follows the closed prefix-availability diagnosis. Exact AST matches are
descriptive, not evidence of safely removable work or equivalent future intent.
"""
import argparse
import ast
from datetime import datetime, timezone
import json
from pathlib import Path
import time

from inspect_truncated_code_prefixes import code_string_prefix, read, sha

DIAGNOSIS = 'materials/20261024_truncated_code_prefix_scope/diagnosis.json'


def statement_matches(left, right):
    count = 0
    for a, b in zip(left.body, right.body):
        if ast.dump(a, include_attributes=False) != ast.dump(b, include_attributes=False):
            break
        count += 1
    return count


def api_shapes(tree):
    calls = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name) or node.func.id != 'call_api':
            continue
        def literal(index):
            return (node.args[index].value if len(node.args) > index and isinstance(node.args[index], ast.Constant)
                    and isinstance(node.args[index].value, str) else None)
        calls.append(dict(line=node.lineno, app=literal(0), api=literal(1),
                          keyword_names=[k.arg for k in node.keywords]))
    return calls


def inspect(storage, root, output):
    started = time.monotonic()
    if output.exists():
        raise FileExistsError('preserve_first_prefix_followup')
    diagnosis = read(root / DIAGNOSIS)
    if (diagnosis['conditions'] != 48 or diagnosis['model_attempts'] != 855
            or diagnosis['unknown_usage_calls'] != 6
            or diagnosis['script_sha256'] != sha(root / 'scripts/inspect_truncated_code_prefixes.py')):
        raise ValueError('fixed_closed_prefix_diagnosis_required')
    for name, expected in diagnosis['source_sha256'].items():
        if sha(root / name) != expected:
            raise ValueError('bound_prefix_source_changed')
    cohort = {(r['run_id'], r['call_id']): r for r in diagnosis['calls']}
    def response(run, call):
        ref = cohort[run, call]
        path = storage / 'records/context_pilot' / run / call / 'response.json'
        if sha(path) != ref['response_sha256']:
            raise ValueError('audited_response_changed')
        return read(path)
    summaries, later = [], []
    for entry in diagnosis['malformed_arguments']:
        prefix_record = entry['syntactic_prefix']
        if not prefix_record or prefix_record['status'] != 'parseable_observed_line_prefix':
            raise ValueError('this_followup_requires_the_observed_seven_parseable_prefixes')
        run, call = entry['run_id'], entry['call_id']
        raw = response(run, call)['message']['tool_calls'][entry['tool_index'] - 1]['function']['arguments']
        code = code_string_prefix(raw)['code'][:prefix_record['characters']]
        tree = ast.parse(code)
        rows = [r for r in diagnosis['calls'] if r['run_id'] == run and r['call_id'] > call]
        local = []
        for row in rows:
            saved = response(run, row['call_id'])
            known = saved['status'] == 'ok'
            value = dict(run_id=run, source_call_id=call, later_call_id=row['call_id'],
                terminal_observed=known, full_prefix_ast_matches=None if not known else 0,
                valid_code_arguments=None if not known else 0,
                maximum_matching_initial_statements=None if not known else 0,
                response_sha256=row['response_sha256'])
            if known:
                for tool in saved['message'].get('tool_calls') or []:
                    fn = tool['function']
                    if fn['name'] != 'run_python':
                        continue
                    try:
                        args = json.loads(fn['arguments'])
                        candidate = args.get('code') if isinstance(args, dict) else None
                        if not isinstance(candidate, str):
                            continue
                        candidate_tree = ast.parse(candidate)
                    except (ValueError, SyntaxError, TypeError):
                        continue
                    value['valid_code_arguments'] += 1
                    matches = statement_matches(tree, candidate_tree)
                    value['maximum_matching_initial_statements'] = max(value['maximum_matching_initial_statements'], matches)
                    value['full_prefix_ast_matches'] += matches == len(tree.body)
            local.append(value)
        summaries.append(dict(run_id=run, source_call_id=call, prefix_sha256=prefix_record['prefix_sha256'],
            top_level_statements=len(tree.body), public_api_call_shapes=api_shapes(tree),
            first_statement_type=type(tree.body[0]).__name__,
            later_call_slots=len(local), later_unknown_calls=sum(not r['terminal_observed'] for r in local),
            later_full_prefix_ast_matches=sum(r['full_prefix_ast_matches'] or 0 for r in local),
            maximum_later_matching_initial_statements=max((r['maximum_matching_initial_statements'] or 0 for r in local), default=0)))
        later.extend(local)
    result = dict(phase='closed_prefix_api_and_later_code_followup', posthoc=True,
        created_at=datetime.now(timezone.utc).isoformat(), source_diagnosis_sha256=sha(root / DIAGNOSIS),
        extractor_sha256=sha(root / 'scripts/inspect_truncated_code_prefixes.py'),
        script_sha256=sha(Path(__file__)), malformed_argument_occurrences=len(summaries),
        unique_observed_prefixes=len({r['prefix_sha256'] for r in summaries}),
        rows=summaries, later_call_slots=later, raw_code_or_credentials_published=False,
        returned_reasoning_semantically_read=False, api_expression_nodes_are_request_counts=False,
        exact_ast_matching_proves_savings=False, partial_execution_authorized=False,
        new_model_generations=0, input_count_requests=0, environment_api_requests=0,
        generated_programs_executed=0, evaluations=0,
        analysis_wall_seconds=time.monotonic()-started)
    with output.open('x') as f:json.dump(result,f,ensure_ascii=False,indent=2);f.write('\n')
    print({k:result[k] for k in ('malformed_argument_occurrences','unique_observed_prefixes','analysis_wall_seconds')})
    print([{'run':r['run_id'],'later_slots':r['later_call_slots'],'full_matches':r['later_full_prefix_ast_matches'],
            'maximum_initial_statements':r['maximum_later_matching_initial_statements']} for r in summaries])
    return result


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('storage-root','repo-root','output'):
        p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();inspect(a.storage_root.resolve(),a.repo_root.resolve(),a.output.resolve())
