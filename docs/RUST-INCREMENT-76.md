# Rust increment 76: observe buffered worker synchronization

## Scope and acceptance

Observe eight healthy qualification workers: claim (`claim_apply`) and delivery
(`copy_chunk`), debug/release, same-share/separate-share NMP-41B roots. Source and
destination are NFS; state/configuration/SQLite/ownership stay local. Keep
production NFS and post-delivery source deletion disabled. No Rust, dependency,
schema, retry/review policy or shutdown deadline changes are introduced.

Retain the mount-profile runner's `--buffered-sync`, dedicated helper, independent
verifier, raw syscall/RPC records and step-by-step infrastructure documentation.
Repeat 43 model/inventory controls. Require actual worker security, clock identity
of each live observer/client/active relay, successful synchronization returns,
complete mount-ID accounting, source/state preservation and normal Committed
attempt 1 with validated manifest. The recorder retries identical JSON/IDs until
confirmed 202, then can reuse producer paths with no monitoring duty.

Run an independent native 4 KiB buffered dirty-write/fsync discovery on each
layout. Withhold only a decoded WRITE/COMMIT observed inside both service and
native synchronization intervals. For any eligible operation require matched
successful reply held, actual native fsync pending, server-local identity/content
proof, release and discard-plus-connection-interruption recovery with validated
replay/resend. Otherwise record an unavailable service-matching capability. Do
not synthesize a COMMIT or substitute OS controls for service failure recovery.

## Initial fixture finding and correction

Initial run `mount-profile-20261019T150239Z-dda8b1b6` completed eight healthy
service traces and its runner reported PASSED with cleanup_errors=[]. Independent
inspection found the separate-share native discovery watched only the destination
relay. Actual service traffic used the source relay while the destination relay
had zero records. Mount address alone did not identify the transport. The service
traces already captured both relays, but the native discovery's empty wire window
was insufficient capability evidence. Its source-only same-share native discovery
decoded WRITE inside fsync; the incorrect destination-only discovery decoded none.

Retain the entire original report and all 21 exact driver snapshots in
[initial evidence](RUST-NFS-BUFFERED-SYNC-INITIAL-EVIDENCE.json), explicitly marked
REJECTED_SCOPE for final capability qualification. This preserves the original
runner result without promoting its incomplete observation. No service/data
defect or policy change is inferred from this fixture error.

Correct native discovery to capture every active relay, verify their actual
clock identity, correlate combined raw records and select any withholding relay
from positive decoded discovery traffic. Use full NFS mount-ID observations,
including exact roots, for service candidate operations. Rerun all eight worker
cases and both native discoveries using new exact driver snapshots; keep the
initial attempt separate. The helper's descendant-only `nfs_syncs` convenience
field remains available, but the independent audit derives authoritative totals
from full `trace`/`wire` and mount IDs.

## Results

Corrected run `mount-profile-20261019T151733Z-90641161` **passes** all eight healthy worker traces,
43 model/inventory controls, seven decoder tests and both native discoveries,
with cleanup_errors=[]. The [lossless raw evidence](RUST-NFS-BUFFERED-SYNC-EVIDENCE.json)
retains all 21 exact drivers, actual clocks/security/mounts, syscall and RPC
payloads, handoff/replay/commit and cleanup records. The client reports
`glibc 2.22` on shared modern kernel `6.18.33.2-microsoft-standard-WSL2`.

| Layout | Profile | Worker | NFS syncs | Requests / replies inside sync | Broader calls / undecoded calls |
|---|---|---|---:|---:|---:|
| same-share | debug | Claim | 8 | 0 / 0 | 993 / 44 |
| same-share | debug | Delivery | 20 | 0 / 0 | 702 / 31 |
| same-share | release | Claim | 8 | 0 / 0 | 989 / 40 |
| same-share | release | Delivery | 20 | 0 / 0 | 709 / 37 |
| separate-shares | debug | Claim | 8 | 0 / 0 | 995 / 46 |
| separate-shares | debug | Delivery | 20 | 0 / 0 | 711 / 39 |
| separate-shares | release | Claim | 8 | 0 / 0 | 995 / 46 |
| separate-shares | release | Delivery | 20 | 0 / 0 | 712 / 39 |

All **112** observed NFS fsync/fdatasync calls return zero. Full mount-ID
accounting includes exact role roots; it does not depend on descendant-only
convenience fields. There are **zero outgoing calls, zero incoming replies and
zero captured request/reply pairs spanning sync entry** in these intervals.
The broader windows contain 6806 outgoing calls,
including 322 undecoded compounds,
32 decoded WRITE operations and eight decoded COMMIT operations. Those positive
broader-window observations are preserved, not described as absent. They do not
establish which worker/syscall caused them: windows can include another worker
or background I/O. Requests outside the capture or without captured replies
remain outside the paired-history analysis.

