# Ordinary receipt disclosure: isolated synthetic prototype

This is a preparation artifact, not an experiment, adoption decision, or new
mechanism claim. No worker, inference driver, experiment plan, result collector,
research registry, existing source file, or running P125 condition is changed.
The prototype is based on commit `d79c7286dcabeba285218fa744d4c5f5c8f7519c`.

The purpose is to prepare an ordinary control for a future comparison: make the
already archived API receipt index available by an explicit archive read instead
of repeating every row in every model input. Actual model token use, expansion
frequency, API budget effects, whole-job cost, and final quality remain unmeasured.

## Interface and exact transformation

`scripts/receipt_disclosure_history.py` provides
`ReceiptDisclosureConversation(system_prompt, task, execution_scope=..., mode=...)`.
The trusted host fixes `mode` (`full` or `disclose`), execution scope, and page
limit at construction. Both modes append the same `SHARED_GUIDE` to the system
instructions and retain the same complete reasoning and archival messages.

`append_recorded(response, spans, events=..., archive_spans=..., pending_reads=0)`
accepts the closed turn's actual host records. The archive mapping must contain
exactly the inner and outer records named by that turn's events. It is not a
model tool and does not accept an eligibility flag. Ordinary `append` without
these records is supported only as an unchanged, full-display fallback.

Only the outer `run_python` observation's `api_receipts` field can change:

```json
{"format":"archived_receipt_index_v1","span_id":"outer-source-span","receipt_rows":4}
```

The original compact table, including each ID, API name, Boolean request flag,
and row order, remains in `archive()` and `messages()`. `for_model()` derives a
copy and applies the existing canonical protocol-reference renderer. Assistant
content, code arguments, returned reasoning, stdout, errors, API counts,
completion flags, and other observation fields are not changed. The code never
parses or replaces JSON embedded in stdout, API values, or archive-read text.

The reference is used from the first display of an eligible closed turn. There
is no initial full display that is later rewritten. Appending turns therefore
does not change the earlier normalized prefix. An ordinary explicit `read_span`
response is a new, literal turn and never replaces the old reference in place.

## Deliberately limited eligibility

Every eligible turn must satisfy all of the following:

- Exactly one native `run_python` call with the ordinary `code` and `span_ids`
  argument shape. This prototype does not handle multi-call or mixed batches.
- Exactly the currently supported outer observation fields, explicit normal
  Boolean flags, `status == "ok"`, text stdout, `error is None`, and an integer
  API request count. Unknown or missing fields fall back to the full display.
- A strict existing compact receipt table, all inner records linked exactly
  once and in event order, matching API names/request flags, and matching counts.
- No pending reads or unknown effects. Every recorded inner API row must report
  an actual sent request and a returned transport execution, without retries.
  A caught API exception still disqualifies a turn whose Python status is `ok`.
- The unchanged raw outer archive and its ordinary reconstructed conversation
  span must both fit the fixed page limit. Paged source records remain full and
  use the unchanged ordinary paging path. Both corresponding spans after the
  proposed replacement must also fit; fewer UTF-8 bytes need not mean fewer
  characters, so a replacement that would introduce paging is rejected.
- The reference must be strictly shorter in compact UTF-8 bytes than the table.
  This is a deterministic representation rule, not token counting or a tuned
  empirical threshold.

No API rows, all-local computation, unsent/rejected operations, missing execution
evidence, raised/unknown execution status, retry receipts, truncated stdout,
errors, invalid arguments, unknown shapes, no-tool turns, and `read_span` turns
retain their ordinary representation. Missing evidence is a full fallback;
contradictory source identities or counts are rejected before appending anything.
This does not repair an error or label a rejected operation successful.

The pre-existing `receipt_reasoning_history.execution_evidence` is reused only
for host execution checks on a temporary copy whose compact table has been
decoded. Its reasoning-removal `project` function is not used. Transport return
is not proof of semantic API success, correct data, or task completion.

## Trusted evidence boundary and archive identity

Each append stores an owned, serialized source snapshot plus a frozen descriptor
binding the source digest and exact message segment. The snapshot includes the
host execution scope and hash of the initial instructions/task. Every rendering
rechecks these bindings against the unchanged raw messages and archive and
rederives eligibility. Recorded segments must cover the complete message suffix
continuously, and source archive keys must equal the complete archive key set;
unbound extra messages or archive records are rejected. `sidecar()` returns only hashes, counts, reasons, and
decisions; it contains no source text or task values and cannot be supplied back
as a success assertion. Caller mutations to inputs, rendered copies, returned
archives, or returned sidecars cannot modify the owned source.

