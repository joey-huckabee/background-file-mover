# Configurable logging — design for review

2026-11-23 draft, based on `main` at `e0a606e`. **Design only: review is
required before implementation.** User decisions are dated 2026-11-22. No
logging configuration, writer, rotation, unit modification or new dependency is
implemented or qualified by this document.

## Decisions and scope

The user accepts JOB-014's rule that failed recording never authorizes source
deletion or silent continuation, and SEC-008's unconditional no-shell rule.
The user rejects CLI-006's application-managed-log prohibition and requests
configurable levels, journal output and an optional managed/rotated file.
**CLI-006 is approved backlog until this feature ships**, not satisfied by the
old stderr implementation. See the superseding record in
[TRACE-DECISIONS.md](TRACE-DECISIONS.md) and [increment170](RUST-INCREMENT-170.md).

This first design covers daemon diagnostics and their parent-side worker
reports. Command results remain on stdout, including machine-readable JSON;
foreground prompts/results are not subject to a daemon verbosity threshold.
No browser logging API, remote sink, syslog socket client, live reload,
compression, log viewer or new audit/receipt authority is included. Restart
applies changes. Transfers, original-state custody, failure accounting and
all existing control/shutdown deadlines are unchanged.

**Assumption requiring user confirmation:** OFF preserves a small best-effort
stderr safety stream: readiness, terminal startup/service errors, persistence
failures and the qualification-build prohibition. Repeated identical errors are
coalesced. OFF does not mean total silence. Actual readiness is currently
`println!` on **stdout** (`lib.rs:2507/2512/2514`); proposing stderr readiness
is a stream change, not a claim that today's output is already there. Update
readiness-capture tests deliberately; do not change command JSON stdout or
worker IPC. An alternative is total daemon silence when OFF, including readiness
and errors; it hides startup/storage failures from journal users and is not
recommended. Foreground command errors/prompts and exit codes still work.

## Configuration proposal

Omitting `logging` is equivalent to:

```json
{
  "logging": {
    "enabled": false,
    "level": "off",
    "file": null,
    "max_file_bytes": 10485760,
    "max_files": 5,
    "journal_levels": true
  }
}
```

An illustrative enabled block uses `enabled: true`, `level: "info"` and
`file: "/var/log/file-mover/service.log"`; the parent must already exist under
the service user's private custody. This is not an installation instruction.

| Setting | Proposed validation / meaning |
|---|---|
| `enabled` | Boolean, default false. New configurable logging is active only when true **and** a path/name is supplied **and** level is not off. |
| `level` | Exactly `off`, `error`, `warn`, `info`, `debug`; default off. Threshold includes this level and all more severe levels. No trace level. |
| `file` | Optional while inactive; required when enabled at a non-off level. Canonical absolute UTF-8 path, at most 4095 bytes including filename. Basename 1–240 bytes, leaving room for derived names; every derived full path must also fit. Parent and filename safety below. |
| `max_file_bytes` | Integer, default 10 MiB; 64 KiB–1 GiB. Checked multiplication with `max_files` must not exceed 1 GiB. Includes header/newlines; no record exceeds 1024 bytes. |
| `max_files` | Integer 1–20, default 5; counts current file **plus** retained numbered archives. |
| `journal_levels` | Boolean, default true; controls `<N>` severity prefixes on daemon stderr, not whether errors are emitted or whether the host stores them. False uses plain severity names. |

Unknown fields, wrong types and enabled-at-non-off-without-path are configuration
errors before startup effects. Either `enabled: false` or `level: "off"` disables
configurable logging, even with a staged valid path/level in the other fields;
changing level to off alone is sufficient on restart. Validate all supplied
values, path syntax/overlap and rotation bounds even when inactive, but perform
no configured log-path I/O in OFF mode. No log file, lock or directory is created.

The required path follows the user's enable-plus-path condition literally;
there is **no new journal-only enabled mode** in this proposal. If “optional
file” is intended to permit enabled journal-only logging, that needs a clarified
configuration gate; do not silently enable it on a missing path. A configured
file sink can degrade to journal-only after an I/O failure as described below.

Settings are startup-only, excluded from live TLS reload. Reload admission must
reject changed logging settings just like other non-TLS configuration. Failure
to configure logging never grants filesystem authority, changes job eligibility
or rewrites the persistence-error rules.

## Levels, streams and systemd

