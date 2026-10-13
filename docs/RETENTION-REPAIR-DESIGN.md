# Retention and orphan repair boundaries

This is a forward design contract, not an implemented repair command. Read-only
database accounting is implemented in [increment 10](RUST-INCREMENT-10.md).
Source deletion, staging reclamation, orphan adoption and namespace repair remain
disabled. Keep the existing files and receipts while developing those effects.

## Evidence required before repair

An inspection result must distinguish database intent/receipt evidence from
current filesystem observations. A matching pathname, service UID, file age,
plausible length or matching digest alone does not establish operation ownership.
An empty-looking directory alone does not establish ownership either.

Inspection should run with the daemon stopped and qualified root/namespace locks
held, using descriptor-relative NOFOLLOW traversal and bounded output. Before
enabling effects, qualify stable instance/root/mount authorization and prove
that every worker capable of touching the affected objects is fenced. A pause
flag, timed-out request or sent signal is not such proof. NFS work that remains
blocked after a signal must not be redispatched or have its objects reclaimed.
The current local thread profile is not a production worker-fencing mechanism.

Classify each observed object as a recorded current operation, a recorded
superseded attempt, a completed retained object, an allocation without a receipt,
or foreign/uncertain. Classifications must carry exact root/operation/object
evidence and never imply that the database report scanned the filesystem.

## Allocation gaps

Claim directories, destination recording/staging directories and manifest staging
can be allocated before their owning receipt is durable. A crash in that gap
currently blocks recovery. Add durable allocation intent before the dependent
effect, with immutable instance, job/file/attempt, authorized root and operation
identity. Specify how a receipt binds the actual allocated object before any
payload move or write is allowed.

An intent alone cannot prove that an existing object was created by its effect.
If an interrupted allocation cannot be attributed under the qualified namespace
and worker-ownership protocol, retain it and require review. Do not retrofit
ownership to existing unreceipted objects merely from their deterministic names.
Do not remove a directory recursively or move its contents into a job to unblock
claiming. Existing allocation gaps need explicit operator evidence; new intent
records do not retroactively make those gaps safe to adopt.

## Superseded staging and source retention

Reclaiming an older staging attempt requires immutable ownership evidence,
qualified fencing, and a verified replacement/committed delivery under the
required policy. `Intent` does not mean empty: an interrupted copy can have
written data without recording its completed size. Validate the owned object
through held descriptors; reject aliases, replaced entries and uncertain roots.
Never delete consumer-visible final files or `COMMITTED.json` to release a budget.

Source cleanup remains a separate protocol: every required file must be durably
published and the recording manifest committed; both recorded job policy and
current startup authorization must permit deletion. Cleanup targets only the
owned private claim, never a producer path that may have been reused after 202.
Reconcile source/destination custody before applying an uncertain cleanup.

Every repair effect needs committed intent, worker assignment/fence evidence,
object checks, effect, required file/directory synchronization, and an applied
receipt or explicit uncertain outcome. An error is not proof of no effect.
Release the corresponding reservation only after its safe durable outcome is
confirmed. Retrying cleanup must not recopy a published recording.

## Operational qualification still required

Build failure cases around intent, allocation, receipt, replacement, unlink,
directory synchronization and accounting release. Prove foreign objects and
retained sources survive rejected repair, and that stale commands cannot repeat
effects after a newer review. Preserve submission/command idempotency evidence
when designing archive and tombstone retention; deleting database rows to clear
capacity is not a recovery mechanism.

Physical free-space margins, metadata/directory overhead, mount disappearance,
supervised worker death/uncertainty and controlled NFS failures remain required
before production repair or cleanup. Qualify in equivalent containers; do not
introduce a real SLES host test requirement.
