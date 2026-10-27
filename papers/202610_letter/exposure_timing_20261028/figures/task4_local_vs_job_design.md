# Closed Task 4: local input reduction versus whole-job outcome

Use `task4_local_vs_job.pdf` at **65 × 69 mm**, its native single-column size. PDF/SVG/EPS are vector, PNG is a 600 dpi preview. All labels are 7 pt; strokes are 0.5 pt. The upper panel uses zero-origin proportional bars for **one same-boundary local comparison**. The lower panel deliberately uses a table rather than global cost bars: the candidate's known subtotal must not visually masquerade as an exact saving. The outcome is explicit even though usage is incomplete.

The authoritative input is `task4_local_vs_job_data.json`, extracted from **closed public P140 metadata**, with relative source names and SHA-256 digests. `task4_local_vs_job_source.py` binds that data digest before rendering. The table-input CSV is a convenience projection of the same values, not a new experiment or re-audit.

Verified scalar meanings:

- P140 EDO Task 4, second `checkpoint_decided` entry: `after_model_calls=20`, accepted true, ordinary/current full actor view **14,027**, compacted delta view **6,058**. This is the producer's saved native comparison, not a new tokenizer execution. The original auditor reports count-to-input binding; this figure inherits that verification.
- Closed P140 `model_calls.csv`, EDO `call_021`: known actor input **6,058**. The ordinary/current 14,027 comparison view at this EDO boundary is count-only; it is not a second generated continuation of that state.
- P140 Task 4 TR: official success, **319,446 input + 13,142 output = 332,588** logical tokens, 31 model calls, 76 API requests, zero unknown calls.
- P140 Task 4 EDO: official failure at the work wall limit, **301,874 known input + 16,046 known output = 317,920 known** tokens, 31 dispatched model calls, 78 API requests, **one unknown call**. Its exact total and the paired exact total-cost difference remain null. The record is evaluated; missing usage is not an unevaluated outcome.
- The call CSV was summed independently for each depicted P140 condition and matched to the audit and condition CSV. The original producer, auditor, model, native counter, evaluator and prior renderer were not rerun.
- P123's Task 4 rolling-separate public row has the same known I/O, calls, API count and success as P140 TR. This is only historical scalar equality. P123 is neither plotted as a third arm nor pooled as an independent replication, and no full trajectory equality is inferred from that equality.

Claim boundaries: local shortening and successful installation do not show semantic preservation, quality preservation, whole-job savings, or novelty. The 7,969-token local difference is not multiplied by later calls, subtracted from the whole job, or treated as a causal cost decomposition. Repeated known-task/seed development and posthoc selection of this example limit generalization. P140's fixed primary, unchanged-delta and both-control development gates remain false. P141 and all reserved-task contents were not read for this figure.

`task4_local_vs_job_caption.tex` contains Japanese/English macros. The root manuscript author owns the final results table and inclusion decision. If page space is scarce, retain the upper local comparison plus the manuscript's existing all-condition table; do not crop away the failure/unknown explanation while retaining this figure's lower costs.

```tex
\input{figures/task4_local_vs_job_caption.tex}
\begin{figure}[t]
  \centering
  \includegraphics[width=65mm]{figures/task4_local_vs_job.pdf}
  \caption{\TaskFourDiagnosticCaptionJa\\\TaskFourDiagnosticCaptionEn}
  \label{fig:local-versus-job}
\end{figure}
```

EPS was added from the same vector drawing for external figure submission. Its HiResBoundingBox matches the stated millimetre dimensions; original PDF/SVG/PNG bytes were retained. The manifest records the original renderer digest and the EPS-enabled source digest.
