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
