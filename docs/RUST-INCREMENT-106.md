# Rust increment 106: REST error-scenario review draft

## Outcome and review boundary

The user requested an error-scenario inventory and then review/agreement before
implementation. [REST-ERROR-SCENARIOS.md](REST-ERROR-SCENARIOS.md) records sixty
stable API-E01-60 review keys, current behavior alongside recommendations, seven
open decisions and a six-step implementation/acceptance sequence within P01 and
its dependent release packages. The eight release gates remain open.

Capture the agreed explicit-file/full-source-path/global-recording-ID workflow,
whole-set 202 custody, same-ID conflict and success replay. Identify differences
from the current submission_id/source_path/file-object model. Global uniqueness,
recording-ID layout and the discussed envelope are not claimed as implemented.
Existing optional size assertions are not silently removed. Source missing-file
409/true is a recommendation awaiting agreement; current 503 handoff_pending,
missing deadline review and audited reset remain unchanged.

Separate confirmed missing input from uncertain pending NFS work; source/caller
permissions; pre-202 handoff from post-202 delivery; application retry flags from
proxy/TLS/no-response behavior; and REST from the stop/status Unix protocol.
Global duplicate-ID responses must not leak another generator's job information.
No new code/effect authorization, false release, deadline reset, automatic ID
replacement or cancellation follows from an error mapping.

## Documentation and implementation plan

Link the draft from the API, scenario catalog, roadmap, release checklist,
closure plan and handoffs. Preserve 138 SC and six DOC identifiers; API review
keys are not new passing scenarios or replacement requirement IDs. DOC-01 needs
the approved retry table; DOC-03/04/05 need operator, transport and recovery
explanations. Review groups incrementally, beginning with missing/pending/review.
After agreement, freeze schema/code registry, design durable global-ID/wire
compatibility, implement typed proven causes and response mapping, qualify exact
cases, and run required SLES gates for every Rust build/test.

## Validation and limitations

Check local links, sixty unique sequential API review IDs, seven decision IDs,
coverage of existing literal application error codes, scenario-ID stability and
diff whitespace. Runtime sources, dependencies, fixture scripts and retained
SLES evidence are unchanged. This is documentation-only: no Rust build/test,
NFS/systemd run or new compatibility pass is claimed. Production NFS and source
deletion stay disabled; registration and offline repair remain deferred.

HTTP status meanings were checked against RFC 9110 and RFC 6585, linked in the
draft. Application names, missing-input mapping and recorder fallback behavior
are design recommendations, not standards-mandated choices. No full error
contract is frozen by committing this draft.

Documentation checks passed for ten Markdown files: local links, all sixty
sequential API-E rows and seven ER-D decisions, all 31 currently emitted literal
application error names, and unchanged 138 SC/six DOC IDs. Both retained SLES
source archive hashes and their current runtime input bytes match. Diff
whitespace is clean. No new runtime/fixture tests or qualification passes.

## Subsequent contract review: groups 1-3 approved

On 2026-10-23 the user approved fourteen mappings covering missing/pending/review
and ID conflict, validation/source scope/expected size, and temporary source
capacity/retention/queue/shutdown. The authoritative approval table is in the
error-scenario document. ER-D01 is resolved: confirmed missing file is retryable
409 within the existing window, not pending 503; current runtime is unchanged.
Remaining scenarios and compatibility/envelope decisions still require review.
No runtime builds/tests or new qualification results follow from this approval.

## Subsequent contract review: groups 4-6 approved

The user also approved four custody/permission refusals, five database/transport
outcomes and six HTTP request errors: groups 1-6 now contain 29 approved
mappings. Persistent transport failures require alerting as well as backed-off
same-ID retries; exact retry parameters remain under review. Database corruption
and unsafe ownership remain stop/review conditions. Record body/header-specific
413/431 codes and the 405 Allow requirement as approved implementation work, not
present functionality. Remaining remote, response/fallback and operator variants
are not approved by implication. Runtime sources and all 138 SC/six DOC IDs stay
unchanged; no Rust/fixture qualification is run for these documentation approvals.

## Subsequent contract review: groups 7-9 approved

