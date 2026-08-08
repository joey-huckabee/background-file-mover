# Changelog

All notable changes to Background File Mover are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

Work toward the C++11 / REST **v1.0.0**, on one branch per milestone off `main`
(currently `c4-job-manager`). The `v2-cpp` branch these entries were originally written
against merged into `main` at the C0 boundary and was retired.

**`main` no longer ships Python.** The implementation to deploy today is the `v0.4.2`
tag, not a branch.

### Added — C7, the operator dashboard

- **A single embedded page at `GET /`** (`L2-DASH-001`, `L2-DASH-002`), served from the
  binary rather than from disk. The service ships as one executable (`L1-SYS-002`), and
  reading the page from a path at request time would add a filesystem dependency to the
  control plane and a directory an operator could be persuaded to repoint. Styles and
  script are inline; nothing is fetched from the network, which matters because this
  runs on an isolated network — a CDN reference renders blank where it is deployed and
  hands a third party script execution in the operator's browser where it is not.
- **`GET /api/status`** — counts by state from the **durable record**, plus the live
  queue depth and in-flight count. The in-memory queues know what this process has been
  asked to do since it started; the store knows what the system has done, including
  before the last restart, and an operator asking what happened to a job means the
  second. Both are reported so they can be compared: a deep runnable queue with an idle
  pool is a real symptom.
- **The row cap is the router's decision, not the client's.** No `?limit=` is honoured —
  the response is assembled in memory before it is written, so a client-chosen size is a
  client-chosen allocation on an unauthenticated endpoint. The cap and a `truncated`
  flag are reported in the payload, because a dashboard showing 50 of 4,000 jobs without
  saying so lies about the backlog and the operator acts on the lie.
- **`L2-DASH-003` enforced in three places.** Every dynamic value enters the DOM through
  `textContent` or `createTextNode`; there is deliberately **no escaping helper** in the
  page, because an escaper can be forgotten at one call site, applied twice, or applied
  in the wrong context. Removing the parse beats neutralising the input.
  `make dashboard-safe` refuses `innerHTML`, `outerHTML`, `insertAdjacentHTML`,
  `document.write`, `eval`, `new Function` and `srcdoc` in the source — including the
  harmless-looking `innerHTML = ""`, since allowing it would require the gate to tell
  safe assignments from unsafe ones. `tests/test_dashboard.cpp` asserts the same
  properties against the string the binary actually serves, so a page assembled some
  other way in future is still covered.
- **A status query is refused when the manager is not running** (503, not an empty
  success). A dashboard rendering "0 jobs" for a service that is down is worse than one
  saying it cannot reach the service: the first is a confident wrong answer.

### Added — C6, the daemon

- **The operational event stream** (`L2-EVT-001..005`, `L3-EVT-001..005`). Typed
  immutable `Event` records on an `EventPublisher` with function-pointer
  subscribers, matching the clock and the phase hook rather than dragging
  `std::function` through a C++11 header.
- **Observation, never control** (`L2-EVT-003`). Publication is the last step of an
  operation and never a step it depends on. The manager emits after the durable
  write and outside its mutex — `emit()` asserts that, the same way
  `store_for_command()` does — and the whole job lifecycle works with **no publisher
  installed at all**, which every C4 test already relied on and two new tests now
  assert deliberately. A run in which every subscriber throws produces a byte-identical
  durable record.
- **Subscriber isolation** (`L2-EVT-002`, `L3-EVT-003`). Each callback runs in its own
  `try`/`catch`, including `catch (...)` — a subscriber in another translation unit
  can throw anything, and an escaping throw on a worker thread would call
  `std::terminate` and take the daemon with it. A subscriber that throws is **not**
  auto-unsubscribed: dropping it would silently disable logging for the rest of the
  process, and "the logs stopped" reads like a hang.
- **Snapshot, and no lock across callbacks** (`L3-EVT-001`, `L3-EVT-002`). Holding the
  subscriber lock across arbitrary subscriber code would serialise every emitting
  thread and deadlock outright on a subscriber that publishes from its own callback.
  There is a test for exactly that; with the lock reinstated it *hangs*, which was
  verified rather than assumed.
- **`unsubscribe` blocks until in-flight publishes are done with the subscriber.**
  The snapshot `L3-EVT-001` requires is otherwise a use-after-free waiting to happen:
  the list no longer names you, but a publishing thread still holds the copy it took.
  Callers may destroy their `user_data` as soon as `unsubscribe` returns. Called from
  inside a callback it does not wait — the publication it would wait for is the one
  calling it.
- **A log sink** (`L2-CLI-006`) — the one subscriber the service always installs.
  `DEBUG`/`INFO` to stdout, `WARNING`/`ERROR` to stderr, no log file ever opened,
  named, rotated or deleted (twelve-factor XI). `format_event` is a pure function, so
  the formatting decisions are asserted directly instead of by capturing a descriptor;
  only the stream *split* needs redirection, because which stream a line went to is not
  visible in the line.
- **Control characters in identifiers are escaped** before they reach a log line. Paths
  are attacker-influenced by definition — whoever can create a file chooses its name —
  and a newline in a job id would end the line and start one the attacker composed,
  including a forged `ERROR`. Same reasoning as `L2-DASH-003` for the dashboard.
- **`[logging] level`** in the configuration (`DEBUG`/`INFO`/`WARNING`/`ERROR`/`OFF`),
  parsed into the enum at load time so a typo is one of the issues `--check` lists
  rather than a log line that never appears. `OFF` disables the sink rather than naming
  a level above `ERROR`, because a level invites a comparison against it.
- **`JobHaltedAfterCommit` and `JobFailedExternal` are distinct event types.**
  `L2-JOB-014`'s halted-after-commit means the move happened and the record disagrees;
  `L2-SEC-011`'s failed-external means something outside the service took the file. An
  operator's next action differs, and collapsing them into "failed" deletes the only
  signal that says which. The mapping is a `switch`, so a sixth `MoveOutcome` is a
  `-Werror=switch` build failure rather than a silent default of "failed".

- **The singleton lock** (`L2-CTL-008`, `L3-CTL-004`). Two daemons on one state
  database is not a degraded mode, it is corruption: both run crash recovery over
  the same rows, both claim the same `QUEUED` jobs, and both move the same file —
  with the second finding the source gone and recording a failure for work that
  actually succeeded. SQLite serialises the *writes*; it has nothing to say about
  two processes that each believe they own the queue.
- **A lock, deliberately not a pidfile.** A pidfile has to answer "is pid 4212 still
  alive, and is it still us?" and cannot, because pids are reused; every repair for
  that (check `/proc`, compare start time, unlink if stale) is racy and defeated by a
  reboot. The kernel releases an advisory lock when the holder dies however it dies,
  including `SIGKILL`, so there is no stale state to reason about and no recovery
  path to get wrong. Tested by having a child acquire and `_exit` without releasing.
