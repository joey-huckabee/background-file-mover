# API engineering closeout and protected-ingress specification

2026-11-08. User: "proceed with your recommendations" after release checks.
Base main: `4832459410f14b497460a908d90048d54eadbbfa`.

## Delivered scope

Prepare [one current contract authority](api/API-CONTRACT-CLOSEOUT.md), align
OpenAPI/schema candidate2 and define the [next producer-ingress increment](api/PRODUCER-INGRESS-INCREMENT.md).
No Rust, dependency, schema migration, service/account or operational state is
changed. All eight release gates remain open.

The fifteen-operation inventory stays fixed. Existing producer/v2 and executable
compatibility results are credited without pretending the admin/security routes
exist. Technical dispositions cover per-job retry receipts, capacity refusal,
partial-batch failure, current authorization before admission/receipt disclosure,
read/confirmation bounds, session/credential/throttle limits and route separation.

One consequential engineering correction replaces cross-job full-batch receipt
storage with exact own-job command projections and opaque internal keys. Earlier
full-selection persistence conflicts with group-50 forgetting when one selected
job clears. A job's receipts must not retain other selected IDs/epochs/paths.
Whole ordered request validation still applies on arrival; clearing one job
does not remove other jobs' retry protection.

Invalid fabricated future-ID contexts have no exact-replay guarantee. Rejecting
one before effects does not prove that identical bytes will stay invalid after
later allocation. Clients must discard rejected contexts; no durable rejection
history or human-inspection proof is added.

## Explicit pending product defaults

The four-row table in the closeout is the remaining approval package: skip
completed retries; permanently skip frozen null reviews; cancellation transport
replay uses current state; valid no-work deletion returns 202/zero/not pending.
These affect dashboard counts or repeated-request behavior and are not relabeled
approved by this documentation. Full P01 freeze remains blocked until accepted.
The updated checker prevents schema/OpenAPI from silently claiming otherwise.

## Next implementation boundary

Protected mode uses actual Unix peer credentials and configured generator
binding on a producer-only pathname socket. It has no TCP fallback and needs a
separate private operator HTTP socket, while control.sock remains independent.
Default explicit loopback prototype mode remains unchanged. Initial socket
custody is conservative: unsafe/existing/unproven stale names refuse; clean exit
can remove only the exact newly owned endpoint. Crash-restart socket recovery
must be qualified before shipping lifecycle closure; no blind unlink/repair is
added. TLS proxy selection and admin/session/action implementation stay separate.

This specification does not start a Rust implementation while P01 remains
pending. A later implementation needs independent review and both SLES modes;
no new dependency, remote exposure or account provisioning is authorized here.

## Actual checks and review

Existing WSL Python/jsonschema checks passed: 70 definitions, 108 structural
cases, 11 semantic examples, 15 operation/reference/access checks, seven original
request-identity vectors, existing manifest golden/bound and copied Rust fixture
checks. Retry-header checks passed four known answers and 52 decoding cases.
No encoding-only fixture collection is added. New checks bind the pending
decision set, per-job forgetting/replay metadata and login429 registry across
the candidate artifacts. These are consistency checks, not runtime enforcement.

No Rust build/test, authenticated HTTP/SQL race, consumer acceptance or ingress
qualification is claimed. Credential/session cost, proxy availability and actual
traffic behavior remain unmeasured until their implementations exist; proposed
bounds are requirements to qualify, not latency or availability claims.

Coordinator owns closeout/specification and integration. Existing cloud reviewer
performed a bounded gap pass and identified the full-selection/partial-clear
receipt conflict. Independent review of the prepared increment-120 diff found no actionable
issues. It confirmed the explicit receipt-design revision, invalid-request replay
boundary, pending defaults and producer/operator separation.
Token/cloud cost is unknown. Production NFS/source deletion remain disabled;
no deployment, operational conversion or release publication occurs.