The user approved five remote-access outcomes, three post-202 conditions and
six local operator outcomes. The approval table now contains 43 mappings across
nine groups. Remote authentication remains unimplemented; registration stays
deferred. Successful operator status 200 is not delivery completion or a new
producer release; existing retry/review policy and consumer manifest validation
remain authoritative. Exact operator command replay preserves its original
receipt and cannot reset later review. Request edge cases, response/fallback,
source-allocation classification and exact retry rules remain under review.
All runtime/qualification evidence and existing scenario IDs are unchanged.

## Subsequent contract review: groups 10-12 approved

The user approved four remaining request rejections, conservative uncertain-source
refusal, retryable internal_error and invalid-success acknowledgement refusal.
There are now fifty approved outcome rows across groups 1-11. Group 12 approves
the common mover error envelope: recording_id/error/retryable/retry_after_seconds/
source_paths_released, null recording ID when unavailable or unsafe, null delay
when retry is disallowed, and no new release on an error. TLS/proxy responses
need not carry that JSON. Five seconds remains illustrative pending retry timing
review. Do not add a source-capacity-specific retry code in the initial contract.
Global-ID persistence/wire compatibility and precise schemas remain P01 work.
Documentation-only checks preserve the sixty review IDs and 138 SC/six DOC IDs;
no runtime/fixture builds, tests or new qualification are claimed.

## Subsequent contract review: retry timing approved (group 13)

Honor a valid mover delay when retryable, then valid Retry-After without usable
JSON timing, then configurable fallback 5/10/20/30 seconds capped at 30.
The configurable five-minute persistent-failure warning does not stop permitted
retries or release paths. A false retry flag wins over headers; TLS validation
and invalid acknowledgement refusals do not become transient by losing JSON.
This recorder guidance changes neither the mover's missing-file deadline nor
background delivery retry/review intervals. Consolidate API-I01-06: registry and
schema, durable global IDs/compatibility, local mapping, protected remote access,
operator/user guidance, and exact-case/SLES qualification. Remaining request and
schema details still precede implementation. No recorder executable or new
notification system is introduced. Runtime/fixture evidence is unchanged.

## Subsequent schema clarification: no prototype API clients

The user confirms no one uses the Rust prototype API. Resolve ER-D05's wire
compatibility question: directly replace submission_id/source_path/file objects
with the reviewed recording_id/source_directory/string-file producer form; no
adapter, dual schema or deprecation obligation for unused prototype clients.
Add the reviewed minimal JSON to the API draft, clearly above historical/current
examples. This does not remove optional size assertions, discard stored jobs or
waive C++ cutover. Global-ID stored-state migration/refusal and precise schema
rules still require design. Documentation only; no runtime/qualification change.

## Subsequent contract review: expected-size policy approved (group 14)

The user requests documentation of the disabled-checking scenario and accepts
ignoring a complete expected_sizes_bytes map when checking is off. Checking is
default-disabled; enabled requires a complete map and compares every size.
Partial/extra/invalid maps remain invalid in both modes. An expected 100-byte
value for an actual 200-byte file does not prevent normal claim processing while
disabled; record/copy/verify actual 200 bytes. Enabled mismatch remains 409
source_size_mismatch; missing required or malformed/incomplete map is 400
invalid_submission. Preserve immutable request replay, partial custody and
mandatory actual-size/hash/destination verification in either mode.

Add SC-139 and API-E61-66 as approved-contract, implementation/qualification
pending scenarios. Preserve all prior 138 SC and sixty API review identifiers;
there are now 139 SC and sixty-six API situations. Update DOC-01/03/05 guidance
obligations, request example notes, roadmap and handoffs. Exact config spelling
and persisted-policy handling across retry/restart remain design work, not
implicitly implemented features. No runtime/dependency/fixture changes or new
Rust/NFS/SLES qualification; production NFS and deletion remain disabled.

Group-14 documentation checks pass: six new API cases, concrete complete-map
JSON, policy/example anchors and existing local links, unchanged original 138 SC
IDs plus SC-139 (139 total), unchanged six DOC IDs and fifty initial approval
rows. Both retained SLES source archives still match current runtime inputs.
No new Rust build/test, fixture run or compatibility result is claimed.