- **`flock`, deliberately not `fcntl(F_SETLK)`.** POSIX record locks are owned by the
  `(process, file)` pair, so a second lock taken by the same process silently replaces
  the first — precisely the case the lock exists to catch, made invisible. `flock` is
  owned by the open file description, so a second open in one process conflicts
  correctly. Confirmed by swapping in `fcntl` and watching the in-process test fail.
- **Taken before the store is opened, released after it closes.** A second instance
  that reached the store first would run recovery over rows the running instance owns
  and would have done the damage before discovering it was not alone. `Impl` declares
  the lock first so reverse member destruction releases it last, matching `stop()`.
- **The lock file is never unlinked.** Between another process's open and its `flock`
  there is a window where unlinking would delete the object it is about to lock,
  leaving two instances holding exclusive locks on two different inodes with the same
  name. A leftover file is not a held lock — tested, because the alternative reading
  would let the service start exactly once per machine.
- **`fsops::open_lock_file`** — an `openat`-based primitive so `singleton.cpp` needs no
  `<fcntl.h>` and stays inside `L2-SEC-001` without an allowlist entry. `O_CLOEXEC` is
  load-bearing rather than hygiene: `L2-XFR-002` forks and execs, and a lock descriptor
  inherited by that child would keep the lock alive after this process died, so the
  next start would refuse forever with nothing an operator could find holding it.

- **A hardened systemd unit** (`deploy/systemd/file-mover.service`, `L2-SEC-014`),
  `Type=notify` rather than `Type=simple`. The difference is not cosmetic: with
  `Type=simple` systemd considers the service started the moment `exec` returns,
  which is before the port is open, so every unit ordered `After=` this one starts
  against a service that refuses connections. `ExecStartPre` runs `--check`
  (`L2-CTL-019`) so a bad configuration fails the unit before a socket or a
  database exists. `TimeoutStopSec=120` because shutdown *drains* — a move past its
  commit point must finish, and killing it leaves the record and the filesystem
  disagreeing.
- **sd_notify readiness and watchdog** (`L2-CTL-011`, `L2-CTL-012`, `L3-CPP-054`),
  hand-rolled rather than linked against libsystemd, for the reason ADR-0004 gives
  generally: the protocol is one `AF_UNIX` datagram. `READY=1` is sent **after** the
  listener is accepting, `STOPPING=1` before teardown, and `WATCHDOG=1` at half the
  interval systemd asked for. A leading `@` in `$NOTIFY_SOCKET` means the abstract
  namespace, which on the wire is a leading NUL — copying the `@` verbatim addresses
  a path that does not exist, and since a failed notification is deliberately not
  fatal, the symptom would be a unit killed at its start timeout rather than an
  error. That conversion has its own test, negative-tested by injecting the `@`.
- **`notify_service_manager` is a no-op when `$NOTIFY_SOCKET` is unset, and a failed
  send is not an error** (`L3-CPP-054`). Without that the service starts under
  systemd and refuses to start anywhere else — in a test, at an operator's shell, in
  a container.
- **`scripts/smoke-readiness.py`** drives the real binary end to end: `READY=1`,
  a live `/healthz`, watchdog pings, `STOPPING=1`, clean exit on `SIGTERM`. Its
  ordering case occupies the port first so the daemon's `bind` is *guaranteed* to
  fail, making "no `READY=1` when the listener never opened" deterministic.
  Connecting the instant `READY` arrives looks like the same check and is not — the
  daemon wins that race every time, confirmed by injecting a premature `READY` and
  watching it pass.
- **`scripts/assert-unit-valid.sh`** (negative-tested by `unit-gate-selftest.sh`)
  checks the unit with `systemd-analyze` and then runs the daemon with the unit's
  *own* `ExecStartPre` arguments against the config that actually ships. The unit
  and the reference config are the two deliverables nothing compiles and no test
  imports, so a mistake in either survived every other gate here.

### Fixed — C6

- **`Service::start` after `stop()` would have failed on its own log sink.** `start`
  subscribes the sink and `subscribe` refuses a duplicate (`L3-EVT-004`), so a `stop`
  that did not unsubscribe made the next `start` fail with "subscriber is already
  registered" — an error with no visible connection to restarting. Found by writing
  the restart test; the failure paths in `start` had the same hole.
- **The shipped reference config was still the Python-era schema.** The C++ parser
  rejected nearly every line of `config/file-mover.ini`, so the unit's `ExecStartPre`
  validation could not have succeeded on any real install — the daemon would have
  refused to start with a wall of "unknown section" errors. Found by
  `assert-unit-valid.sh` on its first run. Rewritten to the accepted schema;
  `docs/CONFIG-REFERENCE.md` (which documents the retired Python implementation)
  now says so rather than pointing at it as its reference copy.

### Changed — C6

- **`L3-CTL-004` rewritten for C++.** It required "`ProcessLock` shall use
  `fcntl.flock`" — a Python class and a Python module, left from the retired
  implementation. It now names `SingletonLock` and `flock(2)`, states why record locks
  are forbidden, and adds the no-unlink-on-release clause.
- **`make format-check` is documented as advisory and failing.** It reports most of
  the tree as violating and always has — the sources use column alignment
  clang-format rewrites, and the CI workflow deliberately does not gate on it. The
  wall of output reads exactly like a real failure and was briefly mistaken for a
  clang-format version gap, so the Makefile now records what it is and warns
  against reformatting tested code to quiet it.

### Added — C5, the REST control plane

- **A bounded pool of connection handlers (ADR-0013).** One accept thread, N
  handler threads, and `503` when every handler is busy. Serial-accept — the
  inherited design — makes one slow client a total outage of the control plane,
  and needs no attacker to trigger: a suspended laptop or a dead reverse proxy
  will do. A single-threaded event loop was rejected for a subtler reason worth
  keeping: route handlers call `JobManager`, which reaches SQLite, and a durable
  write blocks for `busy_timeout`. In an event loop that freezes *every*
  connection, because they share the thread now parked inside `sqlite3_step`.
- **The listening socket** (`L2-CTL-001`), defaulting to loopback — which at
  v1.0.0 is the entire access control, since there is no authentication and
  ADR-0003 forbids in-process TLS. `port()` reports the port actually bound,
  read back with `getsockname`, which is what lets every test bind to port 0
  without a fixed port and without racing another run.
- **Per-syscall deadlines on every connection** (`L2-SEC-009`), configurable
  through `ServerOptions`. Per *syscall*, not per request: a client that keeps
  sending is never cut off for being slow overall, only for going silent. A
  zero timeout is refused, because to `setsockopt` it means "block forever" —
  the configuration the requirement exists to forbid, arriving silently as a
  default-constructed `int`.
- **`IoResult`** distinguishes `TimedOut` from `PeerClosed` from `Error`.
  Collapsing them is what makes a stalled connection indistinguishable from a
  client that hung up, and `L2-SEC-009` wants the suspicion recorded.