| Level | Prefix | Meaning |
|---|---|---|
| error | `<3>` | Startup failure, lost persistence/discovery capability or service-stopping error. |
| warn | `<4>` | Recoverable refusal, retained uncertain work, capacity retry or reduced capability. |
| info | `<6>` | Readiness, normal lifecycle/cancellation and bounded policy summaries. |
| debug | `<7>` | Additional bounded phase/scheduling diagnostics; no per-byte/per-chunk events. |
| off | none selected | No configurable event stream/file; only the assumed minimal safety stream remains. |

The [candidate unit](../scripts/bundle/file-mover.service.in) does not override
standard-output/error routing or `SyslogLevelPrefix`. Upstream systemd v228
specifies prefix parsing enabled by default, stdout defaulting to the manager's
journal setting and stderr to inherited stdout. Thus `<N>` on stderr carries
priority **under those defaults**; local manager/unit overrides can change it.
This is source confirmation, not an actual installed-SLES journal test.
[Primary systemd documentation](https://raw.githubusercontent.com/systemd/systemd/v228/man/systemd.exec.xml).

The implementation should make `StandardError=journal` and
`SyslogLevelPrefix=yes` explicit in the candidate when separately authorized;
this PR changes no unit. Verify actual PRIORITY fields under the target manager
and test disabled prefix parsing as a negative. Writing stderr alone does not
assign severity. Plain terminal redirection sees literal prefixes when enabled;
`journal_levels: false` is the foreground readability option. The journal's
storage, quotas and retention remain host policy, separate from managed-file
rotation. Readiness stays informational, not manager-ready notification.

### Inventory of all 42 current stderr macro sites

Snapshot from `file-mover/src` at the base above. Numbers are source lines,
not stable event IDs. Implementation gives each site a stable constant code
and compares this inventory with a fresh search. Repeated source sites are
listed separately. References: [lib.rs](../rust/crates/file-mover/src/lib.rs),
[main.rs](../rust/crates/file-mover/src/main.rs),
[claim_worker.rs](../rust/crates/file-mover/src/claim_worker.rs),
[delivery_worker.rs](../rust/crates/file-mover/src/delivery_worker.rs),
[missing_retry.rs](../rust/crates/file-mover/src/missing_retry.rs),
[source_space.rs](../rust/crates/file-mover/src/source_space.rs),
[bootstrap.rs](../rust/crates/file-mover/src/bootstrap.rs),
[account_cli.rs](../rust/crates/file-mover/src/account_cli.rs).

| Site | Current message / condition | Assigned level / treatment |
|---|---|---|
| `account_cli.rs:570` | Submitting password change | info, foreground progress; omit raw change ID from new log events. |
| `account_cli.rs:599` | Password active, sessions revoked, earlier actions finishing | info, foreground completion; no password/session values. |
| `bootstrap.rs:165` | Termination requested, awaiting child exit | warn, coalesced; never imply that the child has exited. |
| `claim_worker.rs:174` | Validated worker diagnostic | warn, parent-side bounded code/errno. |
| `claim_worker.rs:220` | Claim problem record failed | error. |
| `claim_worker.rs:367` | Claim problem record failed | error. |
| `claim_worker.rs:471` | Unrecorded empty allocation kept | warn; no raw path/error rendering. |
| `delivery_worker.rs:377` | Worker sequence diagnostic | warn, parent-side bounded code/errno. |
| `lib.rs:508` | Cancellation settlement failed | error. |
| `lib.rs:521` | Retained deletion discovery failed | error. |
| `lib.rs:545` | Retained deletion target failed | warn; job/file indices only. |
| `lib.rs:554` | Deletion result persistence failed | error. |
| `lib.rs:577` | Destination deletion/cleanup discovery failed | error. |
| `lib.rs:594` | Automatic cleanup eligibility lookup failed | error. |
| `lib.rs:628` | Destination deletion/automatic cleanup target failed | warn. |
| `lib.rs:650` | Destination deletion/cleanup result persistence failed | error. |
| `lib.rs:666` | Source cleanup discovery failed | error. |
| `lib.rs:682` | Source cleanup eligibility lookup failed | error. |
| `lib.rs:721` | Source cleanup target failed | warn. |
| `lib.rs:729` | Source cleanup result persistence failed | error. |
| `lib.rs:756` | Delivery discovery failed | error. |
| `lib.rs:808` | Delivery problem record failed | error. |
| `lib.rs:811` | Delivery stopped by job cancellation | info. |
| `lib.rs:816` | Destination refusal persistence failed | error. |
| `lib.rs:822` | Capacity backoff scheduled | warn, coalesced. |
| `lib.rs:824` | Capacity retry persistence failed | error. |
| `lib.rs:832` | Availability deferral persistence failed | error. |
| `lib.rs:838` | Delivery requires reconciliation | warn; no new retry authority. |
| `lib.rs:840` | Delivery retry persistence failed | error. |
| `lib.rs:847` | Delivery discovery failed | error. |
| `lib.rs:1665` | Shared custody unavailable, serialized fallback | warn; disclose no destination path. |
| `main.rs:11` | Internal invocation's debug-formatted failure | error conceptually, **IPC compatibility branch**, never routed to a logger or prefixed. Parent emits only a validated sanitized diagnostic. |
| `main.rs:15` | User-facing command/startup error | error; bounded sanitized fallback before logger availability. |
| `main.rs:92` | Qualification binary not deployable | warn, mandatory safety banner independent of threshold. |
| `main.rs:386` | Confirmed history-clear consequence message | info, foreground command notice; not a droppable daemon confirmation mechanism. |
| `missing_retry.rs:151` | Wall-clock jump | warn, aggregate. |
| `missing_retry.rs:159` | Windows affected by clock jump | warn; count/summary instead of an unbounded job-list dump. |
| `missing_retry.rs:168` | Clock-jump lookup failed | error. |
| `missing_retry.rs:189` | Retry discovery failed | error. |
| `missing_retry.rs:276` | Retry operation failed | warn, fixed operation code; ordinary missing-file waits need no per-pass log. |
| `source_space.rs:259` | Admission policy summary | info, allowlisted public scalar fields instead of serializing arbitrary config. |
| `source_space.rs:291` | Source-space worker diagnostic | warn, validated bounded code/errno. |

No existing site needs debug merely to fill that level. Future debug events
may describe phase boundaries, not buffers, requests or credentials. The three
readiness stdout sites become info-level stderr events, retained by the OFF
assumption. Command stdout, password-library test output and worker streams are
not logging sinks. Existing foreground no-echo prompts must remain synchronous
foreground I/O, not queued/dropped logs; no terminal is required for the daemon
or explicit account `--stdin` mode.

**IPC boundary:** logger initialization occurs only on the daemon path. Internal
workers must not inherit a logger handle or log file FD; all such FDs are
CLOEXEC. Some worker stderr/stdout descriptors carry receipts, sockets or custody
locks. Never insert prefixes, debug text or a logger thread there. Parent-side
receipt decoders emit the sanitized events above; preserve protocol bytes.

## Bounded producers and isolated writers

Proposed fixed budgets, not new configuration knobs:

- Threshold check first: a cheap immutable/atomic level check returns before
  formatting, allocation, clock sampling, locks or channel operations for
  suppressed configurable messages. OFF still permits the rare safety events.
- Capture a bounded typed event: constant code, level, optional numeric job/file
  index, numeric errno and allowlisted counters/reason enums. At most 256 bytes;
  no generic `Debug`/`Display` input or stored config/request object.
- Two independent bounded channels, capacity 1024 events each, with
  `try_send`: one for stderr and, only when enabled, one for the file writer.
  No producer waits for capacity, acknowledges a write, flushes, stats a path,
  rotates, or falls back to direct `eprintln!` in a service loop. This covers
  main control, claim, delivery, retry, cleanup and store callback paths.
- One stderr-dispatch thread and one optional dedicated file-writer thread;
  the latter never writes stderr directly. OFF needs only the minimal diagnostic
  dispatcher (its OFF-mode resource cost is included in the benchmark). Use a
  CLOEXEC duplicate of stderr with raw writer-side I/O, without holding a global
  stdio lock or changing inherited file-description flags. File stalls cannot
  stop journal dispatch; a blocked stderr sink
  cannot stop file dispatch. Their bounded queues can independently lose events.
- `try_send` full/disconnected drops the record and increments per-sink atomic
  counters. No unbounded retry or recursion. The API is non-waiting for capacity,
  not a promise of lock-free implementation or hard real-time scheduling.
- Writer-side bounded formatting produces one escaped line, at most 1024 bytes,
  with epoch timestamp, level, PID and code plus permitted fields. No per-record
  fsync, SQLite write, transfer callback or payload-tree access. Queue payload
  storage is at most 512 KiB combined, plus bounded formatting buffers and two
  explicitly sized 256 KiB thread stacks; this is not a whole-service RAM cap.
- Successful sinks emit coalesced drop summaries at most once per second,
  reading counters directly rather than enqueueing their own reports. The file
  writer reports a file failure through stderr `try_send` once, without recursion.
  Below-threshold messages are not queue drops. Counters distinguish each sink,
  write errors, queue loss and shutdown loss; logs are not audit receipts. Drop
  summaries are warn-level and obey the configured threshold; sink failure is
  error-level. OFF safety diagnostics are the stated exception, not a hidden
  debug stream.

Rate-limit repeating `(code, job)` events with a bounded table (256 slots, fixed
one-second windows, eviction counts); use atomics or try-lock-and-drop on
contention, never wait on a limiter lock. No unbounded map keyed by filenames or
requests. Count coalescing separately from sink drops. Filtering precedes rate-limit work. Journal/file thresholds share the
configured level; OFF safety events have a separate explicit allowlist.

## File custody, rotation and failure policy

The writer uses a preprovisioned **0700** directory owned by the effective
non-root service UID and primary GID. Active file, archives and persistent
`basename.lock` require owner UID/GID, **0600**, regular type and nlink=1. The
lock uses nonblocking flock for single-writer exclusion; an existing lock name
is validated and reused, never blindly unlinked. A second logger targeting the
same name disables its file sink, not the service. No automatic directory
creation, chown, permission repair, shell or external logrotate process.

Reuse the private-path primitives within `mover-fs`:
[credentials.rs](../rust/crates/mover-fs/src/credentials.rs)'s `parts`,
`parent_directory`, `local`, `unchanged`, and
[instance.rs](../rust/crates/mover-fs/src/instance.rs)'s `ingress_local` before
configured pathname I/O. These helpers are internal today; a future scoped
log-directory API can compose them like
[account_file.rs](../rust/crates/mover-fs/src/account_file.rs). The credential
reader is read-only and the account publisher is record-specific: neither is
an append/rotation API that can be reused unchanged. Keep credential read-size
limits unchanged: log capacities need their own metadata validation, not a wider
credential reader. Reuse/extract lexical path checking without treating the
credential `parts` maximum-read argument as a multi-megabyte logging allowance.

Require canonical absolute paths, no empty/dot/dot-dot/backslash/control
components, NOFOLLOW traversal, CLOEXEC descriptors, safe root-or-current-UID
ancestors and exact private parent custody. Reject remote/FUSE/unsupported
filesystems, bind aliases, duplicate mounts and mounted leaves/nested mounts,
including archive/lock names, before opening them. Local allowlist stays
ext/tmpfs/overlay as in the existing helpers, **never NFS even in qualification**.
Hold directory FDs and revalidate device/inode/ownership plus pathname binding
before namespace changes; failure disables the sink. Same-UID/root hostile
mutation remains outside the private-custody threat model, not a new fence.

The dedicated directory must be component-wise disjoint (neither ancestor nor
descendant) from state, source, destination, credential/account parents and
operator/producer socket parents. Compare configured paths and existing safe
mount/identity observations; add no synchronous payload-mount traversal for
logging. Parent mode and alias rules also protect against prefix-lookalike
paths, symlink components and redirection into a private key or SQLite file.

Open active files for append without truncation. New files are exclusive 0600;
existing files/archives must have the managed-format header and checked custody,
otherwise preserve them and disable the file sink. Rotation owns only
`basename`, `basename.1` … `basename.(max_files-1)` and its exact lock name.
Prevalidate the family; an unsafe/foreign member prevents rotation, not adoption
or deletion. With the private parent/lock held, remove only the checked oldest
owned archive, rename checked archives down the bounded chain, move the active
file to `.1`, then exclusively create a fresh active file. For `max_files=1`,
remove only the checked active file and exclusively recreate it. No copytruncate.
Recheck named inodes before rename/unlink; never glob or recursively clean.

Rotate **before** a whole record would exceed `max_file_bytes`, including headers.
A partial write, ENOSPC, EIO, unsafe replacement or failed rotation disables
file writes for this process lifetime; do not keep reopening a broken sink.
Retain uncertain files and their names for operator inspection. A safe stderr
warning is attempted once and a counter remains even if stderr is also full or
blocked; delivery of that warning cannot be guaranteed on a failed sink.
Transfers continue, with no injected delivery failure/retry/cancellation.
Existing oversized files after a lower restart limit are preserved and the sink
is disabled, not truncated to fit. Rotation is diagnostic best effort: a crash
may lose the newest lines or leave a partial rotation; it cannot trigger state
restore, payload cleanup or log-based adoption. No durable-log guarantee.

**Storage isolation limit for review:** outside the payload paths is not the
same as outside their filesystem. Logs filling shared free space can cause
SQLite/payload ENOSPC; separate threads cannot prevent that indirect failure.
For the user's strict “logging disk never fails a transfer” goal, recommend
requiring a separate log filesystem from state/source/destination devices,
using already established device observations or refusing the file sink if
independence cannot be established. Separate devices can still share physical
storage/CPU and need deployment I/O isolation. Shared-filesystem operation would
need explicit acceptance of the weaker guarantee, not an undocumented exception.
Caps bound log bytes, not filesystem metadata/reservations or competing writers.

## Startup, shutdown and blocked sinks

Configuration validation does no logging-path I/O on service/copy paths. Start
sink threads with readiness/error channels; wait at most 500 ms for optional
sink preparation, then continue with that sink unavailable if it is not ready.
Thread-spawn failure similarly marks the sink unavailable and does not introduce
a synchronous service-loop fallback. A late preparation result cannot activate a disabled sink; check the gate before
writes/rotation and close safely on eventual return. A pending open/create may
complete late, leaving an empty owned log file; never claim that timeout cancels
filesystem effects. Unsafe configuration syntax/overlap is rejected before
service admission; operational sink failures degrade diagnostics, not transfers.

Start minimal stderr dispatch before daemon diagnostics; activate the optional
file sink only after existing startup validation supplies the safe root/device
observations. Pass public observations, never custody handles, to its validator.

Logger threads own only log/stderr resources and bounded counters: **no
InstanceGuard, Store, worker, TLS generation or transfer references**. Keep their
JoinHandles tracked; join on confirmed exit. A panic disables that sink without
panicking a transfer or requesting lifecycle stop. No nested untracked threads.

**Shutdown proposal needing review:** stop event producers, allow at most 250 ms
of best-effort diagnostic drain, then abandon queued diagnostics. Never wait
unboundedly on a logger join or reset the service's first stop deadline. A regular
file or stderr write can remain blocked in the kernel; channel deadlines and
O_NONBLOCK do not make regular-file I/O cancellable. All existing custody-owning
threads/workers must still exit under their original rules. Only after their
normal final teardown may process termination end a still-blocked diagnostic
thread; do not report it joined or invent a child PID/worker adoption path.
Rust documents that process termination at main-thread completion also ends
remaining threads, potentially without their destructors.
[Primary Rust documentation](https://doc.rust-lang.org/std/thread/index.html).
If review requires every logger thread joined before return in all cases, a
stalled-sink service exit cannot also be bounded with this std-thread design;
that requires a separately reviewed isolation mechanism. This is an explicit
trade-off, not permission to release payload custody early.

## Secrets and diagnostic authority

Logging takes only allowlisted typed fields and constant templates. Never log
Config Debug, passwords/confirmations, verifier/PHC/salt material, private keys,
DER/PEM bytes, HTTP headers/bodies/cookies, authorization/CSRF/session/reset
values, proxy secrets, TTY input, environment dumps or TLS session/keylog data.
Do not log arbitrary native error strings or third-party Debug/Display chains.
Use existing bounded diagnostic code/operation/errno validation, not “sanitize”
by removing newlines while retaining secret text. Disallow producer filenames,
source/credential/account paths and usernames by default; numeric job/file IDs
and explicitly public counters are sufficient for these sites. Escape any
allowed text/control characters before a single-line render; never let input
supply a syslog prefix. Candidate file paths may enter guarded config validation
errors only under existing operator rules, never key contents.

Foreground account prompts and machine command results keep their existing
secret-safe protocols. No file sink is started in internal workers or offline
commands; daemon logging settings cannot break account no-echo or CLI JSON.
Replacing a print never removes the existing error/stop/persistence behavior:
logging failure must neither create a transfer failure nor mask a real one.
Logs can be missing, reordered across sinks, truncated on crash or dropped;
never use them to authorize handoff, deletion, retry, replay or recovery. JOB-014,
SEC-008 and existing credential-redaction obligations remain unconditional.

## Performance and verification plan

No measured results are claimed. “No blocking sink I/O in transfer loops” is a
structural guarantee to test; literally zero performance cost on shared CPU or
disk is not possible. Suppressed events should reduce to a cheap threshold
branch. Review measurement tolerances before calling overhead insignificant.

1. Unit tests: complete config truth table/ranges/checked budgets; level and
   prefix mapping; below-threshold formatting closure never evaluated; bounded
   event/line size, escaping and deterministic redaction fixtures with sentinel
   secrets absent from both sinks, panic/error paths and drop summaries.
2. Deterministic sink tests: hold each writer, fill its queue and prove producer
   calls finish without waiting; counters/other sink still progress. Simulate
   ENOSPC/EIO/partial writes, blocked journal, writer panic, slow open and late
   startup completion. No failure is returned into transfer logic. Do not fill
   the host disk to test this: use disposable injected sinks/bounded fixtures.
3. Filesystem tests: root/UID/GID/mode/link checks; symlink and mounted-leaf/alias
   refusals; overlap in both directions; foreign archives/lock, lock contention,
   substituted names and crash points in rotation; max_files=1; restart append,
   lower caps and the no-clobber/preserve-uncertain policy. Only owned fixtures.
4. Service/IPC tests: OFF with no log files; readiness/error stderr assumption;
   CLI stdout byte-for-byte JSON and unchanged internal worker framing; logger
   FDs absent after exec; native/control/claim/delivery remain responsive under
   blocked sinks; all admitted jobs commit once with no logging-induced failure.
   Stop during stalled writer without changing custody/first-deadline behavior.
5. Run existing `timer_retries_do_not_starve_under_sustained_sender_load` in
   [api.rs](../rust/crates/file-mover/tests/api.rs) with six senders and the
   zero-sender baseline, separately for OFF/info/debug. Preserve all late-claim
   progress, health, exact replay and pre-stop commitment assertions. Add a
   repeatable completed-job throughput benchmark with equal data sets and
   logging OFF/info/debug plus a deliberately saturated sink; compare against
   the unchanged executable too. Report throughput, p95 admission/health latency,
   late-claim time, CPU, RSS, I/O, queue/drop counts and logging enqueue cost.
   Include a threshold-only microbenchmark, cold/warm runs and multiple repeats
   with host/cache conditions recorded. Debug adds phase events, never chunk
   events. Do not relax transfer assertions or infer speed from an unsaturated
   test. Proposed tolerances and storage-isolation policy need review; noisy
   results are inconclusive, not a performance pass.
6. Both full SLES production/qualification debug/release gates, actual target
   systemd PRIORITY observation and independent review follow implementation.
   Fixed-thread isolation is not an OS I/O quota, real-time guarantee, deployment
   approval, production NFS qualification or FR release closure.

## Requirements, dependencies and review questions

CLI-006's no-managed-files clause is rejected. Proposed replacement obligation:
“Provide startup-configured, default-OFF leveled daemon diagnostics to stderr and
an explicitly enabled managed file with bounded rotation; logging sinks never
block transfer loops or turn logging failures into transfer failures. Preserve
non-terminal service/automation and stdout command results.” Exact wording and
OFF fallback depend on this review. SEC-008 still forbids every shell launch;
JOB-014's source-preservation/reporting rule remains accepted. SEC-001/002/003/006
and SEC-012/013/014 security/host constraints are not weakened to permit logs;
log-directory safety and writable-path hardening require additional evidence,
not automatic upgrades. Keep all other backlog items and FR gates open.

Use std channels/threads/atomics/fmt plus existing rustix/path primitives. No new
crate, native library, dependency feature, background service or external tool is
proposed. If implementation cannot meet the reviewed design with that graph,
return the exact dependency proposal for user approval before adding it.

Questions for the user/reviewer before implementation:

- Confirm minimal OFF-mode stderr safety lines, including the proposed stdout
  to stderr readiness move, versus total silence and its diagnostic risk.
- Confirm the enable-plus-path gate, or explicitly permit a journal-only enabled
  mode despite the original path requirement.
- Confirm separate-filesystem enforcement/required deployment isolation, or accept
  the weaker shared-space guarantee. Agree benchmark acceptance tolerances.
- Review bounded diagnostic drain/process-exit handling for a blocked sink versus
  requiring an isolation redesign. No implicit logger-thread cancellation claim.

This PR records the user decision and proposed design only. Formal L2 wording,
trace dispositions/checker bookkeeping and rollout instructions for the new
feature must be reconciled together after design review; legacy Inspection of
CLI-006 is evidence of the old stream behavior, **not** satisfaction of this
approved logging backlog. No logging feature is shipped by recording it here.
