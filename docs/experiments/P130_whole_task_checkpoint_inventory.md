# P130: accepted-checkpoint runtime inventory utility

## Question and scope

P127's closed CSV traces retained fetched metadata in a persistent Python binding,
but later checkpointed actor inputs omitted that binding name. The final writer
constructed a new literal mapping rather than reading the retained metadata.
This supports a testable retrieval hypothesis; it does not establish the cause of
the official task failure. P130 asks whether a small runtime inventory following
an accepted history checkpoint improves whole-task efficiency with preserved
official success. Ordinary variable inventories have already been studied in
P33 and overlap prior systems such as CaveAgent. This cohort establishes neither
a new mechanism nor superiority of one inventory timing over another.

The hypothesis and four conditions were chosen from closed P127 evidence before
reading P128 or P129 outcomes. During operational monitoring on 2026-10-26 at
19:17 JST, the root agent displayed the first three P128 rows, including their
outcomes and usage. This disclosure is recorded; those observations do not alter
P130's task, modes, seeds, controls, budgets or decision rule. No P129 outcomes
are used to select conditions. No reserved unseen scenarios are read.

## Fixed comparison

One known development CSV task, `P29_04_CODE`, is run in four independent task
instances: `off` then `checkpoint_inventory` with model seed 57, and
`checkpoint_inventory` then `off` with model seed 157. World seed is 42. There is
one independent task and two repetitions, not four independent tasks.

Both arms use the pinned MiniMax-M3 IQ4_XS model/runtime, the same native tool
transport, common guide, `explicit_joined_fields`, ordinary complete cache,
full compact receipts, hidden wall-clock budget display, `rolling_separate`
checkpoint policy and `output_grounding_policy=feedback`. Automatic region
projection and automatic output repair are disabled. Public evidence can block
a contradicted write in both arms; unknown evidence passes unchanged. Delete
operations are not rewritten or blocked by this monitor.

Both arms capture the same bounded namespace inventory only after an accepted
checkpoint revision, outside model-generated code. The inventory lists eligible
top-level binding names, exact built-in types and built-in container lengths.
It does not include values, scalar/string lengths, custom type names or object
representations, and invokes no custom inspection/length/representation methods.
Capture bounds and filtering are fixed in `checkpoint_runtime_inventory.py`.

Only the inventory arm appends the pending notice to the existing first system
message for the next actor request. The exact count and dispatch messages match.
Actual dispatch consumes exposure once; a count-only/admission-rejected attempt
does not count as exposure. The raw conversation, original programs, archived
outputs and focus/summary input are unchanged by this transient notice. A rejected
or unknown summary does not trigger a capture. Capture requests, replies, byte
counts, hashes and host time are recorded in both arms, including failures.

## Budgets and launch order

Each cell allows 80 shared actor/focus model calls, 450,000 logical tokens,
1,800 work seconds and 120 actual environment API requests. Across four cells
the limits are 320 calls, 1,800,000 tokens, 480 API requests and four evaluations.
At most three accepted checkpoint opportunities per cell are available, with
the common 16,384-token trigger, two recent turns and three fresh turns.

The owned model server has a finite 14,400-second lease. It may launch only if
the entire lease fits before 2026-10-27 06:00 JST, hence no later than 02:00 JST.
It waits for P129's all-six-slot collection and owned-server closure, independent
of P129's performance. There is no automatic repeat or extension of this cohort.
Explicit user stop interrupts running and queued work; ordinary user messages
are not stop signals.

Before generation, bind source hashes and the fixed plan, pass both push and PR
`accounting-and-syntax` checks on the exact source head, and validate four initial
input counts plus two text-only summary-transport counts. Initial actor inputs
must match within each seed. Preflight does not generate or evaluate tasks.

## Accounting and decision

The primary cost is every actual logical input plus output token from task start,
including summaries, feedback, notices, retries within a task and failed actions.
Cached prompt tokens are still logical input tokens. Unknown usage remains
unknown. API requests, capture and verification costs, wire bytes, full cell and
server time are reported separately. Official evaluation is external to the
actor, and no evaluation outcome reaches its conversation.

The development gate requires all four slots evaluated with known usage and no
audit errors; no baseline success lost in either seed; lower aggregate whole-job
tokens and lower tokens on the common-success pairs; at least one actual notice
exposure on a common-success inventory run; and complete inventory/grounding
accounting with intact inventory, grounding and projection contracts. A cheap
failure cannot compensate for a more expensive common success. Quality gains
are reported separately and cannot replace the common-success comparison.
Per-seed costs remain visible; lower cost in each seed is not an additional gate.

All planned slots, failures, unknowns and missing runs are retained. Results from
P33, P127, P128 and P129 remain separate. This four-cell study cannot establish
general quality preservation, timing superiority, novelty or letter acceptance.