- **A route table of pure functions** (`L2-CTL-005`, `L2-CTL-014`): `/healthz`
  and the four lifecycle commands, with `404` for unknown routes, `405` **with
  `Allow`**, and a JSON error body throughout. `status_for` is a total function
  over `CommandResult`, which is why C4 made it a typed enum. The test file
  opens no sockets — that is `L2-CTL-014` being useful rather than merely
  satisfied, since the error matrix is the part that rots unnoticed.
- **The connection driver and the hostile battery.** Garbage → 400, oversized
  head → 431, gigabyte declaration → 413, chunked → 400, trailing bytes → 400,
  and a silent client timed out. The battery fires *first*, then the same
  instance answers `/healthz` — the assertion that separates "rejected the
  input" from "survived rejecting it", since every other case opens its own
  connection and would pass against a server that had wedged itself.
- **`POST /api/jobs`** and manager-side id allocation from the durable sequence
  (`L2-JOB-015`). Answers `202`, not `200`: the job is queued and the move has
  not happened. Allocation lives in the manager because an id is durable state;
  a REST layer minting its own would put identifier policy in the wrong layer.
- **Two gates**, both negative-tested: `no-timed-condwait` bans `wait_for` and
  `wait_until` in `src/` and `include/`, and `manager-lock` requires every
  acquisition of the manager mutex to go through `ManagerLock` so the
  store-under-mutex assertion cannot be silently bypassed.

### Fixed — C5

- **`getaddrinfo` segfaults on the GCC 4.8.5 fidelity image.** Reproduced with
  a thirty-line program containing no project code: it crashes *inside* the
  call, before returning, even with `AI_NUMERICHOST` set — glibc's name-service
  switch initialises and dlopens regardless of whether resolution was asked
  for. Replaced with `inet_pton`, which is a parser rather than a resolver: it
  reads no configuration, opens nothing, and cannot resolve a name even by
  accident. A stronger guarantee than the flag, enforced by what the function
  is.
- **The store was touched under the manager mutex in two places.** `cancel()`
  held it across `store.load()` *and* `store.update_state()`, and `shutdown()`
  across `store.close()`. Both were introduced by the commit that wrote the
  invariant down as a comment, and both were found by the assertion that
  replaced the comment.
- **`pause`, `resume` and `cancel` answered 404 on a stopped manager** rather
  than 503. The job may well exist in the durable record; what is missing is
  the manager, and "no such job" sends an operator to look for the wrong
  problem during startup.
- **The fd-relative gate had a latent false positive.** Its pattern matched
  `::open(` anywhere, including the tail of a qualified member name, so
  `ListenSocket::open` was flagged. It had never fired before by luck: the only
  other such member is `JobStore::open`, and `store.cpp` is on the allowlist.

### Added — C4, the job manager

- **The job manager and worker pool** — the project's first threads.
  `filemover/manager.hpp`. N workers, each with its own `JobStore` connection
  (`L2-JOB-003`). The constructor takes a store **path**, not a store, so sharing one
  handle across threads is not an available mistake. One mutex guards all shared state:
  the states interact — a job moves between runnable, waiting, paused and active — and
  lock ordering between four mutexes is a bug waiting for the first person who takes them
  in a new order.
- **Lifecycle commands return typed results** (`L2-LIF-005`) — `Ok`, `UnknownJob`,
  `InvalidState`, `NotRunning`, `StoreError` — rather than a bool and a string a caller
  would have to parse to decide what to do.
- **Retry with bounded exponential backoff** (`L2-RTY-001/002/003/005`). Schema columns
  `attempts`, `next_retry_ms`, `last_error`. `last_error` is separate from `error` and not
  a duplicate of it: the store's `CHECK` binds `error` to be non-empty if and only if the
  state is FAILED, so a job that failed once and is waiting to retry — and is therefore
  *not* FAILED — has nowhere else to record why.
- **A denial is distinguished from a transient failure.** `MoveOutcome::Rejected` fails
  the job outright; only a pre-commit abort is retried (`L2-RTY-002`). Every `Rejected`
  site in the engine refuses the request itself — an unusable path, a missing source, a
  non-regular file — and none of those become true later.
- **Manual retry submits a new job** (`L2-RTY-006`), returning its id. The failed job
  stays FAILED permanently, because `L1-SYS-021` makes that state terminal and reviving it
  would erase the record that the job ever failed — which is exactly what an operator
  investigating later needs. A `retry_of` column links the attempt to the one it replaces,
  so the chain is reconstructible from the durable record alone. Ids are
  `<root>-retry-<n>` with any existing suffix stripped, so a third attempt is
  `job-retry-3` and not `job-retry-2-retry-1`.
- **A `[retry]` configuration section** — `max_attempts` (1..100, default 3),
  `backoff_initial_ms`, `backoff_max_ms`, with cross-field validation naming *both* values
  when the floor exceeds the ceiling, because "invalid backoff" would send an operator to
  look at one of two lines with no way to tell which is wrong.
- **A latch-based concurrency suite.** The move engine's phase hook holds a worker at a
  chosen phase, so an interleaving is *made* to happen rather than hoped for. A sleep
  makes a race likely; a latch makes it certain, which is the difference between a test
  that fails when the code is wrong and one that fails when the machine is busy.
- **Header dependency tracking in the build** (`-MMD -MP`). There was none, so every
  incremental build since the project began was unsound across a header change.
- **A gate banning permission-based failure injection in tests**
  (`assert-no-permission-tests.sh`), negative-tested across ten accept/reject cases
  including the `01777`-accept versus `01500`-reject boundary.

### Fixed — C4

- **A failed move marked the job permanently unretryable.** The move engine wrote FAILED
  when the commit rename failed. FAILED is terminal, so neither automatic backoff nor
  operator-initiated retry could ever return that job to work — every transient failure
  would have become a permanent loss requiring manual re-submission. The engine now leaves
  the job in RENAMING, which is what actually happened, and `execute()` re-drives it by
  skipping phase 2.
- **A whole class of failure fell through the job manager.** Jobs refused before anything
  happened were neither retried nor failed; they stayed QUEUED forever with no worker
  owning them, indefinitely occupying the queue and reading as pending work.
- **The manager mutex was held across blocking SQLite writes.** A submit arriving while a
  worker held the database write lock could stall the entire pool for `busy_timeout` —
  five seconds — because that mutex is what every worker takes to pick up its next job.
  Commands now claim the id, write outside the lock, and publish; workers record failures
  unlocked. `L2-JOB-013` is preserved exactly, since publishing is what makes a job
  runnable.
- **`clock_gettime` needs `-lrt` on the deployment target.** It lives in `librt` on the
  target's glibc and in `libc` on newer ones, so the link succeeded on three modern
  toolchains and every sanitizer tier and failed only on GCC 4.8.5.