## Subsequent direction: current size policy, no per-job snapshot (group 15)

The user rejects the proposed per-recording expected-size setting as too complex
and expects new configuration to govern existing work. Revise that policy to use
the current startup value for pending size checks on existing partial recordings.
No per-job policy snapshot/version or hot reload. Off-to-on enforces the current
complete-map/size rules; on-to-off removes an expected-size-only barrier on the
next original-ID retry. Keep unrelated review/safety rules and actual-size,
private custody and integrity evidence. Completed handoff still replays 202,
including a lost reply and producer-reused paths; current policy cannot undo a
confirmed effect. Do not add autonomous claiming or a new repair command.

Add planned SC-140/API-E67-70 and DOC-01/03/04/05 obligations. Existing 139 SC
and 66 API IDs remain stable; totals become 140 SC and seventy API situations.
No runtime, dependency, fixture or compatibility evidence changes; production
NFS/source deletion remain disabled. This decision addresses expected-size
checking; it does not silently rewrite other settings' authorization contracts.

Group-15 documentation validation passed: four new restart cases, seventy API
review IDs, six implementation steps, unchanged previous 139 SC IDs plus SC-140
(140 total), six DOC IDs, valid policy anchors/local links and unchanged source
bytes/hashes in both retained SLES archives. No new runtime qualification.

## Resumed review: file-list order is immaterial (group 16)

The user approves same-ID file-list permutations as equivalent requests when
all other values remain unchanged. Match sizes by path; preserve existing durable
file indices/claims/deadlines, partial handoff/review and committed replay.
Duplicates stay invalid and changed membership/path/assertions still conflict,
including size assertions whose comparison is disabled. Add planned SC-141 and
API-E71-72 with accepted/partial/claimed/committed and negative-control variants.
All previous 140 SC/seventy API IDs remain stable; totals become 141 SC and 72
API review situations. Runtime still compares ordered lists; no new tests or
compatibility evidence. Update next-session pointers to ID syntax/retention/
concurrency rather than asking file ordering again. Production NFS/deletion stay
disabled; OpenAPI and implementation still await remaining contract decisions.

Group-16 documentation checks passed: all 72 API IDs, original 140 SC IDs plus
SC-141 (141 total), six DOC IDs, policy links/anchors and next-step handoff.
Both retained SLES source archive hashes and archived runtime inputs remain
unchanged. No new Rust build/test, fixture run or qualification pass.

## Resumed review: UUID recording_id required (group 17)

The user approves required UUID recording_id. Recorder generates it once and
retains it for every retry; mover still enforces global uniqueness, authorization
and original request replay. Non-UUID new input maps to existing 400
invalid_submission/false. No automatic UUID-version restriction, new package
experiment, internal job-ID change or disposal of stored custody follows from
this requirement. Add planned SC-142/API-E73-74; preserve previous 141 SC and 72
API IDs, with totals now 142 SC and 74 API situations. Current free-form
prototype is unchanged. Next discuss ID retention and concurrency; lexical
canonicalization belongs in the precise schema. No new Rust/NFS/SLES result.

## Resumed review: manual detailed-history retention (group 18)

The user declines compact-record retention and selects detailed job history until
an administrator explicitly clears it through the dashboard. Record no automatic
expiry/pruning/compact-only replacement. Post-clear UUID recognition/late retries,
clear eligibility, admin access/audit/capacity and dashboard release placement
remain undecided; do not assume indefinite tombstones or forgetting is approved.
The requested workflow needs scope planning, not blanket deferral or an immediate
unapproved dashboard implementation. History clear does not grant file deletion
or loss of ownership evidence. Add planned SC-143/API-E75; preserve previous 142
SC/74 API IDs. Runtime/history-clear endpoints and qualification remain unchanged.

## Resumed review: forget cleared UUIDs; cancel first (group 19)

The user explicitly approves forgetting recording UUIDs with an admin history
clear; a later submission under one is new work, not replay of an old 202.
No deduplication tombstone/compact completion receipt survives for that UUID.
Only completed or safely cancelled jobs may be cleared. Unfinished and errored/
review jobs require cancellation first; a mere request, signal, timeout or blocked
worker is not completed cancellation. Preserve required ownership/actual data
facts and normal source/destination no-clobber rules; clear is not a file-delete
or overwrite grant. Design cancellation data disposition and exact admin wire,
transaction/bulk/concurrency/audit before implementing these requested controls.