Both native 4 KiB discoveries decode WRITE inside actual fsync with matching
live clock identities. Corrected separate-share discovery captures six records
through the source relay and zero through the destination relay, confirming why
both had to be observed. No outgoing WRITE/COMMIT falls inside the selected
service intervals, so the service/native intersection is empty on both layouts.
The runner correctly executes **zero new withholding controls and zero service
fault/recovery cases**. This is measured unavailable service-matching capability,
not a failed fsync, proof that COMMIT never occurs, or justification to fabricate
an eligible pending operation. Historical increment-67 native FILE_SYNC WRITE
withholding evidence remains separate and is not silently retested/promoted here.

All eight jobs reach Committed on attempt 1 with validated payload manifest,
original private source inode/content, database inode and enrollment preserved.
Four claim observations exceed the unchanged handoff response budget and first
return retryable 503 without path release; four delivery cases first return 202.
Identical-ID replay confirms job 1/202 in every case before the fixture writes
new producer bytes. Newer bytes survive and job 2 remains absent. Delivery
retirement is accepted only with its already-Committed attempt-1 receipt; claim
workers exit zero. This injects no service failure or new recorder duty.

Both fresh mandatory SLES gates pass without cleanup errors:

| Configuration | Run ID | Debug / release tests | Audited ELF artifacts |
|---|---|---:|---:|
| Production | `20261019T145853Z-d68cd378` | 211 / 211 | 20 |
| Qualification | `20261019T145854Z-ed6461b6-nfs-qualification` | 212 / 212 | 20 |

[Production](RUST-SLES-EVIDENCE.json) and
[qualification](RUST-SLES-QUALIFICATION-EVIDENCE.json) retain locked cargo-zigbuild
GNU/glibc 2.22, exact target tests in pinned SLES userspace, loader/library/symbol
audits, six negative controls per configuration, formatting/Clippy and 42 locked
dependencies. One shipping executable remains; artifact counts include tests
and both profiles.

The live matrix uses source-identical passing increment-75 gates
`20261019T130033Z-364dcdf8` and
`20261019T130033Z-937f3a7c-nfs-qualification` while fresh gates run. The
[independent audit](RUST-NFS-BUFFERED-SYNC-INPUT-EVIDENCE.json) verifies all 62
current Rust entries against both live/fresh archives, hashes all forty fresh
artifacts and requires byte equality to the live inputs. It independently
decodes retained raw wire payloads, checks their hashes/capture bounds and exact
interval correlations, complete tuples, clock/security and acceptance invariants.
It retains fresh archives, exact verifier and unchanged gate auditor source,
the fixture-only probe binary/source/compiler/ELF audit, initial-attempt
provenance and post-run inventory. Gzip metadata can differ; Rust entries and
executable/test bytes must match. No Rust or Cargo.lock changes are needed.

Both engines have no containers. The rootful engine retains only pre-existing
`file-mover-rustup-1-99` and `file-mover-cargo-registry` cache volumes and default
`podman` network. Owned export volumes/networks are removed using normal NFS
unmounts. The default engine also retains eleven anonymous volumes; recorded
creation metadata dates all eleven to September, before this work, so they are
left untouched. Cached images remain available. No forced/lazy unmount or
host/NAS configuration/data change is used.

## Reproduction, limits and next boundary

Follow the [complete step-by-step lab](NFS-BUFFERED-SYNC-LAB.md), including both
gates, all-relay native discovery, actual observer clocks, lossless evidence
format, inventory and independent verifier. Keep the initial rejected scope
separate. SC-111 and DOC-01–05 now link results/procedure without renumbering
prior situations: 111 stable SC and six DOC IDs; DOC-06 remains deferred.

These are finite healthy observations on one client, one controlled server,
two logical exports, volatile tmpfs and a modern shared WSL2 kernel. External
ptrace changes scheduling; no latency/performance promise follows. Timing is
correlation rather than unique causal attribution. Decoder uncertainty remains
explicit; absence of a captured outgoing call does not prove no earlier pending
or unobserved RPC. A returned directory fsync need not emit a packet. Kernel,
NAS/firmware/failover, physical media/power, independent appliance caches and
arbitrary size/load/cache regimes remain unqualified. Historical noac NMP-41N
results keep their own scope.

Next locate actual buffered worker WRITE/COMMIT boundaries with descriptor/
filehandle attribution and write/open/close/writeback timing as needed. Only
then select positive service reply-withholding/death cases. Do not assume a
COMMIT belongs to fsync or treat native controls as service recovery. All eight
first-release gates remain open; production NFS and source deletion stay off.