- **ThreadSanitizer was red on the manager suite.** `std::condition_variable::wait_until`
  — correct C++ — breaks TSan's accounting for the mutex passed to it: it subsequently
  believes the mutex is held after an explicit unlock, reports a phantom double lock, and
  treats everything that mutex guards as unsynchronised. Isolated in a standalone program
  with no project code, running one loop three ways from a single binary: `wait()` 0
  warnings, `wait_until()` 11–19, bounded poll 0. `wait_idle` now polls. Full account in
  `docs/C4-TSAN-RESOLVED.md`.
- **A retry test asserted nothing where it mattered most.** It forced a failure by making
  a directory read-only; root bypasses that check and the fidelity container runs as root,
  so on the one tier modelling the production platform the move succeeded and six
  assertions tested the opposite path from the one they named.
- **`assert-hook-mode.sh` inspected the index rather than the file git runs.** Written to
  catch a silently-dead pre-commit hook, it reported all hooks healthy while the hook was
  dead, because an edit had cleared the working-tree execute bit while the index kept
  `100755`.

### Changed — C4

- **Schema migrations were removed until v1.0.0 ships.** Before release there are no
  databases in the field — every store is a developer or CI database and all of them are
  disposable — so a schema change recreates rather than migrates. The version check stays
  and now refuses a mismatch in *either* direction, because without a migration path an
  older database is exactly as unreadable as a newer one. Owed back before the first
  schema change after release; recorded in `docs/ROADMAP.md` with the trap to avoid.
- **`L2-CLI-001` no longer names `argparse`** — a Python library in a requirement for a
  C++ project. It now states the dependency constraint and the option forms, leaving the
  mechanism to an ADR at the milestone that builds the CLI, because `getopt(3)` is POSIX
  but short-options-only while `getopt_long(3)` is a GNU extension.
- **`L2-CLI-006` carries the full output-stream contract.** The CLI writes its *result* to
  stdout and diagnostics to stderr; the service writes its event stream split by severity.
  The two process types have opposite stdout contracts, which is the part implemented
  wrongly when it is not written down. The service half had been specified only in the
  retired `L3-PY-013`.

### Removed — C4

- **The `L3-PY-*` requirement category.** Fourteen requirements specifying Python
  mechanisms for an implementation no longer on this branch. Each was inspected before
  deletion so no *feature* left with its mechanism: twelve carried nothing their L2 parent
  did not already require, and five substantive constraints were preserved — most
  importantly the requirement to `fsync` the containing **directory** and not only the
  file, now `L3-CPP-053`. `L2-POSIX-009` asks only for the file, so that was the only
  written requirement demanding the directory sync. A rename is atomic, but atomicity is
  not durability.
- **`L2-COPY-001/002/003/011` left v1.0.0 scope**, reparented to the already-deferred
  `L1-SYS-003`. They describe a copy engine `L1-SEC-007` forbids at this release, so the
  matrix was reporting four requirements as owed that could not be satisfied without
  violating another.

### Added

- **The fd-relative filesystem layer (C2).** `filemover/fsops.hpp` — every filesystem
  operation on a managed tree takes a `DirHandle` and a *name*, never a path. That shape
  is the requirement rather than a style choice: `L2-SEC-001` prohibits path-based
  operations because each one re-resolves every component, so any of them can be swapped
  between the check and the act. An API that cannot express a path is a stronger
  guarantee than a rule saying not to write one.
- **`renameat2` is reached through `syscall(2)`, as `L2-SEC-007` anticipated.** Measured
  on the fidelity toolchain before any code was written: SLES 12 SP5 ships glibc 2.22 and
  the wrapper arrived in 2.28, so `RENAME_NOREPLACE` and `SYS_renameat2` are undefined
  there too. Calling it directly compiles clean on a modern host and fails to link on the
  target. The syscall number is guarded by `#if defined(__x86_64__)` with a `#error`,
  because a wrong constant on a new architecture would not fail to build — it would call
  a *different* syscall.
- **Both move strategies are primary, tested paths.** `LinkThenUnlink` is not a fallback:
  NFSv3 has no equivalent operation and NFSv4's `RENAME` carries no no-replace flag, so on
  the mount where the recordings live it is what production runs on every move
  (`L2-NFS-002`, CYBERSECURITY §4.1). The strategy is an explicit parameter, so tests
  cover both on any filesystem instead of whichever the test machine happens to support.
- **An interrupted `linkat`/`unlinkat` pair is distinguished from a genuine collision**
  (`L2-NFS-003`). The pair is not atomic together; a crash between them leaves both names
  on one inode. The naive reading — "the target exists, therefore collision" — fails a
  move that had all but completed. Reproduced in tests with a hard link, needing neither a
  crash nor NFS.
- **`make fd-relative` and `make no-shell`** turn `L2-SEC-001` and `L2-SEC-008` from
  Inspection into mechanical gates. `fd-relative` bans the path-taking *headers* rather
  than matching call sites: a translation unit that cannot see `<fcntl.h>` cannot call
  `open()` whatever it names its own methods. The call-site version flagged
  `JobStore::open` — a method declaration — and a gate with false positives gets disabled,
  which is worse than one with a known blind spot.
- **The durable job store (C1).** `JobStore` in `cpp/include/filemover/store.hpp` and
  `cpp/src/store.cpp` — SQLite in WAL mode with `synchronous=FULL` behind the repository
  interface ADR-0010 called for. Both pragmas are **read back** after being set: SQLite
  silently accepts a PRAGMA it does not understand, so "we set it" and "it is set" are
  different claims. Schema migration is idempotent and keyed on `PRAGMA user_version`;
  an absent store is first boot (`L2-JOB-011`); a corrupt store, or one written by a
  newer build, is refused with the damage named and the bytes left untouched
  (`L2-JOB-012`) — continuing past it would discard the record of jobs whose source
  files may still exist. Intent is recorded before any filesystem action (`L2-JOB-013`),
  and the job sequence is committed before it is handed out, so a crash can lose a
  number but never issue one twice (`L2-JOB-015`).
- **Phase-dependent write-failure handling (`L2-JOB-014`), with the fault injection that
  makes it testable.** `record_transition` takes the `CommitPhase` and returns `AbortJob`
  before the commit point and `HaltProcess` after — the same failure, the opposite
  verdict — and always sets an error, because the requirement's last clause is that the
  software never continues silently. Treating both phases as one retryable condition is
  the specific mistake it exists to prevent: before the commit point, continuing means
  acting with no durable record; after it, going on to delete the source leaves reality
  and the record disagreeing.
- **`JobStore::inject_write_fault` provokes a real refusal from SQLite's write path** —
  `PRAGMA query_only` for a deterministic `SQLITE_READONLY`, and `PRAGMA max_page_count`
  for a genuine `SQLITE_FULL`. Two decisions worth keeping: it is **not** behind an
  `#ifdef`, because conditional compilation would mean the failure handling under test is
  not the one that ships — and `L2-JOB-014` is exactly where that would matter; and it
  provokes a real refusal rather than substituting a return value, because what has to
  work is detecting SQLite failing, not us pretending it did.
