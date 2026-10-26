"""Bounded interpreter-side region projection prototype; no live integration.

Original source is retained. The assembly artifact is for inspection, not a
claim about bytes executed: the report records the selected segment hashes.
Only normal paths inside the explicit trusted runtime contract are considered.
"""
import ast
import builtins
from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
import sys
import threading

import automatic_field_projection as base

PREFIX = '_harness_projection_'
MAX_SOURCE = 20000
MAX_NODES = 6000
MAX_DEPTH = 80
MAX_ITEMS = 512
_TYPE = type
_EXEC = exec
_COMPILE = compile
_LEN = len
_STR = str
_INT = int
_BOOL = bool
_LIST = list
_TUPLE = tuple
_DICT = dict
_SORTED = sorted
_SHA256 = hashlib.sha256
_JSON = json
_JSON_DUMPS = json.dumps
_JSON_LOADS = json.loads
_GETTRACE = sys.gettrace
_GETPROFILE = sys.getprofile
_ENUMERATE_THREADS = threading.enumerate
_BUILTINS = builtins.__dict__.copy()
SAFE_CALLS = frozenset(('print', 'len', 'set', 'dict', 'list', 'tuple', 'sorted',
                        'range', 'isinstance', 'str', 'int', 'float', 'bool'))
TYPE_NAMES = frozenset(('str', 'int', 'float', 'bool', 'dict', 'list', 'tuple', 'set'))
METHODS = frozenset(('get', 'items', 'keys', 'values', 'append', 'extend', 'add',
                     'update', 'sort', 'join'))
# Nested stdlib monkeypatches commonly capable of installing callbacks are not
# accepted as the canonical JSON implementation. This is not host authentication.
_JSON_MODULES = (json, json.encoder, json.decoder, json.scanner)
_JSON_STATE = tuple((m, dict(m.__dict__)) for m in _JSON_MODULES)
_JSON_CLASSES = tuple((c, dict(c.__dict__)) for c in (json.JSONEncoder, json.JSONDecoder))
_JSON_INSTANCES = tuple((o, dict(o.__dict__)) for o in (json._default_encoder, json._default_decoder))


@dataclass(frozen=True)
class RegionPlan:
    source: str
    source_sha256: str
    eligible: bool
    reason: str
    sites: tuple
    segments: tuple
    transformed_source: str
    transformed_sha256: str
    plan_sha256: str


def _sha(value):
    return _SHA256(value.encode('utf-8')).hexdigest()


def canonical_plan_segments(value):
    """Length-delimited plain plan encoding, independent of mutable JSON state."""
    kind = _TYPE(value)
    if value is None:
        return 'n'
    if kind is _BOOL:
        return 'b1' if value else 'b0'
    if kind is _STR:
        return 's' + _STR(_LEN(value)) + ':' + value
    if kind is _INT:
        return 'i' + _STR(value) + ';'
    if kind is _LIST or kind is _TUPLE:
        return 'l' + _STR(_LEN(value)) + ':' + ''.join(canonical_plan_segments(v) for v in value)
    if kind is _DICT:
        for key in value:
            if _TYPE(key) is not _STR:
                raise TypeError('non_plain_region_plan')
        return 'd' + _STR(_LEN(value)) + ':' + ''.join(
            canonical_plan_segments(k) + canonical_plan_segments(value[k]) for k in _SORTED(value))
    raise TypeError('non_plain_region_plan')


def _plan(source, eligible, reason, sites=(), segments=()):
    # A deterministic inspection artifact, never passed off as one exec unit.
    artifact = source if not eligible else '\n'.join(
        '# region-segment ' + _STR(i) + ' ' + s['kind'] + '\n' + s['transformed_source']
        for i, s in enumerate(segments, 1))
    content = _DICT(source_sha256=_sha(source), eligible=eligible, reason=reason,
                   sites=sites, segments=segments, transformed_sha256=_sha(artifact))
    fingerprint = _sha(canonical_plan_segments(content))
    return RegionPlan(source, _sha(source), eligible, reason, _TUPLE(sites), _TUPLE(segments),
                      artifact, _sha(artifact), fingerprint)


