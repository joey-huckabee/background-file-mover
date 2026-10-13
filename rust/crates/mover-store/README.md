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

The version-3 schema has an application ID, foreign keys and file-count/ledger
checks. Unsupported/foreign schemas are rejected without replacement. Existing
missing/inconsistent reservations or malformed claim identities block startup.
An explicit transaction migrates versions 1/2, preserving accepted jobs/claims/reservations;
read-only opens refuse an unmigrated version. There is no delete-and-restart upgrade.

`note_missing` persists the first confirmed local absence deadline using the
job's recorded retry duration. Replay does not extend it; `claim_blocked` persists
expiry for operator review. Receipt commit removes that file's missing record.
Background retry scheduling and audited operator unblock remain future work.

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
