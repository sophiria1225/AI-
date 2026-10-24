"""Describe saved demand syntax and input growth without executing saved code.

Field references are lexical observations, not proofs of aliasing, liveness,
future demand, cache validity or removable model calls. Values stay private.
"""
import ast
from collections import Counter, defaultdict
import hashlib
import json

from field_read_contract import READ_ONLY_APIS, canonical
from public_read_opportunity import public_value
from recorded_action_agreement import action_value
from return_use_scope import analyze as root_uses

FIELDS = frozenset(('id', 'name', 'title', 'artists', 'artist_id', 'artist_ids',
    'song_id', 'song_ids', 'songs', 'album_id', 'albums', 'playlist_id', 'playlists',
    'access_token', 'status', 'message', 'path', 'genre', 'duration', 'content'))
NESTED = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda,
          ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def require(condition, label):
    if not condition:
        raise ValueError(label)


def pos(node):
    return node.lineno, node.col_offset


def program_syntax(source, public_names):
    base = root_uses(source)  # Enforces finite source and AST bounds.
    tree = ast.parse(source)
    nodes = list(ast.walk(tree))
    parents = {c: n for n in nodes for c in ast.iter_child_nodes(n)}
    calls = {pos(n): n for n in nodes if isinstance(n, ast.Call)}
    result = []
    for old in base['sites']:
        site = dict(old)
        site['api'] = site['api'] if site['api'] in public_names else None
        site['field_label'] = site['field_label'] if site['field_label'] in FIELDS else None
        call = calls[(site['line'], site['column'])]
        binding = parents.get(call)
        uses = Counter(); fields = Counter(); scopes = set(); nested = 0
        root = None; later_rebinding = None
        if isinstance(binding, (ast.Assign, ast.AnnAssign)) and binding.value is call:
            targets = binding.targets if isinstance(binding, ast.Assign) else [binding.target]
            if len(targets) == 1 and isinstance(targets[0], ast.Name):
                root = targets[0].id
                lower = (binding.end_lineno, binding.end_col_offset)
                stores = [n for n in nodes if isinstance(n, ast.Name) and n.id == root
                          and isinstance(n.ctx, (ast.Store, ast.Del)) and pos(n) >= lower]
                later_rebinding = min(map(pos, stores)) if stores else None
                loads = [n for n in nodes if isinstance(n, ast.Name) and n.id == root
                         and isinstance(n.ctx, ast.Load) and pos(n) >= lower
                         and (later_rebinding is None or pos(n) < later_rebinding)]
                for n in loads:
                    ancestor = n
                    while ancestor in parents:
                        ancestor = parents[ancestor]
                        if isinstance(ancestor, NESTED):
                            nested += 1; break
                    p = parents[n]; label = None
                    if isinstance(p, ast.Subscript) and p.value is n:
                        if not isinstance(p.ctx, ast.Load):
                            kind = 'member_mutation'
                        elif isinstance(p.slice, ast.Constant) and type(p.slice.value) is str:
                            kind = 'literal_field'; label = p.slice.value
                        else:
                            kind = 'dynamic_or_nonstring_subscript'
                    elif isinstance(p, ast.Attribute) and p.value is n:
                        outer = parents.get(p)
                        if (p.attr == 'get' and isinstance(outer, ast.Call) and outer.func is p
                                and len(outer.args) in (1, 2) and not outer.keywords
                                and isinstance(outer.args[0], ast.Constant)
                                and type(outer.args[0].value) is str):
                            kind = 'literal_get'; label = outer.args[0].value
                        else:
                            kind = 'method_or_attribute'
                    else:
                        kind = 'whole_root_syntax'
                    uses[kind] += 1
                    if label is not None:
                        fields[label if label in FIELDS else '<unpublished-field>'] += 1
                ancestor = binding
                while ancestor in parents:
                    ancestor = parents[ancestor]
                    if isinstance(ancestor, (ast.If, ast.For, ast.While, ast.Try, ast.TryStar,
                                            ast.With, ast.Match) + NESTED):
                        scopes.add(type(ancestor).__name__)
        site.update(single_name_binding=root is not None,
            binding_scope_kinds=sorted(scopes), lexical_load_counts=dict(uses),
            public_literal_field_counts=dict(fields), nested_scope_same_spelling_loads=nested,
            later_same_spelling_store_position=later_rebinding,
            alias_or_liveness_proved=False, safe_substitution_established=False)
        result.append(site)
    return dict(source_sha256=base['source_sha256'], ast_nodes=base['ast_nodes'],
        call_api_syntax_sites=len(result), sites=result,
        current_program_hazards=base['current_program_hazards'],
        bridge_name_non_call_loads=base['bridge_name_non_call_loads'],
        explicit_read_fields_syntax_sites=base['explicit_read_fields_syntax_sites'],
        syntax_sites_are_not_API_requests=True, measured_savings=None)


