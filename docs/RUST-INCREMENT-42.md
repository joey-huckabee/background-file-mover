# Rust increment 42: shared local ownership and explicit worker inheritance

Implementation increment on `feature/rust-transfer-coordinator`, 2026-10-16.
Implements the local exclusion slice of the [single-host contract](NFS-OWNERSHIP-FENCING-CONTRACT.md).
Production NFS and source deletion remain disabled. Registration, repair,
cross-host takeover and the configurable shutdown controller remain deferred.

## Behavior and ownership

One empty, persistent `instance.lock` lives beside the configured SQLite database.
The protected local parent must already exist, belong to the service account
and have no group/other permission bits (normally mode 0700). Create the guard once
with mode 0600 and synchronize the file and directory; reuse never truncates,
unlinks, rewrites or replaces it. Validate owner, regular-file type, zero length,
single link, private parent, local filesystem and named/held identities. Admit the
existing ext-family/tmpfs/overlay filesystem types; reject NFS even in the
qualification build. Container tmpfs/overlay admission is not production
persistence qualification. Other local types still refuse.

Normal service startup, --initialize-source and --transfer-one acquire a
nonblocking exclusive local flock before SQLite or source bootstrap. All databases
in the same parent directory share this guard. Contention refuses promptly with
local instance or surviving worker already owns state. The listener may bind
first, so a port collision can refuse before ownership acquisition. Platform
inspection remains read-only. Supported manual and systemd starts still require
the same account, configuration and fixed state directory.

Pass the same locked open description with SCM_RIGHTS over existing private Unix
streams. Every bootstrap, enrollment, claim, payload, delivery and source-space
worker validates a strict version-1 identity prefix and exactly one read/write
descriptor, checks that an independent open contends while the received open
description owns the lock, then acknowledges before reading an assignment.
Reject missing, extra, unlocked, read-only, invalid-version or wrong-scope proof.
The prefix is bounded at 16384 bytes with local channel deadlines. Parent receipt
of the acknowledgement proves child validation, not merely a queued descriptor.

No holder explicitly unlocks the shared description. Coordinator threads and
workers retain their own copies through their work and existing shutdown waits;
only closing the last copy releases exclusion. Runtime admission/operator work,
delivery scheduling and delivery-session frames revalidate before further work.
Existing source/destination custody locks and original-state checks remain.
The prefix is private to the matching executable; no mixed-worker-version support
is promised. No new dependency, unsafe block, worker executable, database schema,
public API or existing assignment/receipt version is introduced.

This is cooperative one-host exclusion. Another host, hostile same-UID process
or deliberate alternate-state launch remains outside the profile. Guard release
or worker exit is not proof that NFS operations settled. Retain uncertain outcomes
and the production block until owned recovery is qualified. No retry policy,
review reset or deletion authorization is changed.

## Selected acceptance scope

- SH-01/13: unsafe guard mode, nonempty content, symlink, hardlink, directory,
  nonprivate parent and changed named identity refuse without automatic repair.
  Mounted-NFS state parents also refuse all three effect commands in both build
  modes and profiles (12 fixture cases), leaving the state directory empty.
- SH-02: eight competing local acquisitions have one winner; all three effect
  entry points refuse with a held guard before SQLite/source bootstrap. The test
  deliberately supplies an unavailable source and an absent alternate database
  in the same state directory, with a free listener.
- SH-03: each of the six real worker modes accepts explicit ownership, retains it
  after the parent holder closes, blocks another acquisition, and releases after
  confirmed child exit. Missing prefixes and malformed descriptor proofs refuse.
  Existing direct-worker tests now supply valid ownership before testing their
  original assignment/custody boundaries.
- SH-04: qualification-only paused claim worker survives SIGKILL of its actual
  coordinator, prevents a replacement service, then releases after its own exit.
  Original-state restart and identical submission complete with original source
  bytes retained. Production builds do not execute this qualification pause case.

These are selected cases, not complete SH closure. Guard admission validates
the local parent and guard, not every SQLite database/WAL/shared-memory alias or
per-file bind mount. Supported provisioning still requires actual local state
files; complete state-layout validation remains SH-01/13 and FR-03/06 work.
Actual systemd/manual races, all active bootstrap/copy/verification/publication
death phases, wrong UID, filesystem durability and delayed server-accepted RPCs
remain pending. A userspace pause is not an in-flight RPC experiment.
SH-05–09's configurable default-60 shutdown wait and bounded stop/status controller
are not implemented. The strict config still rejects that proposed key.

