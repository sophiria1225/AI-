"""Bounded, conditional normal-path projection of already observed API fields.

This module neither certifies an API nor runs model code on the host. A trusted
adapter supplies task-isolated, revision-aware lookup and ordinary full-call
capabilities. A lookup hit is NOT a full API response or a successful API receipt.
Only admitted loop consumers use it; the original root is assigned a real full
response at the original call position in the final iteration. Exception-state
equivalence is not claimed: failures terminate the capability without retry.
"""
import ast
import builtins
from copy import deepcopy
from dataclasses import dataclass
import hashlib


PREFIX = '_harness_projection_'
HELPER = PREFIX + 'v1'
SAFE_BUILTINS = ('print', 'len', 'set', 'dict', 'list')
# Capture before any generated program runs; never trust a later replacement.
_INITIAL_BUILTINS = builtins.__dict__.copy()
_CANONICAL_BUILTINS = {name: _INITIAL_BUILTINS[name] for name in SAFE_BUILTINS}
_INITIAL_TYPE = type
_INITIAL_DICT = dict
_INITIAL_GETATTR = getattr
_INITIAL_EXEC = exec
_INITIAL_COMPILE = compile
SCALAR_FIELDS = frozenset(('song_id', 'title', 'album_id', 'duration'))
MAX_ITEMS = 512


@dataclass(frozen=True)
class ProjectionPlan:
    source: str
    transformed_source: str
    eligible: bool
    reason: str
    sites: tuple
    source_sha256: str
    transformed_sha256: str


def _digest(source):
    return hashlib.sha256(source.encode('utf-8')).hexdigest()


def _literal_ids(node):
    return (isinstance(node, (ast.List, ast.Tuple)) and len(node.elts) <= MAX_ITEMS
            and all(isinstance(n, ast.Constant) and type(n.value) is int
                    and n.value > 0 for n in node.elts))


def _fresh_kind(node):
    if isinstance(node, ast.Dict):
        return 'dict'
    if isinstance(node, ast.List):
        return 'list'
    if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
            and node.func.id in ('set', 'dict', 'list')
            and not node.args and not node.keywords):
        return node.func.id
    return None


def _program_safe(tree):
    """Reject effects we cannot bound, including syntactically unreachable ones."""
    accepted = (ast.Module, ast.Assign, ast.AugAssign, ast.Expr, ast.For, ast.While,
                ast.If, ast.Break, ast.Continue, ast.Pass, ast.Name, ast.Constant,
                ast.Dict, ast.List, ast.Tuple, ast.Set, ast.Call, ast.keyword,
                ast.Attribute, ast.Subscript, ast.Slice, ast.ListComp,
                ast.comprehension, ast.JoinedStr, ast.FormattedValue,
                ast.Compare, ast.UnaryOp, ast.BinOp, ast.BoolOp,
                ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod,
                ast.USub, ast.UAdd, ast.Not, ast.And, ast.Or,
                ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE,
                ast.In, ast.NotIn, ast.Load, ast.Store)
    protected = set(SAFE_BUILTINS) | {'call_api', '__builtins__'}
    fresh = {}
    for node in ast.walk(tree):
        if type(node) not in accepted:
            return False
        if isinstance(node, ast.Name):
            if node.id.startswith(PREFIX) or node.id.startswith('__'):
                return False
            if isinstance(node.ctx, (ast.Store, ast.Del)) and node.id in protected:
                return False
        if isinstance(node, ast.Assign):
            if len(node.targets) != 1 or isinstance(node.targets[0], (ast.Tuple, ast.List)):
                return False
            for target in node.targets:
                if isinstance(target, ast.Name) and _fresh_kind(node.value):
                    fresh.setdefault(target.id, set()).add(_fresh_kind(node.value))
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            if (not isinstance(node.value, ast.Name)
                    or node.attr not in ('items', 'add', 'extend', 'append')):
                return False
            required = {'items': 'dict', 'add': 'set', 'extend': 'list', 'append': 'list'}[node.attr]
            if fresh.get(node.value.id) != {required}:
                return False
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                if node.func.id not in protected - {'__builtins__'}:
                    return False
                if node.func.id == 'call_api':
                    if (len(node.args) != 2 or any(not isinstance(x, ast.Constant)
                            or type(x.value) is not str for x in node.args)
                            or any(k.arg is None for k in node.keywords)):
                        return False
                elif node.func.id in ('set', 'dict', 'list') and (node.args or node.keywords):
                    return False
            elif not isinstance(node.func, ast.Attribute):
                return False
        # Function/method capabilities cannot be saved, passed, or aliased.
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.Name) and child.id in protected:
                if not (isinstance(node, ast.Call) and node.func is child):
                    return False
            if isinstance(child, ast.Attribute):
                if not (isinstance(node, ast.Call) and node.func is child):
                    return False
    return True


