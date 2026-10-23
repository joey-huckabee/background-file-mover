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
