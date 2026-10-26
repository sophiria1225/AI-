# Ordinary demand adapter for the existing joined authority

This module prepares a common control component. It introduces no new join rule,
purity inference, API capability, experiment result or novelty claim. Frozen
existing files are unchanged. Only handwritten synthetic fixtures were executed;
no backend, model, evaluator or saved generated program is invoked by the adapter.

`DemandJoinedReadAdapter(provider, catalog, budget, current_epoch,
public_source_directory=...)` requires the actual existing
`JoinedPublicReadAuthority`, an ordinary public catalog, the shared `RequestBudget`
and the host's epoch getter. Construction calls the existing
`verify_joined_implementation` on the public source directory; a caller-supplied
contract label cannot replace that check. The check pins the existing API/model
source hashes. It does not independently prove every ORM/runtime behavior,
authorization state, isolation assumption, or absence of external mutation.

`lookup_fields(action, fields, epoch)` returns a frozen `DemandLookup` with
`kind`, `fields`, `value` and `reason`:

- `partial`: `value` contains independent copies of exactly the requested fields.
- `miss`: `value` is `None`; the caller follows its normal complete-read path.
  No authority, a valid partial missing a requested field, and the existing
  authority's conflict-as-no-authority decision remain normal misses.
- `complete`: `value` is `None`; the caller uses its shared ordinary call/cache
  path. The adapter does not independently return or install a complete value.

The existing authority's lookup has no field-demand parameter and can return a
title-only partial. The previous automatic runtime expected every partial grant
to contain all five original contract fields. This small adapter separates normal
missing demand from contradictory trusted evidence, so a valid title-only partial
does not itself become a fatal contract error when artists are also requested.

The trusted boundary checks supported positive identity, exact ordinary action
shape, catalog admission and decoded-action equality, fixed execution scope,
host/provider/base-cache epoch consistency, unchanged shared objects and bounds,
plain typed returned fields, and lookup/grant agreement. Artist list order comes
unchanged from the existing authority. That authority joins only a playlist's
ordered Song artist IDs with already observed names; it does not guess order from
an album child's artist IDs. Its conflict and bounded-storage behavior is retained.

For partial results a typed same-epoch `ReadAuthority` must reproduce the lookup
value and retain all three explicit assumptions. A complete label must match the
existing underlying complete cache. Invalid trusted demands, unsupported target
identity, missing capability, malformed fields, changed scope/epoch, inconsistent
grants, source-verification failure and reentrancy cause `DemandJoinContractError`.
The first such failure is sticky and stops the original shared API ledger. Later
lookups do not recover silently. Fatal messages contain fixed labels, not argument
or result values.

The adapter checks ledger readiness but reserves, spends and cancels no API
capacity. A reuse does not require an unused slot if the existing ledger is ready.
It does not bypass an already stopped ledger. `summary()` records lookup counts,
normal misses, partial hits, ordinary-complete routes, failures, source-verification
time and lookup time without task values. These are host costs, not measured token
savings. An integration must include them within whole-job accounting.

The host still owns capability/schema input handling, observations, invalidation,
pending-read barriers, completion, source provenance, dispatch/receipt recording,
and full-root boundary/exception behavior. A normal explicit field-read schema
error must be handled recoverably **before** calling this trusted adapter. Explicit
field requests return requested field dictionaries; they do not assert the
original ordinary API's full-root semantics. Automatic consumers separately need
their own region admission and boundary proof.

Use the same adapter, authority, source acquisition, ordinary complete cache,
explicit field capability and guide in both conditions of any future comparison.
Giving only one condition the joined sources would mix source coverage with
automatic admission. The closed-prefix 13-candidate diagnosis is an opportunity
count for an existing ordinary component; it establishes no API saving, quality
preservation or total-token reduction in a new trajectory.

The new synthetic suite covers normal partial misses, copied demanded fields and
playlist order, exact-cache routing, existing conflict misses, capability failure,
invalid trusted inputs, malformed/changed grants and values, sticky failure,
scope/epoch/barrier changes, shared-binding tampering, empty capacity and reentrancy.
The constructor verifier is mocked only in those synthetic fixtures, with success
and failure cases. No live worker or experiment is launched by this module or test.