## Validation

Production gate `20261017T040242Z-aec7b704` passed: 184 tests per profile,
20 audited executables, six ELF negative controls, formatting and Clippy with
warnings denied. The external graph remains 42 packages; maximum required symbol
version is GLIBC_2.18, below the GNU/glibc-2.22 target. The complete 59-file source
archive and all 20 artifact hashes match current sources/report; cleanup has no
errors. [Production evidence](RUST-SLES-EVIDENCE.json) records the pinned inputs.

Qualification gate `20261017T040243Z-1cf25089-nfs-qualification` also passed,
exit 0: 185 tests per profile, 20 audited executables, six negative controls,
formatting/Clippy checks, unchanged 42 packages and maximum GLIBC_2.18. Its complete
59-file source archive and all 20 artifact hashes match current sources/report;
cleanup has no errors. [Qualification evidence](RUST-SLES-QUALIFICATION-EVIDENCE.json)
records the separate build mode and feature selection.

Both gates use root Podman in WSL2, cargo-zigbuild for GNU/glibc 2.22, and exact
target execution under UID/GID 1000 with eager relocation in pinned actual SLES
12 SP5 userspace. No actual SLES host or host-only cargo build/test is used.
This is userspace compatibility evidence on a shared modern kernel, not old
kernel/CPU, NAS hardware, storage durability or systemd lifecycle qualification.

Controlled fixture `nfs-20261017T042414Z-5fb4bcda` passed with these exact final
artifacts; [saved evidence](RUST-NFS-LOCAL-INSTANCE-EVIDENCE.json) records hashes,
mounts, kernel, cases and cleanup. All six normal transfers passed: NFS source,
NFS destination and both endpoints on NFS, in debug and release. They cover
three explicit files (18 bytes, 2 MiB + 17 bytes and empty), nested names, identical
submission replay, producer path reuse after 202, retained claimed originals,
verified destination hashes and complete manifests. Both-endpoint cases share
one export; separate-share deployment still needs qualification.

Twelve new cases put the database parent on an actual hard NFSv4.1 export:
service, source initialization and single-file transfer, in both profiles and
build modes. Every start refused in 0.859–0.953 seconds, with no guard/database
or other file created there and the deliberately absent source unchanged. The
retained production reachable-NFS refusal, OS inherited-lock model, hard-mount
outage/restoration and isolated source-bootstrap SIGTERM checks also passed.
The latter confirms bootstrap child exit before server restoration and no
SQLite/readiness; it does not implement a configurable stop controller or prove
server-accepted RPC settlement. Runtime death/long-outage, two-client ownership
and capacity-storage suites were not selected for this run.

The fixture uses root Podman in WSL2, pinned SLES/glibc 2.22 userspace and kernel
`6.18.33.2-microsoft-standard-WSL2`. All recorded driver hashes match the final
scripts. Cleanup has no errors: no containers or disposable fixture networks/
volumes remain, only the preexisting toolchain/registry caches and default network.
No production NFS or deletion enablement follows from these selected results.

Development feedback: the first pair of gates found a test-only Clippy
non-Drop lifetime cleanup; the next pair exposed 13 older direct-worker fixtures
that had not supplied the new prefix. Those fixtures now hand off valid local
ownership before testing their original custody/assignment rules. Intermediate
runs preceded the final delivery-session timeout correction and are superseded;
only final-source passing reports are promoted as current evidence.

The [scenario catalog](RUST-SCENARIOS.md) retains 95 stable situation IDs and six
DOC items; SC-092/095 now distinguish implemented local behavior from remaining
qualification. The [operator guide](RUST-OPERATOR-GUIDE.md) explains contention,
preserved instance.lock and surviving-worker ownership. The future-only
[roadmap](ROADMAP.md) advances to bounded stop control and remaining qualification.

Documentation checks pass for 15 changed Markdown files, 459 local link targets
and table structure; all 95 stable SC IDs, six DOC items, eight release gates,
14 SH cases and 18 NF mappings are retained. Generated trace consistency,
fixture Python syntax/CLI help and Git whitespace checks pass. Requirement IDs
and Deferred status annotations are unchanged. Complete final archives and all
40 gate artifact hashes were rechecked after the fixture; Rust sources remain
identical to both passing snapshots.
