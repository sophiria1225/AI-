"""Recognize a small recorded print language, without executing saved code.

This is a conservative baseline adapter, not a general Python provenance system.
No eval/exec, imports from saved code, live API, or mutable runtime is accepted.
Unsupported programs retain their complete original output.
"""
import ast
import copy
import json

from context_preservation import compact
from documentation_exposure import DOCUMENTATION_APIS
from handoff_factors import split_turns
from handoff_output_views import make_view
from input_exposure_accounting import digest, receipt_group
from native_conversation import NativeConversation, recover_turn

MAX_NODES = 5000
MAX_STEPS = 2000
MAX_CHARACTERS = 240000
PROTECTED = {'print', 'call_api', 'json', 'len'}


class Unsupported(ValueError):
    """A recognized limit, never a repair permission or a missing-data label."""


def parse(source):
    if not isinstance(source, str) or len(source) > 50000:
        raise Unsupported('source_size_limit')
    try:
        tree = ast.parse(source)
    except (SyntaxError, RecursionError):
        raise Unsupported('source_syntax_not_supported') from None
    if sum(1 for _ in ast.walk(tree)) > MAX_NODES:
        raise Unsupported('syntax_node_limit')
    return tree


def printer_environment_guard(sources):
    """Reject prefix operations that could replace the fixed print/JSON helpers.

    The pinned worker installs call_api before each program. Accepted prefixes
    only manipulate data, call that bridge, and use ordinary print/JSON/len.
    Reflection, module aliases, callbacks, functions and other imports stay out.
    This relies on the pinned worker's initial namespace and JSON-only replies.
    """
    allowed = (ast.Module, ast.Import, ast.alias, ast.Assign, ast.AugAssign, ast.Expr,
               ast.For, ast.While, ast.If, ast.Break, ast.Continue, ast.Pass,
               ast.Name, ast.Constant, ast.Load, ast.Store, ast.List, ast.Tuple,
               ast.Dict, ast.Subscript, ast.Slice, ast.BinOp, ast.UnaryOp,
               ast.BoolOp, ast.Compare, ast.Call, ast.keyword, ast.Attribute,
               ast.JoinedStr, ast.FormattedValue, ast.operator, ast.unaryop,
               ast.boolop, ast.cmpop)
    for source in sources:
        tree = parse(source)
        parents = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
        for node in ast.walk(tree):
            if not isinstance(node, allowed):
                raise Unsupported('prefix_syntax_outside_data_subset')
            if isinstance(node, ast.Import):
                if any(a.name != 'json' or a.asname is not None for a in node.names):
                    raise Unsupported('prefix_import_outside_json')
            if isinstance(node, ast.Name):
                if node.id.startswith('__') or (isinstance(node.ctx, ast.Store) and node.id in PROTECTED):
                    raise Unsupported('prefix_protected_binding')
                if isinstance(node.ctx, ast.Load) and node.id in PROTECTED:
                    parent = parents.get(node)
                    if not ((isinstance(parent, ast.Call) and parent.func is node)
                            or (node.id == 'json' and isinstance(parent, ast.Attribute)
                                and parent.value is node)):
                        raise Unsupported('prefix_helper_alias')
            if isinstance(node, ast.Attribute):
                if not (isinstance(node.value, ast.Name) and node.value.id == 'json'
                        and node.attr == 'dumps' and isinstance(node.ctx, ast.Load)
                        and isinstance(parents.get(node), ast.Call) and parents[node].func is node):
                    raise Unsupported('prefix_attribute_outside_json_renderer')
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    if node.func.id not in ('print', 'call_api', 'len'):
                        raise Unsupported('prefix_call_outside_data_subset')
                    keywords = {'sep', 'end'} if node.func.id == 'print' else (
                        set() if node.func.id == 'len' else {k.arg for k in node.keywords})
                elif isinstance(node.func, ast.Attribute):
                    keywords = {'indent', 'ensure_ascii', 'sort_keys', 'separators'}
                else:
                    raise Unsupported('prefix_dynamic_call')
                if any(k.arg is None or k.arg not in keywords for k in node.keywords):
                    raise Unsupported('prefix_callback_or_dynamic_keywords')
    return True


