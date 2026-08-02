# Cybersecurity Architecture

How Background File Mover moves data safely on a filesystem it shares with
privileged agents it does not control.

This document states the threat model, the invariants that follow from it, and
the concrete controls. It is the reference for anything touching the
filesystem; `docs/L1-REQ.md`, `docs/L2-REQ.md`, and `docs/L3-REQ.md` carry the
testable obligations, and this explains *why* they say what they say.

> **Status.** Most of what follows is **specified, not yet implemented.** The
> v1.0.0 C++ implementation currently has the core state machine, JSON parser,
> REST codec, and configuration loader. The filesystem layer is being designed
> against this document rather than retrofitted to it. Section 9 tracks what
> exists today; `docs/ROADMAP.md` tracks the sequence.

## 0. v1.0.0 scope — two deliberate constraints

Two scoping decisions shape everything below, and both were taken to *remove*
attack surface rather than to save effort.

**Same filesystem only.** Source and destination must reside on one
filesystem. A cross-filesystem move is refused with a clear error, checked at
startup where possible and at submission otherwise.

This eliminates the staging directory, the recursive fd-relative copy, the
bottom-up fsync ordering, and the `ENOSPC`-mid-staging abort path — which is
where the large majority of the attack surface in §3 lives. Every move becomes
a single atomic operation. Cross-filesystem support is a v1.1 item with its
own design and its own fault-injection suite.

**Files only.** The submitted unit is a set of files, not a directory tree.
Directory moves are rejected outright with a distinct error.

Beyond removing the recursive walk, this resolves a problem that has no good
answer on the target platform: `linkat` does not work on directories, and NFS
has no `RENAME_NOREPLACE`, so **there is no atomic no-clobber directory move
over NFS at all**. Supporting directory moves would mean either breaking the
single-commit-point invariant on the filesystem that matters most, or having
the same submission succeed or fail depending on which mount it landed on.
Neither is acceptable; not offering the operation is.

Sections below that describe recursive traversal, staging, and tree deletion
are retained because they are the v1.1 design, and because losing that
analysis between now and then would be wasteful. They are marked **[v1.1]**.

---

## 1. Threat model

The daemon does not run alone. On a STIG'd DoD Linux host it shares every
filesystem operation with:

* **Endpoint security** (Trellix ENSL / ePO-managed) — fanotify-based
  on-access scanning that can stall an `open()` indefinitely, and quarantine
  that can *delete a file out from under an in-flight operation*.
* **Mandatory access control** — SELinux enforcing on RHEL 9, AppArmor
  enforcing on SLES 12 (the SLES STIG mandates AppArmor; SELinux is not
  supported there).
* **Audit** — `auditd` watches on rename/unlink syscalls in several STIG
  profiles.
* **Other clients of the same NFS export** — the recordings arrive on a
  shared mount; this daemon is not the only writer on that filesystem.

Two assumptions are therefore **rejected**:

1. *"If I checked it, it is still true."* Every check-then-act sequence is a
   race an adversary or an agent can win.
2. *"Another root process interfering is impossible."* It is routine. It must
   be a **modeled state in recovery**, not an unhandled branch.

### Adversary capabilities assumed

| Capability | Assumed? | Consequence |
|---|---|---|
| Create files/symlinks in a watched directory | **Yes** | Symlink and hard-link attacks are in scope |
| Win a race between two of our syscalls | **Yes** | Check-then-act on paths is prohibited |
| Delete or quarantine a file mid-operation | **Yes** | "Neither path exists" is a real recovery state |
| Stall a syscall arbitrarily long | **Yes** | Every blocking call needs a timeout and per-entry isolation |
| Write to the state database directory | **No** | Directory permissions are the control; if this falls, recovery is compromised |
| Compromise the producer account writing recordings | **No** | Out of scope — we faithfully move what a trusted producer stages |

That last row is load-bearing and deserves saying plainly: **everything
downstream assumes the source tree's owner is not adversarial.** If the threat
model ever includes a compromised producer, fd-relative discipline does not
help — content and filename policy becomes a separate layer.

---

## 2. The load-bearing invariants

Everything else traces to these two.

> **Exactly one atomic commit point.** Every move has a single filesystem
> rename that commits it. Before that instant the move has not happened; after
> it, it fully has.

> **Disposable before, idempotent after.** All state prior to the commit point
> is safe to throw away. All actions after it can be repeated without harm.
> Interruption at *any* instant therefore has a correct recovery.

The value of these is that recovery never has to reason about a third state.
Design pressure that would introduce one — a second commit, a partially
observable destination, a non-atomic rename — is rejected on principle, not
weighed case by case.

---

## 3. Attack classes and controls

### 3.1 TOCTOU (time-of-check to time-of-use)

