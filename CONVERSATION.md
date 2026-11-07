# Conversation

Current decision: compute the source hash during copying, then reread destination
staging to verify its hash/size before publication and source cleanup. This is 3N
logical data I/O on the normal filesystem path. The prehash recommendations below
are superseded by this agreement; see [the integrity plan](docs/INTEGRITY-DESIGN.md).

Take a look at https://github.com/joey-huckabee/background-file-mover

We are currently rewriting this in rust. I do not want a one for one code rewrite I would like for you to architecture around best practices and tell me how you improve this using rust and what crates we will need for this

I would redesign this as a durable transfer coordinator—not as a line-for-line Rust port of the existing mover. The main improvements should be stronger transfer and recovery guarantees, simpler ownership of state, bounded resource use, and replacing custom infrastructure with well-maintained Rust libraries.
I reviewed the public main implementation and its requirements, filesystem layer, mover, manager, persistence, and tests. That public implementation is C++; this review does not cover your unpublished Rust rewrite, and I have not executed the repository’s tests. Also, the repository distinguishes the older Python architecture from a deliberately narrower C++ release that defers cross-filesystem copying, source claiming, and some recovery behavior. I would not carry those temporary scope restrictions into the Rust architecture. GitHub
1. What I would preserve—and what I would change
There are useful foundations here. The existing code already takes durable state, descriptor-relative filesystem access, and crash testing seriously. In particular, the mover tests kill a child process at transfer boundaries and reopen its persistent state for recovery. Those are worth preserving rather than replacing with ordinary “copy succeeded” tests. GitHub
However, several implementation choices deserve redesign:
| Area | What I found | Rust redesign |
|---|---|---|
| Final publication | `fsops::publish()` uses plain `renameat()` for the temporary-to-final transition. That operation can replace an existing destination. | Enforce **no-clobber publication at the final transition**, not just during earlier staging.  |
| Recovery evidence | Some recovery paths accept an existing final file as evidence that publication completed. | Require evidence that the destination belongs to this operation and has the expected content—not merely that its name exists.  |
| Filesystem outcomes | The link/unlink fallback can successfully create the destination link, fail to remove the source, and return `false`. | Represent partially applied and uncertain operations explicitly; do not equate an error with “nothing happened.”  |
| State ownership | The manager coordinates several shared containers and locks, with explicit precautions against holding its mutex across database work. | Give scheduling state one owner and database writes another. Communicate through bounded channels.  |
| Protocol implementation | The project maintains custom HTTP and JSON machinery partly because of the legacy C++ environment. | Replace that machinery with Axum and Serde while retaining the existing strict-input tests.  |

Rust’s biggest contribution here is not automatically faster copying. It is making resource ownership, valid transitions, and failure handling harder to get wrong.
2. Recommended architecture: one service, clearly separated responsibilities
I recommend one executable, one configuration file, and one systemd service, with a modular internal architecture.
For your NFS-oriented deployment, I would use an asynchronous coordinator and a small number of supervised transfer workers:

```
                    REST API / dashboard / CLI
                               |
                    Async coordinator process
                    ┌─────────────────────────┐
                    │ Request validation      │
                    │ Admission control       │
                    │ Scheduler               │
                    │ Recovery coordination   │
                    │ Status and telemetry    │
                    └────────────┬────────────┘
                                 |
                  Bounded commands and acknowledgements
                         /                   \
             Local database owner       Worker supervisor
             Dedicated DB thread              |
                     |                  Bounded worker pool
             SQLite on local disk       Same executable,
                                        child processes
                                              |
                                  Claim / hash / copy /
                                  verify / publish / clean
                                              |
                                      Source and destination
                                           filesystems
```