Add planned SC-144/145 and API-E76-80. Preserve original 143 SC/75 API IDs;
totals are now 145 SC/eighty API situations and six DOC rows. Remove superseded
statements that clear eligibility and UUID forgetting are still undecided, and
advance handoff/roadmap to remaining cancellation/admin contract work. No runtime,
dependency, source-deletion, NFS enablement or qualification result changes.

Group-19 documentation validation passed: eighty API IDs, previous 143 SC IDs
plus SC-144/145 (145 total), six DOC IDs, five clear/cancel acceptance cases,
policy links/anchors and unchanged source hashes/bytes from both retained SLES
archives. No new Rust build/test, fixture run or qualification result.

## Resumed review: preserve files on cancellation (group 20)

The user approves preserving files on cancellation and asks to document scenarios
before deciding what happens to them at history clear. Record unclaimed source,
private claims, partial destination staging, published payloads and valid manifest
preservation; no automatic restore/delete or withdrawal of a valid 202. Stop new
work and reconcile authorized effects: pending manifest publication may complete,
and blocked/live workers or uncertain storage effects prevent safe cancelled/
clear status. Keep actual ownership/custody and space accounting. Existing data
already removed by an earlier authorized effect cannot be restored by cancellation.

Add planned SC-146/API-E81-86 and DOC-01-05 obligations, update transfer protocol
and next-session handoff. Previous 145 SC/eighty API identifiers remain unchanged;
totals are now 146 SC/86 API situations and six DOC IDs. File disposition and any
operational records at history clear remain undecided; do not add a ledger, repair
tool or physical deletion feature by implication. No runtime, dependency,
production NFS/deletion or qualification changes.

Group-20 documentation checks passed: six cancellation cases; all 86 API review
IDs; previous 145 SC IDs plus SC-146 (146 total); six DOC IDs; policy links,
transfer-protocol consistency and next-step handoff. Both retained SLES source
archives match unchanged runtime inputs. No new Rust/fixture qualification.

## Resumed review: history clear preserves files; separate admin deletion (group 21)

The user accepts file preservation on history clear and requires a separate
explicit admin action to delete retained data. Keep necessary operational file
ownership/accounting after clear, independently of detailed history and old UUID
recognition. Do not hide full history/dedup tombstones in that tracking. Retained
bytes remain occupied/charged; old files cannot be adopted or overwritten by a
new job under a forgotten UUID. Plan atomic custody/history transitions and
original internal operation targeting; exact storage/transaction design remains
unimplemented. Separate deletion scope, eligibility, permissions/confirmation,
config interaction and recovery are the next contract decisions; do not execute
physical deletion or add a general orphan/repair tool by implication.

Add planned SC-147/148 and API-E87-91. Preserve original 146 SC/86 API IDs;
totals are now 148 SC/91 API situations and six DOC IDs. Update protocol, admin
workflow, capacity/user documentation obligations and next-session pointers.
No runtime, dependency, fixture, NFS/deletion enablement or qualification changes.

Group-21 documentation checks passed: five new history-clear/retained-data cases;
91 API IDs; original 146 SC IDs plus SC-147/148 (148 total); six DOC IDs; policy
links/anchors and transfer-protocol/handoff agreement. Both retained SLES source
archives match current runtime bytes/hashes. No new Rust build/test, fixture run
or qualification result is claimed.

## Resumed review: confirmed owned retained-data disposal scope (group 22)

The user approves deleting only mover-owned retained source and unfinished
destination after work safely stops, with confirmation and protection for
unclaimed originals/completed recordings. Record original identity/root evidence,
current selection/ownership revalidation, blocked-worker/uncertain publication
refusal and cleared/reused UUID isolation. Explicit disposal may remove a
cancelled recording's only source copy; it is not successful delivery or a
relaxation of automatic postcommit cleanup. Preserve completed-output protection
independently of cleared history and keep production deletion/NFS disabled.

