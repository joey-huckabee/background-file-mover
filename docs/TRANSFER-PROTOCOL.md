# Claiming and cross filesystem transfer protocol

This is the proposed Rust design baseline for moving a closed recording set between
approved filesystem roots. It keeps source data until the entire destination
set is verified and committed. The normal copy hashes the source as it is read
and independently rereads destination staging, following
[INTEGRITY-DESIGN.md](INTEGRITY-DESIGN.md). No Rust implementation or storage
qualification is implied by this specification.

Review producer acknowledgements using [REST-API-DRAFT.md](REST-API-DRAFT.md)
before freezing these contracts or starting implementation.

## Guarantees and boundaries

- `Accepted` means the request is durable. It does not release source paths.
- `Claimed` means every submitted source entry has been durably relocated into
  mover custody. Only this acknowledgement releases those paths for reuse.
- A final file is published only after complete copy and verification, without
  replacing another file. Files published before set commitment are not yet a
  consumable recording.
- A valid immutable `COMMITTED.json` is the recording's consumer visibility point.
  Durable SQLite confirmation follows its filesystem publication; these are
  separate effects, with explicit recovery between them.
- Source cleanup requires a reconciled set commitment and per-file receipts.
  It addresses private claimed entries, never the producer's reusable paths.

There is no atomic transaction spanning SQLite, source filesystems, destination
filesystems and all files in a set. Precommit claims are valuable retained data,
not disposable temporary files. An error or a lost response can leave an effect
applied. Recovery inspects durable intent and ownership/content evidence.

The baseline supports regular files and one destination filesystem per recording
set. Source files may span configured roots, each with its own same-filesystem
claim area. No recursive directory submissions, multi-destination commit,
external transfer commands, chunk resumption or same-filesystem
rename fast path is included. Even colocated endpoints initially use the same
copy/verification protocol. Source deletion is disabled in the first implementation.

The additive generator API supplies generator identity and a source directory/
file names; startup configuration chooses its destination. Normalize that form
to the same approved source-root/file records and pin the nonsecret resolved
destination/policy at acceptance. Existing explicit-root submissions remain a
separate permitted form. Generator identity is not authentication, and route
changes never move an already accepted job to a new destination.

