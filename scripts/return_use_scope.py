"""Bounded syntactic return-use inventory, never a Python equivalence proof.

Only the current program is accepted. A saved root may be used by a future
program, so in-program field reads do not license reducing that root. No saved
code is evaluated, transformed or executed; counts denote syntax sites only.
"""
import ast
from collections import Counter
import hashlib
import re

from field_read_contract import FIELDS

MAX_SOURCE = 20000
MAX_NODES = 5000
DYNAMIC = frozenset({'exec', 'eval', 'compile', 'globals', 'locals', 'vars',
                     'getattr', 'setattr', 'delattr', '__import__'})
LABEL = re.compile(r'[a-z][a-z0-9_]{0,79}\Z')


def literal_label(node):
    return node.value if (isinstance(node, ast.Constant) and type(node.value) is str
                          and LABEL.fullmatch(node.value)) else None


def analyze(source):
    if type(source) is not str or len(source) > MAX_SOURCE:
        raise ValueError('source_bound')
    try:
        tree = ast.parse(source)
    except (SyntaxError, RecursionError, ValueError):
        raise ValueError('unsupported_source_syntax') from None
    nodes = list(ast.walk(tree))
    if len(nodes) > MAX_NODES:
        raise ValueError('ast_node_bound')
    parents = {child: n for n in nodes for child in ast.iter_child_nodes(n)}
    hazards = set()
    for n in nodes:
        if ((isinstance(n, ast.Name) and n.id == 'call_api'
             and isinstance(n.ctx, (ast.Store, ast.Del)))
                or (isinstance(n, ast.arg) and n.arg == 'call_api')
                or (isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
                    and n.name == 'call_api')
                or (isinstance(n, ast.alias) and (n.asname or n.name.split('.')[0]) == 'call_api')):
            hazards.add('bridge_binding_changed_in_current_program')
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in DYNAMIC:
            hazards.add('dynamic_execution_or_namespace_access')
        if (isinstance(n, ast.Attribute) and n.attr.startswith('__')) or (
                isinstance(n, ast.Name) and n.id in {'__builtins__', '__loader__', '__spec__'}):
            hazards.add('runtime_introspection')

    def deferred(node):
        while node in parents:
            node = parents[node]
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef,
                                 ast.Lambda, ast.GeneratorExp)):
                return True
        return False

    rows = []
    explicit = 0
    aliases = 0
    for n in nodes:
        if isinstance(n, ast.Name) and n.id == 'call_api' and isinstance(n.ctx, ast.Load):
            parent = parents.get(n)
            if not (isinstance(parent, ast.Call) and parent.func is n):
                aliases += 1
        if not isinstance(n, ast.Call) or not isinstance(n.func, ast.Name):
            continue
        if n.func.id == 'read_fields':
            explicit += 1
        if n.func.id != 'call_api':
            continue
        p = parents.get(n)
        use = 'other_use'; field = None; has_default = False
        if (isinstance(p, ast.Subscript) and p.value is n and isinstance(p.ctx, ast.Load)):
            if isinstance(p.slice, ast.Constant) and type(p.slice.value) is str:
                use = 'literal_subscript'; field = literal_label(p.slice)
            else:
                use = 'dynamic_or_non_string_subscript'
        elif isinstance(p, ast.Attribute) and p.value is n:
            outer = parents.get(p)
            if (p.attr == 'get' and isinstance(outer, ast.Call) and outer.func is p
                    and len(outer.args) in (1, 2) and not outer.keywords
                    and isinstance(outer.args[0], ast.Constant)
                    and type(outer.args[0].value) is str):
                use = 'literal_get'; field = literal_label(outer.args[0]); has_default = len(outer.args) == 2
            else:
                use = 'method_or_attribute'
        elif isinstance(p, (ast.Assign, ast.AnnAssign, ast.NamedExpr)) and p.value is n:
            targets = p.targets if isinstance(p, ast.Assign) else [p.target]
            use = 'name_binding' if all(isinstance(t, ast.Name) for t in targets) else 'container_or_destructuring_assignment'
        elif isinstance(p, (ast.List, ast.Tuple, ast.Set, ast.Dict)):
            use = 'container_escape'
        elif isinstance(p, ast.Call):
            use = 'whole_value_argument'
        elif isinstance(p, (ast.For, ast.comprehension)) and p.iter is n:
            use = 'iteration'
        elif isinstance(p, ast.Expr):
            use = 'discarded_root'
        elif isinstance(p, (ast.Return, ast.Yield, ast.YieldFrom)):
            use = 'returned_root'
        app = literal_label(n.args[0]) if len(n.args) >= 1 else None
        api = literal_label(n.args[1]) if len(n.args) >= 2 else None
        target = app == 'spotify' and api == 'show_song'
        direct_shape = (len(n.args) == 2 and len(n.keywords) == 1 and n.keywords[0].arg == 'song_id')
        delayed = deferred(n)
        rows.append({'line': n.lineno, 'column': n.col_offset, 'api': f'{app}__{api}' if app and api else None,
            'root_use': use, 'field_label': field, 'get_has_default': has_default,
            'deferred_or_nested_definition': delayed,
            'existing_helper_target': target,
            'current_program_hazards': sorted(hazards),
            'direct_field_helper_syntax_candidate': bool(target and direct_shape and field in FIELDS
                and use == 'literal_subscript' and not delayed and not hazards),
            'online_replacement_verified': False})
    rows.sort(key=lambda r: (r['line'], r['column']))
    return {'source_sha256': hashlib.sha256(source.encode()).hexdigest(), 'ast_nodes': len(nodes),
        'call_api_syntax_sites': len(rows), 'explicit_read_fields_syntax_sites': explicit,
        'bridge_name_non_call_loads': aliases, 'current_program_hazards': sorted(hazards),
        'use_counts': dict(sorted(Counter(r['root_use'] for r in rows).items())),
        'direct_field_helper_syntax_candidates': sum(r['direct_field_helper_syntax_candidate'] for r in rows),
        'sites': rows, 'measured_savings': None, 'online_replacement_verified': False}