The child workers would be the same Rust executable in an internal worker mode, not shell commands, rsync, or independently deployed microservices. Private local communication would carry commands, progress, and results—not the file contents.
Why separate the coordinator from filesystem workers?
Tokio is appropriate for the REST API, scheduling, timers, and coordination. It does not make ordinary filesystem operations inherently nonblocking: Tokio’s filesystem support currently uses blocking operations behind the scenes. Also, a started spawn_blocking operation cannot simply be aborted when a timeout expires. Docs.rs
I would therefore keep long-running copying and hashing in bounded synchronous workers.
For a local-disk-only implementation, dedicated threads would be a reasonable simpler choice. For this service, I favor child-process isolation because it gives the coordinator a stronger boundary around worker panics, worker resources, and troubleshooting.
There is an important limitation: process isolation does not make a stuck NFS operation reliably cancellable. Hard-mounted NFS operations can retry indefinitely. A worker blocked in an uninterruptible kernel operation may remain stuck after a termination request. Do not switch to soft mounts merely to obtain convenient timeouts; the NFS documentation warns about data-corruption risks. Man7.org
Consequently, the supervisor must not start unlimited replacement workers or reassign the same transfer merely because a deadline elapsed.
I would also reserve capacity for short claim and reconciliation operations, so a new recording does not wait behind several complete large-file transfers before its source paths can be released.
Workspace organization
Four crates are sufficient:

| Workspace crate | Responsibility |
|---|---|
| `mover-core` | Job/file identifiers, policies, state transitions, retry decisions, recovery decisions. No HTTP, SQL, or filesystem side effects. |
| `mover-store` | SQLite schema, transactions, migrations, durable operation records, and queries. |
| `mover-fs` | Source claiming, descriptor-relative access, streaming copy, hashing, publication, and filesystem capability checks. |
| `file-mover` | Executable, API, scheduler, worker supervision, configuration, logging, metrics, and systemd integration. |

I would use a few meaningful abstraction boundaries, such as a repository interface and a filesystem-operation interface for fault injection. I would not create a trait for every struct or build a generic storage framework for hypothetical future backends.
Mounted NFS can use the POSIX adapter. A future S3 backend would need a different publication protocol, not an implementation pretending that object storage has POSIX rename semantics.
3. Make the transfer protocol the center of the design
The most important design work is defining exactly what each acknowledgement means and what evidence permits the next destructive action.
Distinguish acceptance from safe source-path reuse
Your requirements say simulation preparation can resume once the files are claimed and the job is durably accepted. That is stronger than merely inserting a queued job into a database. GitHub
I would expose two distinct milestones:

| Milestone | Meaning |
|---|---|
| `Accepted` | The submitted request and file list are durably recorded. The producer must not yet reuse the source paths. |
| `Claimed` | Every required source file has been relocated into the mover’s private claim namespace, and the relocation has been durably recorded and confirmed. The original paths can now be reused. |

A 202 Accepted response should not silently imply both.
The producer could submit and then wait or poll for Claimed. A client timeout would not cancel the job; retrying with the same idempotency key would retrieve the existing job.
Require a completed-file contract
The producer must finish writing before handing a file over.
Renaming a file changes its pathname; it does not revoke existing open descriptors. A writer that still has the file open can continue modifying it after the claim. Man7.org
Therefore, I would require an explicit producer handoff: completed file list or completion marker, closed writers, and no subsequent modification. Size and modification-time stability can be diagnostic checks, but I would not treat them as proof of immutability.
Recommended lifecycle
I would implement the destructive move workflow in this order:

| Phase | Required action and invariant |
|---|---|
| **Record intent** | Persist the job, file list, source/destination root IDs, resolved names, integrity policy, and idempotency key. |
| **Claim source files** | Relocate files within the source filesystem into a private namespace such as `.swit-moving/<instance>/<job>/`. Record each claim individually so partial multi-file claiming is recoverable. |
| **Establish source integrity** | Hash the claimed source and durably record the algorithm, digest, size, and relevant identity information before destination copying begins. |
| **Copy to destination staging** | Create a unique, exclusively owned temporary file **on the destination filesystem**. Stream through a reusable bounded buffer. |
| **Verify staging** | Synchronize the copied data, then read and verify the staged file against the recorded source size and digest. |
| **Publish** | Make the verified file visible under its final name without replacing unrelated data. Synchronize the affected directory entries according to the qualified filesystem behavior. |
| **Commit the recording set** | When all required files are published, publish an immutable completion manifest for consumers. |
| **Clean up source** | Remove only the claimed source entries authorized by the committed transfer record. Cleanup failure is recoverable and does not require recopying published data. |

I would preserve the original architecture’s separation between source integrity recording and destination transfer, rather than silently replacing it with a checksum computed only during the copy. GitHub
Claimed source files are not disposable temporary files. Until the destination has been verified and committed, they may be the only authoritative copy.
Add recording-set completion semantics
Publishing each file atomically does not make a recording containing multiple files appear atomically.
I recommend a destination completion manifest, for example:

