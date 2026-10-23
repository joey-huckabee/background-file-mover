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