Add planned SC-149/150 and API-E92-98 (seven cases). Preserve original 148 SC/91
API identifiers; totals become 150 SC/98 API situations plus six DOC IDs. Update
protocol/user obligations and advance the next question to partial-failure/retry,
then admin access/configuration and exact wire/bulk/confirmation. No new deletion
endpoint, retry budget, physical effect, orphan repair tool, Rust/fixture run or
compatibility result is claimed.

Group-22 documentation checks passed: 98 API cases, 150 unique SC IDs and six
DOC IDs; original identifiers preserved; policy links/anchors and handoff agree.
Both retained SLES source archives match unchanged runtime inputs. No new Rust
build/test, fixture run or compatibility qualification is claimed.

## Group-22 clarification: keep deletion failure simple

The user rejects a dedicated partial-deletion pause/retry workflow. Deletion is
best effort: failed files stay behind, other independently safe confirmed files
may be attempted and failures are reported. No automatic retry scheduler,
dedicated paused state, resume protocol or deletion-receipt subsystem is required.
An admin can request deletion again for remaining eligible files. Preserve the
agreed ownership, confirmation, actual stopped-work and protected-file checks;
unknown outcomes are not proof of removal. Refine API-E97/SC-150 in place,
without new scenario IDs. This supersedes earlier next-step failure/retry
questions. Next settle admin access/configuration and wire details.
Documentation only; no runtime, build/test, fixture or production gate changes.

## Resumed review: manual deletion independent of automatic cleanup (group 23)

The user approves manual deletion even when automatic cleanup is disabled.
Keep the separate confirmed admin action and all group-22 ownership, safe-stop,
protected-file and best-effort rules. Do not silently enable background cleanup
or production deletion. Add API-E99/SC-151; preserve prior identifiers, with
99 API cases, 151 SC IDs and six DOC IDs. Next decide admin access, then wire
and confirmation details. No runtime, Rust build/test or fixture change.

## Resumed review: remote admin dashboard access (group 24)

The user requires dashboard access from another computer. Add API-E100/SC-152
without renumbering earlier cases (100 API/152 SC/six DOC IDs). Preserve the
separate recorder/admin boundary and existing admin action rules. Sign-in,
authorization and browser/session/request protection remain to agree; next ask
whether an organizational sign-in system is available. Update the producer
access contract to distinguish its local-operator scope from this new requirement.
No remote ingress, account system, runtime, Rust build/test or fixture change.

## Resumed review: simple admin username/password (group 25)

The user selects admin username/password and explicitly wants to avoid an
in-depth cybersecurity project for the first release. Record the minimal login
scope, defer SSO/advanced account features and retain ordinary login hygiene as
implementation detail. Keep producer/admin separation and all existing operation
protections. Add API-E101/SC-153 (101 API/153 SC/six DOC IDs), without renumbering.
Finalize minimal credential setup/session/wire rather than re-asking login type.
No credential, authentication dependency, remote listener, Rust build/test,
fixture or production NFS/deletion change.

## Resumed review: host-local admin account setup/password changes (group 26)

The user approves one configured admin account, set up and password changed
locally on the mover host. Remote dashboard account-management/reset screens
are not required. Add API-E102/SC-154 without renumbering existing IDs: 102 API,
154 SC and six DOC IDs. Next decide existing-session behavior after password
change; activation/configuration format remains implementation design. Credential
changes do not themselves alter jobs/history/files. No runtime, dependency,
Rust build/test, fixture or production gate change.

## Resumed review: password-change session invalidation (group 27)

The user approves signing out every existing dashboard session when the admin
password changes, without affecting background transfers. Preserve job/history/
file lifecycle and already-authorized effect handling. Add API-E103/SC-155,
preserving prior IDs (103 API/155 SC/six DOC). Specify service-enforced invalidation
when new credentials become active, without old-session resurrection after
restart; activation/session mechanism remains to design. Next decide inactivity
expiry. Documentation only: no runtime, dependency, Rust build/test, fixture or
production gate change.

## Resumed review: configurable dashboard inactivity expiry (group 28)

