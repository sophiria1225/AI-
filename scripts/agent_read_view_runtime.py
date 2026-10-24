"""Preserve same-program schema discovery across the explicit view boundary.

The original view channel records API discovery but returns an empty outer
new_schemas map. A model program looking in api_schemas immediately after a
successful documentation call therefore misses that discovery until the next
program. This opt-in session forwards only schemas actually exposed by those
API rows, using the same catalog and transport. Historical runtimes stay fixed.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

from persistent_read_view_python import PersistentReadViewPython, ViewControlChannel


class SchemaForwardingViewChannel:
    def __init__(self, base):
        if not isinstance(base, ViewControlChannel):
            raise ValueError('explicit_view_control_channel_required')
        self.base = base
        self.exchanges = []

    def __getattr__(self, name):
        return getattr(self.base, name)

    def exchange(self, packet):
        before = len(self.base.rows)
        reply = self.base.exchange(packet)
        names = sorted({name for row in self.base.rows[before:]
                        for name in row.get('new_tools', [])})
        if any(name not in self.catalog.visible or name not in self.catalog.catalog
               for name in names):
            raise ValueError('only_successfully_exposed_catalog_schemas_may_be_forwarded')
        schemas = {name:deepcopy(self.catalog.catalog[name]['function']) for name in names}
        reply = {**reply, 'new_schemas':schemas}
        # This is the exact JSON+newline written to the interpreter by the
        # inherited persistent loop, not a model prompt or an extra API call.
        wire = json.dumps(reply, allow_nan=False).encode()+b'\n'
        self.exchanges.append(dict(control_id=packet['id'], new_schema_names=names,
            reply_wire_bytes=len(wire), reply_wire_sha256=hashlib.sha256(wire).hexdigest(),
            extra_API_requests=0))
        return reply


class AgentReadViewPython(PersistentReadViewPython):
    """Same isolated interpreter, with discovered schemas forwarded immediately."""
    def run(self, source, observations, channel, **kwargs):
        wrapped = SchemaForwardingViewChannel(channel)
        try:
            return super().run(source, observations, wrapped, **kwargs)
        finally:
            folder = Path(kwargs['record_dir'])
            if folder.exists():
                evidence = dict(exchanges=wrapped.exchanges,
                    schema_deliveries=sum(len(e['new_schema_names']) for e in wrapped.exchanges),
                    reply_wire_bytes=sum(e['reply_wire_bytes'] for e in wrapped.exchanges),
                    extra_API_requests=0, generated_source_unchanged=True,
                    source_sha256=hashlib.sha256(source.encode()).hexdigest())
                with (folder/'schema_forwarding_private.json').open('x') as stream:
                    json.dump(evidence, stream, indent=2, allow_nan=False)
                    stream.write('\n')
