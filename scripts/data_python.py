"""Small, bounded interpreter for Python-shaped JSON data transformations.

No eval/exec, imports, filesystem, network, process or environment primitives.
It is intentionally not a general Python or CodeAct runtime. Unsupported syntax
is an execution failure, not silently rewritten. Trusted CSV formatting is the
only provided output helper; the model must select sources and construct rows.
"""
import ast
import copy
import csv
import io
import json
import operator


class DataProgramError(ValueError):
    pass


class DataPython:
    def __init__(self, observations, max_steps=100000, max_items=10000, max_chars=1048576):
        # JSON roundtrip rejects non-JSON capabilities before interpreting code.
        encoded = json.dumps(observations, allow_nan=False)
        if len(encoded) > max_chars:
            raise DataProgramError('input_character_limit')
        self.env = {'observations': json.loads(encoded)}
        self.steps, self.max_steps = 0, max_steps
        self.max_items, self.max_chars = max_items, max_chars

    def tick(self):
        self.steps += 1
        if self.steps > self.max_steps:
            raise DataProgramError('step_limit')

    def bounded(self, value):
        if isinstance(value, (str, bytes)) and len(value) > self.max_chars:
            raise DataProgramError('character_limit')
        if isinstance(value, (list, tuple, set, dict, range)) and len(value) > self.max_items:
            raise DataProgramError('item_limit')
        if type(value) is int and value.bit_length() > 128:
            raise DataProgramError('integer_limit')
        return value

    def bind(self, target, value):
        self.tick()
        if isinstance(target, ast.Name):
            if target.id.startswith('_') or target.id == 'observations':
                raise DataProgramError('protected_name')
            self.env[target.id] = self.bounded(value)
        elif isinstance(target, (ast.Tuple, ast.List)):
            if len(value) != len(target.elts):
                raise DataProgramError('unpack_length')
            for t, v in zip(target.elts, value):
                self.bind(t, v)
        elif isinstance(target, ast.Subscript):
            owner, key = self.expr(target.value), self.expr(target.slice)
            if type(owner) not in (list, dict):
                raise DataProgramError('assignment_target')
            owner[key] = self.bounded(value)
            self.bounded(owner)
        else:
            raise DataProgramError('assignment_syntax')

    def iterable(self, value):
        if type(value) not in (list, tuple, dict, set, str, range):
            raise DataProgramError('not_data_iterable')
        if len(value) > self.max_items:
            raise DataProgramError('iteration_limit')
        return value

    def csv_text(self, rows, headers):
        if type(headers) not in (list, tuple) or any(type(h) is not str for h in headers):
            raise DataProgramError('csv_headers')
        result = io.StringIO(newline='')
        writer = csv.writer(result, lineterminator='\n')
        for row in [headers] + list(self.iterable(rows)):
            self.tick()
            if type(row) not in (list, tuple) or len(row) != len(headers):
                raise DataProgramError('csv_row_shape')
            if any(type(x) not in (str, int, float, bool, type(None)) for x in row):
                raise DataProgramError('csv_cell_type')
            # Check a conservative escaped size before csv allocates a row.
            upper_chars = sum(2*len(str(x)) + 3 for x in row) + 1
            if result.tell() + upper_chars > self.max_chars:
                raise DataProgramError('csv_character_limit')
            writer.writerow(row)
            if result.tell() > self.max_chars:
                raise DataProgramError('csv_character_limit')
        return result.getvalue()

    def call(self, node):
        if any(isinstance(a, ast.Starred) for a in node.args) or any(k.arg is None for k in node.keywords):
            raise DataProgramError('expanded_arguments')
        args = [self.expr(a) for a in node.args]
        kw = {k.arg: self.expr(k.value) for k in node.keywords}
        if isinstance(node.func, ast.Name):
            name = node.func.id
            if name == 'csv_text':
                return self.csv_text(*args, **kw)
            if name in ('str', 'int', 'float') and args and type(args[0]) not in (
                    str, int, float, bool, type(None)):
                raise DataProgramError('scalar_conversion_only')
            if name in ('list', 'tuple', 'set', 'dict', 'sorted', 'enumerate', 'reversed'):
                if args:
                    self.iterable(args[0])
                funcs = {'list': list, 'tuple': tuple, 'set': set, 'dict': dict, 'sorted': sorted,
                         'enumerate': lambda *a: list(enumerate(*a)),
                         'reversed': lambda *a: list(reversed(*a))}
            else:
                funcs = {'len': len, 'str': str, 'int': int, 'float': float, 'bool': bool,
                         'range': range, 'min': min, 'max': max, 'sum': sum, 'abs': abs,
                         'zip': lambda *a: list(zip(*(self.iterable(x) for x in a)))}
            if name not in funcs or any(k not in ('reverse',) for k in kw):
                raise DataProgramError('unknown_function_or_keyword')
            return self.bounded(funcs[name](*args, **kw))
        if isinstance(node.func, ast.Attribute):
            obj, name = self.expr(node.func.value), node.func.attr
            allowed = {list: {'append', 'extend', 'sort', 'count', 'index'},
                       dict: {'get', 'keys', 'values', 'items', 'update', 'setdefault'},
                       set: {'add', 'update', 'union', 'intersection', 'difference'},
                       str: {'join', 'strip', 'lower', 'upper', 'replace', 'split', 'startswith', 'endswith'}}
            if type(obj) not in allowed or name not in allowed[type(obj)] or any(k != 'reverse' for k in kw):
                raise DataProgramError('unknown_data_method')
            if name in ('extend', 'update', 'union', 'intersection', 'difference') and args:
                for a in args:
                    self.iterable(a)
            if name == 'join':
                items = self.iterable(args[0])
                if sum(len(x) for x in items) + len(obj)*max(0, len(items)-1) > self.max_chars:
                    raise DataProgramError('join_character_limit')
            if name == 'replace' and len(args) >= 2:
                if len(obj) + (len(obj)+1)*len(args[1]) > self.max_chars:
                    raise DataProgramError('replacement_character_limit')
            value = getattr(obj, name)(*args, **kw)  # name and exact owner type checked above
            self.bounded(obj)
            if name in ('keys', 'values', 'items'):
                value = list(value)
            return self.bounded(value)
        raise DataProgramError('call_syntax')

    def comprehension(self, node):
        saved, results = self.env.copy(), []

        def visit(level):
            if level == len(node.generators):
                result = ((self.expr(node.key), self.expr(node.value)) if isinstance(node, ast.DictComp)
                          else self.expr(node.elt))
                results.append(result)
                self.bounded(results)
                return
            gen = node.generators[level]
            if gen.is_async:
                raise DataProgramError('async_comprehension')
            for value in self.iterable(self.expr(gen.iter)):
                self.tick()
                self.bind(gen.target, value)
                if all(self.expr(x) for x in gen.ifs):
                    visit(level+1)
        try:
            visit(0)
        finally:
            self.env = saved
        if isinstance(node, ast.DictComp):
            return dict(results)
        return set(results) if isinstance(node, ast.SetComp) else results

    def expr(self, node):
        self.tick()
        if isinstance(node, ast.Constant):
            if type(node.value) not in (str, int, float, bool, type(None)):
                raise DataProgramError('constant_type')
            return self.bounded(node.value)
        if isinstance(node, ast.Name):
            if node.id.startswith('_') or node.id not in self.env:
                raise DataProgramError('unknown_name')
            return self.env[node.id]
        if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
            values = self.bounded([self.expr(x) for x in node.elts])
            return tuple(values) if isinstance(node, ast.Tuple) else set(values) if isinstance(node, ast.Set) else values
        if isinstance(node, ast.Dict):
            if any(k is None for k in node.keys):
                raise DataProgramError('dictionary_expansion')
            return self.bounded({self.expr(k): self.expr(v) for k, v in zip(node.keys, node.values)})
        if isinstance(node, ast.Subscript):
            owner = self.expr(node.value)
            if type(owner) not in (list, tuple, dict, str):
                raise DataProgramError('subscript_owner')
            return self.bounded(owner[self.expr(node.slice)])
        if isinstance(node, ast.Slice):
            return slice(*(self.expr(x) if x is not None else None for x in (node.lower, node.upper, node.step)))
        if isinstance(node, ast.Call):
            return self.call(node)
        if isinstance(node, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
            return self.comprehension(node)
        if isinstance(node, ast.IfExp):
            return self.expr(node.body if self.expr(node.test) else node.orelse)
        if isinstance(node, ast.BoolOp):
            value = None
            for sub in node.values:
                value = self.expr(sub)
                if (isinstance(node.op, ast.And) and not value) or (isinstance(node.op, ast.Or) and value):
                    break
            return value
        if isinstance(node, ast.Compare):
            ops = {ast.Eq: operator.eq, ast.NotEq: operator.ne, ast.Lt: operator.lt, ast.LtE: operator.le,
                   ast.Gt: operator.gt, ast.GtE: operator.ge, ast.In: lambda a,b:a in b,
                   ast.NotIn: lambda a,b:a not in b, ast.Is: operator.is_, ast.IsNot: operator.is_not}
            left = self.expr(node.left)
            for op, sub in zip(node.ops, node.comparators):
                right = self.expr(sub)
                if type(op) not in ops or not ops[type(op)](left, right):
                    return False
                left = right
            return True
        if isinstance(node, ast.UnaryOp):
            ops = {ast.Not: operator.not_, ast.USub: operator.neg, ast.UAdd: operator.pos}
            if type(node.op) not in ops:
                raise DataProgramError('unary_operator')
            return self.bounded(ops[type(node.op)](self.expr(node.operand)))
        if isinstance(node, ast.BinOp):
            ops = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
                   ast.Div: operator.truediv, ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod,
                   ast.BitOr: operator.or_, ast.BitAnd: operator.and_, ast.BitXor: operator.xor}
            if type(node.op) not in ops:
                raise DataProgramError('binary_operator')
            a, b = self.expr(node.left), self.expr(node.right)
            if isinstance(node.op, ast.Mod) and type(a) is str:
                raise DataProgramError('string_format_operator')
            if isinstance(node.op, ast.Mult):
                for x, n in ((a,b),(b,a)):
                    if type(x) in (list, tuple, str) and type(n) is int:
                        limit = self.max_chars if type(x) is str else self.max_items
                        if len(x)*max(n,0) > limit:
                            raise DataProgramError('repetition_limit')
            return self.bounded(ops[type(node.op)](a,b))
        raise DataProgramError('expression_syntax:' + type(node).__name__)

    def statements(self, nodes):
        for node in nodes:
            self.tick()
            if isinstance(node, ast.Assign):
                value = self.expr(node.value)
                for target in node.targets:
                    self.bind(target, value)
            elif isinstance(node, ast.AugAssign):
                value = self.expr(ast.BinOp(left=node.target, op=node.op, right=node.value))
                self.bind(node.target, value)
            elif isinstance(node, ast.Expr):
                self.expr(node.value)
            elif isinstance(node, ast.For):
                # Snapshot the finite iterable; mutation cannot extend the loop.
                for value in list(self.iterable(self.expr(node.iter))):
                    self.tick()
                    self.bind(node.target, value)
                    self.statements(node.body)
                self.statements(node.orelse)
            elif isinstance(node, ast.If):
                self.statements(node.body if self.expr(node.test) else node.orelse)
            elif isinstance(node, ast.Pass):
                pass
            else:
                raise DataProgramError('statement_syntax:' + type(node).__name__)

    def run(self, source):
        if type(source) is not str or len(source) > 20000:
            raise DataProgramError('source_limit')
        tree = ast.parse(source, mode='exec')
        if sum(1 for _ in ast.walk(tree)) > 10000:
            raise DataProgramError('syntax_size_limit')
        self.statements(tree.body)
        result = self.env.get('result')
        if type(result) is not str:
            raise DataProgramError('result_must_be_string')
        return {'content': self.bounded(result), 'steps': self.steps}


def run_program(source, observations):
    return DataPython(copy.deepcopy(observations)).run(source)