def message_components(messages):
    """Unicode characters in disjoint text fields; never tokenizer estimates."""
    require(type(messages) is list and len(messages) <= 1024, 'message_list_bound')
    counts = Counter(); roles = Counter()
    for message in messages:
        require(type(message) is dict, 'message_object_required')
        role = message.get('role')
        require(role in ('system', 'user', 'assistant', 'tool'), 'message_role')
        roles[role] += 1
        content = message.get('content')
        require(content is None or type(content) is str, 'text_content_required')
        counts[role + '_content_characters'] += len(content or '')
        reasoning = message.get('reasoning_content')
        require(reasoning is None or type(reasoning) is str, 'reasoning_text_required')
        require(role == 'assistant' or reasoning is None, 'reasoning_role')
        counts['assistant_reasoning_characters'] += len(reasoning or '')
        for call in message.get('tool_calls') or []:
            require(role == 'assistant' and type(call) is dict and
                    type(call.get('function')) is dict, 'assistant_function_call_required')
            function = call['function']
            require(type(function.get('name')) is str and type(function.get('arguments')) is str,
                    'function_text_fields_required')
            counts['assistant_function_name_characters'] += len(function['name'])
            counts['assistant_function_arguments_characters'] += len(function['arguments'])
    keys = ['system_content_characters', 'user_content_characters',
            'assistant_content_characters', 'tool_content_characters',
            'assistant_reasoning_characters', 'assistant_function_name_characters',
            'assistant_function_arguments_characters']
    counts = {k: counts[k] for k in keys}
    return dict(**counts, total_text_field_characters=sum(counts.values()),
        message_counts=dict(roles), protocol_identifiers_and_JSON_overhead_excluded=True,
        character_counts_are_not_token_counts=True)


def _artist_names(value, api):
    # Only these public response locations establish an observed ID/name pair.
    pairs = []
    if api == 'spotify__show_song_library' and type(value) is list:
        for song in value:
            if type(song) is dict and type(song.get('artists')) is list:
                for artist in song['artists']:
                    if type(artist) is dict:
                        pairs.append((artist.get('id'), artist.get('name')))
    elif api == 'spotify__show_artist' and type(value) is dict:
        pairs.append((value.get('artist_id'), value.get('name')))
    return [(i, n) for i, n in pairs if type(i) is int and i > 0 and type(n) is str]


def acquisition_history(events, spans, usage, public_names):
    require(len(events) <= 4000 and len(usage) <= 80, 'event_bound')
    ids = [e['span_id'] for e in events]
    call_ids = [u['id'] for u in usage]
    require(len(call_ids) == len(set(call_ids)), 'unique_call_ids_required')
    ranks = {cid: i for i, cid in enumerate(call_ids)}
    order = [ranks.get(e['call'], -1) for e in events]
    require(-1 not in order and order == sorted(order) and len(ids) == len(set(ids))
            and set(ids) == set(spans), 'chronological_complete_events_required')
    prior_requests = {}; artists = defaultdict(list); barriers = []
    rows = []; counts = Counter(); epoch = 0
    for ordinal, event in enumerate(events, 1):
        if not event['api_request_sent']:
            if event.get('effects_unknown'):
                epoch += 1
                barriers.append((ordinal, 'unknown_unsent_effect'))
            continue
        require(event['stage'] == 'python_api', 'actual_API_stage_required')
        receipt = event.get('api_execution') or {}
        require(receipt.get('bridge_request_sent') is True and receipt.get('automatic_retries') == 0
                and receipt.get('status') in ('returned', 'raised', 'unknown'), 'typed_receipt_required')
        span = spans[event['span_id']]
        action = action_value(span['action']); api = action['name']
        require(api in public_names, 'known_public_API_required')
        identity = digest(action)
        previous = prior_requests.get(identity)
        known = receipt['status'] == 'returned' and not event.get('effects_unknown')
        value = public_value(span) if known else None
        fingerprint = digest(value) if known else None
        row = dict(event_ordinal=ordinal, call_id=event['call'], api=api,
            receipt_status=receipt['status'], prior_identical_returned_request=previous is not None,
            prior_identical_returned_request_ordinal=previous['ordinal'] if previous else None,
            prior_identical_return_same_conservative_epoch=bool(previous and
                previous['epoch'] == epoch and api in READ_ONLY_APIS),
            prior_complete_return_equals_current=(fingerprint == previous['fingerprint']
                if previous and known else None),
            prior_artist_name_observations=None, prior_artist_name_matches_current=None,
            existing_contract_authorizes_artist_name_substitution=False,
            online_API_omission_established=False)
        if api == 'spotify__show_artist':
            artist_id = action['arguments'].get('artist_id')
            supported = (set(action['arguments']) == {'artist_id'} and type(artist_id) is int
                         and artist_id > 0)
            history = artists.get(artist_id, []) if supported else []
            latest = history[-1] if history else None
            row.update(supported_artist_identity=supported,
                prior_artist_name_observations=len(history),
                prior_artist_name_sources=dict(Counter(h['api'] for h in history)),
                prior_artist_names_conflict=len({h['name'] for h in history}) > 1,
                prior_artist_name_matches_current=(
                    type(value) is dict and value.get('artist_id') == artist_id
                    and value.get('name') == latest['name'] if latest and known else None),
                conservative_barriers_after_latest_name=dict(Counter(api for index, api in barriers
                    if latest and index > latest['ordinal'])))
        rows.append(row)
        counts['sent_API_requests'] += 1; counts['receipt_' + receipt['status']] += 1
        counts['prior_identical_returned_request'] += previous is not None
        counts['prior_identical_return_same_conservative_epoch'] += row['prior_identical_return_same_conservative_epoch']
        if api not in READ_ONLY_APIS or event.get('effects_unknown') or receipt['status'] == 'unknown':
            epoch += 1; barriers.append((ordinal, api))
        if known:
            prior_requests[identity] = dict(ordinal=ordinal, epoch=epoch, fingerprint=fingerprint)
            for artist_id, name in _artist_names(value, api):
                artists[artist_id].append(dict(ordinal=ordinal, name=name, api=api))
                require(sum(map(len, artists.values())) <= 8192, 'artist_observation_bound')
    return dict(counts=dict(counts), api_names=dict(Counter(r['api'] for r in rows)),
        requests=rows, prior_values_are_observations_not_authorities=True,
        name_only_is_not_full_artist_response=True, measured_savings=None,
        removable_model_calls=None)
