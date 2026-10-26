# P128: whole-task receipt disclosure, two fixed seeds

This prospectively fixed development experiment compares ordinary full receipt
indexes with references to their unchanged archive records. It measures actual
whole-job tokens and official task success. It makes no standalone novelty claim.
P127 is closed and audited: its lack of projection activation does not prohibit
this different representation comparison. All earlier cohorts remain separate.

## Conditions fixed before generation

The same four known development tasks are run in both `full` and `disclose`
modes under model seeds **57 and 157**, world seed 42: **16 new cells**. The seed
is fixed by replication, not chosen after outcomes. Task order is fixed; mode
order alternates across task and replication. Repetitions do not create eight
independent tasks. No reserved or new task requirements are read.

Both modes use the same shared instructions, public tool schemas, explicit
joined-field capability and guide, ordinary complete read cache, lossless
column/row receipt format, public schema feedback and `rolling_separate`
checkpoint policy. Automatic region projection is disabled in both modes.
Both preserve returned reasoning from the beginning. Model configuration is
the pinned MiniMax-M3 IQ4_XS local runtime inherited from P29, with thinking
enabled, automatic tool choice, no reasoning-token cap, 65,536 context tokens,
4,096 output cap and the same temperatures. Checkpoints use threshold 16,384,
two retained recent turns, at most three opportunities, three fresh closed turns
between opportunities, and separate summary temperature 0.7. Model calls and
summary calls share one budget.

Only an eligible closed `run_python` turn's `api_receipts` index changes. Full
mode shows its original table. Disclosure mode shows a reference to the
unchanged outer archive and its receipt row count. Eligibility is rederived
from complete trusted recorder events/spans: a single native Python call,
normal known returned executions, exact ordered receipt bindings, no pending
read, no truncation or paging, and a strictly smaller reference in UTF-8 bytes.
This byte rule is fixed, not a learned or token-tuned threshold. Unsupported
or uncertain shapes retain full display. Contradictory source records stop the
cell and remain failures/unknowns in accounting. Returned execution is not a
semantic success or task completion certificate.

Raw messages, archive member order, text, character paging offsets and all
non-index fields stay intact. There is no free injected expansion. Existing
`read_span` or `run_python(span_ids=...)` actions retrieve ordinary original
records and incur their actual subsequent input, output and elapsed costs.
The same shared disclosure guide is present in both modes; initial model
requests must match within each task/seed pair. Mode-specific private metadata
is not inserted into model input.

## Finite budget and execution

Each cell has at most 80 shared model calls, 450,000 logical input plus output
tokens, and 1,800 work seconds. Per-task API caps are 160/80/80/120 in both modes
and both seeds. The cohort reserves at most 1,280 model calls, 7,200,000 logical
tokens, 1,760 environment API requests and 16 independent evaluator calls.
Per-cell bounds are setup 120, cleanup 180, idle recovery 60 and evaluation
180 seconds. The owned server lease is 39,600 seconds. Launch is rejected if
that lease would exceed **2026-10-27 06:00 JST**. A cell and the whole batch
recheck server ownership, model identity, idle status and sufficient lease.
There are no automatic retries, adaptive extensions or additional seed trials.

Before generation, a new plan binds all source hashes and the closed P127
reports. Both exact-head CI events must pass. Preflight makes 16 initial-input
count requests plus two seed-specific text-summary transport count requests,
with zero generations, environment API requests or evaluations. Activation
reconstructs the exact saved requests and checks identities, positive counts,
admission, source/resumption bindings and matched initial inputs.

An explicit user stop or fixed operational failure ends the applicable run
with owned cleanup and retained records. Ordinary user messages do not stop
the research. A finished cohort is analyzed while the next finite comparison
is prepared; this plan does not authorize an unbounded loop of identical runs.

## Accounting and decision fixed before outcomes

Primary cost is all actual logical input plus output tokens from task start,
including checkpoint generation, failed attempts, expansion, recovery and
notices. Cached input remains in logical input. No unknown usage is replaced
by zero. Retain all 16 planned slots, including incomplete, failed and not-run
conditions. API counts, bytes, caching, setup/work/cleanup/evaluation/server
time and validator overhead are secondary measures, separately scoped.

Primary quality is independent official final task success; evaluator results
never enter the actor's history. The development gate requires:

1. All 16 cells evaluated with known usage and no audit errors.
2. In **each** fixed seed, no `full` success becomes a `disclose` failure.
3. In **each** fixed seed, lower aggregate all-task tokens and lower tokens on
   a nonempty set of common-success pairs.
4. At least one receipt reference actually appears in an audited dispatched
   actor or focus request on a common-success disclosure run. A reference
   created only in the final completion turn does not count as exposure.
5. Every disclosure source contract and shared explicit runtime contract remains intact.

Report all-task, common-success and both-failed differences, each seed and
each task pair. An aggregate gain cannot hide a seed-specific regression or a
cheap failed task. This small known-task comparison cannot establish general
quality preservation, unseen-task generalization or novelty. A negative result
is retained and directs the next experiment; it is not replaced or retried.

The independent auditor reconstructs eligibility, every displayed history,
checkpoint request and actual request from raw records and compares the saved
sidecar only afterward. It also retains the existing runtime, typed execution,
wire, cache and logical usage audits. Raw private task data, generated programs,
prompts, reasoning and credentials are not publication artifacts. Aggregate
results, source hashes and reproduction instructions are the output; manuscript
writing remains with the user.