def _field(node, root):
    if (isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name)
            and node.value.id == root and isinstance(node.slice, ast.Constant)
            and type(node.slice.value) is str):
        return node.slice.value
    return None


def _consumer_expr(node, root, item, fields):
    """Only immutable scalars and fresh artist-name lists may escape the slice."""
    field = _field(node, root)
    if field in SCALAR_FIELDS:
        fields.add(field)
        return True
    if isinstance(node, ast.Constant):
        return type(node.value) in (str, int, float, bool, type(None))
    if isinstance(node, ast.Name):
        return node.id == item
    if isinstance(node, ast.Dict):
        return all(isinstance(k, ast.Constant) and type(k.value) is str
                   and _consumer_expr(v, root, item, fields)
                   for k, v in zip(node.keys, node.values))
    if isinstance(node, ast.ListComp) and len(node.generators) == 1:
        gen = node.generators[0]
        if (not gen.is_async and not gen.ifs and isinstance(gen.target, ast.Name)
                and gen.target.id not in (root, item) and _field(gen.iter, root) == 'artists'
                and isinstance(node.elt, ast.Subscript)
                and isinstance(node.elt.value, ast.Name)
                and node.elt.value.id == gen.target.id
                and isinstance(node.elt.slice, ast.Constant) and node.elt.slice.value == 'name'):
            fields.add('artists')
            return True
    return False


def _empty_dict(node):
    return (isinstance(node, ast.Dict) and not node.keys
            or isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
            and node.func.id == 'dict' and not node.args and not node.keywords)


def _candidate(loop, bindings):
    if (not isinstance(loop, ast.For) or not isinstance(loop.target, ast.Name)
            or loop.orelse or not loop.body):
        return None
    ids = loop.iter if _literal_ids(loop.iter) else bindings.get(getattr(loop.iter, 'id', ''))
    if ids is None or not _literal_ids(ids):
        return None
    first = loop.body[0]
    if (not isinstance(first, ast.Assign) or len(first.targets) != 1
            or not isinstance(first.targets[0], ast.Name)
            or not isinstance(first.value, ast.Call)):
        return None
    root, item, call = first.targets[0].id, loop.target.id, first.value
    if (root == item or not isinstance(call.func, ast.Name) or call.func.id != 'call_api'
            or len(call.args) != 2 or [getattr(x, 'value', None) for x in call.args] != ['spotify', 'show_song']
            or len(call.keywords) != 1 or call.keywords[0].arg != 'song_id'
            or not isinstance(call.keywords[0].value, ast.Name) or call.keywords[0].value.id != item):
        return None
    fields, destinations = set(), set()
    for statement in loop.body[1:]:
        if isinstance(statement, ast.Assign) and len(statement.targets) == 1:
            target = statement.targets[0]
            if (not isinstance(target, ast.Subscript) or not isinstance(target.value, ast.Name)
                    or target.value.id in (root, item) or not isinstance(target.slice, ast.Name)
                    or target.slice.id != item or not _empty_dict(bindings.get(target.value.id))
                    or not _consumer_expr(statement.value, root, item, fields)):
                return None
            destinations.add(target.value.id)
        elif isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Call):
            c = statement.value
            if (not isinstance(c.func, ast.Attribute) or c.func.attr != 'add'
                    or not isinstance(c.func.value, ast.Name)
                    or c.func.value.id in (root, item)
                    or _fresh_kind(bindings.get(c.func.value.id)) != 'set'
                    or len(c.args) != 1 or not isinstance(c.args[0], ast.Name)
                    or c.args[0].id != item or c.keywords):
                return None
            destinations.add(c.func.value.id)
        else:
            return None
    if not fields or not destinations:
        return None
    # Literal iterable aliases must not be mutated by the admitted consumers.
    if isinstance(loop.iter, ast.Name) and loop.iter.id in destinations | {root, item}:
        return None
    return root, item, tuple(sorted(fields))


