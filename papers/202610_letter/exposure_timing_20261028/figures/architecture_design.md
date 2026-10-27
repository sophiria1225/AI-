# Source-only architecture for the manuscript

The PDF, SVG and EPS are vector artifacts at **130 × 45 mm**. Use the PDF at its native 130 mm width in a two-column figure. Every printed label is 7 pt and every connecting or border stroke is 0.5 pt (about 0.176 mm); the diagram uses black on white. `architecture.png` is a 600 dpi preview. The two caption macros in `architecture_caption.tex` supply Japanese and English captions. Do not shrink this diagram to the 65 mm single-column width: that would violate the intended text size.

This diagram describes fixed P141 source at commit `5cab33a2e239f3e6d90e63e32c54ba0764b1c594`. **No P141 outcome, usage record, request, response, live status or terminal marker was read.** It is not a positive result, a new method claim, or a drawing of the unfinished full12 confirmation infrastructure.

- The actor view retains the original system/task, installed summary notes and raw suffix. The two most recent closed turns are protected. Raw history remains in the append-only archive.
- `I` is known terminal actor logical input, matched to its saved native count. `I(without new raw)` is a native count-only view that removes only the newly eligible raw prefix and retains original system/task, all prior notes, recent turns, tools and the same budget state. The signed difference is retained by the implementation; only its positive part updates `E`.
- `C` is the last **known paid** focus input plus output. Every such focus resets `E` to zero and replaces `C`, including invalid or nonshrinking summaries. An unsent focus does not reset them. Unknown model usage stops continuation; it is not imputed.
- In the diagram, `16k` denotes exactly **16,384 tokens**. TR is threshold/recursive; TDO is threshold/object-delta; EDO is exposure/object-delta. All initial opportunities use the same threshold. Repeat opportunities use the threshold for TR/TDO and `E ≥ C` for EDO. All require eligible old raw history and at least three fresh closed turns, with at most two opportunities (including rejected/unsent opportunities).
- The paid focus uses the same model with no tools. The first focus contract is common. Only a second delta opportunity with an accepted prior summary uses the explicit delta-object prompt. The host keeps that prior note unchanged and appends the delta; TR recursively replaces its note. Combined canonical summary content is limited to 8,192 characters and 32 strings per field, with each item at most 2,048 characters. The normal shared call/token/context screens still apply. Installation requires the entire next actor input to have fewer native tokens. Rejection retains the existing view.
- The dashed actor-to-exposure edge is a measured-usage dependency; it is not an environment action or saved-token claim. Other arrows show logical data/control dependencies rather than concurrent execution.
- Accounting includes all dispatched actor/focus logical I/O, failures, cached input and unknown/missing terminal records. Native counting adds no generated token charge but consumes the shared work wall time; API/setup/cleanup/evaluation costs are separate measurements. Official evaluation runs after worker closure and server-idle checking, with no evaluator feedback to the actor.

The frozen source bindings and locations are in `architecture_source_bindings.json`. The graph's implementation is `architecture_source.py`; it reads no input data. The output manifest binds the rendering source and artifacts. A larger private draft and the first 130 mm draft were preserved outside the repository; the final edit removed math subscript scaling so all visible labels remain 7 pt. A first layout-boundary check rejected an overwide archive label before any output was written; shortening that label resolved it. PNG visual inspection found no overlapping labels, clipped arrows or ambiguous archive-deletion edge.

Example integration (caption style can follow the manuscript class):

```tex
\input{figures/architecture_caption.tex}
\begin{figure*}[t]
  \centering
  \includegraphics[width=130mm]{figures/architecture.pdf}
  \caption{\ArchitectureCaptionJa\\\ArchitectureCaptionEn}
  \label{fig:architecture}
\end{figure*}
```

EPS was added from the same vector drawing for external figure submission. Its HiResBoundingBox matches the stated millimetre dimensions; original PDF/SVG/PNG bytes were retained. The manifest records the original renderer digest and the EPS-enabled source digest.
