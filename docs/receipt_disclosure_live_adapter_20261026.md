# Ordinary receipt disclosure: live adapter and shared rolling boundary

This is P128 preparation, not an outcome or novelty claim. Full and disclose use
one exact `ReceiptDisclosureLiveConversation` type, identical instructions,
trusted recorder validation, retained raw archives and `rolling_separate`.
Existing frozen P127 modules remain unchanged. The original prototype and its
eligibility/character-offset rules remain the basis of the display transform.

`append_closed_turn(response, outer_spans, call_id=..., events=..., spans=...,
pending_reads=0)` accepts cumulative host recorder events and spans through this
closed actor turn. It checks the unchanged prior event text, original span text
and insertion order, and exactly one new call suffix. All inner and outer rows
must be present once in recorder order. Ordinary `append` and `append_recorded`
are forbidden on the live class so missing integration cannot silently disable
both conditions. A contradictory source rejects the append atomically and
latches a contract failure; the worker retains already paid usage and raw records
and does not retry actions. Unsupported normal turns retain their full display.

`disclosure_snapshot()` rederives the display and includes deterministic hashes,
per-turn decisions, counts and source scope. It has no fetched values or model
eligibility assertion. The worker saves it privately beside original events,
spans and conversation. `rebuild_disclosure_conversation` applies the same
trusted boundary to supplied original turn records; no generated source executes.
A saved snapshot is compared only after reconstruction. It is not authority for
its own eligibility. `disclosure_summary()` exposes counts, the snapshot hash,
and contract status. After a contract failure only the last verified snapshot
is available, explicitly incomplete; absent measurements remain null.

The new `ReceiptDisclosureRollingInference` copies the frozen rolling controller
under a new module name and requires this exact live class and matching receipt
mode/page configuration. It admits only `rolling_separate`. Normalized model
history is the deterministic receipt display; the raw conversation remains
separate. All existing rolling count/admission/summary/usage records remain.
The additional `receipt_disclosure_inference_views.json` records one entry per
agent projection, with the next call ID, raw/normalized history hashes, snapshot
hash and closed/disclosed turn counts. A summary that fails before an agent
projection does not fabricate an agent projection entry. Both roles share the
same finite model-call/token ledger and work clock.

A reference is visible from the first eligible display, never a later rewrite
of an already-bound prefix. Explicit read_span results are new literal turns.
Original raw archive pages retain JSON member order and character offsets,
including Unicode. The adapter does not expand references automatically, remove
ordinary archive access, or synthesize API rows for complete-cache/partial hits.
All-cache turns have an empty receipt index and remain full. Unknown/raised,
unsent, paged and mixed turns follow the prototype full fallback. Runtime API
receipts, cache/field authority and API budgets remain separately audited.

The byte count describes one display of the closed receipt indexes, not tokens,
cumulative model exposure or net savings. Explicit read_span actions consume
normal subsequent agent input/output and time despite making no environment API
request. Existing run_python selection of prior full receipts is also retained.
Rolling trigger timing, summary count/quality and final task behavior can differ
between modes; the synthetic tests do not establish empirical equivalence.
Snapshot hashing/validation cost is inside the worker work clock. The live
adapter is a trusted host contract, not an authentication scheme against a
malicious host able to replace original records and all hashes.

New synthetic tests cover cumulative-prefix tampering, extra/missing/future
records, atomic sticky stops, exact class/config admission, raw Unicode paging,
paid expansion as a new turn, complete-cache empty indexes, full fallbacks,
reconstruction and per-agent snapshot identity. Mock transport/count fixtures
exercise the actual rolling inference admission, accepted/rejected summaries,
unknown-summary stopping and call-budget screening. Fixture token counts are
handwritten, not tokenizer measurements. No model/API/evaluator/tokenizer/Docker
or saved generated program is invoked by these tests. Worker/auditor integration
and the frozen P128 experiment remain separate validation stages.