def _bounded_tree(source):
    if len(source) > MAX_SOURCE:
        return None, 'source_size_limit'
    try:
        tree = ast.parse(source)
    except (SyntaxError, RecursionError, MemoryError) as error:
        return None, 'analysis_error_' + type(error).__name__
    stack = [(tree, 0)]; count = 0
    while stack:
        node, depth = stack.pop(); count += 1
        if count > MAX_NODES or depth > MAX_DEPTH:
            return None, 'AST_size_or_depth_limit'
        stack.extend((child, depth + 1) for child in ast.iter_child_nodes(node))
    return tree, None


def _safe_source(tree):
    accepted = (ast.Module, ast.Assign, ast.AugAssign, ast.Expr, ast.For, ast.While,
        ast.If, ast.IfExp, ast.Break, ast.Continue, ast.Pass, ast.Name, ast.Constant,
        ast.Dict, ast.List, ast.Tuple, ast.Set, ast.Call, ast.keyword, ast.Attribute,
        ast.Subscript, ast.Slice, ast.ListComp, ast.comprehension, ast.JoinedStr,
        ast.FormattedValue, ast.Compare, ast.UnaryOp, ast.BinOp, ast.BoolOp,
        ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.BitOr,
        ast.USub, ast.UAdd, ast.Not, ast.And, ast.Or, ast.Eq, ast.NotEq, ast.Lt,
        ast.LtE, ast.Gt, ast.GtE, ast.In, ast.NotIn, ast.Load, ast.Store,
        ast.Import, ast.alias)
    parents = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
    protected = SAFE_CALLS | {'call_api', 'json', '__builtins__'}
    for node in ast.walk(tree):
        if type(node) not in accepted:
            return False
        if isinstance(node, ast.Import):
            if len(node.names) != 1 or node.names[0].name != 'json' or node.names[0].asname:
                return False
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            return False  # segmented compilation must not create new __doc__ writes
        if isinstance(node, ast.Name):
            if node.id.startswith(PREFIX) or node.id.startswith('__'):
                return False
            if isinstance(node.ctx, ast.Store) and node.id in protected:
                return False
            if isinstance(node.ctx, ast.Load) and node.id in protected:
                parent = parents.get(node)
                direct_call = isinstance(parent, ast.Call) and parent.func is node
                json_attribute = (node.id == 'json' and isinstance(parent, ast.Attribute)
                                  and parent.value is node)
                type_arg = (node.id in TYPE_NAMES and isinstance(parent, ast.Call)
                            and isinstance(parent.func, ast.Name) and parent.func.id == 'isinstance'
                            and len(parent.args) == 2 and parent.args[1] is node)
                if not (direct_call or json_attribute or type_arg):
                    return False
        if isinstance(node, ast.Assign):
            if len(node.targets) != 1 or isinstance(node.targets[0], (ast.Tuple, ast.List)):
                return False
        if isinstance(node, ast.Attribute):
            parent = parents.get(node)
            literal_join = (isinstance(node.value, ast.Constant) and type(node.value.value) is str
                            and node.attr == 'join')
            if (not isinstance(node.ctx, ast.Load)
                    or not (isinstance(node.value, ast.Name) or literal_join)
                    or not isinstance(parent, ast.Call) or parent.func is not node):
                return False
            if isinstance(node.value, ast.Name) and node.value.id == 'json':
                if node.attr not in ('dumps', 'loads'):
                    return False
            elif node.attr not in METHODS:
                return False
        if isinstance(node, ast.Call):
            if any(k.arg is None for k in node.keywords) or any(isinstance(a, ast.Starred) for a in node.args):
                return False
            if isinstance(node.func, ast.Name):
                if node.func.id not in SAFE_CALLS | {'call_api'}:
                    return False
                if node.func.id == 'call_api':
                    if (len(node.args) != 2 or any(not isinstance(a, ast.Constant)
                            or type(a.value) is not str for a in node.args)):
                        return False
                elif node.func.id == 'sorted' and any(k.arg != 'reverse' for k in node.keywords):
                    return False
                elif node.func.id == 'print' and node.keywords:
                    return False  # custom file callbacks are outside this prototype
            elif isinstance(node.func, ast.Attribute):
                if isinstance(node.func.value, ast.Name) and node.func.value.id == 'json':
                    allowed = ('ensure_ascii', 'sort_keys', 'indent') if node.func.attr == 'dumps' else ()
                    if any(k.arg not in allowed for k in node.keywords):
                        return False
                elif node.func.attr == 'sort' and any(k.arg != 'reverse' for k in node.keywords):
                    return False
                elif node.func.attr == 'join' and (len(node.args) != 1 or node.keywords):
                    return False
            else:
                return False
    return True


