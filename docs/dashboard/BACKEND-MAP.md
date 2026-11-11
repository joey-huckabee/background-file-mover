# Dashboard: screen-to-backend implementation map

Step 1, 2026-11-10. Audited against source/design base
`8da6164bf1b89b4df3bc45858814977a191d3e11`.
This maps the [accepted visual direction](mockup.html), not a production UI.
No runtime, route, schema, dependency or stored-state change is introduced.

Authority is the frozen 2.0.0 [API closeout](../api/API-CONTRACT-CLOSEOUT.md),
[OpenAPI inventory](../api/openapi.candidate.json) and
[response schemas](../api/contract.candidate.schema.json). The closeout supersedes
historical proposal wording. The no-proxy native HTTPS decision remains in force.

## Reading this map

- **Existing:** emitted by current trusted-local status/retention reads. This
  does not mean remote admin access is implemented or authorized.
- **Contract:** specified in the frozen contract, but runtime work is required.
- **Derived:** presentation computed from the exact bounded response in hand;
  scope and unknown values must remain visible.
- **Omit:** fictional mockup content has no supporting read field. Keep its
  useful layout, not its made-up value. No new API is proposed to preserve it.

## 1. Shell, access and connection state

| Mockup element | Source / status | First working behavior |
|---|---|---|
| File Mover branding, icons and styling | Static local assets | Embed vanilla HTML/CSS/JS and original SVG; no external asset loads or frontend tooling |
| `mover-production-01`, primary instance, SLES label | Omit: not session/status response fields | Use a static console heading and the browser's configured admin origin; no inferred hostname, OS detection or primary-election claim |
| Private admin interface indicator | Contract: authenticated admin audience | Label the audience, not a blanket security/health attestation; producer certificate approval grants no admin session |
| Administrator avatar/name | Static role label | Show `Administrator`; do not invent a session username/profile endpoint |
| Date in header | Derived browser-local time | Optional convenience only; label local time if retained. It is not service time or freshness evidence |
| Last successful refresh | Derived client observation | Record when the complete validated response arrived. Show `Received at ...`, not a server snapshot timestamp |
| Connected/stale/unavailable | Derived request result | A successful read is not worker health, storage reachability or NFS settlement. Failures retain clearly stale last-known data, never replace it with zero jobs |
| Green instance dot | Omit as unconditional health assertion | Tie any connection marker to the actual read result and label its meaning |
| Sign-in | Contract: `POST /api/v2/admin/login`, `LoginRequest` / `LoginSuccess` | Exact approved 200/401 behavior; no self-registration or browser account management |
| Session | Contract: `GET /api/v2/admin/session`, `SessionStatus` | `authenticated`, `inactivity_timeout_seconds`; session cookie/CSRF are protected transport material, not profile JSON |
| Sign-out | Contract: `POST /api/v2/admin/logout` | 204 only after global invalidation; other tabs/devices require sign-in. Password activation and mover restart also invalidate sessions |
| Sign-out toast | Derived successful response | Never claim global sign-out on a timeout/lost response; show uncertainty and require a session check/sign-in as appropriate |

Do not poll `/healthz` through the producer audience or expose private status,
stop or TLS-reload IPC to the browser. Service administration remains host-local.
Existing native HTTPS in `native.rs` is a producer listener with a private
operator socket; it is not an implemented admin listener.

## 2. Overview and navigation counts

| Mockup element | Source / status | First working behavior |
|---|---|---|
| Retained jobs card / history badge | Existing global `RetentionDetails.retained_jobs` | Global retained count, not number of loaded rows |
| Committed jobs card | Existing global `RetentionDetails.committed_jobs` | Global committed count; not a rate, daily total or sum of copied files |
| Active jobs card | No global active/runnable count in frozen reads | Replace with an available ledger measure, such as global `confirmed_claims`, or omit. Do not infer active workers from retained minus committed |
| Needs-attention card/nav badge | Contract list `items[].condition` | Count only `ReviewRequired` in the current page and explicitly label `on this page`; no global total claim |
| Custody-to-commitment flow | Derived from list summary `state`, `condition`, `source_paths_released` | Show distribution on the loaded page, or use a static explanatory flow. Review/cancel conditions are not silently counted as active delivery |
| Safely cancelled total | No global cancellation count | Current-page count only once cancellation data exists; omit from first read-only slice |
| Review callout | Derived current-page `ReviewRequired` rows | Link to the page-local attention view; do not claim that the page found all exceptions |
| Recent/newest jobs | Contract list is ascending original job ID | Relabel `Job history · current page`; keep authoritative ascending order. Do not call the first page the latest jobs |
| Total displayed vs total retained | Existing retention plus bounded list | Report these independently. They come from separate reads and need not be mutually consistent at one instant |

