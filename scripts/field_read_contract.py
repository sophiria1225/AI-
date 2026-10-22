"""Explicit projected reads, not a transparent replacement for an existing API.

The host owns the execution/audience scope and a trustworthy state revision. A
revision is not inferred from a GET method or from equality with a future reply.
The only cross-API rule is the pinned AppWorld Song serializer relationship.
"""
from dataclasses import dataclass
import copy
import hashlib
import json
from pathlib import Path


CONTRACT_ID = "appworld-song-library-public-fields-v1"
SOURCE = "spotify__show_song_library"
TARGET = "spotify__show_song"
FIELDS = frozenset(("song_id", "title", "album_id", "duration", "artists"))
# Audited read handlers/serializers in the pinned files. This is not a rule that
# every HTTP GET is pure. Other sent operations invalidate the recorded probe.
READ_ONLY_APIS = frozenset((SOURCE, TARGET, "spotify__show_album",
                           "spotify__show_playlist", "spotify__show_playlist_library",
                           "spotify__show_album_library"))
SOURCE_HASHES = {
    "apis.py": "eaa23bb250094ee3ff50330d3b75bdac86999394611a15b0b44934c90464b3f1",
    "models.py": "e35f8c4cd5fcd090d8e6d187bce0ee4c2e1e2f3202ec719186d0e663a13430a6",
}


def verify_public_implementation(spotify_directory: Path) -> str:
    for filename, expected in SOURCE_HASHES.items():
        path = spotify_directory / filename
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError("unverified public API implementation: " + filename)
    return CONTRACT_ID


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


@dataclass(frozen=True)
class ReadContext:
    execution_scope: str
    state_revision: str | None
    contract_version: str

    def usable(self):
        return (type(self.execution_scope) is str and bool(self.execution_scope)
                and type(self.state_revision) is str and bool(self.state_revision)
                and self.contract_version == CONTRACT_ID)


@dataclass
class FieldRead:
    value: dict
    source: str  # fetched / exact / cross_api
    backend_calls: int


def required_fields(fields):
    if (type(fields) not in (tuple, list) or not fields
            or any(type(f) is not str or not f for f in fields)
            or len(set(fields)) != len(fields)):
        raise ValueError("fields must be a nonempty, unique list of names")
    return tuple(fields)


def project(value, fields):
    if type(value) is not dict:
        raise ValueError("projected read requires a dictionary response")
    # Missing fields raise; never invent a null or return a partial success.
    return {name: copy.deepcopy(value[name]) for name in fields}


def target_identity(api, arguments):
    if (api != TARGET or type(arguments) is not dict or set(arguments) != {"song_id"}
            or type(arguments["song_id"]) is not int or arguments["song_id"] <= 0):
        return None
    return arguments["song_id"]


def valid_field(name, value):
    if name == "song_id":
        return type(value) is int and value > 0
    if name == "title":
        return type(value) is str
    if name == "album_id":
        return value is None or type(value) is int and value > 0
    if name == "duration":
        return type(value) is int and value > 0
    if name == "artists":
        return (type(value) is list and all(type(a) is dict and set(a) == {"id", "name"}
                and type(a["id"]) is int and a["id"] > 0 and type(a["name"]) is str
                for a in value))
    return False


class FieldReadCache:
    """Small host-side component with fail-closed scope/version checks.

    Modes have identical projection semantics. `exact` retains whole responses,
    so changing the requested fields alone does not weaken that baseline.
    The caller must invalidate before every write or operation of unknown effect.
    """
    def __init__(self, mode, *, verified_contract=None, max_records=512,
                 max_value_bytes=65536):
        if mode not in ("none", "exact", "contract"):
            raise ValueError("unknown cache mode")
        if max_records < 1 or max_value_bytes < 1:
            raise ValueError("positive cache bounds required")
        self.mode = mode
        self.verified_contract = verified_contract
        self.max_records = max_records
        self.max_value_bytes = max_value_bytes
        self.context = None
        self.exact = {}
        self.fields = {}
        self.bounds_rejected = 0

    def invalidate(self):
        self.context = None
        self.exact.clear()
        self.fields.clear()

    def _activate(self, context):
        if (not isinstance(context, ReadContext) or not context.usable()
                or self.verified_contract != CONTRACT_ID):
            self.invalidate()
            return False
        if context != self.context:
            self.invalidate()
            self.context = context
        return True

    def _bounded(self, value):
        try:
            ok = len(canonical(value).encode()) <= self.max_value_bytes
        except (ValueError, TypeError, RecursionError):
            ok = False
        self.bounds_rejected += int(not ok)
        return ok

    def observe(self, api, arguments, value, context):
        """Only successful, already-authorized responses may enter here."""
        if not self._activate(context) or self.mode == "none":
            return
        identity = target_identity(api, arguments)
        if (identity is not None and type(value) is dict
                and type(value.get("song_id")) is int and value["song_id"] == identity
                and self._bounded(value)):
            key = canonical(arguments)
            if key not in self.exact and len(self.exact) >= self.max_records:
                self.bounds_rejected += 1
                return
            encoded = canonical(value)
            versions = self.exact.setdefault(key, {})
            # At most two versions suffice to mark conflict, without choosing one.
            if len(versions) < 2:
                versions[encoded] = copy.deepcopy(value)
            return
        if self.mode != "contract" or api != SOURCE or type(arguments) is not dict:
            return
        if (not set(arguments) <= {"access_token", "page_index", "page_limit"}
                or type(arguments.get("access_token")) is not str
                or not arguments["access_token"] or type(value) is not list):
            return
        for record in value:
            if (type(record) is not dict or type(record.get("song_id")) is not int
                    or record["song_id"] <= 0 or not self._bounded(record)):
                continue
            identity = record["song_id"]
            if identity not in self.fields and len(self.fields) >= self.max_records:
                self.bounds_rejected += 1
                continue
            entry = self.fields.setdefault(identity, {})
            for name in FIELDS:
                if name in record and valid_field(name, record[name]):
                    versions = entry.setdefault(name, {})
                    if len(versions) < 2:
                        versions[canonical(record[name])] = copy.deepcopy(record[name])

    def lookup(self, api, arguments, fields, context):
        fields = required_fields(fields)
        if not self._activate(context) or self.mode == "none":
            return None
        identity = target_identity(api, arguments)
        if identity is None:
            return None
        exact = self.exact.get(canonical(arguments), {})
        if len(exact) > 1:
            return None
        prior = self.fields.get(identity, {})
        if len(exact) == 1:
            value = next(iter(exact.values()))
            if all(name in value for name in fields):
                # Conflicting observed public fields invalidate even an exact hit.
                for name in fields:
                    versions = prior.get(name, {})
                    if len(versions) > 1 or versions and canonical(value[name]) not in versions:
                        return None
                return FieldRead(project(value, fields), "exact", 0)
        if (self.mode != "contract" or not set(fields) <= FIELDS
                or not all(len(prior.get(name, {})) == 1 for name in fields)):
            return None
        return FieldRead({name: copy.deepcopy(next(iter(prior[name].values())))
                          for name in fields}, "cross_api", 0)

    def read_fields(self, api, arguments, fields, context, fetch):
        fields = required_fields(fields)
        cached = self.lookup(api, arguments, fields, context)
        if cached is not None:
            return cached
        # Exceptions remain exceptions; no failed or partially projected result
        # is inserted as a successful read.
        value = fetch(api, copy.deepcopy(arguments))
        selected = project(value, fields)
        self.observe(api, arguments, value, context)
        return FieldRead(selected, "fetched", 1)