class PrintRecognizer:
    def __init__(self, entries, receipt_ids):
        if len(entries) != len(receipt_ids) or len(set(receipt_ids)) != len(receipt_ids):
            raise ValueError('API entries and receipt identities differ')
        self.entries, self.receipt_ids = entries, receipt_ids
        self.scope, self.segments = {}, []
        self.position = self.steps = self.characters = 0
        self.json_imported = False

    def step(self):
        self.steps += 1
        if self.steps > MAX_STEPS:
            raise Unsupported('recognition_step_limit')

    def literal(self, node):
        value, origin = self.value(node)
        if origin is not None:
            raise Unsupported('API_value_used_as_program_control')
        return value

    def value(self, node):
        self.step()
        if isinstance(node, ast.Constant) and type(node.value) in (str, int, float, bool, type(None)):
            return node.value, None
        if isinstance(node, ast.Name) and node.id in self.scope:
            return self.scope[node.id]
        if isinstance(node, (ast.List, ast.Tuple)):
            values = [self.literal(item) for item in node.elts]
            return (tuple(values) if isinstance(node, ast.Tuple) else values), None
        if isinstance(node, ast.JoinedStr):
            pieces = []
            for value in node.values:
                if isinstance(value, ast.Constant) and isinstance(value.value, str):
                    pieces.append(value.value)
                elif isinstance(value, ast.FormattedValue) and value.conversion == -1 and value.format_spec is None:
                    item = self.literal(value.value)
                    if not isinstance(item, str):
                        raise Unsupported('formatted_label_requires_literal_string')
                    pieces.append(item)
                else:
                    raise Unsupported('formatted_label_outside_subset')
            return ''.join(pieces), None
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == 'call_api':
            if len(node.args) != 2 or any(k.arg is None for k in node.keywords):
                raise Unsupported('API_call_shape_outside_subset')
            app, api = [self.literal(arg) for arg in node.args]
            arguments = {k.arg: self.literal(k.value) for k in node.keywords}
            if len(arguments) != len(node.keywords):
                raise Unsupported('duplicate_API_keyword')
            if not isinstance(app, str) or not isinstance(api, str) or app + '__' + api not in DOCUMENTATION_APIS:
                raise Unsupported('non_documentation_API')
            if self.position >= len(self.entries):
                raise ValueError('additional recorded API call')
            entry = self.entries[self.position]
            expected = entry['request']
            def canonical(value):
                return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)
            if canonical([app, api, arguments]) != canonical([expected['app'], expected['api'], expected['arguments']]):
                raise ValueError('recorded API arguments or order differ')
            if (not entry['originally_sent'] or not entry['reply'].get('ok')
                    or entry['effects_unknown'] or entry['declared_complete']):
                raise ValueError('unsuccessful or uncertain documentation receipt')
            value = copy.deepcopy(entry['reply']['value'])
            if not isinstance(value, (dict, list)) or (
                    isinstance(value, dict) and {'error', 'detail'} & value.keys()):
                raise Unsupported('documentation_value_outside_subset')
            # No user objects enter this recognizer; this must round-trip as JSON.
            json.dumps(value, allow_nan=False)
            sid = self.receipt_ids[self.position]; self.position += 1
            return value, sid
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name) and node.func.value.id == 'json'
                and node.func.attr == 'dumps' and self.json_imported and len(node.args) == 1):
            value, origin = self.value(node.args[0])
            kwargs = {k.arg: self.literal(k.value) for k in node.keywords}
            if (len(kwargs) != len(node.keywords) or not set(kwargs) <= {'indent', 'ensure_ascii', 'sort_keys', 'separators'}
                    or ('indent' in kwargs and kwargs['indent'] is not None
                        and (type(kwargs['indent']) is not int or not 0 <= kwargs['indent'] <= 8))):
                raise Unsupported('JSON_renderer_options_outside_subset')
            return json.dumps(value, **kwargs), origin
        raise Unsupported('expression_outside_print_subset')

    def emit(self, text, origin):
        if not text:
            return
        self.characters += len(text)
        if self.characters > MAX_CHARACTERS:
            raise Unsupported('rendered_size_limit')
        self.segments.append({'text': text, 'receipt_id': origin})

    def statements(self, body):
        for node in body:
            self.step()
            if isinstance(node, ast.Import) and all(a.name == 'json' and a.asname is None for a in node.names):
                self.json_imported = True
            elif (isinstance(node, ast.Assign) and len(node.targets) == 1
                  and isinstance(node.targets[0], ast.Name) and node.targets[0].id not in PROTECTED):
                self.scope[node.targets[0].id] = self.value(node.value)
            elif (isinstance(node, ast.For) and isinstance(node.target, ast.Name)
                  and node.target.id not in PROTECTED and not node.orelse):
                values = self.literal(node.iter)
                if not isinstance(values, (list, tuple)) or len(values) > 100:
                    raise Unsupported('loop_outside_finite_literal_subset')
                for value in values:
                    self.scope[node.target.id] = (value, None)
                    self.statements(node.body)
            elif (isinstance(node, ast.Expr) and isinstance(node.value, ast.Call)
                  and isinstance(node.value.func, ast.Name) and node.value.func.id == 'print'):
                call = node.value
                values = [self.value(arg) for arg in call.args]
                options = {k.arg: self.literal(k.value) for k in call.keywords}
                if len(options) != len(call.keywords) or not set(options) <= {'sep', 'end'}:
                    raise Unsupported('print_options_outside_subset')
                sep, end = options.get('sep', ' '), options.get('end', '\n')
                if not isinstance(sep, str) or not isinstance(end, str):
                    raise Unsupported('print_separator_outside_subset')
                for index, (value, origin) in enumerate(values):
                    if index:
                        self.emit(sep, None)
                    self.emit(str(value), origin)
                self.emit(end, None)
            else:
                raise Unsupported('statement_outside_print_subset')