```
recordings/<job-id>/
    video-01.bin
    telemetry.bin
    events.json
    COMMITTED.json
```
The contract would be:
> Consumers may process the recording only after its valid COMMITTED.json is published.
That manifest would identify the job and list the expected files, sizes, and digests. It would itself use the no-clobber publication protocol.
This is logical job-level visibility, not a claim that SQLite and two filesystems participate in one atomic transaction. It also requires downstream consumers to honor the manifest.
For move mode, I would default to retaining all claimed source files until the complete recording set is committed. That consumes more source space than per-file deletion, but substantially simplifies recovery of partially transferred recordings.
4. Use Rust to encode valid sequencing and uncertain outcomes
I would separate the durable transfer phase from user intent and operational status.
For example:

```
Transfer phase:
IntentRecorded → Claimed → SourceHashed → Copying
→ StagedVerified → PublishPending → Published
→ CleanupPending → Complete

Desired execution:
Running | Paused | Cancelled

Operational condition:
Ready | Retrying | Blocked | ReconcileRequired
```
This avoids one enormous enum containing every combination of “paused while copying after the third retry.”
Filesystem operations need more than Result<(), Error>
On NFS, a failed rename can nevertheless have occurred on the server. The Linux documentation explicitly identifies this ambiguity. Man7.org
I would make the adapter distinguish outcomes along these lines:

```rust
pub enum EffectOutcome<T> {
    Applied(T),

    // The adapter has evidence that the operation did not take effect.
    NotApplied(OperationError),

    // An effect may have occurred, or a multi-step operation partly completed.
    NeedsReconciliation {
        operation_id: OperationId,
        evidence: OperationEvidence,
        error: OperationError,
    },
}
```
The recovery decision then becomes:
Given the durable intent and current filesystem evidence, what can safely happen next?

It is not:
The last call returned an error, so retry the entire operation.