def _candidate(loop):
    if not (isinstance(loop, ast.For) and isinstance(loop.iter, ast.Name)):
        return None
    # Reuse the frozen consumer recognizer with a placeholder iterable proof.
    # The placeholder is never executed; actual values are checked at entry.
    destinations = {}
    for statement in loop.body[1:]:
        if (isinstance(statement, ast.Assign) and len(statement.targets) == 1
                and isinstance(statement.targets[0], ast.Subscript)
                and isinstance(statement.targets[0].value, ast.Name)):
            destinations[statement.targets[0].value.id] = 'dict'
        elif (isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Call)
                and isinstance(statement.value.func, ast.Attribute)
                and isinstance(statement.value.func.value, ast.Name)):
            destinations[statement.value.func.value.id] = 'set'
    bindings = {loop.iter.id: ast.List(elts=[ast.Constant(1)], ctx=ast.Load())}
    for name, kind in destinations.items():
        bindings[name] = ast.Dict(keys=[], values=[]) if kind == 'dict' else ast.Call(
            func=ast.Name('set', ast.Load()), args=[], keywords=[])
    found = base._candidate(loop, bindings)
    if found is None:
        return None
    root, item, fields = found
    if len({root, item, loop.iter.id, *destinations}) != 3 + len(destinations):
        return None
    return dict(line=loop.lineno, root=root, item=item, iterable=loop.iter.id,
                fields=list(fields), destinations=destinations,
                final_iteration='ordinary_full_at_original_position')


def _project_loop(loop, site):
    result = deepcopy(loop); first, tail = result.body[0], result.body[1:]
    root, item = site['root'], site['item']
    flag, values = PREFIX + 'region_last', PREFIX + 'region_fields'
    last = [deepcopy(first), ast.Assign([ast.Name(values, ast.Store())], ast.Name(root, ast.Load()))]
    args = ast.Dict([ast.Constant('song_id')], [ast.Name(item, ast.Load())])
    projected = ast.Call(ast.Attribute(ast.Name(base.HELPER, ast.Load()), 'fields', ast.Load()),
        [ast.Constant('spotify'), ast.Constant('show_song'), args,
         ast.Tuple([ast.Constant(f) for f in site['fields']], ast.Load())], [])
    middle = [ast.Assign([ast.Name(values, ast.Store())], projected),
        ast.If(ast.UnaryOp(ast.Not(), ast.Attribute(ast.Name(base.HELPER, ast.Load()), 'last_projected', ast.Load())),
               [ast.Assign([ast.Name(root, ast.Store())], ast.Name(values, ast.Load()))], [])]
    result.iter = ast.Call(ast.Attribute(ast.Name(base.HELPER, ast.Load()), 'iterate', ast.Load()), [result.iter], [])
    result.target = ast.Tuple([ast.Name(flag, ast.Store()), result.target], ast.Store())
    result.body = [ast.If(ast.Name(flag, ast.Load()), last, middle)] + [
        base._ReplaceRoot(root, values).visit(deepcopy(n)) for n in tail]
    return ast.fix_missing_locations(result)


