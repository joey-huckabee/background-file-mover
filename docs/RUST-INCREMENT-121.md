# Frozen v2 contract and protected local producer ingress

2026-11-08. User: "Approved, Proceed" after the four-default package. Base main
`605d01a0af9e77a989117b203039c949f0afc30e`. Implementation branch:
`feature/protected-producer-ingress`. No deployment or operational conversion.

## Approval and implementation

Group 53 approves completed retry skips, permanently nonauthorizing null-review
skips, current-state cancellation retransmission and valid no-work deletion 202
with zero counts/not pending. API-E144-147 and SC-195-198 are appended without
reusing identifiers. The written fifteen-route v2 engineering contract is frozen
as 2.0.0. Existing candidate filenames stay stable for provenance; runtime/admin/
consumer/release qualification is separate from specification freeze.

Implement the bounded [P02 transport](api/PRODUCER-INGRESS-INCREMENT.md), using
existing Tokio/rustix features and dependency versions. Optional
`protected_ingress` selects producer and private operator Unix HTTP sockets;
absence preserves the existing explicit loopback prototype. Protected mode
creates no TCP listener or producer fallback on the operator socket. Existing
control.sock stop/status remains independent.

Producer authorization uses actual Unix peer UID before request context, then
one configured generator header and existing body authorization. Producer
transport permits only POST /api/v2/jobs, never job reads, health, retention or
operator commands. The private operator endpoint requires the mover UID and
keeps current status/command formats. No authentication/session/cancellation/
deletion runtime or TLS proxy deployment is implemented here.

Socket custody checks kernel mount metadata before traversing local paths,
rejects aliases/unsafe ancestors and requires preprovisioned exact owner/group/
modes. Both parent directories must be disjoint from state and payload roots.
Validate both names before SQLite inspection; existing/stale/foreign names refuse,
never auto-unlink. Compatibility inspection then checks both parents against all
retained payload roots, including historical destinations. Bind under instance/
lifetime ownership before source bootstrap;
activate nonblocking Tokio listeners only on the reactor after startup. Listener
descriptors stay close-on-exec. Clean exit removes only the original socket
device/inode under the still-validated parent; substituted names remain untouched.
Unproven stale sockets after crashes remain a documented shipping-lifecycle gap.

Six producer slots share the existing eight-connection budget, reserving two for
local HTTP. Excess producers get 429 and one-second retry guidance. Framing,
header/body limits, five-second input read, ten-second handoff, immutable UUID
replay and existing source/worker safety remain unchanged. No unbounded request
queue or temporary body file is introduced. Endpoint changes stop ingress;
source state/custody stays authoritative and no replacement is adopted.

## Actual validation status

CI now runs the actual-peer checker after its production gate and retains that
report; both matrix modes run the eight portable checker tests. Changed checker
paths trigger the workflow. This automation is not a pass claim.

Final production/qualification SLES and actual-peer checker results will be
recorded before integration. Required gates remain mandatory. Current source
formatting and strict Clippy pass; the fresh local production gate is running.
No complete gate or actual-peer pass is inferred from that intermediate progress.

Three new filesystem tests cover preserved existing/symlink names, private-parent
refusal, exact-inode cleanup/replacement preservation and actual exec descriptor
closure. A new API CLI regression tests operator paths at jobs.sqlite-journal,
workers.next and operator.sock under state: exact configuration refusal before
either endpoint, instance guard, DB or enrollment creation. These are disposable
fixtures; final target results are reported below when complete. A second API
regression seeds a foreign producer endpoint and compares every SQLite file
name/byte before and after refusal. It also changes the configured destination
and verifies refusal against the old retained destination, preserving its
payload and manifest bytes. Control availability and durable worker-epoch
coverage remain active through this preflight.

The new `scripts/check-producer-ingress.py` uses retained passed production gate
artifacts, checks committed source blobs/archive/ELF/executable hashes, and runs
both debug/release in the pinned network-disabled SLES container. Mover UID 1000,
proxy 1001, wrong 1002 and root 0 execute with actual credentials, no capabilities
and no-new-privileges. Its finite cases exercise route/header isolation, exact
UUID/v2 content, unread-response handoff/replay/path reuse, six-producer/two-local
capacity, private control responsiveness, clean restart, unsafe/stale/live socket
refusal and substituted-name preservation. It is not real TLS/NFS/systemd,
legacy lifecycle or crash-repair qualification. All64 existing/new Python tooling tests pass, including eight portable helper
tests;
actual target execution is pending the finalized production gate.

Existing contract/reference checks pass: 70 definitions, 108 structural cases,
11 semantic examples, 15 operations, seven unchanged identity vectors, original
manifest golden/bound and Rust fixture copies; retry-context checks pass four
known answers and 52 decoding cases. No encoding-only fixture workstream added.

## Review and retained failures

Coordinator owns Rust integration, gate queue and delivery. Existing cloud child
independently reviews source, later deltas and the externally authored checker;
one temporary specialist owns only its two new Python files. No fixed quality
percentage or measured token/cloud cost is claimed.

Freeze review caught two stale approval/scope summaries, corrected. Runtime
review found operator/state overlap: it could occupy reserved recovery names
after compatibility inspection. The symmetric exclusion and actual CLI regression
address it. The first local run `20261108T213500Z-734617d8` was interrupted by its
verified owned PID 775321 for that source fix; FAILED report and clean cleanup
remain retained, with no full pass claimed. Superseded CI is likewise retained.

Driver review caught missing protection assertions for producer-reused leaves;
both replay stages now verify exact replacement bytes, original numeric claims
and destination output in addition to unchanged manifests. Follow-up bounded
reviews found no further actionable source/driver findings. CI review also caught
a missing shared-helper trigger, now included in both workflow path filters.
The coordinator also
aligned the operator's absent producer route with its existing 404/local envelope.

Actual-target checker development retained four failed reports, each with clean
container cleanup. The first exposed Podman archive-copy ownership rewriting;
`--archive=false` retains the fixture's numeric IDs without new capabilities.
The minimal target lacks MIME::Base64, so Perl transport now uses core hex
packing in bounded argument chunks. The second local report included OCI startup
in a responsiveness measurement; prestarted real-UID clients now synchronize
through fixture FIFOs and measure inside the container, preserving all service
deadlines and timeout assertions.

The third and fourth reports exposed SQLite WAL/shared-memory file creation
before foreign-endpoint refusal. Original database and payload hashes stayed
unchanged, but the strict unchanged-file assertion correctly failed. The fix
validates/holds both endpoint plans before SQLite and binds only after
compatibility/retained-root checks. No assertion was relaxed and no old report
was relabeled as passing. These failures and the superseded production pass
remain historical evidence; only fresh final-source runs qualify this increment.

Operator instructions: [protected local ingress](RUST-OPERATOR-GUIDE.md#opt-in-protected-local-http-ingress).
All eight FR gates remain open. Remote proxy/certificate operations, shipping
account/confinement and stale-socket lifecycle, remaining NFS/durability/capacity,
cleanup, admin/actions, consumer and release walkthrough stay separate. Production
NFS/source deletion remain disabled; no operational-state/account change occurs.
