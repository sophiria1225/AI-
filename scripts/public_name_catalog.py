"""Opt-in ordinary Python access to exact names in the fixed public catalog.

AppWorld's ApiCollection binds permitted public API names when it is loaded;
reading documentation is not a prerequisite to invoking a known name. The
legacy harness additionally gates calls on documentation visibility. Keep that
historical policy unchanged and offer this separate comparator for Python RPC.

This changes admission, not credentials, tool definitions shown to the model,
argument values, API budgets, execution, completion, or uncertain-effect rules.
No implicit documentation request, argument repair, or retry is performed.
"""
from appworld_native_tools import NativeCatalog


class PublicNameCatalog(NativeCatalog):
    def __init__(self, public_tools):
        super().__init__(public_tools, enable_compute=False)

    def decode(self, function, visible=None):
        # A supplied schema snapshot denotes native function calling; preserve
        # its historical contract even if this catalog is passed accidentally.
        allowed = set(self.catalog) if visible is None else visible
        return super().decode(function, visible=allowed)