def plan_region_projection(source):
    if _TYPE(source) is not str:
        raise TypeError('region_source_must_be_text')
    if not base.builtin_integrity():
        return _plan(source, False, 'builtin_module_changed')
    tree, reason = _bounded_tree(source)
    if tree is None:
        return _plan(source, False, reason)
    if not _safe_source(tree):
        return _plan(source, False, 'unsupported_program_effect')
    try:
        _COMPILE(tree, '<generated>', 'exec', dont_inherit=True)
    except (SyntaxError, RecursionError, MemoryError) as error:
        return _plan(source, False, 'analysis_error_' + type(error).__name__)
    segments = []; sites = []; pending = []
    def segment(nodes, kind, site=None, transformed=None):
        original = ast.unparse(ast.Module(body=deepcopy(nodes), type_ignores=[]))
        selected = original if transformed is None else ast.unparse(transformed)
        return dict(kind=kind, source=original, source_sha256=_sha(original),
                    transformed_source=selected, transformed_sha256=_sha(selected), site_index=site)
    for statement in tree.body:
        site = _candidate(statement)
        if site is None:
            pending.append(statement); continue
        if pending:
            segments.append(segment(pending, 'ordinary')); pending = []
        index = len(sites); sites.append(site)
        segments.append(segment([statement], 'region', index, _project_loop(statement, site)))
    if pending:
        segments.append(segment(pending, 'ordinary'))
    if not sites:
        return _plan(source, False, 'no_supported_top_level_region')
    return _plan(source, True, 'bounded_region_projection', sites, segments)


class RegionProjectionRuntime(base.ProjectionRuntime):
    """Compatible trusted callbacks: fetch_full, lookup_fields, stop."""
    def __init__(self, fetch_full, lookup_fields, stop):
        super().__init__(fetch_full, lookup_fields, stop)
        self.region_reports = []
        self.segment_reports = []


def _json_intact():
    if sys.modules.get('json') is not _JSON:
        return False
    for obj, original in _JSON_STATE + _JSON_CLASSES + _JSON_INSTANCES:
        # Additional instance/class methods can shadow inherited callbacks even
        # when every previously present entry retains its original identity.
        current = obj.__dict__
        if (current.keys() != original.keys()
                or any(current.get(name) is not value for name, value in original.items())):
            return False
    return True


def _namespace_guard(scope, runtime, names):
    if not base.builtin_integrity():
        return 'builtin_module_changed'
    if scope.get('call_api') is not runtime.fetch_full:
        return 'call_api_binding_changed'
    namespace = scope.get('__builtins__', builtins.__dict__)
    if namespace is builtins:
        namespace = builtins.__dict__
    if type(namespace) is not dict or any(namespace.get(n) is not _BUILTINS[n]
            or scope.get(n, _BUILTINS[n]) is not _BUILTINS[n] for n in SAFE_CALLS):
        return 'builtin_namespace_changed'
    if any(type(n) is not str or n.startswith(PREFIX) for n in scope):
        return 'reserved_or_non_string_namespace'
    if not _json_intact() or 'json' in scope and scope['json'] is not _JSON:
        return 'json_binding_changed'
    if (sys.gettrace is not _GETTRACE or sys.getprofile is not _GETPROFILE
            or _GETTRACE() is not None or _GETPROFILE() is not None
            or threading.enumerate is not _ENUMERATE_THREADS or len(_ENUMERATE_THREADS()) != 1):
        return 'concurrent_or_traced_execution'
    for name in names & scope.keys():
        if name not in SAFE_CALLS | {'call_api', 'json'} and not base._plain_value(scope[name]):
            return 'non_plain_referenced_namespace'
    return None


def _region_guard(site, scope, runtime, names):
    reason = _namespace_guard(scope, runtime, names)
    if reason:
        return reason
    values = scope.get(site['iterable'])
    if (type(values) not in (list, tuple) or len(values) > MAX_ITEMS
            or any(type(value) is not int or value <= 0 for value in values)):
        return 'dynamic_iterable_domain_rejected'
    objects = [values]
    for name, kind in site['destinations'].items():
        value = scope.get(name)
        if type(value) is not (dict if kind == 'dict' else set) or not base._plain_value(value):
            return 'destination_domain_rejected'
        objects.append(value)
    if len({id(v) for v in objects}) != len(objects):
        return 'iterable_destination_alias'
    for name in (site['root'], site['item']):
        if name in scope and not base._plain_value(scope[name]):
            return 'overwritten_binding_callback_risk'
        if name in scope and any(scope[name] is value for value in objects):
            return 'overwritten_binding_alias'
    return None


