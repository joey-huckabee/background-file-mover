# Local acceptance repository

`Store` owns one SQLite connection on a dedicated thread and accepts commands
through a bounded queue. Its methods wait for results; async coordinator code
must dispatch them outside its executor. The constructor requires an existing,
protected parent directory on local Linux storage. Network-filesystem detection
and service singleton ownership belong to the upcoming filesystem/startup slice.

`accept(submission, context)` atomically records the generator/submission IDs,
ordered file list with optional expected sizes, resolved source-root mapping,
destination path/identity, grouping/deletion policy, missing-file retry duration
and source reservations. It returns only after commit. The returned recording is
Accepted with Pending handoff; actual claims are not performed or acknowledged.

The context is trusted administrator-resolved input, not client-supplied routing.
Filesystem authorization, mount identities and alias-free roots must be established
by its caller before filesystem effects. Source reservations use normalized root
ID/relative path, across generators. They are retained in this increment; the
claim slice will release them only with the durable all-files Claimed fact.

Repeating the same generator/submission ID and exact input returns the original
local job ID and stored context. A new startup route does not rewrite an accepted
job. Changed input conflicts; a different key cannot take a reserved source.
Local job IDs are monotonic SQLite IDs; qualify final filesystem namespace/instance
ownership before using them for publication across service instances.

The version-1 schema has an application ID, foreign keys and file-count/ledger
checks. Unsupported/foreign schemas are rejected without replacement. Existing
missing/inconsistent reservations block startup. Future schema changes require
explicit tested migrations; there is no delete-and-restart upgrade path.

WAL, FULL synchronization and foreign keys are set and read back; E1's SQLite
compile options are verified at open. Creation also synchronizes the state parent
directory. Failure to commit returns an error, with no acceptance receipt. A lost
result or uncertain I/O failure still requires replay/reopen by the same ID; an
error alone does not prove that nothing committed.

The only external direct dependency is E1's rusqlite 0.40.1 with defaults disabled
and bundled enabled. All eleven external crate versions/checksums are retained
from E1. No JSON, error-macro or test-helper dependency is added.

Run the repository's mandatory [SLES gate](../../README.md#checks).
The storage tests exercise real SQLite behavior, including a deferred foreign-key
failure at COMMIT, partial inserts, locks, read-only operation and another process
reopening accepted work. They do not qualify power-loss durability or NFS.
