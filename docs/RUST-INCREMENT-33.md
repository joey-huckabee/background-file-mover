# Rust increment 33: durable backoff for payload-copy capacity failures

Increment on `feature/rust-transfer-coordinator`, 2026-10-16. Implements the first
case in [the retry policy](DELIVERY-RETRY-POLICY.md): native ENOSPC during an owned
payload copy. No dependency, binding-version-3, public status shape or persisted
receipt changes. Adds schema 11 to widen the retry-code constraint transactionally,
a status code and private delivery-session wire version 2. Production NFS/deletion remain disabled.

## Behavior and boundaries

Capacity failures wait 30 seconds after persisted failure 1 and 60 seconds after
failure 2; failure 3 still requires audited resume. Its saved 120-second deadline
never bypasses review. SQLite records count/class/deadline atomically and restart
retains them. Mixed classes share the original three-failure budget. A late capacity
result cannot replace an already durable review reason. Generic failures, immediate
binding review, unavailable-destination deferral and uncertain effect reconciliation
keep their existing behavior.

The filesystem error retains its typed payload operation and errno independently
of diagnostic formatting. Only copy-write ENOSPC qualifies. The worker sends the
hint only for a failed Payload/Intent operation. The parent rejects out-of-scope,
unknown or mixed success/failure hints before selecting capacity backoff. Hints
never grant a transfer/manifest receipt, repair, deletion or takeover authority.
Native filesystem calls/order, 3N integrity, protected namespace recovery, partial
retention and attempt limits remain unchanged. Broader automatic capacity waiting,
free-space probes and configurable/jittered schedules remain future work.

## Tests and qualification scope

Migration tests use the historical schema-10 constrained table and compare every
retained table row before/after upgrade, including active ownership/enrollment,
route pins, claims, two attempt records, manifest intent, reservations, missing
deadlines and both operator audit types. A controlled invalid-code copy failure
checks rollback of DDL, rows and schema version. Read-only old-schema refusal is
retained. SQLite scheduling tests cover exact 30/60/120-second deadlines, candidates immediately before/
at the deadline, pending/review restart, mixed failure counts, preserved binding
review, audited reset/replay, negative times, saturated deadlines and atomic SQL
failure rollback. The filesystem tests reject classification by spoofed operation
text or errno alone. IPC tests reject mixed transfer/manifest receipts, wrong
operation scope, unknown classes and missing diagnostics; formatted text alone
does not grant a hint.

The local API tests preserve the eight existing payload failures and 14 staging/
manifest failures; ENOSPC now reaches the new code through its real worker. A new
pending-restart case removes the synthetic capacity fault, keeps the original
saved deadline and commits at the next attempt without resume. Original source,
producer reused path and old attempt survive. Production ignores the fault controls.

The retained real destination-full fixture checks the four original review/resume
cases plus two automatic recovery cases, one per profile. Automatic cases restart
while waiting after two ENOSPC failures, restore capacity, retain the saved deadline
and commit attempt 3 without resume. Submission replay while waiting must retain
count/deadline/review and the producer reused path. The four reviewed cases still need audited
resume and commit attempt 4. Six directional NFS baselines, selected three-minute
outages and OS startup/lock checks regress session/scheduling behavior using the
same audited artifacts. No native filesystem effect logic changed, so the full
short-interruption/ownership matrix from [32](RUST-INCREMENT-32.md) is retained as
prior evidence rather than claimed as rerun here.

## Validation

Production gate `20261016T113703Z-30e9cda0` PASSED 164 tests per debug/release
profile. Qualification gate `20261016T113703Z-11000334-nfs-qualification` PASSED
165 per profile. Both passed formatting/Clippy, 20 executable ELF audits per mode,
six negative controls and exact pinned SLES userspace execution. Each profile
passed all 66 API tests. Source archives contain the same 56 current files;
source/archive/executable hashes were verified. The external graph stays at 42
packages and maximum required GLIBC remains 2.18. See
[production evidence](RUST-SLES-EVIDENCE.json) and
[qualification evidence](RUST-SLES-QUALIFICATION-EVIDENCE.json).

Targeted NFS run `nfs-20261016T115844Z-35fdd61d` PASSED with exit status 0 and
`cleanup_errors: []`: six directional delivery baselines, six real destination-full
cases and four selected three-minute claim/verification outage/recovery cases,
plus OS inherited-lock, interrupted-metadata, isolated startup/shutdown and
production NFS refusal checks. See [native NFS evidence](RUST-NFS-CAPACITY-BACKOFF-EVIDENCE.json).

All four reviewed capacity cases retained three safe copy-write ENOSPC logs,
reached ReviewRequired with the new code, preserved review through restoration
and required audited resume/replay to commit the original job on attempt 4. The
two automatic cases restarted with two failures, retained the count/class/deadline,
restored capacity and committed the same job on attempt 3 without resume. All six
preserved original source, the reused producer path and old partials, and accepted
same-key submission replay without resetting retry/review evidence. Recorded
observations rejected attempts seen before a pending deadline. The completion
manifest/server hashes matched original bytes; all four cases that restarted
after commitment retained it.

Maximum sampled combined health/status time was 4.50 seconds including host engine
and transport overhead, below the selected 15-second fixture window; this is not a
production SLO. Each long outage retained one blocked worker, responsive status and
live recovery. The full short-interruption, two-client ownership and enrollment
storage suites were not rerun here; [32](RUST-INCREMENT-32.md) retains their prior
scope/evidence. Real destination ENOSPC here is separate from synthetic local EIO.

Verified recorded fixture-driver hashes and Rust source/artifact provenance.
Cleanup left no containers, only the default Podman network and existing Rust
1.99/toolchain and registry cache volumes. Images and NFS modules remain. Builds
used the Windows checkout, root Podman WSL2 fallback and native container `/work`;
SLES 12 SP5/glibc 2.22 userspace shared kernel
`6.18.33.2-microsoft-standard-WSL2`, with hard NFSv4.1 and `local_lock=none`.
No real server EIO, physical disk/quota, power-loss, old-kernel/hardware or
independent-host fencing claim. Production NFS/deletion remain disabled.

Rerun after both mandatory gates:

```text
python scripts/check-nfs-boundaries.py rust/validation/<production-run> --qualification-gate rust/validation/<qualification-run> --isolated-startup --delivery-storage --runtime --long-outages-only
```

Maintain SC-051/052/071/072/074 and DOC-01–05 in
[the scenario catalog](RUST-SCENARIOS.md).

## Development findings retained

Initial runs `20261016T112215Z-e4895c4f` and
`20261016T112215Z-c5d2e609-nfs-qualification` failed compilation: the new rollback
test used `StoreError::Sql` instead of existing `StoreError::Sqlite`. Corrected it.

Runs `20261016T112333Z-c58784cb` and
`20261016T112333Z-9f79cb37-nfs-qualification` then found six direct-session tests
still sending wire version 1. Updated valid requests/replies to version 2 and
extended stale-sequence rejection to include old versions. The qualification run
also found capacity-path connection resets caused by the existing retry-code CHECK.

Intermediate production run `20261016T112937Z-9df15912` passed 66 API tests but
failed the three capacity SQLite tests, confirming that exact CHECK constraint.
Qualification companion `20261016T112937Z-e443a674-nfs-qualification` passed the
direct-session tests but still failed the two affected capacity API paths. Schema
11 is therefore required; transactionally widen the constrained vocabulary rather
than change historical DDL in place. Added preservation and rollback tests. These
failed runs are findings, not passing evidence. Final passing gates above include
both corrections and the migration; no native NFS error is injected by these local
synthetic tests.
