# P138 figures: three checkpoint schedules

These are actual closed-cohort figures, not the earlier handwritten synthetic preview. All 12 planned conditions were evaluated: four known development tasks, three checkpoint schedules, and one model seed (57).

- [Whole-job cost and official outcome](whole_job_cost.png), [standalone PDF](whole_job_cost.pdf).
- [Paired comparisons and fixed decisions](paired_comparisons.png), [standalone PDF](paired_comparisons.pdf).
- [Displayed data](figure_data.json), [rendered artifact hashes](output_manifest.json), and [closed-input linkage](closed_data_adapter_manifest.json).

The whole-job figure includes every actor and focus call's known logical input and output tokens, including cached input and failed or rejected summaries. Solid bars have complete recorded usage. Hatched bars are known lower bounds with one unknown-usage call each; their heights are not exact job totals. Official success is displayed separately from usage completeness. The two failed Task 4 conditions also have incomplete exposure accounting.

| Figure label | Public task ID |
| --- | --- |
| Task 1 | `34d9492_1` |
| Task 2 | `3c13f5a_1` |
| Task 3 | `60d0b5b_1` |
| Task 4 | `6104387_1` |

Threshold 16k succeeded on 4/4 tasks; fixed 3 turns and paid prefix exposure each succeeded on 3/4. Their two Task 4 costs remain unknown. A smaller known subtotal for a failed or incomplete condition does not establish token savings at preserved success.

The comparison figure displays the fixed report's values without recomputing them. Each of the three common-success task pairs has a recorded token difference of zero. The fixed report nevertheless leaves both all-task and common-success aggregate differences null under its completeness rule; these appear as “Not estimable.” They must not be relabelled as aggregate zero, or interpreted as every component being missing. Both fixed comparison gates, the primary utility gate, and the both-control development gate are false.

The first actual rendering used the immutable renderer source SHA256 `941eacd23b3ff80f9bdb31fe6ec1a193d5e5a970a864153b3c3940e35990c016`, Matplotlib 3.11.2, and summary SHA256 `82a0554c091e9e7da4c718a6e22789f435a695006cdfa0f0aee4b0b15c8da1e2`. A separate adapter checked the original wrapper/collector end, fixed source graph, stopped processes, all planned slots, copied output hashes and the builder manifest before rendering. The renderer itself performs display validation, not an independent scientific audit; its manifest preserves that distinction. Original PNG, PDF, data and manifests are retained byte-for-byte.

For a later reproduction, use the verified summary with the unchanged renderer's `render_summary(summary, new_output_directory, synthetic=False, input_sha256=...)` function after checking the closed-input chain. The renderer's command-line interface intentionally accepts only synthetic fixtures. Do not use that synthetic CLI to label these results. Do not rerun the original exclusive adapter attempt or overwrite these artifacts.

This is a finite development comparison. Four tasks and one seed do not establish general quality preservation, statistical noninferiority, a competitive guarantee, or prior-art novelty. Predicate differences on realized histories are not a causal decomposition of whole-job cost. Earlier cohorts remain separate.