The user approves 30 minutes of inactivity by default, configurable, with no
background-transfer effects. Add API-E104/SC-156; preserve prior IDs (104 API,
156 SC/six DOC). Expiry requires fresh admin sign-in; automatic polling alone
is not user interaction. Keep password-change invalidation and all operation
protections. Config bounds/activity reporting remain implementation details;
no disable option or absolute lifetime selected. Next decide session behavior
across mover restart. No runtime, Rust build/test, fixture or production gate
change; documentation-only verification applies.

## Resumed review: dashboard sign-out on mover restart (group 29)

The user approves invalidating existing dashboard sessions on mover restart,
with jobs recovering normally. Add API-E105/SC-157 without renumbering prior
cases (105 API/157 SC/six DOC). Preserve original durable state/custody, retry/
review deadlines and startup/ownership checks; sign-out is not job cancellation
or a promise of immediate recovery despite unsafe state. Next decide confirmation
for clearing eligible history; retained-data deletion confirmation is settled.
Documentation only; no runtime, dependency, Rust build/test, fixture or production
gate change. Session implementation and exact wire details remain pending.

## 2026-10-24 review: explicit history-clear confirmation (group 30)

The user approves confirmation showing selected jobs and explaining forgotten
UUIDs with preserved files. Add API-E106/SC-158 without renumbering (106 API,
158 SC/six DOC). Decline/dismiss clears nothing; revalidate eligibility and do
not include unshown jobs or authorize file deletion. Keep a simple confirmation;
no extra password/typed phrase protocol implied. Next decide mixed eligible/
ineligible selection behavior, then finalize exact wire/transaction design.
Documentation only; no runtime, Rust build/test, fixture or production gate change.

## 2026-10-24 review: eligible-only history clear, no skip reasons (group 31)

The user approves clearing eligible selected jobs and skipping the others,
without reporting reasons and without automatic cancellation. Add API-E107/
SC-159 without renumbering (107 API/159 SC/six DOC). Recheck eligibility, preserve
skipped job/history/UUID/file state and exact confirmed selection identity.
Actual storage/request failures must not be reported as successful clears.
Next decide explicit cancellation confirmation; clear/delete confirmation is
settled. Exact summary/wire/transactions remain implementation design.
Documentation only; no runtime, Rust build/test, fixture or production gate change.

## 2026-10-24 review: selected-job cancellation confirmation (group 32)

The user approves confirmation before cancelling jobs, showing the selected jobs
without explanation. Add API-E108/SC-160 without renumbering (108 API/160 SC/
six DOC). Dismiss/decline cancels nothing; target confirmed internal job identities
only. Preserve group-20 file preservation, pending cancellation, commitment and
safe-stop rules without requiring explanatory dialog text. Next decide terminal/
mixed-selection cancellation behavior, then exact wire/transaction details.
Documentation only; no runtime, Rust build/test, fixture or production gate change.

## 2026-10-24 review: unfinished-only cancellation selection (group 33)

The user approves skipping completed/already-cancelled selected jobs without
reasons and requesting cancellation only for unfinished jobs. Add API-E109/
SC-161 without renumbering (109 API/161 SC/six DOC). Recheck current state,
preserve skipped jobs/commitment and existing pending cancellation, and never
reset deadlines or claim safe exit/settlement from a repeated request. Preserve
original job identity, files/history and group-20 safety rules. Next decide
whether safely cancelled jobs may resume; no resume protocol is implied yet.
Documentation only; no runtime, Rust build/test, fixture or production gate change.

## 2026-10-24 review: final cancellation; failed-work retry stays separate (group 34)

The user approves final cancellation for the first release with preserved files.
Keep eligible failed-work retry separate; do not revive cancelled jobs through
resume/retry/restart or retained-UUID resubmission. Preserve prior whole-set 202,
pending cancellation settlement and distinct history-clear/new-submission rules.
Add API-E110/SC-162 without renumbering (110 API/162 SC/six DOC). Exact cancelled-
job producer/admin response mappings remain to finalize, as does failed-work
retry confirmation. No retry timing/review policy, runtime, Rust build/test,
fixture or production gate change; documentation-only increment.

## 2026-10-24 review: failed-work retry needs no confirmation (group 35)

