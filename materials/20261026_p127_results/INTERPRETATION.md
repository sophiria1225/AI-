# P127 publication and accounting notes

The original collector artifacts in this directory and `reports/P127_{comparison,server_session,initial_checks,activation_v01}.json` are byte-for-byte copies. The figures under `figures/` preserve the first actual rendering. This note supplements them without replacing frozen outputs.

Both policies succeeded on three of four tasks and consumed 695,217 whole-job logical input plus output tokens each. The common-success total is 352,584 each; the failed CSV costs remain in the all-task total. All eight outcomes and usage counts are known. Automatic region use and shared explicit-field requests are zero; the CSV has 72 ordinary complete-cache hits per policy. The fixed development gate is false. No token-saving, general quality-preservation, or novelty claim follows.

## Data dictionary qualification

`measures.{input_tokens,output_tokens,cached_input_tokens}.exact_all_condition_total` in the frozen builder denotes the sum of reported known-call subtotals when every condition reports that component. It is an exact whole-job component only when `all_condition_usage_known` is true; cached input additionally requires every component to be measured. With unknown calls, retain the unknown count and interpret those nested fields only as reported subtotals. The primary `exact_total_tokens` correctly remains null when usage is incomplete. In this actual run, all usage is known, so this qualification does not change any displayed total or the adoption gate.

Unknown is not zero. Failure is not missing evaluation. A successful task with a projection contract stop would remain successful with its measured cost while failing the mechanism gate. These conditional cases were checked synthetically; this actual run contains zero unknown usage and zero contract stops.

API requests, cache hits, field hits, schema deliveries, control bytes, model tokens, and wall time measure different things. A hit is not a net API saving or a model-token reduction. Program/control/lookup/work durations overlap; do not add them. Cached input tokens are retained as logical input and are not subtracted from the primary objective.

## Verification and reproduction

The independent audit public export is [P127_closed_independent_audit_20261026.json](../../reports/P127_closed_independent_audit_20261026.json). It preserves aggregate results, scope limits, the original private result hash, 67,270 passing checks, and hash digests of omitted private binding/check labels. It checks saved evidence after closure without executing generated task programs or running model/API/evaluator/tokenizer calls. It is not a formal semantic proof or an independent reimplementation of the compiler. The original private audit remains unchanged.

The actual figures were visually reviewed in PNG and PDF and independently checked against all eight rows and manifests. Automatic use, shared explicit use, and ordinary cache are separate panels. No hidden filtering or successful-task-only total replaces the all-task objective.

To redraw from public files with Python and matplotlib, run from the repository root, choosing a new output directory:

```sh
python scripts/draw_p127_results_20261026.py \
  --repo-root . \
  --closure-record reports/P127_closure_once_end.json \
  --collector-record reports/P127_report_collector_once_end.json \
  --collector-start reports/P127_report_collector_once_start.json \
  --output-dir /tmp/p127-public-redraw
```

The renderer is the same bytes as the original and verifies the fixed plan, closed source/artifact hashes, all eight rows, and aggregate/gate consistency before plotting. No private runtime path is needed. An existing output directory is rejected. PDF creation metadata can change byte hashes on a later redraw; the archived first-render hashes in `figures/output_manifest.json` remain the evidence for that rendering.

The experiment used the launch snapshot of 179 prior ledgers and 2,122 bindings. Later public ledger additions must not be imposed on the old frozen execution tree. The v01 postprocessor was corrected while only waiting; the model experiment was not interrupted. Both its correction record and the successful v02 closure are preserved under `reports/`.