def recognize(program, receipt_ids, prefix_sources):
    expected = program['expected']
    if (expected['status'] != 'ok' or expected.get('stdout_truncated') or expected.get('error')
            or expected.get('unknown_effects') or expected.get('declared_complete')):
        return {'recognized': False, 'reason': 'unsuccessful_or_incomplete_program'}, []
    try:
        if not prefix_sources or prefix_sources[-1] != program['source']['code']:
            raise ValueError('complete prefix through the current program required')
        printer_environment_guard(prefix_sources)
        recognizer = PrintRecognizer(program['entries'], receipt_ids)
        recognizer.statements(parse(program['source']['code']).body)
    except Unsupported as error:
        return {'recognized': False, 'reason': str(error)}, []
    stdout = ''.join(s['text'] for s in recognizer.segments)
    if recognizer.position != len(program['entries']) or stdout != expected['stdout']:
        raise ValueError('recognized print sequence differs from actual saved output')
    position, public = 0, []
    for segment in recognizer.segments:
        end = position + len(segment['text'])
        public.append({'start': position, 'end': end, 'receipt_id': segment['receipt_id'],
                       'text_sha256': digest(segment['text'])})
        position = end
    return {'recognized': True, 'reason': 'restricted_print_program_and_full_output_match',
            'segments': public, 'source_code_sha256': digest(program['source']['code']),
            'stdout_sha256': digest(stdout), 'recognized_API_calls': recognizer.position,
            'steps': recognizer.steps, 'runtime_contract_required': True,
            'future_irrelevance_proven': False}, recognizer.segments


def build_origin_view(item):
    prefix = item['prefix']
    full, _ = make_view(prefix['conversation_private'], prefix['public_task'], 'full_keep')
    _, candidates = make_view(prefix['conversation_private'], prefix['public_task'], 'stdout_mask_keep')
    candidate_ids = {entry['span_id'] for entry in candidates['masked_spans']}
    events = {event['span_id']: event for event in prefix['events']}
    if len(events) != len(prefix['events']):
        raise ValueError('duplicate original event')
    outer = [event for event in prefix['events'] if event['stage'] == 'model_tool']
    if len(outer) != len(item['programs']):
        raise ValueError('all original model programs must correspond')
    programs = {}
    sources = []
    for event, program in zip(outer, item['programs'], strict=True):
        if not program['name'].startswith(event['call'] + '_'):
            raise ValueError('outer program order differs')
        sources.append(program['source']['code'])
        programs[event['span_id']] = (program, sources[:])
    selected = NativeConversation(full.messages()[0]['content'], prefix['public_task'])
    checks = []
    for number, turn in enumerate(split_turns(full.messages()), 1):
        spans = recover_turn(turn)
        for span in spans:
            if span['id'] not in candidate_ids:
                continue
            obs = span['observation']
            group, _ = receipt_group(obs, prefix['spans'], events)
            check = {'span_id': span['id'], 'turn': number, 'receipt_group': group, 'changed': False}
            checks.append(check)
            if group != 'documentation_only':
                check.update(recognized=False, reason='retain_mixed_other_or_uncertain_output')
                continue
            program, source_prefix = programs[span['id']]
            if (program['expected']['stdout'] != obs['stdout']
                    or json.loads(span['action']['arguments'])['code'] != program['source']['code']
                    or any(events[r['span_id']]['call'] != events[span['id']]['call']
                           for r in obs['api_receipts'])):
                raise ValueError('program, model action or observation correspondence differs')
            receipt_ids = [r['span_id'] for r in obs['api_receipts']]
            meta, segments = recognize(program, receipt_ids, source_prefix)
            check.update(meta)
            if not meta['recognized']:
                continue
            replacement = copy.deepcopy(obs)
            replacement['stdout'] = ''.join(
                f'[API documentation omitted; read archived span {s["receipt_id"]}.]'
                if s['receipt_id'] is not None else s['text'] for s in segments)
            omitted = list(dict.fromkeys(s['receipt_id'] for s in segments if s['receipt_id'] is not None))
            replacement['stdout_view'] = {'omitted': True, 'source_span_id': span['id'],
                                         'documentation_receipt_ids': omitted,
                                         'literal_output_preserved': True}
            if len(compact(replacement)) >= len(compact(obs)):
                check['reason'] = 'replacement_does_not_shorten_observation'
                continue
            check.update(changed=True, removed_stdout_characters=len(obs['stdout']) - len(replacement['stdout']),
                         documentation_receipt_ids=omitted)
            span['observation'] = replacement
        selected.append(turn[0], spans)
    return {'full_keep': full, 'documentation_origin_keep': selected}, {
        'checks': checks, 'candidate_outputs': len(checks),
        'changed_outputs': sum(row['changed'] for row in checks),
        'original_archive_modified': False, 'latest_turn_retained': True,
        'mixed_outputs_retained': True, 'novel_method_claim': False,
        'quality_preservation_claim': False, 'future_irrelevance_proven': False}
