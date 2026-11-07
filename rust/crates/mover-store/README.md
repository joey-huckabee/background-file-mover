# Local acceptance repository

`Store` owns one SQLite connection on a dedicated thread and accepts commands
through a bounded queue. Its methods wait for results; async coordinator code
must dispatch them outside its executor. The constructor requires an existing,
protected parent directory on local Linux storage. Network-filesystem detection
remains a production startup obligation. The local API holds a source-namespace
singleton lock; this is not yet a general database/remote-worker ownership fence.

`accept(submission, context)` atomically records the generator/submission IDs,
ordered file list with optional expected sizes, resolved source-root mapping,
destination path/identity, grouping/deletion policy, missing-file retry duration
and source reservations. It returns only after commit. Fresh acceptance has
Pending handoff. Replay restores durable claims; all-file receipts yield Ready202.
Actual filesystem work belongs to `mover-fs`, outside database transactions.

The context is trusted administrator-resolved input, not client-supplied routing.
Filesystem authorization, mount identities and alias-free roots must be established
by its caller before filesystem effects. Source reservations use normalized root
ID/relative path, across generators. They are released only in the same transaction
that commits the last claim receipt; partial claims retain every reservation.

Repeating the same generator/submission ID and exact input returns the original
local job ID and stored context. A new startup route does not rewrite an accepted
job. Changed input conflicts; a different key cannot take a reserved source.
Local job IDs are monotonic SQLite IDs; qualify final filesystem namespace/instance
ownership before using them for publication across service instances.

The version-9 schema has an application ID, foreign keys and file-count/ledger
checks. Unsupported/foreign schemas are rejected without replacement. Existing
missing/inconsistent reservations or malformed claim identities block startup.
An explicit transaction migrates versions 1–8, preserving accepted jobs/claims/reservations;
read-only opens refuse an unmigrated version. There is no delete-and-restart upgrade.

`note_missing` persists the first confirmed local absence deadline using the
job's recorded retry duration. Replay does not extend it; `claim_blocked` persists
expiry for operator review. Receipt commit removes that file's missing record.
Background retry scheduling remains future work.

Fully claimed delivery jobs stopped at three failures can now be resumed through
`resume_delivery`. A stable command ID and expected review epoch protect replay;
an immutable operator audit and retry reset commit atomically. Claims/transfers
and manifest receipts are preserved. Status includes the latest audit and epoch.
See [increment 08](../../../docs/RUST-INCREMENT-08.md).
`reset_missing` now performs an exact-file audited deadline reset using a separate
missing review epoch and stable command ID. It preserves claims/reservations and
the pinned policy; the recorder must retry its original submission for 202.
See [increment 09](../../../docs/RUST-INCREMENT-09.md).

`retention(None)` reports global conservative reservations; `retention(Some(id))`
reports one job. One read transaction streams fixed-size counts, checked u128
source/destination byte totals and attempt-phase counts using the same sums as
admission. It performs no filesystem inspection or reclamation. See
[increment 10](../../../docs/RUST-INCREMENT-10.md) for bounds and limitations.

`save_transfer` records immutable owned-attempt mapping and ordered
copy/verification/publication receipts. Only incomplete copies can allocate a
new attempt. Changed receipts or skipped phases fail closed. Hydration restores
Verified/Published file facts. `save_manifest` records exact bytes and ordered
allocation/write/publication/commit receipts; hydration restores set commitment.
Cleanup stays disabled. Delivery discovery is bounded and driven by durable facts,
with persisted retries/review blocks and a stable local instance identifier.
Admission counts retained jobs/source bytes and conservative destination-attempt
reservations, including committed retained data; replay does not consume another slot.

`begin_claim` records immutable root/parent/private-directory/file observations
and exact operation names. `finish_claim` accepts a trusted worker's synchronized
receipt, checks the matching intent and commits actual size/claim completion.
SQLite cannot prove file custody or fsync by itself. A failed final receipt or
reservation-release transaction leaves Pending handoff and retains reservations.

WAL, FULL synchronization and foreign keys are set and read back; E1's SQLite
compile options are verified at open. Creation also synchronizes the state parent
directory. Failure to commit returns an error, with no acceptance receipt. A lost
result or uncertain I/O failure still requires replay/reopen by the same ID; an
error alone does not prove that nothing committed.

The store's only external direct dependency remains E1's rusqlite 0.40.1 with
defaults disabled and bundled enabled. The workspace now reuses E2's cumulative
graph for the filesystem worker. No JSON, error-macro or test-helper dependency is added.

Run the repository's mandatory [SLES gate](../../README.md#checks).
The storage tests exercise real SQLite behavior, including a deferred foreign-key
failure at COMMIT, partial inserts, locks, read-only operation and another process
reopening accepted work. They do not qualify power-loss durability or NFS.
