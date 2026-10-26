# P127 figures 

Reproduction: `python draw_p127_results_20261026.py --repo-root CLOSED_PUBLIC_REPO --closure-record P127_closure_once_end.json --collector-record P127_report_collector_once_end.json --collector-start P127_report_collector_once_start.json --output-dir NEW_DIRECTORY` with Python and matplotlib 3.11.2. Both figures are saved as PNG and PDF. Existing output directories are never overwritten.

The cost figure retains every task/policy, official success/failure/unevaluated state and contract-stop flag. A hatched bar is a known subtotal; NA is missing data, never zero. Successful official evaluation can coexist with a harness contract stop. All-task totals and common-success totals are distinct. A cheap failed task is not quality-preserving savings.

The mechanism figure separately shows automatic-region partial hits, shared explicit-field partial hits and ordinary full-cache hits. No sum is called net API savings or token savings. Counts with incomplete execution traces are marked. No overlapping time quantities are stacked; durations are deliberately outside these two figures.

Only four already exposed tasks, seed 157, and shared rolling-separate checkpoint are represented. A positive fixed development gate would still not establish general quality preservation, noninferiority or novelty. A false gate is retained unchanged. All missing slots and audit errors remain visible.

Actual rendering requires the fixed collector source/head and complete collector record, closed audit/server/manifest hashes, every frozen source, all eight public rows, exact CSV correspondence and independently recomputed all/common aggregates and fixed gate. This renderer never reads raw task records, stored generated programs, prompts, reasoning or evaluator text. Synthetic preview uses handwritten data only and does not claim closure or measured outcomes.