An S3 destination is a future separately qualified delivery protocol behind the
same acceptance/claim/commit facts. The ordered filesystem effects below apply
to mounted filesystem destinations, not object APIs. S3 must define checksum,
conditional publication, multipart recovery and retention evidence before it
can authorize source cleanup; see the [REST destination design](REST-API-DRAFT.md#startup-destination-configuration).

## Producer and consumer contracts

The producer submits an explicit, nonempty, bounded file list with root IDs,
relative paths, optional expected sizes/recording metadata and an idempotency key.
An expected SHA-256 is optional. The service resolves destination names once,
rejects duplicate source entries and duplicate/reserved destination names, and
persists the resolved mapping and policy snapshot. Naming/config changes cannot
change an accepted job during retry.

The generator request can instead supply its mover-visible directory and file
names, without destination fields. The service resolves approved root IDs and
destination from validated startup configuration. Bind the normalized request,
idempotency scope and manifest to the generator identity for that form.

Names may include explicit relative subfolder components. Traverse each component
without following symlinks or leaving approved mounts; reject traversal into
service-private claim/staging areas. Only listed regular files are claimed;
directories are neither recursively discovered, moved nor deleted. Optional
expected sizes are producer assertions. Capture actual logical sizes from opened
files during claim, confirm stable identity/size after relocation and persist
them in claim receipts. Unknown sizes remain unknown until observed, not zero.

Acceptance also durably reserves each source root/path against other active
jobs. Reject a different submission overlapping an unreleased reservation.
Release those reservations in the all-files Claimed transaction, allowing a new
recording at the reused paths. Configure source scopes without root/mount aliases;
detect duplicate object identities before claims and block ambiguity rather than
letting different root IDs defeat ownership. Idempotency alone does not prevent
two different keys from claiming the same source.

Before submission, the producer completes and synchronizes its writes, closes
all writers, and promises not to modify, remove or replace the entries or their
parent directories until `Claimed`. No external hard-link aliases are permitted
in the initial contract; reject sources with multiple links before claiming.
The producer must not retain writable descriptors or modify claimed files later.
Rename preserves open descriptors and other hard links, so it does not establish
immutability by itself. [Linux rename documentation](https://man7.org/linux/man-pages/man2/rename.2.html).

`202 Accepted` is returned only after the job, full file list, policy and key have
committed locally. Status includes separate acceptance, all-files claim and set
commit facts, file counts and actionable conditions. A lost HTTP response or
client timeout does not cancel work. Repeating the key with the same normalized
request returns the same job; a different request conflicts. Keep durable key
tombstones when archiving jobs; do not silently reuse keys after queue pruning.

The producer waits for the all-files `Claimed` fact before reusing any submitted
path. Partial claiming releases none under this initial API contract. Preparation
that does not touch those paths may continue independently. `Claimed` does not
mean source disk space has been freed: files still occupy the source filesystem
until cleanup. A retried submission must not reopen reused producer paths to
reconstruct an already accepted/claimed recording.

Consumers open only sets containing a valid, supported `COMMITTED.json`, check
the exact listed files and treat their names/content as immutable. They ignore
uncommitted directories, staging and manifests with temporary names. Destination
retention must keep the committed set intact through mover cleanup; consumers
and retention agents cannot rename/remove its files during that interval.
Manifest validation gives set-level visibility, not atomic discovery across
clients or protection against privileged storage tampering.

## Ownership and filesystem prerequisites

Use one active coordinator per local state database and disjoint source scopes
across instances. A local lock is not cross-host fencing. Old and new services
must not operate on the same source namespace during cutover.

Resolve configured root IDs with descriptor-relative, component-wise traversal.
Reject absolute paths, `..`, symlinks, nonregular entries and traversal into
unapproved mounts. Hold validated directory/file descriptors during operations;
check root/mount identity again on startup, recovery and dispatch. An unavailable
expected NFS mount must not redirect operations into the underlying local path.
Device/inode numbers and mount IDs are observations, not permanent global IDs.

An illustrative layout is:

```text
source-root/.file-mover/claims/<instance-id>/<job-id>/<file-id>
destination-root/recordings/<job-id>/
    .control/                 private operation ownership records
    .staging/<file-id>/<attempt-id>.part
    <resolved-final-name>
    COMMITTED.json
```

Claim areas are private and reside on the same mounted filesystem as the source
entries they claim. Staging and final names reside on the destination filesystem.
Private directories are service-only; consumers receive read/traverse access to
published data but no modification rights. The approved parent directories must
prevent untrusted entry swaps. Descriptor-relative access alone does not stop
another writer changing a leaf entry between checking and unlinking it.

Persist directory-creation intent, allocate exclusively, synchronize required
parents and bind ownership records to the recorded instance/job/attempt. Never
adopt an existing directory by writing a fresh ownership marker into it. An
ambiguous creation without sufficient ownership evidence is blocked for
reconciliation. Unexpected entries are preserved, not recursively erased.

Qualify no-clobber rename on each actual filesystem. For regular files, a
qualified exclusive hard-link followed by removal of the old name is a fallback,
with each substep recorded/reconciled. Never use check-then-overwriting-rename.
If neither strategy is qualified, retain the source and block that endpoint.
`RENAME_NOREPLACE` requires filesystem support; ordinary rename replaces an
existing destination. Hard links cannot cross mounted filesystems.
[Linux rename documentation](https://man7.org/linux/man-pages/man2/rename.2.html),
[Linux link documentation](https://man7.org/linux/man-pages/man2/link.2.html).

Use rustix/POSIX facilities compatible with GNU/glibc 2.22 and the target kernel;
do not require openat2 or a newer libc renameat2 symbol. Qualification checks the
selected rustix implementation, runtime fallback and actual mount capabilities.
Directory/data durability must have a documented, qualified endpoint contract.
If required synchronization cannot be established, do not acknowledge a durable
claim/commit or enable deletion. A successful capability probe is not a server
power-loss test. [Linux fsync documentation](https://man7.org/linux/man-pages/man2/fsync.2.html).

## Durable records and worker authorization

SQLite stays on local persistent storage, owned by one dedicated thread, using
checked WAL/FULL/foreign-key settings and short transactions. No database
transaction or coordinator lock spans a filesystem operation.

Persist at least these records:

| Record | Required evidence |
|---|---|
| Job | Version, instance/job ID, idempotency key and normalized request, immutable file list/name mapping, root configuration identity, policy and desired execution |
| File | File ID, producer relative path, optional expected size/digest, observed source identity, actual claimed size and private claim path/receipt |
| Operation | Unique operation/attempt ID, phase, assignment generation, exact source/target names, prerequisites and durable intent before dispatch |
| Copy receipt | Complete byte count and streamed SHA-256, source/attempt identity, staging identity and successful synchronization evidence |
| Verification receipt | Independent staging digest/size match, same staging object, applied permissions/metadata policy |
| Publication receipt | Final path/object identity, verified digest/size, owning job/file/attempt, strategy and directory synchronization evidence |
| Set receipt | Exact versioned manifest bytes/digest, listed publication receipts, publication and synchronization evidence |
| Cleanup record | Committed-set authorization, exact claimed identity/path, deletion intent, observed result and synchronization evidence |

Worker commands refer to durable operation IDs and bounded private IPC. Workers
cannot invent new attempts, publish a manifest, or delete sources without the
corresponding durable authorization. Results include assignment generation and
operation identity; stale/duplicate messages cannot advance a different attempt.
Progress is advisory and coalescible. Transition results require durable storage.

Represent outcomes as `Applied(receipt)`, `NotApplied(evidence, error)` or
`NeedsReconciliation(evidence, error)`. A syscall error alone is not proof of
`NotApplied`. Record each step of a link/unlink strategy; a created link followed
by failed unlink is a partial effect. If storing a result fails, stop dependent
effects and reconcile from the previously committed intent after recovery.

Assignment generations fence messages, not filesystem effects. A timed-out or
disconnected worker may still perform an authorized syscall. Do not dispatch
conflicting work until the old process has exited and outstanding remote effects
have been reconciled under the qualified endpoint contract. Killing a process
does not roll back an NFS request already sent. Bound blocked/replacement workers;
when evidence is insufficient, retain data and report `ReconcileRequired`.

## Ordered transfer

1. **Accept.** Validate the request without mutation; commit all intent/key/name
   records. Perform source inspection in bounded filesystem workers, not the API
   executor. Acceptance is not a promise that every later capability/size check
   will succeed.
2. **Claim every file.** Open and validate the completed source, commit its
   observed identity and claim intent, then relocate into the exclusive private
   claim name on that source filesystem. Confirm the claimed object matches the
   opened source and its observed size; compare any optional expected size.
   Synchronize claimed data and both affected directories as required by the
   endpoint contract; persist its receipt including the confirmed actual size.
   With a link fallback, first durably establish the private link, then remove
   the original entry only under the handoff/exclusive-parent contract and
   identity checks; synchronize that removal. Claim is incomplete while both
   names remain. `EXDEV` here is a claim configuration failure, never permission
   to copy-and-delete the producer entry.
3. **Acknowledge Claimed.** Commit the all-files claim fact only after every
   receipt is confirmed. Lost acknowledgements are recovered by the job/key.
   Claiming is not atomic across files: on failure retain successful claims and
   reconcile the rest. Never automatically roll them back onto producer paths.
   Initially begin bulk copying only after all files are claimed.
4. **Copy.** Commit a new attempt/staging intent, create exclusively, and stream
   from the claimed source through a bounded buffer while hashing the exact
   bytes written. Handle partial writes. Require EOF, exact recorded claimed size and
   optional expected digest match; compare source identity/size/change indicators
   around copying. Apply the recorded safe metadata/permission policy to staging,
   synchronize it and its directory, then persist the complete-copy receipt.
   Metadata checks supplement the producer contract; they cannot prove that
   a concurrently modified source was a consistent snapshot.
5. **Verify.** Independently reread the same staged object and require exact
   byte-count/SHA-256 equality with the complete-copy receipt. Persist verified
   evidence before authorizing publication. No writer may change staging after
   verification. A mismatch retains the source and records a failed attempt.
6. **Publish each file.** Commit publication intent and publish without clobber.
   Confirm final ownership/content identity and synchronize affected directory
   entries before persisting the publication receipt. A foreign final entry is
   a collision even if its bytes match. Link publication may leave a redundant
   owned staging alias; remove it only after the final entry is durably confirmed.
7. **Commit the set.** Once every file receipt is durable, generate the exact
   immutable manifest, persist its bytes/digest and publication intent, write and
   synchronize owned manifest staging, then publish `COMMITTED.json` without
   clobber and synchronize its directory. This is the consumer visibility point.
   Persist the reconciled set receipt before issuing any cleanup authorization.
   If SQLite fails after publication, consumers may already see a committed set;
   reconcile it without replacing/removing the manifest or recopying its files.
8. **Clean up.** Only when enabled by the recorded policy and reconciled set
   receipt, revalidate the intact destination set and exact claimed source
   identities, commit per-file cleanup intent, close mover-held source handles,
   unlink only the authorized private entries, synchronize their parents and
   persist results. Missing entries require reconciliation of authorized intent,
   not a fresh unlink of the producer path. Cleanup failure leaves a committed
   recording with `CleanupPending`; it does not restart transfer or uncommit it.

On the uninterrupted path, cleanup revalidation checks the protected namespace,
receipts and unchanged object identities/metadata; it does not mandate a second
destination hash pass after verification. Lost custody, changed observations or
restart reconciliation may require full content rereads or blocking. Permission
and retention contracts are what keep verified objects unchanged between steps.

Normal data I/O remains N source read + N destination write + N destination reread.
Claiming changes names/links without another payload copy. Recovery may require
extra reads. Initial retention mode reports `Committed` with `SourcesRetained`,
not a completed destructive move. A successful enabled move reaches `Complete`
only after every source deletion is confirmed durable under the endpoint contract.

## Manifest and public state

The manifest is versioned, strictly parsed and bounded. It binds the instance,
job/recording identity, submitted generator identity where provided, immutable
request identity and each required file's ID,
resolved relative final name, byte count, integrity algorithm and SHA-256.
Store its exact serialized bytes before publication; do not regenerate timestamps
or formatting differently on retry. Its owning receipt binds the actual manifest
object and published files. Reject reserved names, duplicate fields/entries,
unlisted additions to the required set and unsupported versions. Filenames use
an explicit lossless API/manifest encoding policy before implementation.

File phases are `ClaimPending → Claimed → Copying → CopyComplete → Verified
→ PublishPending → Published → CleanupPending → SourceRemoved`. Operations carry
their own intent/result records, so a phase is never the only recovery evidence.
Job facts track `Accepted`, all-files `Claimed`, `Committed` and `Complete`.
Keep desired execution (`Running`, `Paused`, `Cancelled`) separate from condition
(`Ready`, `Retrying`, `Blocked`, `ReconcileRequired`) and source-retention policy.

Pause stops new authorizations and requests cooperative stopping; already
authorized operations may finish and must be recorded. Before manifest
authorization, cancellation stops further transfer work and preserves claimed
sources/published files for explicit recovery or no-clobber restoration tooling.
Once manifest publication is authorized, cancellation is pending reconciliation:
it cannot promise the set stayed uncommitted. After commitment, cancellation
cannot retract visibility; it may request retaining remaining sources, subject
to already authorized cleanup. No control command blindly deletes staged/final
objects or restores claims over a producer's newer recording.

## Recovery decisions

Start by recovering local ownership, checking mounts/capabilities and fencing
workers, then reconcile unfinished intents before admitting conflicting work.
Evidence combines private namespace custody, durable operation records, object
identity and content checks. A name, sidecar token, inode number, equal length or
matching hash alone does not establish ownership. Inode reuse, remounts, changed
exports and missing ownership records must not authorize destructive recovery.

| Observed boundary | Safe decision |
|---|---|
| Accepted with no claim effect | Validate the still-reserved producer entry and retry the recorded claim |
| Claimed object exists, result not stored | Confirm ownership/identity and required synchronization, then persist receipt; do not reread a reused producer name as the source |
| Claim fallback has both names | Finish removal only if original still denotes the reserved handed-off object and custody is proven; otherwise block |
| Original is absent and claim is absent/unproven | Report missing/ambiguous data and preserve other files; do not declare Claimed |
| Some files claimed, others failed | Retain claims and continue reconciliation; no all-files path-release acknowledgement |
| Partial staging or no durable complete-copy receipt | Fence the old worker, preserve source, create a new exclusive attempt and restart; retire old staging only with ownership proof |
| Durable copy receipt with staging present | Validate ownership and fully verify contents before advancing; plausible length is insufficient |
| Final exists after uncertain publication | Reconcile recorded publication, ownership and full digest/size; synchronize and persist receipt, or block collision/ambiguity |
| Final and staging alias both exist | Verify they are the owned publication effect; keep final and retire redundant staging without treating link/unlink as all-or-nothing |
| All files published, no committed manifest | Reconcile all receipts, then publish the recorded manifest; retain all sources |
| Manifest exists, set receipt missing | Validate exact expected manifest and file evidence, synchronize as required, then persist commitment; do not overwrite it |
| Committed set with cleanup pending | Revalidate destination/custody and retry only authorized private-source cleanup |
| Deleted source, cleanup receipt missing | Reconcile absence in the protected claim namespace and synchronize parent before recording removal; do not touch producer reuse |
| Root changed, foreign object, stale worker, uncertain remote effect or lost DB | Block destructive actions; require explicit recovery. A new empty DB must not auto-adopt filesystem leftovers |

NFS rename errors can occur after the server has applied the rename. An error
therefore triggers reconciliation rather than a blind retry or rollback.
[Linux rename documentation](https://man7.org/linux/man-pages/man2/rename.2.html).
Use the qualified consistency/revalidation behavior of the actual endpoint;
cached absence alone must not certify a remote mutation never occurred.

Privileged agents can still quarantine/delete/replace objects. Detectable
interference blocks cleanup and requires diagnostics. No local check can promise
continued destination existence against a privileged actor racing the subsequent
unlink. The deletion guarantee requires the stated custody and destination
retention contracts; deployments unable to enforce them keep deletion disabled.

## Required failure evidence before enabling deletion

Exercise crashes before/after every durable intent, effect, synchronization and
result commit, including individual link/unlink steps and manifest publication.
Verify lost acceptance/claim responses, conflicting idempotency keys, partial
multi-file claims, claim `EXDEV`, producer reuse, size changes, aliases and leaf
swaps. Exercise partial writes, ENOSPC, sync/read failures, digest mismatch,
foreign equal-content collisions, missing/replaced finals and unsupported
no-clobber strategies. Include empty files and multi-file sets.

Test DB failure after publication, manifest collision/malformed content, crashes
after manifest publication but before SQL commitment, cleanup failure/absence,
mount disappearance/remount, late worker results and a timed-out worker that
continues executing. Prove no unrelated object is overwritten/deleted, no reused
producer path is touched, no incomplete set becomes consumable and cleanup retry
does not recopy committed files. Model cancellation at publication/cleanup races.

Use local isolated filesystems, pinned SLES 12 SP5-equivalent userspace containers
and the controlled [NFS fixture](NFS-TEST-FIXTURE.md). Containers share the runner
kernel; keep that limitation explicit. Server restart/storage durability tests
are separate qualification work; no actual SLES host is required.

## Requirements and implementation handoff

Keep historical C++ traceability intact until a separately reviewed Rust mapping
exists. The Rust mapping must retain the intent of `L1-SYS-002/003/004/006/010/014`
(claim release, retention, integrity, safe publication and actionable failures).
Revise `L1-SYS-015`/`L1-SEC-007` for copied cross-filesystem transfer,
`L1-SEC-001/002` for set visibility plus recoverable effects instead of disposable
precommit state, and `L1-SYS-021/022` for file/job phases and orthogonal controls.
Existing C++ evidence is not Rust verification.

Before code: review this baseline with the producer/consumer interfaces, settle
the filename encoding and metadata policy, derive schema/transition definitions
and the fault matrix, and revise the detailed milestone sequence. Qualify the
actual claim/publication/durability strategies before acknowledging them in
production. Implement one recoverable cross-filesystem transfer with deletion
disabled first; enable deletion only after set/cleanup failure evidence passes.