I would also use narrowly scoped types such as VerifiedStaging and PublishedReceipt, with private constructors. Source cleanup would require a validated publication receipt rather than just a path and a Boolean.
These types enforce sequencing inside the program. They do not prove that an NFS server or storage controller honored its durability contract.
One owner for scheduling state
The scheduler should own the runnable queue, active assignments, retry deadlines, and admission budgets. API handlers and workers send bounded messages to it.
This eliminates the need to scatter Arc<Mutex<HashMap<...>>> throughout the service. There may still be locks inside libraries or for small snapshots, but application correctness would no longer depend on a large lock-order convention.
Critical commit acknowledgements and worker results must not compete with unlimited progress events. Progress can be coalesced; durable state transitions cannot.
Keep SQLite, but make ownership and recovery explicit
I would keep SQLite for the local durable queue. WAL supports concurrent readers but still has one writer, and SQLite explicitly states that WAL is not suitable for a database shared over a network filesystem. SQLite
My proposed arrangement is:
```
/var/lib/file-mover/state.sqlite
```
on local persistent storage, owned by a dedicated database thread.
Use short transactions with WAL, synchronous=FULL, foreign-key enforcement, and checked configuration. FULL and NORMAL do not provide equivalent power-loss durability in WAL mode. SQLite
The database would record jobs, individual files, operation attempts, expected hashes, publication evidence, and schema versions. Before a worker performs a state-changing filesystem operation, it must receive acknowledgement that the corresponding intent has committed.
Recovery must compare database records with actual claim, staging, and final-file evidence. An existing destination name is not enough; a matching operation identity and validated content are what allow recovery to advance.
Finally, implement tested schema migrations. The current pre-release store deliberately rejects incompatible schema versions and includes a delete-and-restart instruction. That is not an acceptable production upgrade strategy once this database protects real recordings. GitHub
Six hosts do not create a distributed queue
For the multi-host deployment described in the repository, I would assign each instance explicit source ownership or disjoint submission scopes. GitHub
Local SQLite databases must not be mistaken for a cluster-wide lock. Cross-host takeover would require an additional, deliberately designed ownership and fencing protocol. I would not attempt to obtain safe failover merely by putting expiring lock files on NFS.
5. Filesystem safety needs its own small, heavily tested adapter
I would put the dangerous operations behind mover-fs, using rustix and standard Rust file handles.
rustix provides descriptor-oriented filesystem operations such as openat, linkat, unlinkat, synchronization, and flagged rename interfaces without maintaining application-specific syscall-number wrappers. Docs.rs
The adapter should enforce configured source/destination roots, component-wise path validation, regular-file-only policy, exclusive staging creation, and private claim/staging namespaces. The API should accept configured root identifiers and relative paths—not arbitrary unrestricted filesystem locations.
For the SLES baseline, do not require openat2: it was introduced in Linux 5.6. Use a carefully implemented descriptor-relative traversal that works on the older target, with newer facilities only as optional enhancements. Man7.org
Publication must be capability-based
My publication policy would be:
- Use renameat2(RENAME_NOREPLACE) where the actual destination filesystem supports the required behavior.
- For regular files, use a qualified hard-link publication followed by temporary-name cleanup where appropriate.
- When neither safe strategy is available, fail closed and retain the source rather than silently falling back to an overwriting rename.
Filesystem support for rename flags varies; kernel version alone is not sufficient. Man7.org
The hard-link approach needs explicit recovery for “final link exists, temporary name still exists.” Those two steps are not one atomic operation.
Capability tests should use private expendable files and exercise actual collision behavior. A doctor command could report the results along with mount identity, permissions, free-space conditions, and synchronization support.
Also verify that an expected NFS mount is actually present. I would not allow a disappeared mount to redirect output silently into the local directory underneath the mountpoint.
Be precise about durability
Synchronizing a file does not by itself guarantee persistence of its directory entry; directory synchronization is a separate consideration. Man7.org
The application’s guarantees also depend on the NFS server and backing storage. I would document and qualify those assumptions with real server-restart and failure tests. Neither a successful checksum reread nor a successful system call independently proves that remote storage will survive every power-loss scenario.
6. Performance: control the work before optimizing the copy primitive
I would start with buffered streaming, not memory mapping entire recordings, unbounded tasks, or an elaborate zero-copy subsystem.
A reasonable initial experiment is two active copy workers per instance, each reusing a 4 MiB buffer. That is approximately 8 MiB of application copy buffers regardless of whether the files total 1 GB or 100 GB; process overhead and operating-system caches are additional. These are starting parameters to benchmark, not claimed optimal settings.
Concurrency limits should account for the source and destination storage endpoints. Six daemons each making an individually reasonable decision can still overload a shared NFS server.
I would also bound queued files and bytes, prioritize source claiming, and expose backpressure before disk exhaustion—not simply accept an unlimited durable backlog.
Account for the integrity cost honestly
For an uncached buffered transfer with pre-transfer source hashing and destination reread verification, the logical work is approximately:

```
Read source for hash        N
Read source for copy        N
Write destination          N
Read destination to verify N
                          ----
                           4N
```
Thus, a 100 GB recording implies roughly 400 GB of logical file I/O under that model. That is a calculation, not a claim about network traffic: caching and filesystem behavior can change the physical traffic. (MY COMMENT: I dont want this we should be able to do better)
This is why I would not promise that rewriting C++ in Rust makes transfers dramatically faster. Storage behavior, unnecessary rereads, concurrency, and recovery work may dominate.
An optional copy_file_range path can come later, after filesystem-specific testing. It has kernel/filesystem restrictions and must handle partial copies and supported fallback cases correctly. It must not bypass integrity or publication rules. Man7.org
Add resume only after restart-from-source is correct
Initially, an interrupted file can safely restart from its retained claimed source.
Later, add durable chunk checkpoints: persist a checkpoint only after the corresponding destination bytes are synchronized, validate the retained prefix on recovery, discard uncommitted tails, and still perform final full-file verification.
Do not resume solely because a temporary file has a plausible length.
7. The Rust crates I would choose
I would select and lock exact versions after checking the complete dependency graph against your target build and license policy. The following is the stack I recommend evaluating—not a claim that arbitrary latest versions have already been qualified together on SLES.
Runtime dependencies

