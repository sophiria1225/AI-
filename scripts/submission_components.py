"""Separate Python AST sequences from the other parts of normalized tool submissions."""
from public_action_structure import digest, inspect as inspect_structure, strict_object


def components(response):
    structure=inspect_structure(response or {})
    result=dict(status=structure['status'],public_output_sha256=structure['public_output_sha256'],
        original_syntax_actions_sha256=structure['syntax_actions_sha256'],
        tool_names_sha256=None,Python_AST_sequence_sha256=None,noncode_arguments_sha256=None,
        Python_submissions=None,all_components_available=False,semantic_equivalence_claim=False)
    if structure['syntax_actions_sha256'] is None:return result
    functions=response['message']['tool_calls'];names=[];other=[];python=[]
    for call,detail in zip(functions,structure['functions'],strict=True):
        fn=call['function'];args=strict_object(fn['arguments']);names.append(fn['name'])
        if fn['name']=='run_python':
            python.append(detail['code_ast_sha256']);args={k:v for k,v in args.items() if k!='code'}
        other.append(args)
    result.update(tool_names_sha256=digest(names),Python_submissions=len(python),
        Python_AST_sequence_sha256=digest(python) if python else None,
        noncode_arguments_sha256=digest(other),all_components_available=True)
    return result


def equal(a,b):return a==b if a is not None and b is not None else None


def compare(left,right,original):
    if left is None or right is None:
        if original['status']!='one_run_ended':raise ValueError('original_alignment_disagrees')
        return dict(Python_AST_equal=None,tool_names_equal=None,noncode_arguments_equal=None,
                    original_target=False,target_component_class=None)
    syntax=equal(left['original_syntax_actions_sha256'],right['original_syntax_actions_sha256'])
    public=equal(left['public_output_sha256'],right['public_output_sha256'])
    if syntax!=original['syntax_equal'] or public!=original['public_equal']:
        raise ValueError('original_public_or_submission_fingerprint_disagrees')
    python=equal(left['Python_AST_sequence_sha256'],right['Python_AST_sequence_sha256'])
    names=equal(left['tool_names_sha256'],right['tool_names_sha256'])
    arguments=equal(left['noncode_arguments_sha256'],right['noncode_arguments_sha256'])
    if syntax is True and (names is not True or arguments is not True or python is False):
        raise ValueError('equal_submission_components_disagree')
    if syntax is False and names is True and arguments is True and python is True:
        raise ValueError('different_submission_without_component_difference')
    target=original['different_syntax_same_nonempty_API'];category=None
    if target:
        if syntax is not False or original['nonempty_API_equal'] is not True:
            raise ValueError('original_target_definition_changed')
        category=('Python_AST_differs' if python is False else
                  'Python_AST_same_other_components_differ' if python is True else
                  'Python_AST_unavailable')
    return dict(Python_AST_equal=python,tool_names_equal=names,noncode_arguments_equal=arguments,
                original_target=target,target_component_class=category)


def summarize(pairs,runs,*,matched_prefix_only=False):
    tasks={r['run_id']:r['task_id'] for r in runs};rows=[]
    for pair in pairs:
        for row in pair['rows']:
            if matched_prefix_only and row['prior_API_prefix_equal'] is not True:continue
            rows.append((pair,row))
    target_calls={(run,row['ordinal']) for pair,row in rows if row['original_target']
                  for run in (pair['left'],pair['right'])}
    target_runs={run for run,_ in target_calls};categories=[]
    for category in ('Python_AST_differs','Python_AST_same_other_components_differ','Python_AST_unavailable'):
        selected=[(p,r) for p,r in rows if r['target_component_class']==category]
        calls={(run,row['ordinal']) for pair,row in selected for run in (pair['left'],pair['right'])}
        used={run for run,_ in calls}
        categories.append(dict(component_class=category,dependent_comparison_positions=len(selected),
            distinct_generations=len(calls),distinct_runs=len(used),distinct_known_tasks=len({tasks[r] for r in used})))
    return dict(aligned_positions=len(rows),original_target_positions=sum(r['original_target'] for _,r in rows),
        original_target_distinct_generations=len(target_calls),original_target_distinct_runs=len(target_runs),
        original_target_distinct_known_tasks=len({tasks[r] for r in target_runs}),
        component_classes=categories,
        Python_AST_comparable=sum(r['Python_AST_equal'] is not None for _,r in rows),
        Python_AST_equal=sum(r['Python_AST_equal'] is True for _,r in rows),
        tool_names_equal=sum(r['tool_names_equal'] is True for _,r in rows),
        noncode_arguments_equal=sum(r['noncode_arguments_equal'] is True for _,r in rows),
        pairs_independent=False,category_distinct_counts_are_not_additive=True,
        matched_prior_API_prefix_only=matched_prefix_only,full_state_equivalence_established=False)
