"""Inventory current-source bindings; never proves API substitution or liveness.

Lexical references are deliberately not attributed across explicit rebinding.
Loops, definitions, exceptions and an unknown persistent namespace prevent a
normal-path syntactic pattern from becoming an online equivalence guarantee.
"""
import ast
from collections import Counter
import hashlib

from field_read_contract import FIELDS
from return_use_scope import analyze as root_inventory

COMPOUND = (ast.If, ast.For, ast.AsyncFor, ast.While, ast.Try, ast.TryStar,
            ast.With, ast.AsyncWith, ast.Match, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
DEFERRED = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.GeneratorExp)


def position(node):
    return (node.lineno, node.col_offset)


def end_position(node):
    return (node.end_lineno, node.end_col_offset)


def release_kind(statement, name):
    if isinstance(statement, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in statement.targets):
        return 'overwrite'
    if (isinstance(statement, ast.AnnAssign) and statement.value is not None
            and isinstance(statement.target, ast.Name) and statement.target.id == name):
        return 'overwrite'
    if isinstance(statement, ast.Delete) and any(isinstance(t, ast.Name) and t.id == name for t in statement.targets):
        return 'delete'
    return None


def classify_load(node, parents):
    parent = parents.get(node)
    if isinstance(parent, ast.Subscript) and parent.value is node:
        if not isinstance(parent.ctx, ast.Load):
            return 'member_mutation_or_delete', None
        if isinstance(parent.slice, ast.Constant) and type(parent.slice.value) is str:
            return 'literal_field_subscript', parent.slice.value if parent.slice.value in FIELDS else None
        return 'dynamic_or_nonstring_subscript', None
    if isinstance(parent, ast.Attribute) and parent.value is node:
        call = parents.get(parent)
        if (parent.attr == 'get' and isinstance(call, ast.Call) and call.func is parent
                and len(call.args) in (1, 2) and not call.keywords
                and isinstance(call.args[0], ast.Constant) and type(call.args[0].value) is str):
            return 'literal_field_get', call.args[0].value if call.args[0].value in FIELDS else None
        return 'method_attribute_or_dynamic_get', None
    return 'whole_root_use', None


