# P138 closed results

All 12 planned conditions were evaluated. Threshold 16k succeeded on 4/4 tasks; fixed 3 turns and paid-prefix exposure each succeeded on 3/4. The candidate lost one baseline success. Neither fixed scientific gate passed.

- [Findings and limits](../../docs/experiments/P138_findings.md)
- [Original 12-condition table](conditions.csv), [model-call accounting](model_calls.csv), [paired comparisons](pairs.csv)
- [Original summary](summary.json), [original builder notes](README.md), [builder manifest](build_manifest.json)
- [Original audit](../../reports/P138_comparison.json), [server session](../../reports/P138_server_session.json)
- [Independent saved-record review](../../reports/P138_closed_independent_review_20261027.json), [review execution lineage](../../reports/P138_closed_independent_review_execution_lineage_20261027.json)
- [Figures, PDFs and display data](figures/README.md)

The cohort contains 2,215,456 known logical input/output tokens and two unknown-usage calls. Unknown costs are not zero. Both failed conditions reached the work-time limit during a model call. Fixed aggregate nulls are retained, including the stricter common-success aggregate nulls, although the three known successful pairs each have zero token difference. A lower known subtotal on a failed condition is not quality-preserving savings.

This is one seed on four known development tasks. Earlier cohorts are not pooled, reserved tasks remain unopened, and neither novelty nor general quality preservation is established. The original reports and figures are retained without rerunning their producers.
