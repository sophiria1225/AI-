"""Ordinary P33-style binding inventory at an accepted checkpoint boundary.

The collector runs in the trusted interpreter namespace, never as model code.
No value, repr, custom operation or scalar length is disclosed. This is not a
security sandbox against modification of trusted Python/stdlib internals.
The small controller is not connected to a live worker in this prototype.
"""
from copy import deepcopy
import hashlib
import json

from runtime_inventory import MAX_BINDINGS, validate_inventory


FORMAT = 'checkpoint_runtime_inventory_v1'
MODES = ('off', 'checkpoint_inventory')
MAX_NAMESPACE_BINDINGS = 4096
MAX_NAME_CHARACTERS = 80
RESERVED = frozenset(('call_api', 'read_fields', 'api_schemas', 'observations'))
_TYPE, _DICT, _STR = type, dict, str
_DICT_ITEMS, _DICT_LEN = dict.items, dict.__len__
_STR_ISIDENTIFIER, _STR_ISASCII, _STR_STARTSWITH = str.isidentifier, str.isascii, str.startswith
_STR_LEN = str.__len__
_SORTED = sorted
_KINDS = ((dict, 'dict', dict.__len__), (list, 'list', list.__len__),
    (tuple, 'tuple', tuple.__len__), (set, 'set', set.__len__),
    (frozenset, 'frozenset', frozenset.__len__), (str, 'str', None),
    (int, 'int', None), (float, 'float', None), (bool, 'bool', None), (type(None), 'none', None))


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def collect_inventory(namespace):
    """Inspect top-level bindings only; user objects are never traversed.

    The execution engine must call this synchronously with its exact dict scope.
    Nested custom objects and cycles are harmless: only exact container length
    is read. Namespace identity and current program must be bound by the caller.
    """
    require(_TYPE(namespace) is _DICT, 'exact_runtime_namespace_required')
    require(_DICT_LEN(namespace) <= MAX_NAMESPACE_BINDINGS, 'bounded_runtime_namespace_required')
    rows = []
    for name, value in _DICT_ITEMS(namespace):
        if (_TYPE(name) is not _STR or not 0 < _STR_LEN(name) <= MAX_NAME_CHARACTERS
                or not _STR_ISASCII(name) or not _STR_ISIDENTIFIER(name)
                or _STR_STARTSWITH(name, '_') or name in RESERVED):
            continue
        kind = _TYPE(value)
        for exact, label, length in _KINDS:
            if kind is exact:
                rows.append(dict(name=name, type=label,
                    length=length(value) if length is not None else None))
                break
    rows = _SORTED(rows, key=lambda row: row['name'])
    return dict(eligible_binding_count=len(rows), truncated=len(rows) > MAX_BINDINGS,
                bindings=rows[:MAX_BINDINGS])


def plain_fields(value, fields):
    return (type(value) is dict and len(value) == len(fields)
        and all(type(key) is str for key in dict.keys(value)) and set(value) == fields)


def checked_inventory(snapshot):
    """Validate a JSON-only snapshot before reusing the frozen P33 schema check."""
    require(plain_fields(snapshot, {'eligible_binding_count', 'truncated', 'bindings'}),
            'inventory_snapshot_fields_changed')
    require(type(snapshot['eligible_binding_count']) is int
        and 0 <= snapshot['eligible_binding_count'] <= MAX_NAMESPACE_BINDINGS,
        'bounded_inventory_binding_count_required')
    rows = snapshot['bindings']
    require(type(rows) is list and len(rows) <= MAX_BINDINGS, 'bounded_inventory_rows_required')
    for row in rows:
        require(plain_fields(row, {'name', 'type', 'length'})
            and type(row['name']) is str and type(row['type']) is str
            and (row['length'] is None or type(row['length']) is int), 'plain_inventory_row_required')
        require(row['type'] in {label for _, label, _ in _KINDS}
            and 0 < len(row['name']) <= MAX_NAME_CHARACTERS and row['name'].isascii()
            and row['name'].isidentifier() and row['name'] not in RESERVED,
            'inventory_binding_outside_prototype_scope')
    validate_inventory(snapshot)
    return deepcopy(snapshot)