def analyze(source):
    base = root_inventory(source)  # Bound source length and AST before extra traversal.
    tree = ast.parse(source)
    nodes = list(ast.walk(tree))
    parents = {child: n for n in nodes for child in ast.iter_child_nodes(n)}
    calls = {position(n): n for n in nodes if isinstance(n, ast.Call)}
    bindings = []
    for site in base['sites']:
        if site['root_use'] != 'name_binding':
            continue
        call = calls[(site['line'], site['column'])]
        binding = parents[call]
        targets = binding.targets if isinstance(binding, ast.Assign) else [binding.target]
        if (not isinstance(binding, (ast.Assign, ast.AnnAssign)) or len(targets) != 1
                or not isinstance(targets[0], ast.Name)):
            continue
        name = targets[0].id
        owner = parents[binding]
        suite = next((value for _, value in ast.iter_fields(owner)
                      if isinstance(value, list) and binding in value), None)
        if suite is None:
            continue
        release = None; release_type = None; between = []
        for statement in suite[suite.index(binding) + 1:]:
            kind = release_kind(statement, name)
            if kind:
                release = statement; release_type = kind; break
            between.append(statement)
        lower = end_position(binding)
        upper = end_position(release) if release is not None else (10**9, 10**9)
        loads = [n for n in nodes if isinstance(n, ast.Name) and n.id == name
                 and isinstance(n.ctx, ast.Load) and lower <= position(n) < upper]
        release_targets = []
        if release is not None:
            release_targets = release.targets if isinstance(release, (ast.Assign, ast.Delete)) else [release.target]
        other_stores = sum(isinstance(n, ast.Name) and n.id == name
                           and isinstance(n.ctx, (ast.Store, ast.Del))
                           and lower <= position(n) < upper and n not in release_targets for n in nodes)
        usage = [classify_load(n, parents) for n in loads]
        uses = Counter(kind for kind, _ in usage)
        labels = sorted({field for _, field in usage if field is not None})
        scopes = []
        node = binding
        while node in parents:
            node = parents[node]
            if isinstance(node, COMPOUND + (ast.Lambda, ast.GeneratorExp, ast.comprehension)):
                scopes.append(type(node).__name__)
        deferred_loads = 0
        for load in loads:
            node = load
            while node in parents:
                node = parents[node]
                if isinstance(node, DEFERRED):
                    deferred_loads += 1; break
        intervening_control = any(isinstance(n, COMPOUND) for statement in between for n in ast.walk(statement))
        current_hazards = bool(base['current_program_hazards'] or base['bridge_name_non_call_loads'])
        literal_only = bool(loads) and set(uses) == {'literal_field_subscript'}
        known_fields_only = literal_only and all(field is not None for _, field in usage)
        direct_shape = (len(call.args) == 2 and len(call.keywords) == 1 and call.keywords[0].arg == 'song_id')
        candidate = bool(site['existing_helper_target'] and direct_shape and known_fields_only
                         and release is not None and not scopes and not deferred_loads
                         and not intervening_control and not current_hazards and not other_stores)
        bindings.append({
            'line': site['line'], 'column': site['column'], 'api': site['api'],
            'root_name_sha256': hashlib.sha256(name.encode()).hexdigest(),
            'scope_kinds': sorted(set(scopes)), 'lexical_loads_in_window': len(loads),
            'load_counts': dict(sorted(uses.items())), 'permitted_field_labels': labels,
            'unknown_literal_field_uses': sum(kind in ('literal_field_subscript', 'literal_field_get') and field is None
                                              for kind, field in usage),
            'current_window_literal_subscripts_only': literal_only,
            'same_suite_release_kind': release_type,
            'same_suite_release_line': release.lineno if release is not None else None,
            'intervening_control_structure': intervening_control,
            'deferred_name_loads': deferred_loads,
            'other_same_spelling_stores_in_window': other_stores,
            'later_same_spelling_loads_after_release': sum(isinstance(n, ast.Name) and n.id == name
                and isinstance(n.ctx, ast.Load) and position(n) >= upper for n in nodes) if release else 0,
            'normal_path_release_syntax_candidate': candidate,
            'exception_exit_equivalence_verified': False,
            'persistent_namespace_equivalence_verified': False,
            'online_replacement_verified': False,
        })
    counts = {
        'all_call_api_syntax_sites': base['call_api_syntax_sites'],
        'root_name_binding_sites': base['use_counts'].get('name_binding', 0),
        'tracked_single_name_bindings': len(bindings),
        'bindings_with_literal_field_read': sum(any(r['load_counts'].get(k, 0) for k in
            ('literal_field_subscript', 'literal_field_get')) for r in bindings),
        'literal_subscripts_only_windows': sum(r['current_window_literal_subscripts_only'] for r in bindings),
        'explicit_same_suite_releases': sum(r['same_suite_release_kind'] is not None for r in bindings),
        'bindings_inside_control_or_definition': sum(bool(r['scope_kinds']) for r in bindings),
        'normal_path_release_syntax_candidates': sum(r['normal_path_release_syntax_candidate'] for r in bindings),
        'existing_helper_target_bindings': sum(r['api'] == 'spotify__show_song' for r in bindings),
    }
    return {'source_sha256': base['source_sha256'], 'ast_nodes': base['ast_nodes'],
            'counts': counts, 'current_program_hazards': base['current_program_hazards'],
            'bridge_name_non_call_loads': base['bridge_name_non_call_loads'], 'bindings': bindings,
            'normal_path_syntax_only': True, 'online_replacement_verified': False,
            'exception_exit_equivalence_verified': False, 'measured_savings': None}
