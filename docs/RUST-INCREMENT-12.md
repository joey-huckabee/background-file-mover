# Claim and publication child workers

The service now performs source observation, private claim-directory allocation,
claim rename/reconciliation, per-file publication/reconciliation and final
`COMMITTED.json` publication/reconciliation in supervised children of the same
executable. Copying and verification remain child operations from increment 11.
SQLite stays in the coordinator's dedicated owner thread. No REST endpoint,
dependency, schema migration or startup setting is added. The recorder still
submits the same JSON, retries the same submission ID and receives 202 only after
every claim has a durable applied receipt.

## Claim sequence

1. The parent durably accepts the job and checks for an existing claim receipt.
   A completed claim is replayed without reopening a reused producer path.
2. An observation child measures and validates the source without allocating
   directories or moving data. Its temporary area observation identifies the
   namespace, not an allocated claim directory; it is not saved as a claim intent.
3. The SQLite owner checks capacity using the observed size.
4. An allocation child repeats the observation and rejects changed source/root/
   parent/namespace evidence before exclusively allocating the private directory
   and synchronizing it. The parent checks immutable receipt fields and persists
   the actual allocated claim intent.
5. Only then does an apply child rename without clobber or reconcile an uncertain
   prior rename, validate source identity/original-path absence and synchronize
   the relevant file/directories. The parent matches the returned claim to the
   exact unfinished intent and persists the applied receipt.

Missing-source and expected-size errors retain their API behavior. Malformed,
failed or interrupted child communication is uncertain/blocked, not proof of
absence or a completed handoff. No transaction spans filesystem work. The old
allocation-before-intent crash gap remains: a lost allocation receipt leaves an
unattributable private directory and blocks reuse; it never authorizes a rename,
adoption or deletion. Durable allocation intents remain future work.

## Publication sequence

After independently verified staging, the coordinator records `PublishIntent`.
A child publishes the file with NOREPLACE, validates custody and synchronizes
staging/final directories before reporting `Published`. Lost receipts reconcile
only when the staging name is absent and the owned final identity/content match;
equal content in a foreign object does not permit adoption or replacement.

Once all files are published, the existing parent path constructs, allocates,
writes and verifies the exact manifest and records its publication intent. A
child publishes `COMMITTED.json` without clobber, independently validates exact
manifest bytes/object identity and synchronizes the file and directories. The
parent accepts only an unchanged manifest/object with phase 4 and then records
the committed receipt. A crash after the filesystem commit but before its SQLite
receipt is reconciled, never undone. The integrity path remains 3N.

## Resource and custody boundaries

One serialized claim coordinator and one serialized delivery coordinator permit
at most one claim child plus one delivery child at a time. Claim capacity is
reserved separately from long-running delivery. Both inherit the same protected
source namespace lock; claim children use it for both lock descriptors and never
require the destination to be online. Delivery children also inherit the
destination lock. Private sockets carry metadata only. Claim requests/replies and
ordinary transfer requests are bounded at 32 KiB, transfer replies at 2 KiB;
manifest requests allow 384 KiB for the existing 128 KiB manifest plus JSON
escaping and assignment metadata. Unknown/duplicate fields, invalid versions,
paths, phases and copied-file evidence are rejected.

The common supervisor requests termination and confirms exit before replacement.
Inherited locked open descriptions survive coordinator descriptor closure. A
signal/timeout is not a fence; a stuck worker or failed reaping can delay shutdown.
The internal worker modes are trusted local implementation interfaces, not an OS
sandbox or authenticated public API. The stopped-daemon reference CLI still runs
inline. Local locks do not establish distributed NFS ownership.

## Evidence and remaining work

Three new exact-service subprocess tests cover observation without allocation,
capacity/intent/receipt ordering, lost claim receipts and producer-path reuse;
confirmed absence and changed-source refusal before allocation; and repeated
file/manifest publication after effects completed without database receipts.
Existing process-crash, collision, handoff, background delivery and manifest
tests remain required. This extends the worker architecture and provides partial
Rust evidence for claim/recovery behavior (`L1-SYS-002`, `L1-SYS-006`), not full
configurable concurrency (`L1-SYS-017`) or production NFS qualification. Formal
Rust L2/L3 trace derivation remains roadmap work.

Destination staging allocation/restart, manifest allocation/write/initial
verification, some custody/root checks and already-published reconciliation reads
still run on local coordinator threads. Isolate those before controlled NFS
transfers; qualify coordinator death, worker interruption, mount/root replacement
and stable ownership. Source deletion and NFS remain disabled. Offline inspection,
repair and registration remain deferred. No real SLES host test is required.

The mandatory gate passed via native WSL in
`rust/validation/20261014T003656Z-cd890708`: 94 tests per profile (10 core,
35 storage, 10 claims, 13 transfer/manifest, 26 executable/API), debug and release.
All 20 executable artifacts passed ELF/loader/library audits and eager relocation
in pinned SLES userspace; maximum required version remains GLIBC_2.18. Six negative
audit controls passed; the external Linux graph remains 42 packages. Container
cleanup recorded no errors. Formatting, Clippy with warnings denied and the
existing trace-matrix check passed. See
[RUST-SLES-EVIDENCE.json](RUST-SLES-EVIDENCE.json).

The earlier run passed the three new worker tests but exposed two completion
tests stopping the daemon after manifest visibility and before its database
receipt. Those tests now wait for both the manifest and durable `Committed`
status before shutdown; the lost-receipt tests still exercise the intervening
state. No completion condition was removed. Containers share the runner kernel
and CPU; these results do not qualify old-kernel behavior, NFS or power-loss
durability.