class _ReplaceRoot(ast.NodeTransformer):
    def __init__(self, root, replacement):
        self.root, self.replacement = root, replacement

    def visit_Name(self, node):
        if node.id == self.root and isinstance(node.ctx, ast.Load):
            return ast.copy_location(ast.Name(id=self.replacement, ctx=ast.Load()), node)
        return node


def _invalidate_binding(bindings, name):
    value = bindings.get(name)
    if value is None:
        return
    for alias in tuple(bindings):
        if bindings[alias] is value:
            del bindings[alias]


def builtin_integrity():
    """Check before parsing; this path calls no replaceable builtin function."""
    for name, original in _INITIAL_BUILTINS.items():
        if builtins.__dict__.get(name) is not original:
            return False
    return True


def plan_projection(source):
    """Plan from visible source alone; rejected programs retain the exact source."""
    def result(transformed, eligible, reason, sites=()):
        return ProjectionPlan(source, transformed, eligible, reason, tuple(sites),
                              _digest(source), _digest(transformed))
    if not builtin_integrity():
        digest = _digest(source)
        return ProjectionPlan(source, source, False, 'builtin_module_changed', (), digest, digest)
    if type(source) is not str:
        raise TypeError('source_must_be_text')
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return result(source, False, 'invalid_python')
    if not _program_safe(tree):
        return result(source, False, 'unsupported_program_effect')
    bindings, sites = {}, []
    for statement in tree.body:
        candidate = _candidate(statement, bindings)
        admitted_iterator = statement.iter if candidate else None
        direct_alias = (statement.value if isinstance(statement, ast.Assign)
                        and len(statement.targets) == 1 and isinstance(statement.targets[0], ast.Name)
                        and isinstance(statement.value, ast.Name) else None)
        if candidate:
            root, item, fields = candidate
            index = len(sites)
            flag, values = PREFIX + 'last_' + str(index), PREFIX + 'fields_' + str(index)
            first, tail = statement.body[0], statement.body[1:]
            last_body = [deepcopy(first), ast.Assign([ast.Name(values, ast.Store())], ast.Name(root, ast.Load()))]
            args = ast.Dict([ast.Constant('song_id')], [ast.Name(item, ast.Load())])
            projected = ast.Call(ast.Attribute(ast.Name(HELPER, ast.Load()), 'fields', ast.Load()),
                                 [ast.Constant('spotify'), ast.Constant('show_song'), args,
                                  ast.Tuple([ast.Constant(f) for f in fields], ast.Load())], [])
            intermediate = [ast.Assign([ast.Name(values, ast.Store())], projected),
                            ast.If(ast.UnaryOp(ast.Not(), ast.Attribute(ast.Name(HELPER, ast.Load()),
                                                                      'last_projected', ast.Load())),
                                   [ast.Assign([ast.Name(root, ast.Store())], ast.Name(values, ast.Load()))], [])]
            statement.iter = ast.Call(ast.Attribute(ast.Name(HELPER, ast.Load()), 'iterate', ast.Load()),
                                      [statement.iter], [])
            statement.target = ast.Tuple([ast.Name(flag, ast.Store()), statement.target], ast.Store())
            statement.body = [ast.If(ast.Name(flag, ast.Load()), last_body, intermediate)] + [
                _ReplaceRoot(root, values).visit(deepcopy(s)) for s in tail]
            sites.append({'line': first.lineno, 'root': root, 'fields': fields,
                          'final_iteration': 'ordinary_full_at_original_position'})
        # Do not retain literal authority across an unknown alias escape.
        for node in ast.walk(statement):
            if (isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)
                    and node is not admitted_iterator and node is not direct_alias
                    and _literal_ids(bindings.get(node.id))):
                _invalidate_binding(bindings, node.id)
        # A mutated literal is no longer statically certified for later regions.
        for node in ast.walk(statement):
            if isinstance(node, ast.AugAssign) and isinstance(node.target, ast.Name):
                _invalidate_binding(bindings, node.target.id)
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and isinstance(node.func.value, ast.Name)
                    and node.func.attr in ('add', 'extend', 'append')):
                _invalidate_binding(bindings, node.func.value.id)
            if (isinstance(node, ast.Subscript) and isinstance(node.ctx, ast.Store)
                    and isinstance(node.value, ast.Name)):
                _invalidate_binding(bindings, node.value.id)
        # Keep only dominating simple bindings; nested name writes may replace them.
        for node in ast.walk(statement):
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
                bindings.pop(node.id, None)
        if isinstance(statement, ast.Assign) and len(statement.targets) == 1 and isinstance(statement.targets[0], ast.Name):
            bindings[statement.targets[0].id] = (bindings.get(statement.value.id, statement.value)
                if isinstance(statement.value, ast.Name) else statement.value)
    if not sites:
        return result(source, False, 'no_supported_loop')
    ast.fix_missing_locations(tree)
    return result(ast.unparse(tree), True, 'bounded_normal_path_projection', sites)