`lstat(path)` then `rename(path, ...)` is exploitable: the entry can be
swapped between the two calls. `O_NOFOLLOW` alone does **not** close this — it
stops a symlink, not a *different regular file* swapped in.

**Control.** All filesystem operations on managed trees are **fd-relative**:
`openat`, `renameat2`, `fstatat`, `unlinkat`, `mkdirat`, `fchmod`. Directory
descriptors are opened once at operation start and held. Path-based operations
on managed trees are prohibited.

**Residual control.** After every `openat`, `fstat` the descriptor and compare
`st_dev`, `st_ino`, and file type against the preceding `fstatat`. A mismatch
means the entry was swapped mid-race; abort that entry.

### 3.2 Symlink redirection

If any path component is attacker-writable, a symlink redirects the operation
elsewhere — catastrophic if the daemon is privileged.

**Control.** Directory opens use `O_RDONLY | O_DIRECTORY | O_NOFOLLOW`; file
opens within managed trees use `O_NOFOLLOW`. Symlinks are **rejected by
default**; verbatim recreation is available only by explicit configuration and
never follows the link.

`openat2(RESOLVE_NO_SYMLINKS)` would be stronger but does not exist on
SLES 12's kernel. Per-component `openat` with `O_NOFOLLOW` is the portable
equivalent.

### 3.3 Hard-link tricks

An attacker who can create hard links in a watched directory can make the
mover act on a file they do not own.

**Control.** After opening, verify `st_uid` against the configured trusted UID,
and verify file type. Refuse to operate in a world-writable directory lacking
the sticky bit.

### 3.4 Destination clobbering

Plain `rename(2)` **silently replaces** an existing destination. That is a
data-destruction primitive if an attacker can pre-place a name.

**Control.** `renameat2` with `RENAME_NOREPLACE`, invoked through
`syscall(SYS_renameat2, ...)` because SLES 12's glibc 2.22 predates the
wrapper (added in glibc 2.28). On `EEXIST` the move fails without touching the
destination.

This is a **security control, not merely a correctness one**.

### 3.5 State-store integrity

Recovery acts on what the durable store says. Whoever can write it controls
what recovery does — including fabricating a committed entry to trigger
deletion of an arbitrary path.

**Control.** The store lives in a directory writable only by the service
account, opened `O_NOFOLLOW`. Recorded paths are validated before replay:
absolute after canonicalization, no `..` components, no control characters.
Directory permissions are the real control; path validation is defence in
depth.

### 3.6 Recursive deletion **[v1.1]**

Recursive delete has its own TOCTOU class — this is literal CVE territory
(`rm -rf` symlink races).

**Control.** Bottom-up, fd-relative `unlinkat` exclusively. **`system(3)` is
never invoked**, for this or anything else.

Not reachable at v1.0.0 (files only, §0), but the prohibition on `system(3)`
applies unconditionally and now — including to the external-command transfer
strategy, which uses `fork`/`execvp` with an argv array so no shell exists to
inject into.

---

## 4. NFS — the case the generic design punts on

Generic guidance says *"if either endpoint is NFS, that is a design review of
its own."* NFS is not an edge case here: the recordings arrive on a shared NFS
mount by design. This section is that review.

### 4.1 `RENAME_NOREPLACE` does not work over NFS

NFSv3 has no equivalent operation and NFSv4's `RENAME` carries no
no-replace flag, so the client returns `EINVAL`/`EOPNOTSUPP`. **On the NFS
mount, the fallback is the normal path, not an exception.**

Consequences that must be designed for rather than discovered:

* The `linkat` + `unlinkat` fallback is the **primary tested path** for NFS
  sources, and must be treated as such in the test matrix. It is not an edge
  case to be exercised once; it is what production runs.
* That pair is **not atomic together**. A crash between them leaves *both*
  names pointing at one inode. This is the safe direction — no data is lost —
  but recovery must treat an existing target as *possibly our own interrupted
  rename*, disambiguated by inode identity, rather than as a collision. Naive
  "target exists → fail" is the wrong answer here, and it is the answer a
  reasonable implementer would reach for.
* `linkat` does not work on directories, so over NFS there is **no atomic
  no-clobber directory move at all**. This is the reason v1.0.0 is files-only
  (§0) rather than a limitation discovered later.

### 4.2 Capability detection, not assumption

Support for `RENAME_NOREPLACE` varies by kernel *and* by filesystem. SLES 12
GA (kernel 3.12) predates the syscall entirely; SP2+ (kernel 4.4) has it, and
the SP5 target (kernel 4.12) does. Filesystem support is separate.

**Control.** Detect at startup, per managed filesystem, by attempting the
operation and observing `EINVAL`/`ENOSYS`/`EOPNOTSUPP`. Log the selected
strategy per tree. Never infer capability from kernel version alone.

