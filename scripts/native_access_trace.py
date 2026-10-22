"""Limited access observation on native JSON containers, never an omission proof.

Injected only into an isolated, recorded-reply replay. AST instrumentation leaves
dict/list/scalar types intact. It can still change introspection, stack frames,
timing and unsupported operations; the driver must compare every observable
program result with an ordinary replay. No values or field names are exported.
"""
import ast
import builtins
from collections import Counter
import json
import types

HELPER = '_harness_access_20261022'


class Instrument(ast.NodeTransformer):
    def helper(self, name, args, original):
        return ast.copy_location(ast.Call(
            func=ast.Attribute(value=ast.Name(id=HELPER, ctx=ast.Load()),
                               attr=name, ctx=ast.Load()),
            args=args, keywords=[]), original)

    def visit_Call(self, node):
        self.generic_visit(node)
        # Moving these calls to a helper frame changes their implicit scope.
        # Aliased/dynamic variants remain explicitly outside complete coverage.
        if isinstance(node.func, ast.Name) and node.func.id in (
                'globals', 'locals', 'vars', 'dir', 'exec', 'eval', 'super'):
            return node
        # The positional-only function parameter cannot consume a user keyword.
        return ast.copy_location(ast.Call(
            func=ast.Attribute(value=ast.Name(id=HELPER, ctx=ast.Load()),
                               attr='call', ctx=ast.Load()),
            args=[node.func, *node.args], keywords=node.keywords), node)

    def visit_Subscript(self, node):
        self.generic_visit(node)
        if isinstance(node.ctx, ast.Load):
            key = node.slice
            if isinstance(key, ast.Slice):
                key = self.helper('slice_key', [key.lower or ast.Constant(None),
                    key.upper or ast.Constant(None), key.step or ast.Constant(None)], node)
            return self.helper('get_item', [node.value, key], node)
        node.value = self.helper('write_target', [node.value], node)
        return node

    def visit_For(self, node):
        self.generic_visit(node)
        node.iter = self.helper('iterate', [node.iter], node.iter)
        return node

    def visit_comprehension(self, node):
        self.generic_visit(node)
        if not node.is_async:
            node.iter = self.helper('iterate', [node.iter], node.iter)
        return node

    def visit_FormattedValue(self, node):
        self.generic_visit(node)
        node.value = self.helper('presentation', [node.value], node)
        return node


def transformed(source):
    tree = ast.parse(source, filename='<generated>', mode='exec')
    if any(isinstance(n, ast.Name) and n.id == HELPER for n in ast.walk(tree)):
        raise ValueError('measurement helper collides with original program')
    return compile(ast.fix_missing_locations(Instrument().visit(tree)), '<generated>', 'exec')