- **The attention flag is documented and tested as best-effort.** If the durable write
  failed because the store is unwritable, recording the flag is another write to that
  same store and fails too. That is why `L2-JOB-014` also requires logging at high
  severity: the log is the guarantee, the flag is the convenience that survives when the
  store is inconsistent rather than unreachable.
- **State transitions are validated by the core state machine, not re-implemented.**
  `update_state` loads the job, calls `Job::transition`, and writes only if the core
  accepts — one set of rules, in the component that already owns them. The schema
  additionally enforces `L2-JOB-010` as a `CHECK` constraint, so a row that could not
  have come from a legal transition cannot be stored even by a future caller that
  bypasses the method. The duplication is deliberate: the core check governs this
  process, the constraint governs the file.
- **A kill-at-every-statement crash suite.** Forks a child, has it perform a growing
  number of durable writes, then `SIGKILL`s it outright — no unwinding, no `close()`, no
  cleanup — and verifies the store reopens, reports itself as existing rather than
  silently recreated, and never reissues a sequence number. The kill is real because the
  property is about what the *file* looks like when a process dies mid-write, and an
  injected in-process error still unwinds and lets SQLite tidy up, which is exactly what
  a crash does not do.
- **`make sql-confined` turns `L2-JOB-009` from an inspection into a gate.** SQL and
  `sqlite3.h` appear only in the repository implementation and the vendoring smoke test,
  which is allow-listed explicitly with its reason. Inspection is the verification method
  that quietly stops happening — it holds until the week someone needs one quick query
  elsewhere and no tool objects. Verified by introducing the violation and confirming the
  gate fails.
- **`docs/TEST-STRATEGY.md`** — which kinds of testing exist, which are deferred and
  why, and which get disproportionately more expensive the longer they are put off
  (migration fixtures, fault injection, conformance corpora, a coverage floor).
- **SQLite is vendored and pinned at 3.53.4** (ADR-0010, ADR-0004), filling the last
  `pending` row in `cpp/VENDORED.md`. The zip was authenticated against upstream's
  published SHA3-256 and byte size before extraction, and `sqlite3.c` / `sqlite3.h` are
  hash-pinned individually — `make verify-vendored` checks four files now, not two.
  The latest release proved viable on GCC 4.8.5, so no version step-back was needed.
  It compiles by its own Makefile rule, with `-Werror` intact: `-fno-strict-aliasing`
  removes the type-punning diagnostics at their cause rather than suppressing them, and
  `-Wextra` is dropped because its style warnings can only be satisfied by editing a file
  ADR-0004 forbids editing. Extension loading, double-quoted string literals, and memory
  accounting are compiled out.
- **`tests/test_sqlite_vendor.cpp`**, covering the two things a vendoring commit can get
  wrong that no other gate would catch: `sqlite3.c` and `sqlite3.h` drifting to different
  releases despite each being individually hash-intact, and the compile-time hardening
  silently not taking effect. It carries **no requirement tag** and does not move the
  trace figure — vendoring a dependency verifies no requirement.

### Removed

- **The Python implementation is no longer in the tree.** `src/file_mover/`,
  the pytest suite, `pyproject.toml`, `poetry.lock`, `packaging/systemd/`, and the Python
  CI workflows (`ci.yml`, `fuzz.yml`) were deleted. Nothing is lost: that code is tagged
  `v0.4.2` — on `origin` as well as locally — which remains the version to deploy today.
  `scripts/build-trace-matrix.py` stayed — it is repository infrastructure covering the
  requirements rather than either implementation, and it imports only the standard
  library, so it needs no Python packaging.

### Changed

- **One branch per milestone, replacing the long-lived `v2-cpp` branch.** C0 merged into
  `main` with `--no-ff` and was published; `v2-cpp` was deleted locally and on `origin`.
  Work now happens on `c<N>-<short-name>` branches cut from `main` and deleted at the
  boundary. The cadence, and the `git branch -d` refusal that makes a fully-merged branch
  look unmerged, are documented in `docs/ROADMAP.md`.
- **CI pins a C compiler.** `CC` is set to `gcc-14` alongside `CXX: g++-14`, and the jobs
  that compile now install `gcc-14`. The `g++-14` package alone leaves no usable `cc`, so
  the first build with a C translation unit in it failed with `make: cc: No such file or
  directory`; the runner's default `cc` is gcc-13, a different compiler from the one
  building the C++ objects. The fidelity job blanks `CC` as it already blanked `CXX`.
- **The GCC 4.8.5 fidelity tier runs from a mirror, `ghcr.io/joey-huckabee/gcc-4.8:4.8.5`.**
  `docker.io/library/gcc:4.8` was pushed in 2016 with a Docker manifest v2 *schema 1*,
  which modern Docker disables by default; the CI job had been dying at the pull with
  `exit code 125` before compiling anything, while the same tier passed locally because
  podman still accepts schema 1. The mirror is that image republished with a v2s2
  manifest. Schema 1 is slated for removal outright, so pinning the upstream tag would
  not have survived. **The tier that decides whether the code ships had not actually run
  in CI for some time.**
- **`make check-gcc48` replaces three hand-written container invocations.** `cpp-ci.yml`,
  `CONTRIBUTING.md`, and `CLAUDE.md` each spelled out their own `docker`/`podman` command,
  which is how CI and developers came to pull different images without anyone noticing.
  One target, one `GCC48_IMAGE`, both callers.
- **Coverage is a gate, not just a number.** `make coverage` now fails below
  `COVERAGE_MIN` (85%, against an actual 90.8%). Measured-but-unenforced coverage can
  only decay, and it decays invisibly — nobody notices two points a milestone until it
  is twenty. The floor sits deliberately below the current figure so a new component
  landing partially covered does not block the work that will cover it, and it is a
  **ratchet**: raised deliberately, never lowered quietly to make a build pass.
- **The fuzz targets link a subtractive source list.** They built from `$(LIB_SRC)`,
  which now contains a translation unit requiring the vendored SQLite object, so they
  stopped linking. `FUZZ_LIB_SRC` is `$(LIB_SRC)` minus an explicit exclusion — a new
  source is fuzzed by default and removing one is deliberate, rather than a hand-written
  list that silently stops covering things. `store.cpp` is excluded because the fuzz
  targets consume bytes with no I/O, and compiling a 9.5 MB amalgamation into every fuzz
  build costs about a minute per target for code no fuzzer reaches.
- **The CI tiers compile in parallel.** `make -j` across `check-ci`, `check-gcc48`, and
  every compiling workflow job, with `CI_JOBS` defaulting to `nproc`. Measured on a
  16-core host: the default tier went from **97s to 52s** from clean, and five
  consecutive clean parallel builds passed — the test that matters, since a missing
  prerequisite surfaces under `-j` as an intermittent failure rather than a reproducible
  one. It will not scale past this: the vendored `sqlite3.c` is a single 9.5 MB
  translation unit taking **48.8s** against 1.35s for a typical C++ file, so a parallel
  build is now almost exactly "compile sqlite3.c".