### 4.3 Identity verification is weaker on NFS

The `fstat`-after-`openat` check (§3.1) compares attributes that on NFS come
from the **client attribute cache**. A stale `st_ino`/`st_nlink` weakens the
check without failing it.

This is an accepted residual risk, recorded rather than hidden. Mounting with
`actimeo=0` would close it at a substantial performance cost; that is a
deployment decision, not a code one, and belongs in the qualification
checklist.

### 4.4 Silly rename

Unlinking a file another NFS client holds open does not remove it — the server
renames it to `.nfsXXXX` in the same directory. Source deletion must tolerate
these appearing, and must not treat them as unexpected entries during a
recursive walk.

### 4.5 Visibility is not atomic across clients

A rename is atomic *on the server*, but other clients may briefly observe
neither name or both. Consumers must not poll the destination directory and
assume a visible name is a complete file. The two-hop pattern — rename to a
temporary name in the destination directory, fsync, then rename to the final
name — is what makes the destination safe to watch.

### 4.6 `fsync` semantics

`fsync` on NFS issues a COMMIT to the server, but close-to-open consistency
means other clients see data only after close. Directory `fsync` is weakly
defined on NFS. Durability claims are therefore **server-side**, not
client-side, and the qualification checklist must verify them on the actual
export rather than a local temporary directory.

### 4.7 `ESTALE`

Another client's operation can invalidate an open file handle. `ESTALE` is a
**retryable, expected** condition, not a fault — the Python implementation
already classifies it this way, and the C++ implementation must match.

### 4.8 Root squash

STIG requires `root_squash` on NFS exports, which turns a root daemon into
`nobody` on that mount. This is one more reason the unprivileged service
account is the correct posture rather than a nicety.

---

## 5. External interference (ePO / ENSL)

On-access scanning uses fanotify **permission events**: the kernel parks
`open()` until the scanner responds. There is **no errno and no signal** — the
syscall simply takes longer. Rename is generally not gated; the stall lands on
`open()`.

**There is no reliable way to ask "is a scan in progress?"** Any answer is
stale by the time it is acted on. So the daemon does not ask.

**Controls:**

* Every potentially blocking syscall on a managed file carries a configurable
  timeout. Expiry fails **only that entry**, logged as suspected external
  interference with measured duration and file size — latency correlating with
  size is the on-access-scan fingerprint.
* A stalled entry never blocks other queued moves or state processing.
* **Quarantine produces a state the naive invariant calls impossible.** If a
  file is removed between the intent record and the rename, recovery finds
  *neither* path. That is a third outcome: mark the entry failed-external, log
  at high severity, and **do not retry automatically**.
* A source entry disappearing mid-walk fails that entry gracefully without
  aborting sibling entries or the containing tree move.
* At startup, query local on-access configuration where available and log
  whether managed trees are covered by exclusions — this verifies the ePO
  exclusion request actually landed on this host.

**Deployment precondition.** Required ePO exclusions (staging directory,
ideally the data trees; or the daemon binary as a trusted process) must be a
documented **policy assignment in ePO**, not a local tweak — local changes are
overwritten at the next policy enforcement interval, which is a classic
"worked yesterday" failure.

---

## 6. Platform compliance

### SELinux (RHEL 9)

Files created by the daemon inherit context from its domain and the parent
directory, **not** from the source file. A same-filesystem `rename` preserves
the original context, which can be equally wrong at the destination.

**Control.** Label objects with the destination tree's default context
**before** the commit rename, so a wrongly labelled object is never observable
at the final path. Context is **destination-determined**; source contexts are
not preserved. File context mappings are installed persistently via
`semanage fcontext`, not per-file `chcon`.

The state-store directory needs its own label, or the daemon's own policy
blocks its writes.

### AppArmor (SLES 12)

Path-based, and it interacts with fd-relative design correctly — permissions
are checked at `open()` against the resolved path. No label management, so the
copy-fidelity problem does not arise. A profile enumerating exactly the
readable/writable paths is loaded enforcing.

### systemd hardening

`ProtectSystem=strict`, `ReadWritePaths=` limited to managed trees and the
state directory, `NoNewPrivileges=yes`, `PrivateTmp=yes`, `ProtectHome=yes`, a
trimmed `CapabilityBoundingSet=`, `User=` service account, `UMask=0077`.

### FIPS

Where FIPS mode is enabled, file-verification hashing uses SHA-256 or
stronger. Non-cryptographic framing checksums (CRC32) remain acceptable for
torn-write detection only — that is integrity framing, not cryptography.

### Audit volume

`auditd` watches on rename/unlink will be **noisy** — thousands of operations
per run. Not a compliance problem, but the audit log budget must be sized, or
`auditd` hitting `space_left_action` can halt the host.

