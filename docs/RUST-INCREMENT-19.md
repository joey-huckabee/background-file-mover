# Increment 19: Scenario catalog and NFS payload-read interruption

The user requested a maintained list of use cases and failure/recovery situations
to feed user documentation as incremental development continues. The new
[scenario catalog](RUST-SCENARIOS.md) backfills increments 01–18, gives stable
SC identifiers and plain behavior/user actions, distinguishes local behavior
from controlled fixture evidence and future work, and tracks six user-guide
deliverables. Repository handoffs require updating it with each increment.
The roadmap remains future-only; historical evidence stays in result documents.

This increment also extends the permanent qualification capability with two
read-specific points in the actual delivery child:

- `source_read`: NFS source and local destination; pause before the first source
  payload read, with the transfer at Intent. After outage/interruption, confirmed
  exit precedes replacement. Recovery preserves attempt 1 and allocates attempt 2.
- `verify_read`: local source and NFS destination; pause before independently
  rereading already synchronized staging, with the transfer at Copied. No Verified
  receipt/publication may appear during the incomplete read. Recovery repeats
  verification on the same copied attempt and completes normally.

Only a selected qualification read issues per-file Random and DontNeed cache
advice. Metadata checks/opening and advice complete before the local rendezvous;
the next payload operation is the read loop. Advice alone cannot prove eviction.
The worker therefore creates a local `read-completed` marker after the entire
loop and before post-read metadata checks. The runner requires its absence during
the outage, requires the still-assigned child to be in kernel-blocked state `D`
with an unchanged durable phase, and records its wait channel. This distinguishes
an unfinished payload read
from a fully cached read followed by a blocked NFS metadata call. It does not
measure physical device I/O or change normal 3N logical payload I/O.

Production compiles both helpers to no-ops, ignores fixture controls, and still
rejects NFS roots. Unselected qualification operations also use the ordinary path.
Recovered publication hashing has no new verification pause. No dependency,
schema, REST field or additional deployed executable is introduced.

The fixture restores connectivity before cleanup, confirms worker completion,
then unmounts and removes only its resources. Source custody and original-path
reuse, expected SHA-256/manifest, attempt numbers, health/status responsiveness
and disabled cleanup are checked after recovery in both debug and release.

Production gate `20261014T144611Z-287c12db` passed 114 tests per profile;
qualification gate `20261014T144611Z-97ffc0ea-nfs-qualification` passed 115.
Both completed debug/release exact-artifact execution in pinned SLES userspace,
formatting/Clippy, ELF/loader/library audits and six negative audit controls per
build mode, without cleanup errors. Maximum required GLIBC remained 2.18, below
the 2.22 limit; the locked external Linux graph remained 42 packages. See
[production evidence](RUST-SLES-EVIDENCE.json) and
[qualification evidence](RUST-SLES-QUALIFICATION-EVIDENCE.json).

Fixture `nfs-20261014T151123Z-329f30d1` passed all six normal transfers, twelve
qualification runtime cases and two production-control cases, plus the existing
startup/OS lock/outage boundaries. Cleanup reported no errors. Each runtime row
now carries its scenario ID. See [runtime evidence](RUST-NFS-RUNTIME-EVIDENCE.json)
and [baseline evidence](RUST-NFS-BASELINE-EVIDENCE.json).

All four new read cases observed state `D` and wait channel
`folio_wait_bit_common`, with no read-completed marker and no durable phase
advance. Health/status remained available with one assigned worker. Their worker
and coordinator exits were observed before server restoration after the requested
signals. This contrasts with increment 18's copy-write observations and is not
a guarantee of prompt cancellation under other kernels, operations or outages.
Replacement still requires confirmed exit.

Both source-read cases retained the zero-byte uncertain attempt 1 and committed
attempt 2. Both verification cases recovered the synchronized Copied object,
reverified it and committed attempt 1. Exact source/destination SHA-256 and V1
manifest checks passed, observed root identities were stable, reused producer
paths remained intact and source cleanup stayed disabled. SC-041/042 are now
marked Fixture in the catalog. This does not enable production NFS.

The historical trace-matrix check, Python syntax checks, catalog ID/file-link
checks and whitespace checks passed. No formal Rust requirement coverage is
promoted by this documentation index.

Production NFS and source deletion remain disabled. This is one NFS client on
the modern WSL2 kernel with pinned SLES userspace, not cross-client/export fencing,
the historical SLES kernel, long-outage, reboot, hardware or power-loss evidence.
Interrupted claim/file link intermediates, stable export authorization and
cross-client ownership remain subsequent increments. Package experiments stay
paused and registration/offline repair remain deferred.
