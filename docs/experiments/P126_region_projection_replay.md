# P126: finite saved-prefix region replay preparation

This prepares a bounded offline diagnostic. No experiment is launched by this
document or module import. The parent must finish source review and synthetic
tests, commit the implementation, bind the private input manifest and launch
the replay separately. Saved generated programs may run only through the
existing network-free, read-only, unmounted Docker interpreter. The host reads
JSON, hashes and ASTs; it never executes saved program text.

The fixed set is the two closed P125 CSV traces, each with 12 original programs,
replayed once under each new policy: `explicit_joined_fields` and
`automatic_region_joined_fields`. This is at most 48 program attempts and four
owned containers. Total time is bounded to 1800 seconds, each program to 30
seconds, with a 120-second cleanup reserve. A mismatch stops without retry or
replacement; all 48 planned slots remain visible, with null measurements for
unperformed or incompletely recorded work. All task API, model, tokenizer and
evaluator calls are zero. Simulated saved-response counts are a separate metric.

The manifest binds the local import closure of replay and synthetic-test source
dependencies, the Docker image configuration and this protocol. Unrelated P127
online driver/reporting changes are outside that closure. It also binds all original program and control records,
public API schemas, the prior closed P125 audit, the 146-source AST-only
coverage report and a separate passing synthetic contract-test report. The
loader checks each original input against its outer action, each inner receipt
against its exact ordinary control action, continuous control identities,
sent flags, known effects, typed status and unique nonce, schema maps, exact
stdout/error and dispatch counts. Program files and events/spans must match
the original closed audit's recorded hashes. Empty original observations are
required, so omitted full responses cannot reenter through replay inputs.

P125 wire records wrap ordinary calls and reports in `__harness_views__` control
packets. Reports are never treated as API replies. Previously rendered
public-schema feedback on a rejected call is preserved byte-for-byte in the
error payload and is not decorated a second time. Known typed invocation
exceptions remain exceptions; an unknown effect is not replayable. Neither
catalog rejection nor a saved missing reply becomes a successful partial hit.

The sole allowed call without an inner receipt is the last logical call of
original program 12. Its original public budget rejection, exact action hash,
trace, program ordinal and logical index are fixed before execution. The new
host intercepts that exact position before provider lookup, complete cache,
reservation or backend simulation. An earlier occurrence of the same action
is processed normally. The final source must have no exception-handler or
context-manager blocks that could intercept this stop. No unobserved reply is
created and no unknown suffix is executed. The interpreter receives a fixed
frontier exception, emits its trusted error/segment report, and closes without
materializing a final root snapshot.

A partial hit is generated only from the host provider's actual prior observed
saved backend responses. The saved full reply for that logical action is then
used solely to check the selected fields. Skipped full replies never enter the
provider, full cache, API receipts or request budget. The action tape consumes
each logical call exactly once, whether it uses a saved response, an ordinary
complete-cache hit, a validated partial hit or the fixed frontier. This also
checks the dependency loss when a skipped full response would otherwise have
seeded a later full-cache hit.

Programs 1–11 compare exact original status/stdout/error and the plain namespace
and real-dict root fingerprints between the two new policies at normal Python
boundaries, including ordinary exception boundaries. The `normal_prefix_boundary`
label denotes a regular boundary of the original path and does not imply normal
termination: original and actual execution statuses are retained explicitly.
The equivalence flag is true only after the paired boundary and all observable
checks pass. Unsupported object names
are retained privately; their internals are not compared. Program 12 compares
only the observed action sequence, matched field values and stdout prefix to
the fixed frontier. No final-root equivalence or completed-task claim applies
there. Automatic partial use followed by this deliberately inserted frontier
can trigger the real runtime's sticky stop; it is recorded explicitly as a
fixture-frontier termination, not evidence of a real task contract failure.

The assembled transformed artifact is review-only. The region runtime's actual
per-segment choice/completion/hash trace is retained separately; it is not
mislabelled as execution of one transformed whole-source artifact. Neither
logical actions nor API/wire byte reductions establish total-token savings,
quality preservation, task completion or novelty. Explicit joined fields are
a shared ordinary control. A handwritten explicit-field synthetic control is
tested separately; original generated sources are not rewritten to use it.

`--prepare-only` requires `--coverage` and `--synthetic-evidence`, and exclusively
creates the private manifest. The latter must report status `pass`, positive
integer `tests_run`, zero `failures`/`errors`, and current relative source hashes
for the compiler/runtime/adapter/provider and their synthetic tests. Execution
requires an existing unchanged manifest and a new `--output` directory. The
private summary retains all slots and publishable aggregate counts/hashes;
raw task values, identifiers, generated code, prompts and reasoning are absent.
Publication to `reports/P126_region_projection_replay.json` remains a separate
parent-controlled step after independent review.