class ProjectionRuntime:
    """Callbacks are trusted harness capabilities, never model supplied values.

    lookup_fields(app, api, args, fields) returns only observed, authorized fields
    or None. Complete cache hits return None and go through fetch_full instead.
    stop(reason) must revoke the task/session before another model invocation.
    """
    def __init__(self, fetch_full, lookup_fields, stop):
        self.fetch_full = fetch_full
        self.lookup_fields = lookup_fields
        self.stop = stop
        self.hits = 0
        self.misses = 0
        self.failed = False
        self.last_projected = False

    def fail(self, reason):
        self.failed = True
        self.stop(reason)

    def iterate(self, values):
        if (type(values) not in (list, tuple) or len(values) > 512
                or any(type(v) is not int or v <= 0 for v in values)):
            raise RuntimeError('projection_literal_iterable_contract_false')
        size = len(values)
        for index, value in enumerate(values):
            yield index == size - 1, value

    def fields(self, app, api, args, fields):
        if self.failed:
            raise RuntimeError('projection_capability_stopped')
        self.last_projected = False
        value = self.lookup_fields(app, api, args, fields)
        if value is None:
            self.misses += 1
            return self.fetch_full(app, api, **args)
        if type(value) is not dict or set(value) != set(fields):
            self.fail('projection_observed_fields_contract_false')
            raise RuntimeError('projection_observed_fields_contract_false')
        for field, entry in value.items():
            if field == 'title':
                valid = type(entry) is str
            elif field == 'artists':
                valid = (type(entry) is list and all(type(a) is dict
                         and set(a) == {'id', 'name'} and type(a['id']) is int
                         and a['id'] > 0 and type(a['name']) is str for a in entry))
            elif field == 'album_id':
                valid = entry is None or type(entry) is int and entry > 0
            elif field in ('song_id', 'duration'):
                valid = type(entry) is int and entry > 0
            else:
                valid = False
            if not valid:
                self.fail('projection_observed_value_contract_false')
                raise RuntimeError('projection_observed_value_contract_false')
        self.hits += 1
        self.last_projected = True
        return deepcopy(value)