def execute_region_projection(plan, scope, runtime):
    """Interpreter only. A failed entry guard never repeats a prefix or program."""
    if _TYPE(scope) is not dict or _TYPE(runtime) is not RegionProjectionRuntime:
        raise TypeError('exact_region_runtime_and_namespace_required')
    if runtime.failed:
        raise RuntimeError('projection_capability_stopped')
    get = plan.get if _TYPE(plan) is dict else lambda key: getattr(plan, key)
    source = get('source')
    if not base.builtin_integrity():
        _EXEC(_COMPILE(source, '<generated>', 'exec'), scope, scope)
        return {'transformed': False, 'reason': 'builtin_module_changed', 'hits': 0,
                'segments': [], 'regions': []}
    expected = plan_region_projection(source)
    if (get('source_sha256') != expected.source_sha256 or get('plan_sha256') != expected.plan_sha256
            or get('transformed_sha256') != expected.transformed_sha256
            or get('transformed_source') != expected.transformed_source
            or get('eligible') is not expected.eligible or get('reason') != expected.reason
            or canonical_plan_segments(get('sites')) != canonical_plan_segments(expected.sites)
            or canonical_plan_segments(get('segments')) != canonical_plan_segments(expected.segments)):
        raise ValueError('region_plan_hash_mismatch')
    tree, _ = _bounded_tree(source)
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} if tree else set()
    initial = _namespace_guard(scope, runtime, names) if expected.eligible else expected.reason
    if initial:
        _EXEC(_COMPILE(source, '<generated>', 'exec'), scope, scope)
        return {'transformed': False, 'reason': initial, 'hits': 0, 'segments': [], 'regions': []}
    # Validate every alternative before any prefix effect. Whole-source compile
    # above also rejects break/continue outside loops before segmentation.
    compiled = [(_COMPILE(s['source'], '<generated-region>', 'exec', dont_inherit=True),
                 _COMPILE(s['transformed_source'], '<generated-region>', 'exec', dont_inherit=True))
                for s in expected.segments]
    before = runtime.hits; regions = []; segments = []
    try:
        for number, segment in enumerate(expected.segments):
            selected = segment['source']; transformed = False; reason = 'ordinary_segment'
            site = expected.sites[segment['site_index']] if segment['kind'] == 'region' else None
            if site is not None:
                rejected = _region_guard(site, scope, runtime, names)
                transformed = rejected is None
                reason = rejected or 'bounded_region_projection'
                selected = segment['transformed_source'] if transformed else segment['source']
                region = dict(site_index=segment['site_index'], admitted=transformed,
                              transformed=transformed, reason=reason,
                              original_sha256=segment['source_sha256'], executed_sha256=_sha(selected),
                              hits_before=runtime.hits, hits_after=None)
                regions.append(region); runtime.region_reports.append(region)
            evidence = dict(segment_index=number, kind=segment['kind'], reason=reason,
                original_sha256=segment['source_sha256'], candidate_sha256=segment['transformed_sha256'],
                selected_sha256=_sha(selected), transformed=transformed, completed=False)
            segments.append(evidence); runtime.segment_reports.append(evidence)
            if transformed:
                scope[base.HELPER] = runtime
            try:
                _EXEC(compiled[number][int(transformed)], scope, scope)
                evidence['completed'] = True
            finally:
                if site is not None:
                    region['hits_after'] = runtime.hits
                if transformed:
                    for name in tuple(scope):
                        if name.startswith(PREFIX):
                            del scope[name]
    except BaseException:
        if runtime.hits > before and not runtime.failed:
            runtime.fail('automatic_projection_execution_failed')
        raise
    return dict(transformed=any(r['transformed'] for r in regions), reason='region_execution_complete',
                hits=runtime.hits-before, segments=deepcopy(segments), regions=deepcopy(regions),
                assembly_artifact_is_executed_whole_source=False)
