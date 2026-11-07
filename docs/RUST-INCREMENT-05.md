# Rust single-file copied transfer increment

The first copied-file transfer is available through the actual Linux executable:

```sh
file-mover --transfer-one /path/to/local.json 1
```

The configuration identifies the local database; the job ID selects the accepted
recording. Its persisted destination is used, including after configuration
changes. This slice requires exactly one fully claimed file with grouping disabled.
Submitted subfolders are preserved beneath `<destination-root>/<job-id>/`.
The transfer holds local source/destination namespace locks. Stop the local REST
service before running this command; its claim lock deliberately excludes the
second worker. Automatic background delivery scheduling is not implemented yet.

Provision the destination root and its `.file-mover` directory with the same
protected service ownership as the source setup. Claim files must remain immutable.
Source and destination may be on different admitted local mounted filesystems;
staging/final publication occurs entirely on the destination filesystem. NFS and
other unqualified endpoints remain blocked. Use disposable fixtures until the
production mount, worker, storage and namespace contracts are qualified.

On success the command reports `Published`, SHA-256, actual size,
`source_retained:true` and `committed:false`. The claimed source remains in
private custody and a producer's reused path is untouched. There is no source
deletion or `COMMITTED.json`; consumers must continue waiting for that manifest.
File publication does not imply recording commitment or cleanup authorization.

## Integrity and durable effects

Copying reads the claimed source once through a reusable 1 MiB buffer, hashes
those same bytes and uses write_all for destination writes. Require EOF and the
claimed byte count, recheck source identity/size/mtime/link count, set staging to
owner-read-only, synchronize it and its directory, then commit copy evidence.
Verification independently rereads that staging object, checks digest/byte count
and unchanged observations, then commits verification. The normal path remains
N source read + N destination write + N destination reread = 3N logical data I/O.
It does not prehash the source or copy using rename across filesystems.

Schema 4 stores immutable destination root/name mapping, root/recording/private
staging/final-parent directory observations, stage identity, attempt, copy digest
and phase. Versions 1–3 migrate transactionally without replacing acceptance,
claim or missing-file records. Storage rejects phase skips, changed intent fields
and changed receipts after copy completion. Loaded recording phases restore
Verified/Published from those trusted worker receipts; set commitment is absent.
No transaction spans filesystem I/O. SQLite still cannot prove fsync or custody.

The filesystem worker exposes tested boundaries: Intent, Copied, Verified,
PublishIntent and Published. A committed publication intent precedes the
descriptor-relative NOREPLACE rename. Required file/directory synchronization
precedes recording Published. A final collision is retained, even if its bytes
match. Symlinks, changed directory/file identities, extra aliases or uncertain
effects block advancement. No overwrite, link fallback or source deletion occurs.

Normal publication checks the protected verified object and synchronizes it;
it does not add a second destination hash pass. If a final exists after an
uncertain publication, recovery requires the recorded private custody/identity,
absence of the staging name, and a full final digest reread before persisting
publication. Missing/replaced published data blocks rather than causing blind
recopy or replacement. Identity numbers/hash equality alone never adopt a foreign
destination; protection depends on the stated directory/worker custody contract.

## Partial-copy recovery and remaining limits

An interrupted copy without a committed copy receipt starts a new exclusive
staging attempt beneath the recorded owned directory. Previous staging is kept,
including a completely written file whose receipt commit failed. Attempts are
limited to 100; exhaustion requires review. Existing complete-copy evidence
resumes verification, and existing publication intent reconciles publication
without recopying the source. Failures preserve the claimed source.

Initial destination directory/staging allocation is exclusive and synchronized
before copy intent commits. A failure in that allocation gap leaves an orphan
and blocks reuse rather than adopting/deleting it. A staging attempt allocated
before its new intent commits is also preserved and blocks conflicting allocation.
Production needs persisted creation intent, stable instance/mount ownership,
orphan reconciliation and bounded retained-byte/attempt budgets. Old staging is
not automatically retired. No resume-from-offset, metadata-preservation policy,
multi-file delivery, manifest, operator repair or deletion is implemented here.

## Dependencies and evidence

SHA-256 uses pinned sha2 0.10.9 with defaults disabled and std/force-soft enabled.
The selected [crate features](https://docs.rs/crate/sha2/0.10.9/features) permit the
software backend without an assembly feature. The nine new transitive/direct
packages and their exact versions/checksums/licenses are recorded in
[rust-integrity-dependencies.json](../scripts/rust-integrity-dependencies.json).
Declared licenses are MIT/Apache-2.0-compatible under the existing policy. The
earlier E5 graph remains unchanged; E6 and standalone package experiments remain
paused. This increment qualifies the added graph through the mandatory gate.

The gate checks package graph/checksums and exact sha2 features, compiles offline
with baseline x86-64 flags using cargo-zigbuild for GNU/glibc 2.22, audits every
executable and executes the exact debug/release tests in pinned SLES userspace.
Python 3.11+ is needed by the host harness for standard-library TOML parsing;
there is no Python/runtime/hash package to install on the deployed Rust target.
Current counts, inputs, import versions and hashes are in
[RUST-SLES-EVIDENCE.json](RUST-SLES-EVIDENCE.json).
The passing run has 59 tests per profile and twenty audited executables, with
maximum imported version GLIBC_2.18 and no additional shared libraries.

Tests include a real cross-device overlay-to-tmpfs copy larger than the buffer,
an independent system hash comparison, SHA-256 empty/abc known vectors, nested
layout, source retention/producer reuse, corruption with restored size/mtime,
foreign equal-content collisions, changed source/staging custody, allocation
orphans, SQL failures after copy/publication, migration and phase rollback.
Subprocesses exit without destructors after intent, partial data write, completed
copy, verification, publication intent, rename before directory sync and receipt.
Recovery proves new-attempt retention versus verification/publication resumption.
An executable integration test submits over HTTP, stops the daemon and invokes
the real transfer command inside SLES userspace.

Containers share the runner kernel. Tmpfs/cached rereads and successful fsyncs
are process-recovery evidence, not storage/server power-loss qualification or
proof for an old SLES kernel. NFS effects and destructive cleanup stay deferred.
This slice supports the copied-file integrity/publication intent of L1-SYS-003,
004/014 and L2-DPR-001/003 plus the 3N protocol. Rust evidence does not promote
historical C++ trace status. Next: automatic delivery scheduling, multi-file
recording completion manifests and failure qualification, keeping cleanup disabled.
