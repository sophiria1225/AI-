"""Ordinary demand filtering for the existing joined authority; no API dispatch.

Trusted callers validate model-facing arguments before this boundary. Missing
fields are a normal miss. Malformed trusted evidence and changed scope/epoch or
capability stop the shared ledger. Complete hits stay on the ordinary path.
"""
from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
import time

from appworld_native_tools import NativeCatalog
from deferred_read_obligations import Assumptions
from deferred_view_protocol import ReadAuthority
from field_read_contract import (CONTRACT_ID, FIELDS, FieldReadCache, canonical, required_fields,
                                 target_identity, valid_field)
from joined_public_read_views import (JOINED_CONTRACT_ID, JoinedPublicReadAuthority,
                                      verify_joined_implementation)
from public_api_envelope import validate_json_value
from public_contract_read_views import PublicReadAuthority
from shared_api_reservations import RequestBudget


class DemandJoinContractError(RuntimeError):
    """Sticky trusted-boundary failure; never a recoverable user-schema response."""


@dataclass(frozen=True)
class DemandLookup:
    kind: str
    fields: tuple[str, ...]
    value: dict | None
    reason: str


class DemandJoinedReadAdapter:
    """A trusted shared control component, not a model tool or a new join rule.

    The existing host still owns observations, invalidation, reservations,
    dispatch, completion and full-root materialization. `current_epoch` must be
    its actual epoch getter. Constructor verification is mandatory; a bare
    contract string from the caller is not accepted instead of the file check.
    """
    def __init__(self, provider, catalog, budget, current_epoch, *, public_source_directory):
        if type(budget) is not RequestBudget:
            raise TypeError('shared_RequestBudget_required')
        self.provider, self.catalog, self.budget = provider, catalog, budget
        self.current_epoch = current_epoch
        self.failed = False
        self.failure_reason = None
        self._busy = False
        self._calls = self._partials = self._misses = self._complete = self._failures = 0
        self._lookup_seconds = self._verification_seconds = 0.0
        self._require(type(provider) is JoinedPublicReadAuthority, 'trusted_joined_authority_required')
        self._require(type(getattr(provider, 'base', None)) is PublicReadAuthority
                      and type(provider.base.cache) is FieldReadCache, 'trusted_base_authority_required')
        self._require(isinstance(catalog, NativeCatalog), 'ordinary_public_catalog_required')
        self._require(callable(current_epoch), 'host_epoch_getter_required')
        self._scope = provider.base.scope
        self._provider = provider
        self._catalog = catalog
        self._budget = budget
        self._epoch_getter = current_epoch
        self._bounds = (provider.max_entities, provider.max_value_bytes,
                        provider.base.cache.max_records, provider.base.cache.max_value_bytes)
        began = time.perf_counter()
        try:
            verified = verify_joined_implementation(public_source_directory)
            self._require(verified == JOINED_CONTRACT_ID, 'public_implementation_verification_failed')
        except DemandJoinContractError:
            raise
        except Exception:
            self._fail('public_implementation_verification_failed')
        finally:
            self._verification_seconds += time.perf_counter() - began
        self._check_bindings()

    def _fail(self, reason):
        if not self.failed:
            self._failures += 1
            self.failure_reason = reason
        self.failed = True
        self._busy = False
        for ledger in (self.budget, getattr(self, '_budget', None)):
            if type(ledger) is RequestBudget:
                ledger.stopped = True
        raise DemandJoinContractError(self.failure_reason)

    def _require(self, condition, reason):
        if not condition:
            self._fail(reason)

    def _check_bindings(self):
        self._require(self.provider is self._provider and self.catalog is self._catalog
                      and self.budget is self._budget and self.current_epoch is self._epoch_getter,
                      'trusted_adapter_binding_changed')
        provider = self.provider
        self._require(type(provider) is JoinedPublicReadAuthority
                      and type(getattr(provider, 'base', None)) is PublicReadAuthority
                      and type(provider.base.cache) is FieldReadCache and provider.cache is provider
                      and type(provider.base.scope) is str and bool(provider.base.scope)
                      and provider.base.scope == self._scope
                      and provider.base.cache.verified_contract == CONTRACT_ID
                      and provider.base.cache.mode == 'contract', 'joined_authority_scope_or_contract_changed')
        self._require((provider.max_entities, provider.max_value_bytes,
                       provider.base.cache.max_records, provider.base.cache.max_value_bytes) == self._bounds
                      and all(type(value) is int for value in (provider.max_entities, provider.max_value_bytes,
                          provider.base.cache.max_records, provider.base.cache.max_value_bytes))
                      and 1 <= provider.max_entities <= 512 and 1 <= provider.max_value_bytes <= 65536
                      and 1 <= provider.base.cache.max_records <= 512
                      and 1 <= provider.base.cache.max_value_bytes <= 65536,
                      'joined_authority_bounds_changed')

    def _check_epoch(self, epoch, *, after_lookup=False):
        self._check_bindings()
        self._require(not self.failed, 'demand_adapter_stopped')
        self.budget._ready()
        actual = self.current_epoch()
        self._require(type(epoch) is int and epoch >= 0 and type(actual) is int and actual == epoch,
                      'host_epoch_mismatch')
        self._require(not self.failed, 'demand_adapter_stopped')
        self._require(type(self.provider.epoch) is int and self.provider.epoch == epoch
                      or not after_lookup and self.provider.epoch is None,
                      'authority_epoch_not_invalidated')
        context = self.provider.base.cache.context
        self._require(context is None or context == self.provider.base.context(epoch),
                      'base_authority_context_changed')

    def _validate_value(self, value, identity, *, complete):
        self._require(type(value) is dict and bool(value), 'authority_value_object_required')
        self._require(type(value.get('song_id')) is int and value['song_id'] == identity,
                      'authority_value_identity_changed')
        self._require(complete or set(value) <= FIELDS, 'unknown_partial_authority_field')
        self._require(not complete or FIELDS <= set(value), 'complete_authority_missing_public_fields')
        self._require(all(valid_field(field, value[field]) for field in FIELDS if field in value),
                      'malformed_public_authority_field')
        try:
            validate_json_value(value)
        except Exception:
            self._fail('authority_not_plain_bounded_JSON')

    def lookup_fields(self, action, fields, epoch):
        """Return a copied partial value, a normal miss, or an ordinary-path directive.

        This method never calls a backend, observes a returned value, synthesizes
        a complete response, changes epoch, or consumes/reserves API capacity.
        """
        began = time.perf_counter()
        self._calls += 1
        try:
            self._require(not self.failed and not self._busy, 'stopped_or_reentrant_demand_adapter')
            self._busy = True
            self._check_epoch(epoch)
            demand = required_fields(fields)
            self._require(set(demand) <= FIELDS, 'unsupported_trusted_field_demand')
            self._require(type(action) is dict and set(action) == {'app', 'api', 'args'}
                          and type(action['app']) is str and type(action['api']) is str
                          and type(action['args']) is dict, 'ordinary_action_shape_required')
            action = deepcopy(action)
            identity = target_identity(action['app'] + '__' + action['api'], action['args'])
            self._require(identity is not None, 'joined_target_identity_required')
            try:
                decoded = self.catalog.decode(dict(name=action['app'] + '__' + action['api'],
                    arguments=json.dumps(action['args'], allow_nan=False)))
            except Exception:
                self._fail('ordinary_public_capability_or_schema_rejected')
            self._require(canonical(decoded) == canonical(action), 'ordinary_decoded_action_changed')
            self._check_epoch(epoch)
            found = self.provider.lookup(action, epoch)
            self._check_epoch(epoch, after_lookup=True)
            if found is None:
                self._misses += 1
                return DemandLookup('miss', demand, None, 'no_observed_authority')
            self._require(type(found) is tuple and len(found) == 2
                          and found[0] in ('partial', 'complete'), 'malformed_authority_lookup')
            kind, value = found
            self._validate_value(value, identity, complete=kind == 'complete')
            if kind == 'complete':
                # An adapter must not turn a forged complete label or partial
                # value into a bypass of the common complete-response cache.
                original = self.provider.base.lookup(action, epoch)
                self._check_epoch(epoch, after_lookup=True)
                self._require(type(original) is tuple and len(original) == 2 and original[0] == 'complete'
                              and canonical(original[1]) == canonical(value),
                              'complete_authority_not_bound_to_ordinary_cache')
                self._complete += 1
                return DemandLookup('complete', demand, None, 'ordinary_complete_cache_path')
            grant = self.provider.grant(action, epoch)
            self._check_epoch(epoch, after_lookup=True)
            self._require(type(grant) is ReadAuthority and type(grant.epoch) is int and grant.epoch == epoch
                          and type(grant.assumptions) is Assumptions
                          and all(getattr(grant.assumptions, name) is True for name in (
                              'pure_total_read', 'partial_matches_snapshot', 'all_changes_intercepted')),
                          'trusted_joined_grant_required')
            self._validate_value(grant.partial, identity, complete=False)
            self._require(canonical(grant.partial) == canonical(value), 'lookup_and_grant_disagree')
            if not set(demand) <= set(value):
                self._misses += 1
                return DemandLookup('miss', demand, None, 'required_fields_not_observed')
            self._partials += 1
            return DemandLookup('partial', demand, {field: deepcopy(value[field]) for field in demand},
                                'observed_required_fields')
        except DemandJoinContractError:
            raise
        except Exception:
            self._fail('trusted_demand_lookup_failed')
        finally:
            self._busy = False
            self._lookup_seconds += time.perf_counter() - began

    def summary(self):
        return dict(contract=JOINED_CONTRACT_ID, lookup_calls=self._calls,
            partial_hits=self._partials, normal_misses=self._misses, ordinary_complete_routes=self._complete,
            fatal_failures=self._failures, stopped=self.failed, failure_reason=self.failure_reason,
            lookup_wall_seconds=self._lookup_seconds, verification_wall_seconds=self._verification_seconds,
            scope_sha256=hashlib.sha256(self._scope.encode()).hexdigest(),
            additional_environment_API_requests=0, additional_model_calls=0,
            complete_values_returned_by_adapter=0, novel_method_claim=False)
