# C2 — fd-relative filesystem layer: implementation plan

The layer every later milestone touches the disk through. Nothing in C3–C9
performs a path-based filesystem operation; they all go through this.

Written before any code, because the ordering matters: `docs/CYBERSECURITY.md`
§10 documents that building the data-safety layer last is how security
requirements get retrofitted instead of designed in.

---

## 1. Pre-flight measurements

Taken in the `gcc:4.8` fidelity container before planning, because they change
the design rather than the implementation. The answer on a modern host is the
opposite of the answer on the target, which is exactly the trap.

| | GCC 4.8.5 / glibc 2.13 (fidelity) | Host glibc 2.35 |
|---|---|---|
| `renameat2` libc wrapper | **absent** (needs glibc ≥ 2.28) | present |
| `RENAME_NOREPLACE` | **not defined** | defined (`1`) |
| `SYS_renameat2` | **not defined** | defined (`316`) |
| `O_PATH` | **not defined** | defined |
| `AT_EMPTY_PATH` | **not defined** | defined |
| `O_NOFOLLOW`, `O_DIRECTORY`, `AT_SYMLINK_NOFOLLOW` | defined | defined |
| `openat`, `fstatat`, `unlinkat`, `linkat`, `mkdirat` | all present | all present |

**Consequences, decided now rather than discovered mid-implementation:**

1. **`renameat2` must be called through `syscall(2)`.** There is no wrapper to
   link against on the target, so the layer defines its own thin inline caller
   with the syscall number and the `RENAME_NOREPLACE` constant supplied by us.
   This is not a portability nicety — code that calls `renameat2(...)` directly
   compiles on the host and fails to link on SLES 12 SP5.
2. **The syscall number is architecture-specific.** `316` is x86_64. The
   deployment targets are x86_64 today; the number must be behind an
   `#if defined(__x86_64__)` with a compile-time error on anything else, rather
   than a silently wrong constant.
3. **Do not use `O_PATH` or `AT_EMPTY_PATH`.** Both are absent from the
   fidelity toolchain's headers. They are available on SLES 12 SP5 (glibc 2.22
   added them at 2.14), so this is the proxy being *stricter* than the target —
   an acceptable direction, and cheaper than making the fidelity tier lie.

**Note the proxy/target gap this exposes.** The mirror is Debian 7 "wheezy"
with glibc 2.13; the real target is SLES 12 SP5 with glibc 2.22. For
`renameat2` both are below the 2.28 threshold so the conclusion holds, but for
`O_PATH` the proxy is more restrictive than production. Anything C2 rejects on
header-availability grounds should say which of the two drove it, so C9's
qualification on real hardware can revisit it deliberately.

---

## 2. Scope

**24 requirements**, of which most are Test-verifiable and therefore land here.

### `L2-SEC-*` — 16 requirements

| Req | Substance | Method | Lands |
|---|---|---|---|
| 001 | All operations fd-relative; path-based prohibited | I + T | C2 (+ source gate) |
| 002 | `fstat` after `openat`, verify dev/ino/type against the prior `fstatat` | T | C2 |
| 003 | `O_RDONLY\|O_DIRECTORY\|O_NOFOLLOW` for dirs, `O_NOFOLLOW` for files | I + T | C2 |
| 004 | Classify by type; act only on regular files | T | C2 |
| 005 | Trusted UID; parent not world-writable without sticky | T | C2 |
| 006 | Validate external paths: absolute, no `..`, no control chars | T | C2 |
| 007 | *(read before implementing)* | T | C2 |
| 008 | Never `system(3)` or any shell | I + T | C2 (source gate) |
| 009 | Per-syscall timeouts on blocking calls | T | C2 partial, C5 completes |
| 010 | A stalled entry must not block others | T | **C4** (needs the worker pool) |
| 011 | Quarantine by endpoint, not by the naive one-path invariant | T | C2 |
| 012 | State store directory writable only by the service account | I + T | **C8** |
| 013 | *(read before implementing)* | T + D | C2 |
| 014 | Hardened systemd unit | I | **C8** |
| 015 | *(inspection)* | I | C2 doc |
| 016 | *(demonstration)* | D | **C9** |

The roadmap lists C2 as advancing `L2-SEC-001..016`; four of those genuinely
belong to later milestones. Recording the split here rather than discovering it
when the trace figure does not move as predicted.

### `L2-NFS-*` — 8 requirements

The important discovery: **most are testable without NFS**, if the layer is
designed so the strategy is selectable rather than implicit.

| Req | Substance | Testable in CI? |
|---|---|---|
| 001 | Detect `RENAME_NOREPLACE` at runtime per tree, never from kernel version | **Yes** — force each outcome |
| 002 | `linkat`+`unlinkat` is a primary tested path, not a fallback | **Yes** — if strategy is forcible |
| 003 | Recovery distinguishes an interrupted `linkat`/`unlinkat` pair from a real collision | **Yes** — create both names on one inode with a hard link |
| 004 | `ESTALE` is retryable, not a fault | **Yes** — classify errno as a pure function |
| 005 | Tolerate `.nfsXXXX` silly-rename artifacts | **Yes** — create such names |
| 006 | Document that identity checks weaken over NFS (attribute cache) | Inspection |
| 007 | Two-hop rename into the destination directory, with fsync | **Yes** |
| 008 | Durability claims are server-side; qualify on a real export | **C9 — demonstration only** |