| Area | Crates | Why I would use them |
|---|---|---|
| Async coordinator | **`tokio`** | API runtime, bounded channels, timers, signals, and worker supervision. Keep bulk filesystem operations out of its core executor. ([Docs.rs][1]) |
| REST API | **`axum`**, **`tower`**, **`tower-http`** | Routing, typed extraction, request limits, middleware, tracing, and concurrency controls rather than custom HTTP parsing. ([Docs.rs][2]) |
| Serialization | **`serde`**, **`serde_json`** | Typed API requests, worker messages, and versioned manifests. Add explicit strictness tests, including unknown and duplicate fields. ([Docs.rs][3]) |
| Persistence | **`rusqlite`**, normally with **`bundled`** | Direct control over local SQLite transactions without introducing a database server or general async database framework. Bundling avoids dependence on the target’s installed SQLite version. ([GitHub][4]) |
| Filesystem boundary | **`rustix`** | Descriptor-relative operations and low-level Linux/POSIX functionality behind a small audited adapter. ([Docs.rs][5]) |
| Integrity | **`sha2`** | Incremental SHA-256 as the initial integrity algorithm. ([Docs.rs][6]) |
| Typed errors | **`thiserror`** | Preserve operation, phase, and underlying OS error rather than driving recovery from formatted strings. ([Docs.rs][7]) |
| Structured diagnostics | **`tracing`**, **`tracing-subscriber`** | Structured spans/events, filtering, and JSON output suitable for journald and collection systems. ([Docs.rs][8]) |
| Operational CLI | **`clap`** | `serve`, configuration validation, `doctor`, and explicit recovery/inspection commands. ([Docs.rs][9]) |
| Identifiers | **`uuid`** | Globally unique job and attempt identifiers; retain a separate database sequence for ordering. ([Docs.rs][10]) |
| systemd integration | **`sd-notify`** | Readiness/watchdog notifications without requiring a `libsystemd` integration layer. ([Docs.rs][11]) |
| Configuration compatibility | **`rust-ini`**, subject to compatibility tests | Preserve the existing INI interface initially. Add the project’s schema, duplicate-setting, and diagnostic requirements around the parser. ([Docs.rs][12]) |

[1]: https://docs.rs/tokio/latest/tokio/task/fn.spawn_blocking.html "spawn_blocking in tokio::task - Rust"

[2]: https://docs.rs/axum/latest/axum/ "axum - Rust"

[3]: https://docs.rs/serde/latest/serde/ "serde - Rust"

[4]: https://github.com/rusqlite/rusqlite "GitHub - rusqlite/rusqlite: Ergonomic bindings to SQLite for Rust · GitHub"

[5]: https://docs.rs/rustix/latest/rustix/fs/index.html "rustix::fs - Rust"

[6]: https://docs.rs/sha2/latest/sha2/ "sha2 - Rust"

[7]: https://docs.rs/thiserror/latest/thiserror/ "thiserror - Rust"

[8]: https://docs.rs/tracing/latest/tracing/ "tracing - Rust"

[9]: https://docs.rs/clap/latest/clap/ "clap - Rust"

[10]: https://docs.rs/uuid/latest/uuid/ "uuid - Rust"

[11]: https://docs.rs/sd-notify/latest/sd_notify/ "sd_notify - Rust"

[12]: https://docs.rs/rust-ini/latest/ini/ "ini - Rust"

Useful additions, not all mandatory on day one

| Crates | When I would add them |
|---|---|
| **`tokio-util`** | Cooperative cancellation and bounded message framing where needed. Cancellation remains cooperative; it does not cancel an arbitrary blocked filesystem syscall. ([Docs.rs][1]) |
| **`metrics`**, **`metrics-exporter-prometheus`** | Production telemetry and a scrape endpoint. This need not make an installed Prometheus server a prerequisite for running the mover. ([Docs.rs][2]) |
| **`blake3`** | An additional integrity algorithm only after policy approval and workload measurements justify it. I would not require two hash implementations initially. ([Docs.rs][3]) |

[1]: https://docs.rs/tokio-util/latest/tokio_util/sync/struct.CancellationToken.html "CancellationToken in tokio_util::sync - Rust"

[2]: https://docs.rs/metrics/latest/metrics/ "metrics - Rust"

[3]: https://docs.rs/blake3/latest/blake3/ "blake3 - Rust"