---

## 7. Durable state: phases, not a journal

The source material specifies an append-only journal with phases
`intent → staged → committed → source-deleted → complete`. **ADR-0010 chose
SQLite instead**, so the mechanism differs while the phase model carries over
intact.

| Journal concept | How it lands here |
|---|---|
| Phase progression | A state column, same five phases, same meaning |
| Length-prefixed + CRC per record | SQLite's own page checksums and WAL; the framing problem does not exist |
| `fsync` at each phase transition | `synchronous=FULL` plus WAL (ADR-0010) |
| Torn final line tolerated | Not applicable — WAL recovery handles partial writes |
| Unreadable journal → fail closed | **Retained** — `L2-JOB-012`. A corrupt store fails startup loudly and is never partially recovered |
| Record source identity (`st_dev`, `st_ino`, size) at intent | **Retained and important** — see below |
| Store in a service-account-only directory, `O_NOFOLLOW` | Retained |
| Store must be local | `L2-JOB-008` — SQLite locking is unsafe over NFS |

**Recording source identity at intent time is not optional.** After a crash
with phase `intent`, "the source name exists" is ambiguous when producers are
actively writing: is it the original file, or a *new* file the next simulation
run just created at the same path? `st_dev`/`st_ino`/size recorded at intent
disambiguates. Without it, recovery can move or delete the wrong file — which
is the worst outcome this system has.

---

## 8. Testing

The guarantees live in crash-window behaviour, which ordinary tests never
reach. Recovery logic that only runs during disasters is the worst possible
place for untested code.

Required:

* **Crash injection** — `SIGKILL` between each phase transition, verifying
  correct recovery on restart.
* **Fault injection** — entry swapped mid-walk (identity mismatch), file
  removed mid-copy, `ENOSPC` mid-staging, `EEXIST` at commit, both paths
  missing at recovery.
* **Enforcing-mode pass** — full suite with SELinux enforcing (RHEL) or the
  AppArmor profile enforcing (SLES), asserting zero AVC/AppArmor denials.
  Denials-in-permissive is exactly what works in dev and fails at the test
  site.
* **Latency injection** — artificial `open()` delay, asserting timeout expiry
  produces a failed-external entry while sibling moves complete.
* **NFS qualification** — on a real export, not a local temporary directory.
  See the checklist in `docs/DEPLOYMENT.md`.

---

## 9. What exists today

Being explicit, because a security document describing unimplemented controls
is worse than none.

| Area | Status |
|---|---|
| Core job state machine | Implemented, `L3-CPP-001..015` |
| Strict JSON parser, hostile-input tested and fuzzed | Implemented, `L3-CPP-016..024` |
| REST codec, strict-reject | Implemented, `L3-CPP-025..032` |
| Configuration loader with strict schema | Implemented, `L3-CPP-033..040` |
| State-store location check (rejects network filesystems) | Implemented, `storage_path_is_local` |
| Rename template expansion, escape-proof | Implemented (pure; see §10) |
| **fd-relative filesystem discipline** | **Not implemented** |
| **`renameat2(RENAME_NOREPLACE)` + capability detection** | **Not implemented** |
| **Durable phase model / SQLite store** | **Not implemented** |
| **Crash and fault injection tests** | **Not implemented** |
| **SELinux / AppArmor policy and enforcing-mode CI** | **Not implemented** |
| **ePO exclusion documentation and startup check** | **Not implemented** |

---

## 10. Why the first rename engine was not adopted wholesale

An inherited milestone delivered a working template-driven rename engine. Its
**template expansion is adopted**: it is a pure function, validates its own
output against `.`, `..`, `/`, and NUL so a template cannot escape its
directory, and takes the timestamp from the caller rather than reading a clock.

Its **filesystem operation was not adopted**, for three reasons that this
document makes concrete:

1. **It is path-based.** `lstat` then `link` then `unlink` on paths is exactly
   the check-then-act pattern §3.1 prohibits. The fd-relative rewrite is not a
   refinement of it; it is a different implementation.
2. **`link` + `unlink` is the fallback, not the primary.** It was chosen there
   because `rename(2)` clobbers — correct reasoning, incomplete conclusion.
   `renameat2(RENAME_NOREPLACE)` is a single atomic syscall with no window
   between two operations. The link/unlink pair remains as the NFS and
   older-filesystem fallback (§4.1), where its non-atomicity is a documented,
   recovery-handled property rather than an unnoticed one.
3. **No commit-point ordering.** The engine renames and returns; nothing
   specifies when durable state is updated, so a crash in between loses track
   of the file — the precise failure the invariants in §2 exist to prevent.

The engine was good work against the problem as it was framed. This document
reframes the problem.