The user rejects confirmation for retry. Submit eligible failed-work retry
directly while retaining authentication, original identity/custody, eligibility
and existing audited review/command checks. Preserve final cancellation and
required cancel/clear/delete confirmations. Add API-E111/SC-163 without
renumbering (111 API/163 SC/six DOC). Next consolidate admin requests/responses
and remaining schema details; no further retry-confirmation question needed.
No runtime, retry timing/review policy, Rust build/test, fixture or production
gate change; documentation-only verification applies.

## 2026-10-24 review: cancelled producer retry and durable handoff (group 36)

The user approves 409 recording_cancelled/false before completed durable handoff
and established 202 replay after completed handoff, including lost responses.
Use the agreed error envelope/null delay/no path release before handoff; preserve
final cancellation/files without reviving delivery or reopening reused originals.
Add API-E112/113 and SC-164 (113 API/164 SC/six DOC); preserve prior IDs.
Pending cancellation still needs safe settlement. Next decide admin cancellation
acknowledgement while workers stop, separate from producer custody 202.
Documentation only; no runtime, Rust build/test, fixture or production gate change.

## 2026-10-24 review: accepted admin cancellation and pending safe stop (group 37)

The user approves admin cancellation HTTP 202 Accepted, Cancellation pending
until work safely stops, then Cancelled. Add API-E114/SC-165 without renumbering
(114 API/165 SC/six DOC). Distinguish accepted admin intent from producer custody
202 and preserve files/ownership, pending-operation recovery and clear/delete
restrictions. Do not alter shutdown waits or infer safety from timeout/sign-out.
Exact persistence/body/bulk response remains design work. Next decide admin
failed-work retry acknowledgement; no retry confirmation required.
Documentation only; no runtime, Rust build/test, fixture or production gate change.

## 2026-10-24 review: accepted failed-job retry 202 and actual progress (group 38)

The user approves HTTP 202 Accepted for accepted failed-job retry, without
confirmation, and display of actual progress without implying success. Add
API-E115/SC-166 without renumbering (115 API/166 SC/six DOC). Preserve original
job/custody, current eligibility and existing audited review/command checks;
request acceptance is not execution, delivery or publication success. Exact
request/body/idempotency/progress wire remains pending. Next decide completed
history-clear response, preserving eligible-only clearing and silent skips.
Documentation only; no runtime, retry policy, Rust build/test, fixture or
production gate change.

## 2026-10-24 review: completed history clear 200 and actual count (group 39)

The user approves 200 OK with the number of jobs cleared, silent ineligible skips
and files untouched. Add API-E116/SC-167 without renumbering (116 API/167 SC/
six DOC). Count actual applied clears, not selected/attempted/unknown work; zero
is valid if none qualify. Preserve original job identity, confirmed selection,
UUID forgetting and separate retained-file ownership/accounting. Exact field,
error/transaction/idempotency details remain to finalize. Next decide manual
deletion acknowledgement/result while keeping best-effort handling simple.
Documentation only; no runtime, Rust build/test, fixture or production gate change.

## 2026-10-24 review: manual deletion 202 and deleted/failed counts (group 40)

The user approves 202 Accepted for manual deletion and dashboard counts of files
deleted/failed, without automatic retries or special recovery workflow. Add
API-E117/SC-168 without renumbering (117 API/168 SC/six DOC). Keep best-effort
handling, actual outcomes/accounting, remaining-data protection and all original
confirmation/ownership/safe-stop/protected-recording rules. Exact count/status/
interruption wire remains design work; do not fabricate success for unknown
attempts. Next finalize admin selection identifiers and compact wire schemas.
Documentation only; no runtime, Rust build/test, fixture or production gate change.

## 2026-10-24 clarification: use existing job_id/state for deletion

The user clarifies that deletion should evaluate state under the existing job_id
being targeted. Do not introduce another admin identifier scheme or re-ask this
as a new choice. Clarify group 40/API-E117/SC-168 in place; counts stay 117 API,
168 SC/six DOC. Preserve current eligibility, retained-file ownership/accounting,
confirmation/safe-stop/protected-file rules and history-clear UUID forgetting.
Next consolidate exact admin wire schemas around the existing identity/state.
Documentation only; no runtime, storage redesign, Rust build/test, fixture or
production gate change.