def _plain_value(value, seen=None, remaining=None):
    """Reject implicit Python callbacks from persistent interpreter objects."""
    if seen is None:
        seen, remaining = set(), [10000]
    remaining[0] -= 1
    if remaining[0] < 0:
        return False
    if type(value) in (str, bytes, int, float, bool, type(None)):
        return True
    if (type(value) not in (dict, list, tuple, set, frozenset)
            or id(value) in seen or len(seen) > 100):
        return False
    seen.add(id(value))
    children = (tuple(value.keys()) + tuple(value.values())) if type(value) is dict else value
    result = all(_plain_value(v, seen, remaining) for v in children)
    seen.remove(id(value))
    return result


def execute_projection(plan, scope, runtime):
    """Interpreter-side execution only. No recovery/materialization after failure.

    A mapping plan allows JSON transport without re-creating its dataclass.
    Runtime namespace guards precede execution and choose whole-program eager
    fallback. The adapter must record that fallback and any stopped capability.
    """
    get = plan.get if _INITIAL_TYPE(plan) is _INITIAL_DICT else lambda name: _INITIAL_GETATTR(plan, name)
    source, transformed = get('source'), get('transformed_source')
    # This check itself must not call possibly replaced builtin functions.
    for name, original in _INITIAL_BUILTINS.items():
        if builtins.__dict__.get(name) is not original:
            _INITIAL_EXEC(_INITIAL_COMPILE(source, '<generated>', 'exec'), scope, scope)
            return {'transformed': False, 'reason': 'builtin_module_changed', 'hits': 0}
    if any(type(name) is not str for name in scope):
        exec(compile(source, '<generated>', 'exec'), scope, scope)
        return {'transformed': False, 'reason': 'non_string_namespace_key', 'hits': 0}
    if _digest(source) != get('source_sha256') or _digest(transformed) != get('transformed_sha256'):
        raise ValueError('projection_plan_hash_mismatch')
    if runtime.failed:
        raise RuntimeError('projection_capability_stopped')
    namespace = scope.get('__builtins__', builtins.__dict__)
    if type(namespace) is not dict:
        namespace = builtins.__dict__ if namespace is builtins else {}
    loaded = {node.id for node in ast.walk(ast.parse(source))
              if isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Load, ast.Store))}
    plain = all(_plain_value(scope[name]) for name in loaded & scope.keys()
                if name not in set(SAFE_BUILTINS) | {'call_api'})
    guarded = (get('eligible') and plain and not any(name.startswith(PREFIX) for name in scope)
               and scope.get('call_api') is runtime.fetch_full
               and all(namespace.get(name) is _CANONICAL_BUILTINS[name]
                       and builtins.__dict__.get(name) is _CANONICAL_BUILTINS[name]
                       and scope.get(name, _CANONICAL_BUILTINS[name]) is _CANONICAL_BUILTINS[name]
                       for name in SAFE_BUILTINS))
    if not guarded:
        exec(compile(source, '<generated>', 'exec'), scope, scope)
        return {'transformed': False, 'reason': 'namespace_guard_or_static_fallback', 'hits': 0}
    before = runtime.hits
    scope[HELPER] = runtime
    try:
        exec(compile(transformed, '<generated-projected>', 'exec'), scope, scope)
    except BaseException:
        if runtime.hits > before and not runtime.failed:
            runtime.fail('automatic_projection_execution_failed')
        raise
    finally:
        for name in tuple(scope):
            if name.startswith(PREFIX):
                del scope[name]
    return {'transformed': True, 'reason': 'bounded_normal_path_projection',
            'hits': runtime.hits - before}
