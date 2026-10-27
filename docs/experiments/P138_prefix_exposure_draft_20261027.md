# P138 draft: repeat checkpoints driven by paid prefix exposure

2026-10-27. Preparation only: no P138 generation, environment operation or
evaluation has started. The configuration and executable source must be fixed
before launch. P137 is closed; its four failures and missing usage remain
unchanged. This is a different timing hypothesis, not another seed intended to
rescue its obligation-notice mechanism.

## Question

Can a controller using measured repeated exposure of older raw history preserve
final task success while reducing all logical input and output tokens, compared
with the ordinary rolling checkpoint control that succeeded on all four P123
development tasks? A new timing rule is a testable utility hypothesis; novelty,
quality preservation and a competitive cost bound have not been established.

All three arms use the same ordinary P123 interface, summary prompt, persistent
Python, public tools, first checkpoint threshold of 16,384 native input tokens,
two retained recent turns, three fresh closed turns between opportunities, and
at most three opportunities. Neither uses P137 field notices or credential
repair. All actor and summary requests share the same budgets.

After a paid checkpoint attempt, let C be that attempt's known input plus output
tokens and set E to zero. For each subsequent actor request whose usage is
known, measure its native input X and the input U obtained by removing only
newly eligible older raw turns. Keep the current checkpoint, original system
and task, recent two complete turns, budget notice and tool schemas unchanged.
Store X-U, including negative values; add max(0, X-U) to E only for an actual
dispatched request with known terminal usage. U is a counting-only payload and
must never be submitted for generation. The difference is a representation
exposure metric, not achievable savings from a real summary.

For repeat opportunities, the candidate replaces the 16,384 threshold with
E >= C. The existing fresh-turn, archive-boundary, opportunity and shared-budget
checks still apply. First opportunity behavior remains ordinary. All three arms
perform and record the same exposure measurements; the ordinary arm uses them
only as shadow diagnostics. A paid invalid or nonshrinking summary still costs
tokens, spends an opportunity and resets E/C. An unsubmitted summary does not
reset E/C. Unknown usage prevents continuation. No retries or hidden recovery
calls are added.

## Feasibility before launch

Use every P123 rolling_separate development run, with original requests bound
to their closed audit. Count original and counting-only inputs using the
already built, hash-verified vocabulary-only native renderer. It creates no
inference context and executes no generated program. Validate each original
input count against recorded terminal usage. Identify only the first policy
decision disagreement on an unchanged recorded prefix. Do not continue a
counterfactual trajectory through that disagreement, or report its later cost
or success as observed. No thresholds or seeds will be searched to force a
disagreement. Unsupported request structures remain explicit failures.

## Proposed finite comparison

If feasibility and implementation checks pass, run the four previously known
development tasks in three modes: twelve new cells, world seed 42 and model seed
57 plus the existing within-role call index. Rotate mode order across task
slots. The third mode keeps the same first opportunity and then offers a
checkpoint at each eligible three-fresh-turn boundary, up to the common cap.
This ordinary fixed-interval control tests whether the cumulative exposure
signal improves on a simple timing rule. Include every task, failure, unknown usage and unrun cell. No earlier
result is reused as a new control, and reserved tasks remain unread.

Per cell: 80 shared model calls, 450,000 logical tokens, 1,800 work seconds,
4,096 maximum output tokens, and the existing per-task API caps 160/80/80/80.
Setup, cleanup, idle recovery and evaluation caps remain 120/180/60/180 seconds.
The twelve-cell reservation is 960 model calls, 5,400,000 tokens, 1,200
environment API requests and twelve independent evaluations. A finite server lease and
absolute launch deadline will be set in the executable plan; this draft does
not authorize starting a server. Native counting and control time count toward
work time and are reported separately from logical inference tokens.

The primary utility gate compares exposure with the 16k control: all eight
evaluations and usages must be known, accounting (including exposure accounting)
must be complete, no paired control success may be lost, and both all-task cost
and cost on a nonempty common-success set must decrease. A changed trigger
must reach an actual dispatched model request on a common-success candidate
run. A count-only decision followed by no applicable dispatch cannot qualify.
The both-control development gate requires these conditions against fixed
interval as well. Fixed interval is a previously unmeasured timing control,
not an empirically established stronger control. Passing only the primary gate
does not establish the value of cumulative exposure over simple timing.
All twelve slots and both comparisons remain reported; an aggregate gain cannot
hide a success loss against one control.
Empty common-success sets have no defined cost-effect estimate. Same success
counts alone are insufficient. Report per-task pairs, all-task costs, common
successes and both-failed costs, actor/summary costs and timing interventions.
One seed on four known tasks cannot establish statistical noninferiority,
unseen-task generalization, novelty or acceptance at a journal.

The manuscript remains the user's work. Outputs are the implementation,
reproducible fixed comparison, full results and limitations.

The executable reservation is a 32,400-second owned server lease, a
30,000-second batch cap, and an absolute lease-end deadline of
2026-10-28 03:00 JST. Starting later than 2026-10-27 18:00 JST is rejected.
This is a finite ceiling, not an expected runtime or authority to extend a
running cell. A clean fixed source commit and successful push/pull_request CI
are required before model-server launch.