The global retention response provides no aggregate count per current job
condition. Do not scan all pages, issue a detail request for every retained job,
or add hidden aggregate endpoints just to fill overview cards. The first version
can use fewer cards while retaining the accepted typography/layout.

## 3. Job history, filters and selection

| Mockup element | Source / status | First working behavior |
|---|---|---|
| List of jobs | Contract `GET /api/v2/admin/jobs` → `JobList.items` | New bounded Store query and authenticated HTTP handler required |
| Friendly titles such as `West lab · Session 038` | Omit: no recording title field | Primary label `Job #<job_id>` with generator and existing recording identity as supporting text |
| Original job ID | Contract `JobSummary.job_id` | Preserve decimal string; never reuse or replace it with a UI-generated ID |
| Generator | Contract `generator_id` | Exact returned text; display with safe text nodes |
| Recording UUID / legacy identity | Contract mutually exclusive `recording_id` / `submission_id` | UUID label only for the UUID branch. Explicit `Legacy submission` label for legacy jobs; no invented conversion |
| State / condition | Contract summary `state`, `condition` | Translate known enums into readable labels while preserving the distinction between durable state and current condition |
| Files column / ratio | Omit from summary: no file count/phase list | Keep in selected-job detail, not an N+1 fetch per list row |
| Measured size column | Omit from summary: no byte total | Keep a derived, exact, explicitly measured total in detail |
| Accepted today / timestamp column | Omit: no acceptance timestamp in summary/detail or `jobs` table | Do not use first browser observation or job ID as an acceptance time |
| Search input | No search query parameter in frozen list operation | Clearly labeled `Search this page` across returned ID/generator/identity. No implied global search |
| State tabs / attention navigation | No state-filter query parameter | Filter current page only; preserve visible indication that other pages may contain matches |
| Pagination | `limit`, opaque `cursor`, `next_cursor` | Default 50, maximum 256; ascending job ID. `next_cursor:null` means no next page, not an estimated page count |
| Previous page | Derived navigation memory | Retain a bounded cursor stack in this tab if supplied. Re-read on navigation; no snapshot guarantee across pages or clears |
| Selected rows | UI-local ordered original IDs | Initially select only visible rows, bounded by the 256-entry action limit. No `select all retained` without complete authoritative selection |
| Zero matches | Derived current page filter | Distinguish `No matches on this page` from an authoritative empty retained history |
| Job disappeared while opening | Existing detail `404 not_found` | Show no longer tracked, remove stale selection and refresh. Never fall back to another job or reconstruct cleared state |

The frozen list parameters are only `limit`, `cursor`, and the separate paired
confirmation-mode parameters. Do not send `search`, `sort`, `state` or `offset`.
Normal pages have a 1 MiB bound; selection survives neither sign-out nor a
switch to a different instance. Cursor navigation does not keep an idle session
alive unless it is an authenticated deliberate user interaction.

## 4. Job detail and exception review

Source: existing `GET /api/v2/jobs/{job_id}` response via `status_response` in
[file-mover/src/lib.rs](../../rust/crates/file-mover/src/lib.rs).
The admin audience and optional action extensions still require implementation.