Only 006 and 008 need something CI cannot provide. That is the argument for
making the strategy an explicit, injectable choice: it converts six NFS
requirements from "qualify on hardware someday" into "tested every commit".

---

## 3. Design

### Types

```
DirHandle      owns one directory fd, opened O_RDONLY|O_DIRECTORY|O_NOFOLLOW
FileIdentity   { dev, ino, type } — the tuple L2-SEC-002 compares
EntryKind      Regular, Directory, Symlink, Fifo, Socket, Device, Unknown
FsError        errno plus a classification (Retryable / Fatal / Denied)
MoveStrategy   RenameNoReplace | LinkThenUnlink
```

### Operations

Every one takes a `DirHandle` and a *name*, never a path. That is the shape
`L2-SEC-001` requires, and making the API incapable of expressing a path is
stronger than a rule saying not to write one.

```
open_dir(parent, name)                 -> DirHandle
classify(dir, name)                    -> EntryKind + FileIdentity   (fstatat, AT_SYMLINK_NOFOLLOW)
open_regular(dir, name, expected)      -> Fd    (openat O_NOFOLLOW, then fstat and compare)
detect_strategy(dir)                   -> MoveStrategy               (L2-NFS-001)
move_within(dir_from, from, dir_to, to, strategy) -> Result
publish(dir, temp_name, final_name)    -> Result                     (L2-NFS-007 two-hop)
classify_errno(int)                    -> Retryable | Fatal | Denied (L2-NFS-004)
is_silly_rename(name)                  -> bool                       (L2-NFS-005)
```

### Two source gates to add alongside

Following the `sql-confined` precedent — an inspection nobody runs is not a
verification.

* **`make fd-relative`** — fails if any source outside the filesystem layer
  calls a path-based operation (`open(`, `stat(`, `rename(`, `unlink(`,
  `mkdir(`, `opendir(`). Serves `L2-SEC-001`, which is specified as Inspection.
* **`make no-shell`** — fails on `system(`, `popen(`, `exec*p(`. Serves
  `L2-SEC-008`, also Inspection, and cheap insurance given ADR-0011 removed the
  external-command transfer strategy for exactly this reason.

Both get a negative test proving they fail, like every other gate here.

---

## 4. Testing

### The symlink-swap race (`L2-SEC-002`)

The requirement exists because `O_NOFOLLOW` stops a symlink but not a *swap*
between the `fstatat` and the `openat`. Testing it needs the swap to happen
inside that window, which no amount of test-side timing can arrange reliably.

Use the seam pattern C1 established for `inject_write_fault`: a hook invoked
between the classify and the open, default null, not behind an `#ifdef` —
because the code under test must be the code that ships. The test installs a
hook that replaces the file, and asserts the open is refused on identity
mismatch.

### Fault injection to add

`setrlimit(RLIMIT_FSIZE)` in a forked child, with `SIGXFSZ` ignored, for a true
kernel `EFBIG`. `docs/TEST-STRATEGY.md` deferred this until "C2 starts writing
files rather than rows" — that is now.

### What CI cannot cover

`L2-NFS-006` (attribute-cache weakening) and `L2-NFS-008` (server-side
durability) are Inspection and Demonstration respectively, and belong to C9's
qualification on real hardware. They should be *written down* in C2 as
explicitly deferred, not left to be noticed when the trace figure is short.

---

## 5. Sequence

1. Read `L2-SEC-007` and `L2-SEC-013` in full, plus `docs/CYBERSECURITY.md` §4.
   Two requirements above are placeholders precisely because they should not be
   summarised second-hand.
2. Land the syscall shim and its compile-time architecture guard, with a test
   that `RENAME_NOREPLACE` actually refuses to clobber. Smallest piece with the
   largest unknown — and the fidelity tier is the only place it can be proven.
3. `DirHandle` + `classify` + `open_regular` with identity verification, and
   the swap-race seam.
4. `detect_strategy` and both move paths, tested against each other. Force each
   strategy explicitly so `linkat`+`unlinkat` is a primary tested path.
5. `publish` two-hop, `classify_errno`, `is_silly_rename`.
6. Path validation (`L2-SEC-006`) and the trusted-UID / sticky-bit checks
   (`L2-SEC-005`).
7. The two source gates, each with a negative test.
8. Recovery disambiguation for the interrupted `linkat`/`unlinkat` pair
   (`L2-NFS-003`).
9. Trace matrix, docs, full battery, merge.

Steps 2 and 3 are where the design risk is. If either turns out differently
than the pre-flight suggests, stop and revise this plan rather than working
around it.

---

## 6. Coverage expectation

The roadmap estimates ~45% in-scope after C2, from 37.2% today. That assumes
all 24 requirements land here; four belong to C4/C8/C9, so **~43% is the
honest target**. A figure materially above that means requirements were tagged
onto tests that do not really verify them — the failure mode this project has
been careful to avoid, and the reason C1's tests carry no tag for the vendoring
smoke test.