- **The vendored SQLite object is cached with ccache.** It is the one source here that
  never changes — ADR-0004 forbids editing vendored files — and the most expensive to
  build, so every one of the five or six rebuilds per `check-ci` run produced a
  byte-identical object at ~49s each. Measured in the CI container: **60s cold, 0s warm.**
  Scoped to that object alone and deliberately not applied to the project's own sources,
  where the saving is a second or two and the coverage tier compiles with `--coverage`,
  which requires ccache to place `.gcno` files where gcov can resolve them — a real risk
  for no measurable gain, in a project whose coverage reporting has already been broken
  once by a path-resolution subtlety.
- **Every compiling CI job runs in the toolchain image.** Nine of the thirteen jobs in
  `cpp-ci.yml` declare it as their `container:` and no longer `apt-get install` anything,
  so CI and `make check-ci` now execute the same toolchain rather than two independently
  pinned copies of it. The ASan job carries `options: --cap-add=SYS_PTRACE`: LeakSanitizer
  uses ptrace, containers block it by default, and it was previously exempt only because
  GitHub's runner is not a container. The remaining four jobs stay on the runner
  deliberately — the fidelity job drives `docker run` itself, and the vendored-integrity,
  trace-matrix, and locale-free gates need no compiler.
- **`make check-ci` runs from a prebuilt toolchain image** (`.github/ci-image/Dockerfile`,
  published as `ghcr.io/joey-huckabee/bfm-ci`) instead of apt-installing the toolchain on
  every invocation. The Makefile used to justify that cost as "the price of not
  maintaining a second distro"; the repository already maintains the GCC 4.8.5 mirror, so
  the trade changed. The image *is* the pin, which is why the package list is not
  duplicated back into the Makefile. Tags are dates, never `latest`, so a run always
  names the toolchain it used. The runtime `locale-gen` became an assertion that
  `tr_TR.UTF-8` exists, so a future image dropping it fails the gate rather than quietly
  downgrading the L3-CPP-052 check to a warning.
- **SonarCloud coverage is ingested rather than silently discarded.** The scanner now runs
  with `sonar.projectBaseDir=cpp`. gcov records the path it compiled with -- `src/config.cpp`,
  relative to `cpp/` -- and scanning from the repository root made SonarCloud look for
  `<root>/src/config.cpp`, log `File not analysed by Sonar, so ignoring coverage` for
  every file, drop the whole report, and let the Zero Coverage Sensor record 0%. The
  analysis still succeeded, so this stayed invisible until a default-branch push waited
  on the Quality Gate and failed it.
- **The trace-matrix generator reads Catch2 tags as well as pytest markers.** A
  requirement id inside a `TEST_CASE` tag string — `TEST_CASE("...",
  "[json][L3-CPP-019]")` — now counts as verification evidence. Until this landed the
  generator scanned only `tests/*.py`, so 49 tagged C++ tests traced to nothing and the
  matrix reported the C++ tree as entirely untested. Removing Python without fixing this
  first would have taken the whole matrix to zero.
- **The matrix reports a v1.0.0 scope-adjusted figure** alongside the unadjusted one.
  Five L1 requirements are annotated `Deferred`, which places 69 L2/L3 requirements
  outside this release; counting those against v1.0.0 reported a gap that is a deliberate
  decision rather than missing work. Both numbers are published — the unadjusted one
  remains the honest total.
- **The pre-commit hook now gates C++** — vendored-file integrity, the locale-free parser
  check, then `make check` — instead of ruff, mypy, and pytest. The file-hygiene and
  trace-matrix parity checks are unchanged.
- **`codeql.yml` and `sonarcloud.yml` are C++-only**, and the requirements trace-matrix
  gate moved into `cpp-ci.yml`. That gate lived in the deleted `ci.yml`; without the move
  the removal would have silently dropped it.
- **Documents describing the Python implementation are retained, not deleted**, each
  behind a banner marking it as source material for the C++ rewrite. The rewrites owed
  are tracked in `docs/ROADMAP.md`. `docs/12-FACTOR.md` is only *partly* superseded and
  now says which parts: factor VII inverted when the `AF_UNIX` socket became a REST port,
  taking the free filesystem-permission authentication with it.

### Fixed

- **The fidelity container was documented as the wrong operating system.** Six places
  described `gcc:4.8` as a Debian Jessie base with glibc 2.19; it is Debian 7.10
  "wheezy" with **glibc 2.13**, confirmed from `/etc/os-release` and `getconf`. The error
  was benign in direction -- 2.13 is *older* than the SLES 12 SP5 target's 2.22, making
  the tier a more conservative floor than advertised rather than a weaker one, so every
  "passes on 4.8.5" conclusion still holds. Corrected in `cpp-ci.yml`, `cpp/README.md`,
  `CONTRIBUTING.md`, `cpp/Makefile`, and ADR-0001 and ADR-0005 (a factual correction to
  their context sections; no decision changed).
- **`L3-CPP-019` was implemented but untested.** The JSON parser has always reported the
  byte offset of a rejection; nothing asserted it. The non-empty half of the requirement
  was covered incidentally by a test helper, which is what disguised the gap.
- **`L3-CPP-013` declared verification by Test for a property no test can assert** — that
  the code compiles clean under `-Werror` on GCC 4.8.5. It is verified by Demonstration
  on every commit by the fidelity CI tier. A modeling error rather than a missing test,
  and it left a permanent hole in the matrix.
- **`L1-SYS-015`'s status line was unparseable.** It read `**Rewritten.**` where every
  other status is a bare word, so status-driven tooling skipped it silently.

## [0.4.2] - 2026-07-12

### Documentation

- **`docs/DEPLOYMENT.md` gained end-to-end platform runbooks.** A complete **Red Hat
  Enterprise Linux 9** walkthrough (install `python3.11`, the `mover` service account, the
  shipped systemd unit, SELinux with `audit2allow`, `doctor` validation) and a separate
  **SUSE Linux Enterprise Server 12** walkthrough (building CPython 3.10 from source — with
  the OpenSSL-1.0.2 caveat that `ssl`/`_hashlib` are skipped but the built-in hashes still
  work — a manually-created state directory and a trimmed systemd-228 unit, and AppArmor).
  Cross-linked `docs/USER-GUIDE.md`, and corrected the vestigial `/var/log` / `log_to_file`
  note left over from twelve-factor logging.

## [0.4.1] - 2026-07-12

### Added

- **`docs/USER-GUIDE.md`** — an install / deploy / use guide. It explains the topology (the
  CLI and the service share **one** virtualenv and **one** config file — the CLI reads it only
  to find the control socket; there is no separate CLI venv or config), the **system-service
  (root)** and **rootless (per-user, `systemctl --user`)** deployment models, a step-by-step
  **Red Hat Enterprise Linux 9** tutorial (Python 3.11, SELinux, NFS permissions), everyday
  CLI usage, and platform notes — including a **SLES 12** assessment (not recommended: no
  Python ≥ 3.10 in-repo, and systemd v228 predates `StateDirectory`/`LogsDirectory`).