The serialized source preserves original object member order and has a byte SHA.
Each raw span also has a SHA of its original `compact(row)` text; both the loaded
source span and the current archive must reproduce it. Canonical semantic hashes
and dictionary equality alone cannot protect character paging offsets when
object members are reordered. `archive()` retains the original member order.

This detects tested accidental or inconsistent source changes. SHA-256 does not
authenticate a malicious host that can replace the entire source and all hashes.
The future worker must obtain the records from its existing trusted recorder,
give every run a unique execution scope, and save the raw records and sidecar.
No authenticated persistence/load protocol or integrated offline auditor is
provided here. A source-binding exception leaves this conversation unchanged;
the host remains responsible for preserving its original execution records.

## Existing archive access and ordinary cache behavior

No new tool or tool schema is introduced. Existing
`context_preservation.page_span` reads the unchanged raw span with the same
**character offsets**, total length, text, and continuation offset. The model can
read the referenced outer span to obtain the table, then read an inner span. The
existing `native_data_compute.selected_receipts` still yields full original
observations when a subsequent `run_python(span_ids=...)` names the outer span.
Canonicalization changes only protocol call IDs; the archive reference uses the
original outer span ID and remains resolvable.

The complete-cache path was checked directly in the frozen source:

- `OrdinaryCompleteReadCache._send` in `ordinary_complete_read_cache.py` returns
  a copied value on a hit and writes `ordinary_cache_events`; it does not call
  the underlying channel and does not synthesize an unsent API receipt.
- `DeferredReadHost._send` in `deferred_view_protocol.py` forwards new channel
  rows through `host.on_record`. `ViewControlChannel` connects that callback to
  `code_agent_interface.execute_response`'s `inner_record`, which creates the
  visible receipt index rows.
- `AutomaticProjectionHost._lookup` likewise records projection controls without
  synthesizing an inner API receipt. Private control rows are not forwarded by
  `OnlineProjectionProgram` as visible API index rows.

Thus an ordinary complete-cache hit contributes **zero receipt rows**, not an
unsent row. The synthetic unsent tests represent actual unsent recorder rows,
such as a rejected operation; they do not simulate a cache hit. A turn combining
normal actual API calls with complete-cache hits can be eligible because only
the actual recorded API rows enter this evidence check. An all-cache-hit turn
has an empty index and remains full. This corrects an earlier preparation
message that incorrectly equated a cache hit with an unsent index row.

## Rolling history and costs

Synthetic tests use the existing `RollingCheckpoint('separate')` to bind an
ordinary prefix, install a handwritten summary, append a later closed turn, and
check that the prefix and new suffix remain valid. The supplied numeric token
counts in that test are fixture inputs; no tokenizer or model is called. This
is a structural compatibility test, not evidence that actual checkpoint timing,
summary quality, or whole-job behavior would match between receipt modes.

The prototype does not alter dynamic API budget notices or resource limits.
They are attached by existing inference code outside this conversation class.
Their values can still differ between execution policies. Future comparisons
must retain the same ordinary complete cache, budget notices, receipt guide,
and rolling policy on both sides and include the actual notice bytes/tokens.
Receipt references still expose their outer span ID and row count, so the
transformation does not make the two execution policies' model inputs identical.

Expanding a reference must take the existing explicit tool action and subsequent
model input/output, not a free host retrieval injected into old history. Such
actions, new context, checkpoint calls, failed attempts, unknown usage, host
validation time, and setup/cleanup must remain in whole-job accounting. This
module supplies neither usage accounting nor an expansion scheduler. Its byte
statistic is only the difference in receipt-index UTF-8 bytes in one rendering;
it is not cumulative model exposure, API savings, token savings, or measured time.
Repeated hashing/revalidation also has a host cost that is currently unmeasured.

## Synthetic verification and remaining work

Run only the new synthetic suite with:

```sh
python3.12 -m unittest discover -s tests -p 'test_receipt_disclosure_history.py' -v
```

The fixtures are handwritten and no saved generated program is executed. Tests
cover shared instructions, the exact allowed field change, native pairing,
canonical-reference resolution, raw archive paging offsets, full-value selection,
explicit expansion, all documented fallbacks, atomic source rejection, fake
success assertions, copy ownership, tampered evidence/history/configuration,
cross-scope evidence reuse, nonshrinking references, and rolling prefix stability.

This prototype is not wired to a worker, inference adapter, accounting path,
frozen-source manifest, plan/predecessor gate, checkpoint trace auditor, or result
builder. It makes no experiment calls and does not inspect P125 interim results.
Integration, independent review, a finite preregistered comparison, actual usage
measurement, and unchanged-quality evaluation remain separate decisions after
P125 closes. No conclusion about P125's outcome or the adequacy of this ordinary
control follows from these tests.