| Mockup element | Exact source / status | Display rule |
|---|---|---|
| Durable job state | Envelope `state` | Existing `Accepted`, `Claimed`, `Committed`; cancellation variants require their lifecycle implementation |
| Operational condition | `details.condition` | Existing `Committed`, `ReviewRequired`, `AwaitingClaims`, `Retrying`, `Ready` |
| `Delivering` badge | No proof of currently running work in `Ready` | Prefer `Ready for delivery` / `Retrying` from the response; do not claim a worker is active |
| Source custody / released paths | `source_paths_released` | False: producer must preserve paths. True: whole-set custody confirmed; does not mean destination commitment |
| File count | `details.files.length` | Count the validated complete file array (bounded to 256) |
| Published files | `details.files[].phase` | Count `Published` and `SourceRemoved`. Label as file-phase progress; no byte-progress percentage or ETA |
| Actual size per file | `details.files[].size_bytes` | Null is `Not measured`; zero is a known zero-byte file, never expected size |
| Recording measured total | Derived exact sum of non-null actual sizes | If any are unknown, say `Known bytes + N unmeasured files`; never present a partial sum as a complete recording total |
| Relative path / stable file ID | `details.files[].name`, `.file_id` | Preserve exact UTF-8 text and durable path/index mapping; no renaming, normalization or list-order-derived IDs |
| File custody phase | `details.files[].phase` | Preserve enum: Pending, Claimed, Verified, Published, SourceRemoved |
| Transfer phase / attempt | `details.files[].transfer_phase`, `.attempt` | Separate from file phase. Nullable; no current attempt if absent |
| Per-file SHA-256 / `SHA-256 verified` | Omit: digest not returned in `FileStatus` | Show reported phases only. Do not fetch committed payloads or manifests through invented admin routes to fill a hash column |
| Committed manifest / consumer boundary | Durable `state:Committed`, `details.manifest_phase` | Commitment comes from validated stored state. A precommit/published manifest alone is insufficient; immutable serialized bytes/hash/version are not returned here |
| Automatic source cleanup | `details.source_cleanup_enabled` | Currently false; read-only indicator, not an enable/disable setting |
| Source directory / destination directory | Omit: not exposed by detailed-status schema | Data exists in stored custody/routing, but browser exposure is not approved by its existence. Keep relative file names; no private-path reconstruction |
| Milestone timeline and relative durations | Omit: no complete event/timestamp history | Replace with current facts and existing latest audit evidence, not synthetic acceptance/claim/publication times |
| Latest delivery resume | `details.latest_resume` | Actor, reason, recorded_at, consumed epoch, prior retry/code; one latest audit, not a complete timeline |
| Latest missing reset | `details.latest_missing_reset` | Existing latest audit only; consumed audit epoch differs from current outer epoch |
| Delivery retry status | `details.delivery_retry` | Failures, absolute Unix `retry_after`, fixed code; no parsing diagnostic text to authorize actions |
| Missing source condition | `details.missing[]` | File ID, deadline, blocked and deadline_elapsed. Distinguish this from destination review |
| Reviewed retry context | Contract `details.retry_review` | Existing instance/job/nullable epoch projection; runtime extension not currently emitted |
| Retry explanation | Contract audit reason | 1–512 UTF-8 bytes, valid nonblank control-free text; HTML maxlength in characters alone cannot enforce the wire bound |

`ReviewRequired` can arise from missing-file review or persisted delivery failure.
Do not show the sample's universal “destination unavailable after three failures”
message for every reviewed job. Display the actual code/evidence; preserve the
specialized trusted-local missing-reset command as local-only. Bulk retry must
not become an undocumented substitute for missing-file reset.

## 5. Retention screen

Source: existing global/per-job `RetentionResponse.details`, produced by
`retention_response` in the same Rust file, backed by Store reservation state.

| Mockup element | Exact field / presentation |
|---|---|
| Source/destination reservations | `source_reserved_bytes`, `destination_reserved_bytes`: exact u128 decimal strings |
| Configured limit and meter | `configured_limits.max_reserved_bytes`; show no limit/meter if configuration is null. Calculate bounded display ratio from exact integers; flag over-limit rather than hiding overflow |
| Retained / committed totals | `retained_jobs`, `committed_jobs` |
| Confirmed/source claims | `confirmed_claims`, `source_claims`; distinct ledger meanings |
| Unknown sizes | `unmeasured_files`; no zero-byte substitution |
| Jobs limit | `configured_limits.max_retained_jobs`, nullable limits |
| Headroom | Global `global_headroom`, nullable; per-job headroom is null. This is admission-ledger headroom, not physical free disk |
| Attempts by phase | `destination_attempts_by_phase`; includes all retained attempts, not only each file's latest attempt |
| Physical filesystem inspection | `filesystem_inspected:false` |
| Leftovers coverage | `unreceipted_allocations_accounted:false`; do not imply all physical data is inventoried |
| Automatic reclamation | `automatic_reclamation_enabled`, currently false |
| Source-space observation | Global-only cached `source_space_admission`; state/sample age/reason are observations, not a fresh probe caused by dashboard reads |

Show exact bytes on demand alongside a human-readable GiB/TiB value. After clear,
the removed job has no retention detail, inventory, action result or ownership
lookup. Files remain in place and are no longer managed by the mover.

## 6. Actions and confirmation screens

These flows are contract mappings for later increments, not part of read-only
activation. None of the mockup's browser-local eligibility/target arrays is
production authorization.

