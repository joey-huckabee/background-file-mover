# Increment 15: Isolated source singleton bootstrap

Source singleton acquisition now runs in an internal child mode of the existing
executable. A dedicated startup supervisor owns that child and its private Unix
socket; the async coordinator awaits a bounded result channel. Local SQLite
initialization also runs on that supervisor after source custody succeeds, while
SQLite work retains its existing dedicated owner. No child accesses the database.

## Custody and readiness

The child applies the existing source-root/namespace ownership, filesystem and
singleton checks. NFS remains rejected. It sends versioned metadata and exactly
one locked namespace descriptor using SCM_RIGHTS. This transfers the same open
description, preserving the lock after child exit. The coordinator does not reopen
or revalidate the source during receipt handling. It trusts its own executable
on the private inherited socket; this is not a public capability-adoption API.

Request and receipt bodies are bounded to 16 KiB. The receiver rejects unknown
fields, wrong version/scope, malformed identities, missing/extra descriptors and
ancillary truncation. Received descriptors are close-on-exec; later worker
inheritance remains explicit. Any receipt is provisional until successful child
exit is confirmed. Failures create no replacement bootstrap assignment.

The service emits `Ready on ...` only after source custody, confirmed bootstrap
exit and local worker/database initialization. It serves no HTTP response before
that point. Its TCP listener may already be bound, so connecting alone is not
readiness. `/healthz` remains the existing liveness endpoint after startup;
there is no new REST endpoint or configuration field.

The executor remains available to its signal tasks while source initialization
is pending. SIGINT/SIGTERM set the shared stop flag. The supervisor requests
bootstrap termination and waits for confirmed exit before returning a clean
shutdown. Initialization errors and deadline expiry without a shutdown request
remain startup failures.
The 30-second source-bootstrap deadline similarly requests termination; it is
not a guarantee that a stuck kernel operation will exit within that duration.
IPC writes have a three-second timeout. An unkillable child can still delay
shutdown, but it does so in the supervisor, with no readiness or replacement
worker. Local SQLite initialization has no new cancellation deadline.

Workers share the service stop flag so shutdown requested during initialization
does not launch ongoing delivery after startup completes. Fatal worker persistence
errors that set this flag also stop the service's accept loop.

## Dependency and compatibility scope

There are no new packages, package version changes, schema changes or additional
executables. The locked rustix 1.1.5 package adds its `net` feature for safe
sendmsg/recvmsg descriptor passing. That feature also enables linux-raw-sys
network-binding definition features (`net`, `if_ether`, `netlink`, `xdp`). The
service uses private Unix socket messages; it introduces no netlink/XDP behavior.
The mandatory gate checks the explicit expanded feature sets and audits every
emitted executable before executing it in pinned SLES userspace.

## Validation

Three additional audited service subprocess tests cover transferred lock
lifetime after bootstrap exit and descriptor duplication, malformed/oversized
requests and scope rejection, and startup contention without readiness or SQLite
creation. An additional coordinator test checks clean shutdown requested before
startup, without source or database access. Two filesystem unit tests cover missing/extra descriptors and oversized
receipts. The existing API, transfer and recovery suites now exercise startup
through the bootstrap child.

The controlled hard-mount runner adds `--isolated-startup`. It checks one bootstrap
child during the outage, an unanswered health request, SIGTERM termination of the
service and confirmed child exit before restoring NFS, and absence of SQLite or
readiness. It retains the lock-lifetime, interrupted metadata and restored-identity
checks from increment 14. Its observation deadline is evidence on the tested
kernel, not a general NFS cancellation guarantee.

The mandatory gate `20261014T030232Z-1f39b638` passed all 104 tests per profile,
debug and release. All 20 executable artifacts passed ELF/loader/library audits
and eager relocation/execution in pinned SLES 12 SP5 userspace. Maximum required
version remains GLIBC_2.18, with 42 external Linux packages, six negative audit
controls and no cleanup errors. Formatting, Clippy with warnings denied and the
existing trace-matrix check passed. See [RUST-SLES-EVIDENCE.json](RUST-SLES-EVIDENCE.json).

The controlled hard-mount run `nfs-20261014T031938Z-ee834aa2` passed with no
cleanup errors. It observed one bootstrap child, no health response while startup
was pending, and successful service shutdown after SIGTERM with bootstrap exit
confirmed before NFS restoration. No SQLite database or readiness announcement
was produced. Both profiles still rejected reachable NFS. Lock-lifetime,
interrupted metadata and restored root/namespace identity checks also passed.
See [RUST-NFS-STARTUP-EVIDENCE.json](RUST-NFS-STARTUP-EVIDENCE.json). The fixture
uses SLES userspace on the WSL2 kernel and does not establish old-kernel/CPU or
power-loss behavior. Its privileged fixture is separate from standard CI.

Full Rust claim/copy/verification/publication recovery on NFS,
distributed fencing and stable root/export authorization remain future work.
Production NFS and source deletion remain disabled.