### Removed

- **`docs/CAPTURE.md`.** The original design conversation was fully retired into the
  specifications in v0.4.0 and is now deleted; its content remains in git history and the
  v0.4.0 changelog entry. The references in `CLAUDE.md`, `docs/ROADMAP.md`, and
  `docs/MAINTAINER-GUIDE.md` were updated accordingly.

## [0.4.0] - 2026-07-12

Operability, observability, and provenance: `doctor` now gates a deployment on the runtime
environment, logging is twelve-factor and effectively free when off, and every job's
manifest agrees with its durable record — while the original design conversation has been
fully retired into the specifications. Runtime is still Python-3.10 standard library only.

### Added

- **`file-mover doctor` now verifies the runtime environment.** It checks the capabilities
  the service depends on — `AF_UNIX` sockets, `fcntl` locking, SQLite WAL, the configured
  hash algorithm, Python ≥ 3.10, POSIX signals (required), plus `O_NOFOLLOW` and
  kernel-assisted copy (optional/advisory) — and reports each with `pass`/`warn`/`fail`.
  A missing **required** capability returns the new `ExitCode.ENVIRONMENT_UNSUPPORTED` (8),
  so a deployment can gate on `doctor` (L2-ENV-001..003).
- **`file-mover doctor` also reports advisories** for valid-but-consequential option
  combinations — a bandwidth limit with `use_kernel_copy` (kernel copy is bypassed while
  limited) and `resume_partial_files` without `source-and-destination-hash` (a crash-torn
  resume may go undetected). The same advisories are logged once at service start.
- **Manifest ↔ durable-record metadata parity.** Every accepted job now records the **same**
  creation timestamp and integrity policy (mode + hash algorithm) in both the SQLite job
  record and the JSON manifest, so the two never disagree (L2-JOB-007 / L3-JOB-003). The
  `jobs` table gains `hash_algorithm` and `integrity_mode` columns and the manifest gains
  `created_at` and an `integrity: {mode, algorithm}` block, stamped once at submission and
  threaded to both writers. **Schema note:** fresh-schema change (pre-1.0) — new databases
  only; there is no migration for an existing `jobs.db`.
- **Gated, context-aware logging with near-zero overhead when off.** Job/file correlation is
  carried in structured fields (`extra={job_id, file_id}`) via stable `file_mover.<area>`
  loggers and a `ContextFormatter`, and lifecycle DEBUG/INFO events were added across the
  transfer, state, submission, recovery, and control paths (previously the transfer path
  logged nothing). A per-level `LogGate` computed once at startup lets a disabled level cost
  a single boolean — no `isEnabledFor`, argument evaluation, formatting, or dispatch. Hot
  paths guard DEBUG with `if __debug__ and GATE.debug:`, which `python -O` strips from the
  bytecode entirely; `[logging] level = OFF` disables all logging. The systemd unit runs the
  service under `-O` (L3-PY-014).

### Changed