| Flow | Contract source | Required UI behavior |
|---|---|---|
| Retry | POST `/api/v2/admin/jobs/retry`; frozen retry-context header and job_ids-only body | Inspect state and explain correction; no extra confirmation dialog. Freeze context at deliberate click, resend unchanged on transport retry, never refresh it from background polling. Render 202 attempt counts, not successful transfers |
| Cancel | GET list confirmation mode `confirm_action=cancel`, then POST `/api/v2/admin/jobs/cancel` | Confirm selected original jobs. 202 counts mean attempts; pending remains until actual safe stop. Completed/already cancelled/missing skip according to the frozen rules; repeated unfinished occurrences retain their classification |
| Clear | GET confirmation `clear-history`, then POST `/api/v2/admin/jobs/clear-history` | Explain preserved files, UUID forgetting and complete linkage removal. 200 `cleared_count` is actual removals, not a guaranteed selection count. Server checks settled eligibility; no auto-cancel |
| Delete | GET confirmation `delete-data`, then POST `/api/v2/admin/jobs/delete-data` | Show complete `deletion_targets`: job/file/kind/relative_path/attempt/nullable measured size. Never a truncated authority preview or guessed private path. 202 `completion_pending`, deleted/failed counts reflect latest pass, not freed bytes |
| Action observations | Contract `cancellation`, `deletion` in summary/detail | Report current stored pending/latest results while tracked; do not invent another public operation ID or retain them after clear |

Confirmation comes from the server's complete `ConfirmationPreview` and proof,
not locally inferred `Eligible` / `Will skip` labels: those per-job eligibility
labels are not preview fields. Re-fetch on expired/stale confirmation and require
a fresh deliberate confirmation; never widen scope or silently retry deletion.
Apply the 256-selection, 65536-target, 16 MiB preview and five-minute bounds.
If one job exceeds the preview limit, report the refusal; do not manufacture a
partial selectable scope. Lost action replies remain uncertain until reconciled
under their action-specific replay contract. No fabricated success toast.

## 7. Browser adapter requirements before read integration

1. Preserve exact identities. Read job IDs/file IDs as strings. POST job_ids
   are numeric i64 values on the frozen wire: validate canonical decimal strings
   and serialize their exact numeric tokens without a JavaScript Number roundtrip.
2. Preserve exact measurements. Existing operator/status numeric u64 sizes and
   other wide integer fields cannot safely pass through ordinary `JSON.parse`
   into binary64 Numbers. Plan a bounded, dependency-free lossless JSON decoding
   adapter and exact integer arithmetic (for example BigInt with a declared
   supported-browser baseline). Test values above 2^53, u64/i64/u128 limits and
   null/zero distinctions. Do not change the existing wire to strings to avoid
   this issue. New producer/manifest decimal-string sizes remain separate.
3. Use safe DOM construction/textContent for all service text; no live API values
   in HTML templates, event attributes or evaluated code. Original icons remain
   static trusted markup. The mockup renderer is not production rendering code.
4. Bound responses, arrays, outstanding requests and refresh state. One refresh
   cycle at a time, bounded deadlines and cancellation; ignore superseded replies.
   Never load all pages or all job details to derive a dashboard-wide metric.
5. Preserve source scope and freshness per response. List/detail/retention reads
   are not one atomic snapshot. An unavailable response is not an empty success.
   Disable mutations while fresh reviewed context is unavailable.
6. Polling and auto-retry do not renew inactivity. Deliberate reads follow the
   session-bound CSRF/activity rule; browser GET need not supply Origin. Mutations
   require the cookie AND CSRF plus strict Origin. Do not persist secrets in
   localStorage, URLs or logs. Session expiry returns to sign-in without changing
   service-owned transfers.

## Implementation handoff

Proceed in bounded increments: (A) define/review the admin native HTTPS audience
and host-local credential verifier setup, including any required dependency
approval and SLES cost/ABI proof; (B) implement session/login/logout and embedded
offline shell with route segregation; (C) implement bounded list and authorized
detail/retention reads plus the lossless browser adapter; (D) integrate real
read-only screens, then refine UI. Retry/cancel/clear/delete follow separately.
Do not hand-write password cryptography or reuse producer leaf identity as admin
authentication. Do not enable unimplemented action buttons in a working read-only
release. Keep their reviewed designs for subsequent increments.

Step 1 is complete when every visual field above has an exact read source,
explicit derivation or omission and the missing runtime boundaries are named.
That is the scope of this document. SLES builds and browser/runtime acceptance
tests belong to actual code changes; none was run or claimed for this mapping.