Serde can reject unknown fields with deny_unknown_fields, but adopting Serde does not automatically preserve every existing parser rule. Retain tests for duplicate fields, bounds, nesting, malformed input, and request-size limits. Serde
I would not initially add an actor framework, Redis, Kafka, SQLx, Rayon, an io_uring stack, directory-watching infrastructure, or a universal object-storage SDK. None is necessary to establish this service’s core guarantees.
8. Operations and testing should be designed alongside the transfer engine
The public service has a periodic watchdog notifier. I would distinguish that timer from meaningful evidence that the scheduler, database, and workers are functioning. GitHub
The operational model should separate:

| Signal | What it answers |
|---|---|
| **Liveness** | Is the coordinator functioning? |
| **Readiness** | Can it safely accept or dispatch the requested kind of work? |
| **Storage health** | Which source/destination endpoints are unavailable or blocked? |
| **Transfer progress** | Are active operations advancing, retrying, or awaiting reconciliation? |

An NFS outage should not automatically cause an endless whole-service restart loop.
I would record structured events containing job ID, file ID, attempt ID, phase, operation, elapsed time, and underlying error. Metrics should include queued bytes, oldest-job age, blocked workers, copy/verification throughput, synchronization latency, database commit latency, and pending source cleanup.
Keep filenames and job IDs out of metric labels to avoid unbounded label growth.
For API security, retain loopback as the default. Remote access needs an authenticated and authorized deployment boundary; the current requirements explicitly acknowledge the absence of in-process authentication. Requests must still be constrained to approved roots and operations inside the application. GitHub
Test the failure boundaries, not just the happy path
I would expand the existing kill-at-boundary approach into a deterministic failure matrix covering crashes around database commits, claims, writes, synchronization, verification, publication, and source deletion.
The essential outcomes to test are: source retained after unsuccessful publication; unrelated destinations never overwritten; ambiguous operations reconciled rather than blindly repeated; partial recording sets not consumed; and published recordings not recopied merely because cleanup failed.
Use proptest for generated transition sequences, tempfile for isolated test environments, and cargo-fuzz for externally supplied data and recovery inputs. Use criterion for isolated hot paths, with separate end-to-end benchmarks on the actual NFS deployment. Docs.rs
Production staging files should have explicit durable lifecycles; I would not rely on automatically deleted temporary-file objects to represent recoverable transfers.
9. Keep the SLES and disconnected-deployment constraints in the build design
The repository identifies SLES 12 SP5, glibc 2.22, and an older kernel as important deployment constraints. That is separate from its C++ compiler constraint. GitHub
Rust’s published x86_64-unknown-linux-gnu target requirements list a lower kernel/glibc baseline, but that does not establish compatibility of your final executable and every native dependency. Rust Documentation
I would use a pinned modern Rust toolchain on the build host, a controlled target sysroot, a conservative CPU target, and native dependencies built against that same target environment. With bundled SQLite, a C compiler is still involved at build time. GitHub
Release qualification should inspect the executable’s actual required GLIBC symbol versions and then run it on SLES with the real mounts.
For disconnected builds, vendor the locked Cargo dependency set and separately package the toolchain, targets, and native build prerequisites. Cargo’s vendoring support provides the crate source-replacement mechanism; it is not a substitute for packaging the rest of the build environment. Rust Documentation
Also review the transitive dependency licenses and enabled features. The repository’s legacy-platform discussion documents a restrictive license policy, so “permissively licensed” should not be assumed to mean automatically approved. cargo-deny can help enforce an explicit dependency policy. GitHub
My recommended implementation order
I would build the Rust rewrite in four increments:
1. Core protocol and persistence: reconcile the requirements, define state transitions and evidence, establish the SLES build, and implement the local store.
2. One correct cross-filesystem transfer: claim, prehash, copy, verify, no-clobber publish, and crash recovery—with source deletion disabled initially.
3. Safe production operation: enable gated cleanup, multi-file completion manifests, admission control, worker isolation, operational diagnostics, and real NFS failure tests.
4. Measured optimization: tune concurrency and buffering, then consider resumable chunks, kernel-copy paths, and dashboard enhancements.
During cutover, drain the old service or explicitly migrate its outstanding work. Do not let old and new implementations independently manipulate the same source namespace.
My recommended foundation is Tokio/Axum for coordination, rusqlite for local durable state, rustix plus bounded synchronous workers for filesystem effects, and a protocol built around durable intent, verified no-clobber publication, and recoverable cleanup. That is where Rust can materially improve this project without turning it into an unnecessarily complicated platform.