- **Twelve-factor logging.** The service now writes its event stream to the standard streams
  and lets the environment (systemd's journal, a log shipper) route it — `INFO`/`DEBUG` to
  **stdout**, `WARNING` and above to **stderr** — and no longer manages log files. The
  `[logging] level` is now applied at service start (previously the section was validated but
  ignored), with an explicit CLI `-v`/`--log-level` taking precedence. The CLI is unchanged
  (stdout = command result, stderr = diagnostics) (L3-PY-013).
- **`__version__` is derived from the package metadata, not hard-coded.**
  `file_mover.__version__` now reads `importlib.metadata.version("background-file-mover")`
  (standard library), so `pyproject.toml` is the **single source of truth** for the version —
  the CLI `--version`, the `health` response, and the package all follow it. An uninstalled
  source tree falls back to `0.0.0+unknown`.

### Removed

- **`[logging]` destination options `log_to_journal`, `log_to_file`, and `log_directory`.**
  In the twelve-factor model the application does not choose log destinations, so these were
  removed; `[logging]` now exposes only `level` (with `OFF`). **Migration:** delete those
  keys from your INI (strict validation now rejects them), and route/rotate logs at the
  environment level (journald, or redirect the service's stdout/stderr).

### Fixed

- **Pausing an in-flight copy with `resume_partial_files = false` no longer fails on resume.**
  The kept partial would previously collide with the exclusive create when the job resumed;
  now a pause under a disabled resume policy drops the partial so the file cleanly restarts
  from byte zero (mirroring startup recovery). With resume enabled the partial is kept and
  continued as before (L2-RSM-002).

### Documentation & internals

- Added **`docs/LOGGING.md`** (the stdout/stderr + logging architecture, for operators *and*
  developers) and **`docs/12-FACTOR.md`** (twelve-factor alignment and deliberate
  deviations); documented `doctor`'s environment checks and exit code 8 in CLI-REFERENCE and
  DEPLOYMENT, and added "add an environment check" / "add a log call" workflows to
  MAINTAINER-GUIDE. Added **`docs/FEATURE-INTERACTIONS.md`** (combining kernel copy, bandwidth
  limiting, partial resume, and pause/cancel/resume) plus a matching matrix in ARCHITECTURE.
- **Retired `docs/CAPTURE.md` into the specifications.** The original design conversation
  (~6,200 lines) was fully retired section by section — each removed only after its every
  claim was verified to live in a canonical doc, a requirement, a config option, or
  code+tests. CAPTURE is now a **design-history index** (a retirement ledger mapping each
  section to its home and the commit that removed it; git history retains the content).
  Unbuilt-but-valuable ideas surfaced during the review were migrated to `docs/ROADMAP.md`
  (spool-queue transport, streaming hash-while-copy, manifest per-file hashes, `version`
  collision policy, proactive free-space check, durable event/audit log, file-size and regex
  submission policies, per-job overrides, per-phase timings).
- **Requirements traceability audit.** Reconciled the trace matrix with the code — markers on
  existing data-safety tests plus focused new tests (filesystem identity, cross-filesystem
  claim rejection, inventory rules, temp/directory `fsync`, `O_NOFOLLOW`, config errors).
  `Draft` requirements dropped from **48 to 8**; every remaining `Draft` now means *genuinely
  unbuilt*, documented in `docs/ROADMAP.md` § Known gaps (claim-directory cleanup
  `L2-CLN-003/004`, manual-retry handler `L2-RTY-006`, event publisher `L2-EVT-*`) for an
  implement-or-withdraw decision.

## [0.3.0] - 2026-07-12

Adds operator **job lifecycle control** (cancel / pause / resume) and **partial-file
byte-offset resume**, alongside a separation-of-concerns refactor of the transfer and
control layers. Zero runtime dependencies; the full CI battery, no-panic fuzz harness,
L1/L2/L3 trace matrix, and SonarCloud quality gate remain green.

### Added

- **Job lifecycle control** — `file-mover pause` / `resume` / `cancel`. A job that is not
  copying is transitioned directly with a compare-and-set; an in-flight copy is stopped
  **cooperatively** at a safe buffer boundary via a thread-safe pause/cancel signal (there
  is no OS primitive to pause a file copy). Cancel always **retains the source** and
  discards only the incomplete partial; resume returns a paused job to the queue. New
  `PAUSED` state and transitions (L2-LIF-001..005).
- **Partial-file byte-offset resume** (`[transfer] resume_partial_files`, default on) — an
  interrupted copy continues from its fsynced `.swit-partial-` offset using `os.stat` /
  `os.lseek` / `os.copy_file_range` rather than restarting a large recording from byte
  zero. Startup recovery preserves interrupted partials when resume is enabled
  (L2-RSM-001/002, L3-PY-012).

### Changed

- **Separation of concerns (Fowler).** Extracted the per-file workflow into `FileMover`
  (job orchestration stays in `TransferCoordinator`), the control-response wire format into
  `presentation.py`, the lifecycle operations into `control/lifecycle.py`, the pause/cancel
  registry into `transfer/control_signals.py`, and partial cleanup into
  `transfer/partials.py` — reducing class/function complexity with no behavior change.

### Security

- A resumed partial that fails size or hash verification is discarded and the file restarts
  from zero; unverified bytes are never published (L2-RSM-003).

## [0.2.0] - 2026-07-12

Adds dynamic bandwidth limiting — a userspace token-bucket throughput ceiling that is
adjustable live over the control socket — and resolves the first round of static-analysis
findings. Zero runtime dependencies; the full CI battery, no-panic fuzz harness, and
L1/L2/L3 trace matrix remain green.

### Added

- **Dynamic bandwidth limiting.** A configurable aggregate copy-throughput ceiling,
  `[transfer] max_bytes_per_second` (bytes/sec; `0` = unlimited), enforced in userspace by
  a thread-safe token bucket shared across all concurrent copies — no `tc`/cgroup or
  `libsystemd` dependency (L2-BWL-001/003/004, L3-PY-011).
- **`file-mover throttle <bytes-per-second>`** control command that retunes the live limit
  without restarting the service (applies to in-flight copies); accepts SI/IEC suffixes
  (`50MB`, `1GiB`). The current ceiling is reported as `max_bytes_per_second` in
  `file-mover health` (L2-BWL-002).

### Changed

- A non-zero throughput limit forces the buffered copy strategy, because kernel-assisted
  `copy_file_range` moves bytes inside the kernel and cannot be paced from userspace
  (L3-PY-011). An unlimited limit leaves the kernel-copy fast path unaffected.

### Security

- Validate and normalize the operator-supplied configuration path before it is read:
  reject NUL bytes, resolve to an absolute real path, and require an existing regular file,
  closing a path-injection finding.

## [0.1.0] - 2026-07-11

First release. A durable, **standard-library-only** (Python 3.10) background transfer
coordinator that moves completed simulation recordings from a local NFS mount to a remote
processing filesystem independently of the simulation orchestration, with transaction-like
`claim → copy → verify → publish → delete-source` semantics. A source file is never
deleted until its destination has been written, fsynced, published, and verified.

### Added

**Service & operations**

- systemd-managed background service (`file-mover service run`) with a singleton `fcntl`
  process lock, `Type=notify` readiness + `WatchdogSec` liveness, and signal-driven
  graceful shutdown that drains in-flight work.
- Unix-domain-socket control plane: length-prefixed JSON protocol, a `CommandDispatcher`
  with a static command→handler map, and safe stale-socket recovery.
- CLI (`file-mover`): `submit`, `status`, `list`, `stats`, `health`, `config validate`,
  `doctor`, `service run` — with human and JSON output, documented exit codes, and a
  top-level exception boundary.

**Submission & claiming**

- Idempotent-by-`request_id` submission that atomically claims files into a per-source
  `.swit-moving/<job>/` staging directory (same-filesystem `os.replace`, device+inode
  identity checks), writes a durable JSON manifest, and returns only after the job and its
  file inventory are recorded. Directory and `--file-list` submissions; symbolic-link and
  non-regular-file rejection; optional source-stability polling.

**Transfer engine**

- Durable per-file workflow: verify claimed identity → optional source hash → copy to a
  `.swit-partial-` temporary file → size/hash verify → atomic publish → directory fsync →
  revalidate identity → delete the claimed source.
- Configurable integrity (`metadata` / `source-hash` / `source-and-destination-hash`) via
  `hashlib` with constant-time `hmac.compare_digest`.
- Kernel-assisted copy (`os.copy_file_range`, `[transfer] use_kernel_copy`) with a safe
  fallback to a bounded buffered loop; existing-destination collision handling
  (verify-and-reuse / fail); error classification and bounded exponential-backoff retry.

**Durability & recovery**

- SQLite job/file state (WAL, `synchronous=FULL`, `foreign_keys=ON`, per-thread
  connections, idempotent migrations) as the authoritative durable queue, with an
  explicit, enforced job state machine.
- Startup recovery reconciles interrupted jobs against the filesystem (re-queue, remove
  stale temporaries) idempotently; a transfer scheduler drives queued and due-retry jobs
  to completion on its own.

**Robustness ("no panic")**

- Every operational error becomes a typed, classified state; the control dispatcher, the
  SQLite repository, and the CLI never crash on bad input.
- A deterministic no-panic fuzz harness over the protocol, dispatcher, configuration
  loader, and CLI argv (`L1-ROB-001`), plus fault-injection tests proving source retention
  at every destructive boundary.

**Configuration & documentation**

- Strict INI configuration (`configparser`): unknown-section/option rejection,
  missing-required detection, range and cross-field validation, with all issues reported
  together; a single `OptionSpec` schema drives validation and generated docs. A
  fully-commented reference config ships in `config/file-mover.ini`.
- Documentation: architecture, CLI, config, maintainer guide, deployment runbook +
  NFS-qualification checklist, roadmap, and a full L1/L2/L3 requirement set with an
  auto-generated trace matrix.

**Quality**

- CI on Python 3.10–3.14 (Linux) plus Windows smoke: pytest with an 85% coverage floor,
  mypy `--strict`, ruff, pylint, vulture, bandit, CodeQL, SonarCloud, and a scheduled
  no-panic fuzz burn-in.

[Unreleased]: https://github.com/joey-huckabee/background-file-mover/compare/v0.4.2...HEAD
[0.4.2]: https://github.com/joey-huckabee/background-file-mover/compare/v0.4.1...v0.4.2
[0.4.1]: https://github.com/joey-huckabee/background-file-mover/compare/v0.4.0...v0.4.1
[0.4.0]: https://github.com/joey-huckabee/background-file-mover/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/joey-huckabee/background-file-mover/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/joey-huckabee/background-file-mover/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/joey-huckabee/background-file-mover/releases/tag/v0.1.0
