# Region field projection: bounded prototype

Status: synthetic implementation only. This document is not an experimental
plan, activation, or token-reduction result. Frozen P124/P125 sources and the
experiment registry are unchanged. No saved generated program has been executed
to develop or validate this prototype.

## Purpose and boundary

P125 closed with zero static eligible programs, transformations, partial hits,
or ordinary complete-cache hits. Both policies had 3/4 final successes and
766,875 logical tokens. Its negative result remains unchanged. A subsequent
read-only diagnosis found that a dynamic missing-ID list and ordinary JSON and
collection handling prevented the old whole-program recognizer from reaching
an otherwise supported title/artist-name consumer. The existing library-only
provider had no required-field coverage for those requests. An existing ordinary
join provider had 13 candidate title-plus-artists opportunities; these are
coverage observations, not measured savings and not new join research.

This prototype tests one narrower implementation question: can a top-level
dynamic list/tuple loop use the existing field-demand recognizer after its
ordinary prefix has run, while preserving normal-path stdout and ordinary
public boundary values? Source coverage, provider validity, and online cost
benefit remain separate checks. Novelty is not established.

## Interface and source evidence

The new module is `scripts/region_field_projection.py`. It imports the frozen
`automatic_field_projection` consumer recognizer, field validator, and runtime;
it does not modify them.

- `plan_region_projection(source)` returns a `RegionPlan` with the original
  `source`, `source_sha256`, `eligible`, `reason`, `sites`, and ordered `segments`.
- `RegionProjectionRuntime(fetch_full, lookup_fields, stop)` has the same trusted
  callback constructor as the old runtime. It adds region/segment evidence.
- `execute_region_projection(plan, scope, runtime)` is an interpreter-side entry.
  The source must be executed inside the isolated interpreter in any future
  integration, never by the host process.

The planner retains the exact original source. Each segment has its original
AST-rendered source and hash plus a proposed transformed source and hash. The
plan's `transformed_source` and `transformed_sha256` are a deterministic assembled
inspection artifact, **not the bytes of one executed program**. The executor
replans and verifies all plan fields before use, and records the hash actually
selected for every segment. It reports `transformed`, `reason`, `hits`,
`regions`, and `segments`; each region includes `admitted`, `reason`,
`original_sha256`, and `executed_sha256`. Evidence retained on the runtime also
covers a segment that raises. Original tracebacks, source-line positions, and
object identities are not claimed equivalent.
Plan fingerprints use a restricted, length-delimited plain-value encoding;
planning and hash comparison do not call the mutable JSON encoder before its
integrity guard.

## Limited accepted program

Parsing is bounded to 20,000 characters, 6,000 AST nodes, and depth 80. The
explicit syntax allowlist rejects unknown syntax. In particular, functions,
classes, try/with, reflection, identity tests, callback arguments, aliases of
runtime capabilities, `from`/future imports, and docstring-like string statements
are outside this prototype. A whole-source `compile` validation runs before any
effect; all original and transformed segment alternatives are also compiled
before the first segment. This prevents a suffix syntax error from executing a
prefix that the original whole program would never execute.

The ordinary prefix/suffix may contain allowlisted builtin collection
operations, constant-target `call_api`, `import json`, canonical JSON formatting,
and literal or plain-string `join`. Their source is not rewritten into a second
program run. The candidate itself is a top-level `for` over a named value, with
the frozen recognizer's `show_song` call and scalar/artist-name consumers. It has
no root escape, arbitrary callback, early exit, identity observation, or whole
artists-value disclosure. The source must first pass the allowlist; successful
recognition alone does not authorize partial reuse.

## Runtime entry guard and execution

The executor requires the captured trusted `call_api`, builtin namespace and
canonical JSON module/class/default-instance state. Active tracing/profiling,
additional threads, reserved helper names, and non-plain referenced or overwritten
global bindings cause ordinary fallback. Initial failure executes the exact
original source once without transformation.

After an ordinary prefix executes once, each region rechecks these conditions
and checks its actual values:

- The iterable is an exact builtin `list` or `tuple`, length at most 512, with
  exact positive integers. Empty and singleton iterables are allowed.
- Destinations are exact plain builtin `dict`/`set` values; they may already
  contain ordinary values. Subclasses, cycles, and custom objects are rejected.
- Root and loop-item bindings, if already present, are plain. Iterable,
  destination, root, and item aliases that could invalidate the transformation
  are rejected conservatively.

A failed region guard executes that region's original loop once **at the same
position**, then continues its suffix. It never restarts the prefix or the whole
program. Other admitted regions in the same program may still be transformed.
Internal helper bindings exist only during a transformed region and are removed
before the next segment.

For intermediate iterations, a valid observed-field lookup may supply private
consumer values; a miss performs the ordinary full call. A partial hit does not
manufacture a successful full response, normal receipt, or complete-cache entry.
The final actual iterable position always performs the ordinary full call at its
original position. Thus an empty loop preserves absent/present old root/item
bindings, and a completed nonempty loop leaves the real final full dictionary.
Repeated IDs do not change which position is final.

The provider's pure-read, task-isolation, snapshot/epoch, and value-validation
contracts remain prerequisites. This compiler supplies none of those proofs and
adds no ID guard. Value availability must be checked at the lookup time, not
injected from future saved responses. An ordinary complete cache belongs in both
comparison arms. Skipping a full response changes later cache contents; saved
calls across successive programs cannot be added independently.

## Failure semantics and exclusions

Before the current program has a partial hit, ordinary API/Python failures retain
the ordinary error path. After a partial hit, any loop or suffix exception stops
the projection capability through the trusted `stop` callback and is re-raised.
There is no full fetch after an exception to fabricate an earlier root state, and
the same cell must not resume. Failure states and exception equivalence are not
covered by the normal-path claim. Later independent cells or tasks require the
experiment driver's explicit failure policy.

This is not a general Python optimizer or a transparent deferred proxy. It does
not preserve traceback locations, frame/trace inspection, allocation timing,
signals or concurrent execution, arbitrary object identity, or custom callback
behavior. Unsupported programs use the ordinary source. The new compiler alone
does not establish that the closed task's actual source passes its static or
runtime guards, that joined fields survive every write barrier, or that total
job tokens decline while final success is preserved.

The Python standard library and the trusted compiler/runtime implementation are
assumed intact. Arbitrary hostile mutation of those modules by earlier cells is
outside this prototype; for example, replacing `ast.parse` changes the planner
before its source guards. This is not a security sandbox or a tamperproof
interpreter. The explicit builtin and JSON integrity checks cover the added
supported operations and selected mistakes, not all possible process mutations.
This assumption does not relax the separate host/wire boundaries, API request
validation, paid accounting, or observed-field authority requirements.

## Synthetic validation

`python3.12 -m unittest discover -s tests -p test_region_field_projection.py`
passes 22 handwritten synthetic tests. They cover dynamic and nonempty
destinations, stdout/full-root equality, empty/singleton/duplicate/tuple inputs,
prefix-once fallback, multiple regions, domain/alias/custom-object rejection,
ordinary complete caches on both sides, missing and invalid lookup values,
final-read/body/suffix failures, sticky stop, bounded parsing, compile-before-
effects, plan tampering, canonical JSON bindings, JSON-independent plan
hashing, and callback-free builtin-integrity rejection. The synthetic mock backend
uses in-memory fixtures; these counts are not online API or token savings.

Independent synthetic review is recorded separately. Integration, any actual
closed-source applicability gate, fixed replay, and a new finite online
comparison require separate review. This prototype creates no run or new
experimental result.