class CheckpointInventory:
    """An immutable notice for one next actor request per accepted revision.

    Call needs_snapshot after a checkpoint decision. A trusted interpreter may
    then collect once and pass the result to prepare. Repeated view calls for
    counting and dispatch use identical metadata; submitted closes that offer.
    Rejected checkpoints never request a snapshot. Both modes capture at the
    same boundary; off omits the notice, retaining its capture/dispatch evidence.
    """
    def __init__(self, *, mode, execution_scope):
        require(mode in MODES and type(execution_scope) is str and execution_scope,
                'fixed_inventory_mode_and_scope_required')
        self.mode = mode
        self.scope_sha256 = hashlib.sha256(execution_scope.encode()).hexdigest()
        self.prepared_revision = 0
        self.pending = None
        self.events = []

    def needs_snapshot(self, *, accepted, revision):
        require(type(accepted) is bool and type(revision) is int and revision >= 0,
                'exact_checkpoint_decision_required')
        if not accepted:
            return False
        require(revision > 0, 'positive_accepted_revision_required')
        return revision > self.prepared_revision

    def prepare(self, snapshot, *, accepted, revision, program_index, source_boundary_sha256):
        require(self.needs_snapshot(accepted=accepted, revision=revision), 'new_accepted_inventory_revision_required')
        require(self.pending is None and revision == self.prepared_revision + 1,
                'inventory_revision_must_follow_submitted_predecessor')
        require(type(program_index) is int and program_index >= 0,
                'exact_program_boundary_required')
        require(type(source_boundary_sha256) is str and len(source_boundary_sha256) == 64
            and all(c in '0123456789abcdef' for c in source_boundary_sha256), 'source_boundary_hash_required')
        checked = checked_inventory(snapshot)
        packet = dict(format=FORMAT, execution_scope_sha256=self.scope_sha256,
            checkpoint_revision=revision, program_index=program_index,
            source_boundary_sha256=source_boundary_sha256, inventory=checked,
            values_included=False, scalar_lengths_included=False,
            availability_only=True, relevance_or_truth_verified=False)
        text = ('Runtime inventory immediately after this accepted checkpoint. '
            'These are currently available Python binding names, exact builtin types, and container lengths. '
            'Values are not included. Scalar lengths, custom objects, private names and runtime helpers are omitted. '
            'This does not establish relevance, freshness, completeness or task success. '
            'Use ordinary Python inspection or read_span when needed.\n' +
            json.dumps(packet, ensure_ascii=False, sort_keys=True, separators=(',', ':')))
        self.pending = dict(packet=packet, packet_sha256=digest(packet), message=dict(role='system', content=text))
        self.prepared_revision = revision
        self.events.append(dict(kind='prepared', checkpoint_revision=revision, program_index=program_index,
            packet_sha256=self.pending['packet_sha256'], source_boundary_sha256=source_boundary_sha256,
            message_UTF8_bytes=len(text.encode()), listed_bindings=len(checked['bindings']),
            eligible_binding_count=checked['eligible_binding_count'], truncated=checked['truncated']))
        return deepcopy(packet)

    def view(self, messages, *, revision, role='agent'):
        """Return a transient view; do not alter the archived conversation."""
        require(role in ('agent', 'focus'), 'known_inventory_request_role_required')
        result = deepcopy(messages)
        if self.pending is None or role == 'focus':
            return result
        require(type(revision) is int and revision == self.pending['packet']['checkpoint_revision'],
                'inventory_view_revision_changed')
        if self.mode == 'checkpoint_inventory':
            result.append(deepcopy(self.pending['message']))
        return result

    def submitted(self, *, revision, call_id):
        require(self.pending is not None and type(revision) is int
            and revision == self.pending['packet']['checkpoint_revision']
            and type(call_id) is str and call_id, 'inventory_submission_binding_required')
        self.events.append(dict(kind='submitted', checkpoint_revision=revision, call_id=call_id,
            packet_sha256=self.pending['packet_sha256'], exposed=self.mode == 'checkpoint_inventory'))
        self.pending = None

    def summary(self):
        return dict(mode=self.mode, prepared_revision=self.prepared_revision,
            prepared=sum(e['kind'] == 'prepared' for e in self.events),
            submitted=sum(e['kind'] == 'submitted' for e in self.events),
            exposed=sum(e.get('exposed') is True for e in self.events),
            pending=self.pending is not None, events_sha256=digest(self.events),
            additional_model_calls=0, additional_API_requests=0,
            input_tokens_must_include_notice=True, task_quality_established=False,
            ordinary_inventory_not_novel=True, live_worker_connected=False)
