# Ordinary public export checking before writes

This bounded prototype addresses the closed P127 CSV failure: an actual file-write payload disagreed with previously returned public song data. It implements ordinary schema, set, join, and CSV checks for the already known export-then-delete instruction. P67 already implemented post hoc export evidence checking. Neither the task-specific monitor nor deterministic CSV generation is claimed as a new general method.

The module is `scripts/public_output_grounding.py`. It has no API dispatch, model call, task database access, code execution, or autonomous deletion. The source string that produced an argument is irrelevant: the host supplies the actual imminent API arguments and previously recorded public replies. A proposal is not evidence that a write occurred.

## Accepted evidence

| Question | Rule and public implementation basis |
| --- | --- |
| Whose library? | The initial public task's supervisor email identifies the expected account. A successful typed `spotify.login` or `file_system.login` with that exact username binds its returned token to that app and principal. Token refresh for the same username does not change principal. No token is decoded, guessed, or accepted from a failed login. |
| Complete inventory? | Only unfiltered song, album, and playlist library pages with a bound Spotify credential count. The pinned `api_lib.paginate` is a list slice. Contiguous pages starting at zero through a page shorter than its limit establish that series' end. Different limits are separate series; all observed slices and complete sequences must agree. A full page alone, a missing page, filtered playlists, duplicates across pages, or changed pages do not establish completeness. |
| Song values? | A successful public `show_song` or song-library item gives `song_id/title/artists[].{id,name}`. Actual album/playlist detail serializers give `songs[].{id,title,artist_ids}`; those artist IDs can join only to previously returned public artist ID/name records from `show_artist`, song artists, or album artists. The album's artist list is not substituted for each song's artist-ID list. Request IDs must match returned IDs. |
| Failed reads? | Typed raised replies of the explicitly listed read-only APIs supply no values and do not invalidate earlier successful evidence. Unsent actions supply no evidence. Unknown outcomes, untyped sent requests, changed values, unhandled effects, and malformed identity data prohibit repair. Repeated event IDs/nonces are rejected. |
| CSV meaning? | Exact `Title,Artists` columns, exactly one row per observed union song, correct title and artist-name multiset, and no missing/extra/duplicate pairs. Artist order and row order are unspecified by the public request and therefore are not extra quality requirements. Standard CSV quoting handles commas, newlines, Unicode and quotes. Same title/artist pairs for distinct IDs remain ambiguous/unknown. |
| Write scope? | Only the instruction's exact canonical home-relative path and `file_system.create_file/update_file`, with a bound file-system credential and supported argument shape. Unknown or other writes pass unchanged. |

`verify_public_export_sources(appworld_package_root)` checks fixed SHA-256 values of public `apps/api_lib.py`, Spotify API/serializer, file-system API, and supervisor API files, without importing them. The host must call it before activating the monitor and bind `PUBLIC_CONTRACT_ID` in its source/condition manifest. This does not prove every dependency or arbitrary external mutation safe. The assumed task world is isolated and the inspected public API/serializer semantics apply; no concurrent external mutation or hidden-state oracle is used.

## Interface and integration obligations

`PublicExportMonitor(public_task, execution_scope=run_id)` is owned by one execution. `observe(event, span)` receives the host's chronological recorded API result after dispatch, with its actual effective arguments, assigned span ID, and typed receipt. A request, source-code literal, schema example, stdout, future reply, or another arm's state must never be supplied as a witness.

`propose(full_api_name, actual_args, mode='check'|'repair')` runs before dispatch. It returns `outside_scope`, `unknown`, `supported`, or `contradicted`, bounded reasons/counts/hashes, and optional `replacement_args`. Only `repair` plus a complete contradicted proof returns a replacement; only `content` changes. The original argument dictionary is not modified. Sorted observed song IDs select a deterministic row order; no new values are generated. A supported write is left byte-for-byte unchanged.

The planned three ordinary controls use the same monitor and guide:

- **off:** `check`, dispatch the original arguments and retain shadow evidence.
- **feedback:** `check`; a proved contradiction is a local pre-dispatch error so the model can repair it. Do not fabricate a sent API receipt or charge an environment request for a local rejection. Unknown passes unchanged.
- **repair:** `repair`; dispatch the corrected content once through the original budget/typed-result path and disclose a concise repair notice. Unknown passes unchanged.

The runtime must bind original/proposed/effective action hashes, source-evidence hashes, policy, decision, monitor cost, notice, and the actual API nonce/result in a private ledger. The generated source/archive remain original. Python locals holding the original string are not silently rewritten, so normal-path program-value equivalence is not claimed. In particular, an agent may read back the corrected file and find a difference from its local original; all resulting work and tokens belong to the experiment. The independently reconstructed audit must observe effective dispatched values and must not treat the proposed value as a successful response.

Deletion is never intercepted, repaired, scheduled, or authorized by this monitor. `summary()` records whether a confirmed supported write preceded the observed deletion. A successful write/readback alone is insufficient. Missing backup evidence stays unknown; it does not introduce a new deletion-admission contract.

## Bounded development evidence and limits

Seventeen synthetic tests cover payload-only repair, unchanged arguments, unknown/non-target behavior, credential refresh and separation, short/full/gapped/changed pagination, direct and joined metadata, stale/unknown effects, CSV quoting and artist order, actual-write confirmation, and source hashes. They are implementation checks, not token or final-success results.

A private data-only pass over six already closed known traces reads public task descriptors, typed API events/spans and usage metadata only. At the final target writes, the four previously successful P118/P123 traces are supported; the two P127 traces are contradicted and have deterministic repair proposals. One earlier failed write with an unverified credential remains unknown. Source metadata is complete at those six final writes: 72 required song IDs, using direct returns or ordinary public joins. P127 has two malformed rows and no matching required pair in its original payload. No proposal was dispatched; this does not establish counterfactual success, cost savings, or the sole cause of an evaluator failure.

The first private diagnostic used ordered artists and incorrectly flagged nine rows in three successful traces. The public requirement specifies no artist order; the preserved v01 is superseded by the multiset comparison, not relabelled as a task failure. The same review added already returned album artist ID/name evidence to close the fourth trace's ordinary join. Hidden answers, evaluators, task databases, unseen scenarios and P128 interim records were not read.

## Next finite comparison

The separately fixed next question is **deterministic payload correction versus ordinary model feedback**, with off as an auxiliary reference: one known CSV task × three modes × seeds 57 and 157 = six cells. This is fixed from closed P127 evidence before P128 results; it is not seed search or a retry of P128. All modes use P127's explicit joined-fields runtime, rolling separate checkpoints, full receipt history, and the same truthful guide. Each cell retains 80 shared model calls, 450,000 logical tokens, 1,800 work seconds, and 120 environment requests. Totals: 480 calls, 2.7M tokens, 720 API requests, six independent evaluations, and a 21,600-second server lease including bounded setup/cleanup/evaluation/idle time.

All six outcomes, failures, unknown usage and monitor/recovery costs must be reported. Repair must not lose a feedback/off success within either seed. Report all-task and common-success whole-job token differences separately; improved success against a cheap failed baseline is not a quality-preserving token-reduction result. Require actual pre-write opportunities and interventions to interpret a mechanism comparison. Two repetitions of one known task do not establish broad quality preservation or novelty. Driver activation, deadline feasibility and live execution remain separate gates owned by the parent study controller.
