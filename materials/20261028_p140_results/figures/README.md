# P140 actual figures

These figures show all 12 evaluated conditions of the closed, known-four-task, seed-57 development experiment. T/R succeeded on 4/4 tasks; E/D and E/DO each succeeded on 3/4. Both fixed comparison gates are false. A lower known subtotal with a failed task and unknown usage is not token savings with preserved quality.

- [Whole-job cost PNG](whole_job_cost.png) / [PDF](whole_job_cost.pdf): all actor and focus logical input plus output, including cached input and failed/rejected calls. Hatched bars are known lower bounds with unknown usage, not exact totals.
- [Paired comparisons PNG](paired_comparisons.png) / [PDF](paired_comparisons.pdf): all eight pairs, original nulls, strict and transport-ID-canonical prefix flags, and the two separate gates.
- [Compact cost PNG](compact/compact_cost.png) / [PDF](compact/compact_cost.pdf): 7.0 × 3.8 inch, 300 dpi, minimum nonempty text size 8 pt. A separately versioned data-only layout derived from the already validated original figure_data.json. All 12 cells and the saved gates are retained. It does not rerun the experiment, original renderer, evaluator or audit.

The original [figure data](figure_data.json) and [manifest](output_manifest.json) are unchanged byte copies. The compact [manifest](compact/output_manifest.json) binds the same original data hash and its own renderer/artifacts. Neither directory contains synthetic preparation figures. Renderer source is included beside each figure set; pixel-for-pixel reproducibility across software environments is not promised.

Root visually inspected the two original PNGs and the compact PNG on 2026-10-28. The original independent review is [recorded separately](../../../reports/P140_actual_figures_review_20261028.json); it visually inspected the original PNGs, not the compact derivative. PDF bytes and headers were checked; no PDF visual or physical print review is claimed. Both scientific gates remain false, and independent 12-scenario confirmation is unperformed.
