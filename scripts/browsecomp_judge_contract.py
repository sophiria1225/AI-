"""Load reviewed official grading functions from an exact, locally pinned source.

No benchmark labels or vLLM imports occur here. MLX inference is a separate adapter;
using these functions alone is not reproduction of the upstream evaluation runtime.
"""
import ast
import hashlib
import re
from typing import Dict, List

UPSTREAM_COMMIT = '046949032b0328319cc9a02663a759ec601d9402'
SOURCE_SHA256 = '1a21233937c377ab6323c98ff9af67742756a57fbacab4ebf9bc30852eae530a'
FUNCTIONS = {'create_judge_prompt', 'parse_judge_response',
             'extract_citations_from_response', 'compute_citation_metrics'}
SAMPLING = {'temperature': 0.7, 'top_p': 0.8, 'top_k': 20,
            'max_output_tokens': 4096, 'enable_thinking': False}


def official_contract(source):
    data = source.read_bytes()
    if hashlib.sha256(data).hexdigest() != SOURCE_SHA256:
        raise ValueError('official judge source differs from reviewed immutable revision')
    tree = ast.parse(data.decode('utf-8'))
    namespace = {'re': re, 'Dict': Dict, 'List': List}
    functions, templates = [], []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in FUNCTIONS:
            functions.append(node)
        if (isinstance(node, ast.Assign) and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name) and node.targets[0].id == 'GRADER_TEMPLATE'):
            # The reviewed assignment is a literal triple-quoted string followed
            # by .strip(). Do not evaluate other module-level expressions.
            value = node.value
            if (not isinstance(value, ast.Call) or value.args or value.keywords
                    or not isinstance(value.func, ast.Attribute) or value.func.attr != 'strip'
                    or not isinstance(value.func.value, ast.Constant)
                    or not isinstance(value.func.value.value, str)):
                raise ValueError('unexpected official template syntax')
            templates.append(value.func.value.value.strip())
    if len(templates) != 1 or {f.name for f in functions} != FUNCTIONS:
        raise ValueError('missing reviewed official grading definitions')
    namespace['GRADER_TEMPLATE'] = templates[0]
    exec(compile(ast.Module(body=functions, type_ignores=[]), str(source), 'exec'), namespace)
    return {name: namespace[name] for name in FUNCTIONS}