class Recorder:
    def __init__(self, max_nodes=100000, max_responses=2000):
        self.nodes = {}  # Strong refs prevent id reuse. Scalar identities ignored.
        self.responses = []
        self.api = None
        self.phase = None
        self.max_nodes = max_nodes
        self.max_responses = max_responses
        self.limits = Counter()
        self.dynamic = Counter()

    def register(self, value, app, api):
        if len(self.responses) >= self.max_responses:
            self.limits['response_limit'] += 1
            return value
        rid = len(self.responses)
        row = dict(api=app+'__'+api, phase=self.phase, leaves={}, read=set(),
                   presentation=set(), opaque=set(), structure=0, mutated=False,
                   scalar_root=type(value) not in (dict, list), bounded=False)
        self.responses.append(row)

        def visit(item, path, depth):
            if depth > 80 or len(self.nodes) >= self.max_nodes:
                row['bounded'] = True
                self.limits['node_or_depth_limit'] += 1
                return
            if type(item) in (dict, list):
                slot = self.nodes.setdefault(id(item), (item, []))
                slot[1].append((rid, path))
                children = item.items() if type(item) is dict else enumerate(item)
                for key, child in children:
                    visit(child, path+(key,), depth+1)
            else:
                row['leaves'][path] = len(json.dumps(item, ensure_ascii=False).encode())
        visit(value, (), 0)
        return value

    def routes(self, obj):
        slot = self.nodes.get(id(obj))
        return slot[1] if slot is not None and slot[0] is obj else ()

    def subtree(self, obj, kind):
        for rid, path in self.routes(obj):
            row = self.responses[rid]
            if kind == 'mutation':
                row['mutated'] = True
            elif kind == 'structure':
                row['structure'] += 1
            else:
                row[kind].update(p for p in row['leaves'] if p[:len(path)] == path)

    def expose(self, value, kind, seen=None, depth=0):
        # A new ordinary container can hold a previously registered child.
        if type(value) not in (dict, list, tuple) or depth > 80:
            return
        seen = set() if seen is None else seen
        if id(value) in seen:
            return
        seen.add(id(value))
        if self.routes(value):
            self.subtree(value, kind)
            return
        for child in value.values() if type(value) is dict else value:
            self.expose(child, kind, seen, depth+1)

    def field(self, obj, key):
        if type(key) not in (str, int, bool):
            self.subtree(obj, 'opaque')
            return
        if type(obj) is list and type(key) in (int, bool) and key < 0:
            key += len(obj)
        for rid, path in self.routes(obj):
            row = self.responses[rid]
            full = path+(key,)
            if not row['mutated'] and full in row['leaves']:
                row['read'].add(full)

    def get_item(self, obj, key):
        result = obj[key]  # Original exception is allowed to escape unchanged.
        self.field(obj, key)
        return result

    def write_target(self, obj):
        self.subtree(obj, 'mutation')
        return obj

    @staticmethod
    def slice_key(start, stop, step):
        return slice(start, stop, step)

    def presentation(self, obj):
        self.expose(obj, 'presentation')
        return obj

    def iterate(self, obj):
        native = iter(obj)
        self.subtree(obj, 'structure')

        def values():
            for index, value in enumerate(native):
                if type(obj) is list:
                    self.field(obj, index)
                yield value
        return values()

    def call(self, fn, /, *args, **kwargs):
        if fn is self.api:
            # API arguments can forward values from an earlier response.
            for value in (*args, *kwargs.values()):
                self.expose(value, 'opaque')
            result = fn(*args, **kwargs)
            app = args[0] if args else kwargs.get('app')
            api = args[1] if len(args) > 1 else kwargs.get('api')
            return self.register(result, app, api)

        bound = fn.__self__ if type(fn) is types.BuiltinMethodType else None
        name = fn.__name__ if type(fn) is types.BuiltinMethodType else None
        if type(bound) is dict and name == 'get':
            result = fn(*args, **kwargs)
            if args:
                self.field(bound, args[0])
            return result
        if type(bound) in (dict, list):
            if name in ('update','clear','pop','popitem','setdefault','append',
                        'extend','insert','remove','reverse','sort','__setitem__','__delitem__'):
                self.subtree(bound, 'mutation')
            elif name == 'keys':
                self.subtree(bound, 'structure')
            else:
                self.subtree(bound, 'opaque')
        if any(fn is item for item in (builtins.exec, builtins.eval, builtins.compile)):
            self.dynamic['dynamic_code'] += 1
        if any(fn is item for item in (builtins.globals, builtins.locals, builtins.vars, builtins.dir)):
            self.dynamic['introspection'] += 1
        if any(fn is item for item in (builtins.len, builtins.type, builtins.id, builtins.isinstance,
                                      builtins.issubclass, builtins.bool)):
            for value in args:
                self.subtree(value, 'structure')
        else:
            kind = 'presentation' if any(fn is item for item in (
                builtins.print, builtins.str, builtins.repr, json.dumps)) else 'opaque'
            for value in (*args, *kwargs.values()):
                self.expose(value, kind)
        return fn(*args, **kwargs)

    def execute(self, source, scope, api, phase):
        self.api = api
        self.phase = phase
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                if node.func.id in ('globals','locals','vars','dir','super'):
                    self.dynamic['introspection'] += 1
                if node.func.id in ('exec','eval'):
                    self.dynamic['dynamic_code'] += 1
        code = transformed(source)
        exec(code, scope, scope)

    def summary(self):
        rows = []
        for row in self.responses:
            leaves = row['leaves']
            rows.append({
                'api':row['api'], 'phase':row['phase'], 'scalar_leaves':len(leaves),
                'scalar_json_bytes':sum(leaves.values()),
                'explicit_leaf_reads':len(row['read']),
                'presentation_exposed_leaves':len(row['presentation']),
                'opaque_exposed_leaves':len(row['opaque']),
                'observed_union_leaves':len(row['read'] | row['presentation'] | row['opaque']),
                'structure_operations':row['structure'], 'mutation_observed':row['mutated'],
                'scalar_root_untracked':row['scalar_root'], 'bounded_scan':row['bounded']})
        return {'responses':rows, 'limits':dict(self.limits), 'unsupported_operations':dict(self.dynamic),
                'complete_read_coverage_claim':False, 'unobserved_means_unnecessary':False}
