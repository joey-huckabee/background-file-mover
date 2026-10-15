# Increment 20: Interrupted NFS claim and file-publication links

This increment extends the permanent controlled NFS capability to the durable
two-name intermediate of source claiming and verified file publication.
Production NFS and source deletion remain disabled. There are no new packages,
schema changes, public API fields or deployed executables; normal integrity
remains streamed source hashing plus independent staging verification (3N).

The relocation caller explicitly selects `claim_link`, `file_link` or
`manifest_link`. Selection is not inferred from submitted filenames. The shared
helper pauses only after synchronizing the new exclusive link, before rechecking
and unlinking the old binding. A failed fixture checkpoint returns immediately;
it cannot fall through into unlinking. A fault test forces that failure and
checks both owned aliases and later non-destructive reconciliation.
Production's pause implementation remains a no-op.

The fixture adds SC-049/050 in both debug and release:

- **Claim link:** the original submitted leaf and recorded private claim share
  the same inode with exactly two links. Persisted status must remain Accepted,
  source paths unreleased and the interrupted POST must never return 202.
- **File publication link:** verified staging and the final payload name share
  the recorded inode with exactly two links. Persisted status stays at
  PublishIntent and no completion manifest may exist.

For these two cases, stop NFS while keeping the worker at the local rendezvous,
observe health/status and the single assignment, kill the worker and request
coordinator shutdown, then restore the server and confirm exit. The local pause
is deliberately not released: an in-flight unlink could otherwise complete on
restoration and fail to exercise the two-name recovery path. These cases test
process interruption of a real NFS link intermediate during server unavailability;
they do not claim to interrupt an in-flight unlink RPC or measure a kernel-blocked
worker. Other retained cases qualify blocked operations separately.

Before restarting, the runner requires both aliases to retain their exact
observed identity, two-link count, size and independently checked SHA-256, with
no COMMITTED.json. Recovery must keep the same inode, remove only the old owned
binding and finish with one link. File publication must retain attempt 1.
Claim recovery must complete before returning 202; after that, original-path
reuse and exact submission replay must preserve the next recording.
Both cases validate the complete V1 manifest, source/destination hashes, stable
observed root identities and retained private sources.
The intermediate has two names for one payload inode; creating/removing the
link is not another full-file copy. Uncertain file-publication recovery can add
the existing verification reread, without changing normal 3N transfer I/O.

Production gate `20261015T003101Z-95c3a6d4` passed 115 tests per profile;
qualification gate `20261015T003249Z-3f413ad7-nfs-qualification` passed 116.
Both passed formatting/Clippy, debug/release zigbuild, ELF/loader/library audits,
six negative audit controls per build mode and exact target execution in pinned
SLES userspace. Cleanup reported no errors. Maximum required GLIBC remained 2.18
and the locked external Linux graph remained 42 packages. See
[production evidence](RUST-SLES-EVIDENCE.json) and
[qualification evidence](RUST-SLES-QUALIFICATION-EVIDENCE.json).

Fixture `nfs-20261015T004040Z-b4ba6821` passed all six normal transfers and
eighteen runtime/control cases (sixteen qualification cases plus two production
controls), along with existing startup/OS lock/outage checks. Cleanup reported
no errors. See [runtime evidence](RUST-NFS-RUNTIME-EVIDENCE.json) and
[baseline evidence](RUST-NFS-BASELINE-EVIDENCE.json). SC-049/050 are now Fixture.

All four new cases preserved identical two-link inode/size observations and
expected hashes before restart, with no completion manifest. Recovery kept the
same inode, reduced its link count to one, retained attempt 1 and committed the
expected recording without replacing data. Both interrupted claim requests
returned 503 `handoff_pending` with `source_paths_released:false`; subsequent
claim recovery/replay returned 202 and preserved the reused original paths.
All private sources remained retained and cleanup stayed disabled.

In the debug claim-link case, neither worker nor coordinator exit was observed
before server restoration, despite requested signals at the locally held pause.
Both exits were confirmed before restarting. The other three new cases observed
both exits before restoration. These are measured outcomes, not cancellation
guarantees; the test does not infer which kernel operation delayed exit.
Health/status remained available and no replacement preceded confirmed exit.

Python syntax, scenario-ID/file-link, whitespace and the historical trace-matrix
checks also passed. No formal Rust trace coverage is promoted by the catalog.

The first gate launches after reboot stopped before compilation because the
Ubuntu rootless Podman runtime directory `/run/user/1000` was missing. Failed
run directories `20261015T002658Z-d8d475c2` and
`20261015T002658Z-f0edfa36-nfs-qualification` retain that environment failure;
they are not compatibility passes.
Ubuntu boot was waiting on `systemd-tmpfiles-setup`; its user-runtime service
could not start. Validation instead uses the unchanged gate from Windows with
`CONTAINER_CONNECTION=podman-machine-default-root`, selecting the healthy
Podman WSL2 engine. The pinned builder still compiles in native container `/work`
and the pinned SLES runtime still executes exact target artifacts. No Ubuntu
configuration or persistent Podman connection default is changed.

In-flight link/unlink RPCs and other synchronization boundaries remain unqualified.
Long outages, export/root authorization, cross-client fencing, server reboot,
power loss and old-kernel/hardware behavior remain separate qualification.
Registration, offline repair and new package experiments remain deferred.
