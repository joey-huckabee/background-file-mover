# Bounded native TLS executor isolation

2026-11-09. Authorized after increment124/PR13. Base main
`c18148f5d22caf3ea16f60aecfe13cc100ad5fc6`; branch
`feature/tls-resource-isolation`. Implementation and bounded qualification are recorded below; deployment and release remain unapproved.

## Bounded design

Use two explicitly owned OS threads, each driving an existing Tokio current-thread
runtime. No new crate/features or general blocking pool. Dispatch only native HTTPS
connections; prototype/local Unix/native HTTP and private operator traffic keep
the existing main executor. Keep six producer/eight total permits, acquired before
dispatch and held until actual task/queued-job exit. A separately bounded executor
queue and six-job admission budget prevent hidden accumulation. Queue-full closes
the unhandshaken producer transport without plaintext fallback or fabricated429.

Convert accepted Tokio TCP to nonblocking std TCP on the owner executor and
register it with the TLS worker reactor before TLS I/O. Handshake expiration is
five seconds from acceptance, including queue delay; never refresh it on dequeue.
Keep HTTP/body/write/handoff limits and UUID/custody behavior unchanged.

A queued raw TCP job holds no old TLS policy or authenticated authority. On first
execution it registers/snapshots the current policy atomically using the existing
manager; an old certificate cannot use a previously captured policy. Registered
sessions retain existing reload cancellation, actual worker admission and expiry
checks. Queued authenticated Work still cannot authorize after generation change.

Stop closes dispatch, drops queued transports and aborts/drains connection futures.
Join every executor thread before dropping native endpoints/loader/worker ownership.
Every thread holds the instance guard. Do not detach non-yielding CPU work or claim
an async timeout can preempt it. Existing first-stop deadlines/status remain the
authority: incomplete synchronous work retains exclusion until actual exit.
This bounds executor concurrency, not an OS CPU percentage or hard realtime.

## Proof plan

Review exact pinned runtime/reactor and Rustls buffer/handshake limits from source;
record their actual scope rather than treating send-buffer limits as receive caps.
Run finite real-service handshake/slow-client/over-limit/reload/custody cases and
qualification-only deterministic non-yielding work on both TLS executors. Assert
private health/status/stop responsiveness, bounded job admission, no stale queued
authorization and guard retention through actual exit. Preserve normal TLS1.2/1.3,
known bytes/manifest/replay and explicit certificate-free loopback HTTP coverage.

Both full local SLES modes and final PR CI remain required. Record actual source,
pins, test timings, artifacts, failure packs and cleanup before integration. No
current passing increment124 evidence qualifies this changed source. Independent
client interoperability, fresh offline bundle, stale socket shipping lifecycle,
production NFS/deletion, operational state and all eight FR gates stay separate.

## Source inspection and bounded evaluation

Pinned local registry source (Cargo.lock checksums unchanged) confirms Rustls
0.23.46 handshake deframing/message bound65,535 bytes and ordinary record buffer
18,437 bytes. Received plaintext uses16KiB backpressure. Explicit64KiB send
buffering matches the prior default and is not a receive/handshake or total-memory
cap. Do not equate six connections with six times one buffer's memory.
See upstream [deframing](https://raw.githubusercontent.com/rustls/rustls/v/0.23.46/rustls/src/msgs/deframer/buffers.rs),
[handshake bounds](https://raw.githubusercontent.com/rustls/rustls/v/0.23.46/rustls/src/msgs/deframer/handshake.rs),
[common state](https://raw.githubusercontent.com/rustls/rustls/v/0.23.46/rustls/src/common_state.rs)
and [Tokio bridging](https://tokio.rs/tokio/topics/bridging).
A fixed worker budget also appears in [NGINX's worker configuration](https://nginx.org/en/docs/ngx_core_module.html);
this is design research, not selecting a proxy or importing its deployment profile.

Independent preflight at8a42fba found no architectural blocker. It required explicit
pre-TLS expiration checks, nonblocking dispatch, actual thread/guard closure and
physical registered-session exclusion during reload. These remain implementation
review and target-test obligations, not a passing qualification statement.

The first scoped run20261110T023607Z-4af59c46-nfs-qualification stops at strict
Clippy for two unnecessary two-element test Vec allocations; use arrays without
suppressing the lint. Independent review ofd3f9873 also finds that aborting the
main deadline watcher during shutdown must actively shut down its socket. The
fix keeps the watcher armed until successful handshake notification; Drop closes
on timeout, failed dispatch or cancellation. A shared wire-close guard inside the
session future also shuts down before removing session registration, so a main
watcher's duplicate descriptor cannot outlive reload's physical-exclusion ACK.
The shutdown regression now retains both CPU workers beyond five seconds and
checks closed wires before release while instance exclusion remains held.


CI follow-up: qualification debug exposed a test synchronization race after
closed wires were released from a non-yielding hold. Wire closure did not prove
that the original six producer budgets had drained. The test now first asserts
six budgets remain while held, releases the hold, and waits at most three seconds
for observed zero before its single positive request. No request retry or timeout
increase is used. Local TLS status exposes the original producer budget count;
private TLS-control wire version 2 safely refuses mixed-version control commands.
Existing strict decoding tests cover the required field, upper bound and v1 refusal.
The obsolete local full run `20261110T025712Z-38dba86c` was interrupted and its
containers cleaned; it supplies no full-pass evidence. Fresh full results are recorded below.

## Verification

Both full local SLES12SP5/glibc2.22 modes pass debug and release, with five
existing ignored tests per profile and clean cleanup:

| Run | Mode | Passed per profile | API seconds debug/release |
|---|---|---:|---|
| `20261110T033036Z-4fafb36f` | production | 315 | 612.86/455.02 |
| `20261110T041844Z-79039f6b-nfs-qualification` | nfs-qualification | 319 | 917.42/838.03 |

Production retains its 900-second API ceiling; qualification retains 1,200 seconds.
All 18 TLS functions and 28 application unit tests pass per profile. Three CPU
checkpoint integration bodies execute only in qualification; production function
counts do not prove those deterministic stalls. The nine executor unit tests
cover queue bounds, actual destructor/guard lifetime, panic, stopping and partial
thread-start failure. No new dependencies or Cargo features are introduced.

[Machine-readable evidence](NATIVE-TLS-RESOURCE-EVIDENCE.json) records all 83 Rust
input hashes, seven pins, both full local reports and 44 executable hashes. The
coordinator compares archived source bytes and independently rehashes every local
executable. Recomputed native compiler audits match the recorded intended
compiler/glibc2.22 sysroot in both phases of both modes. Runtime Rust tree:
`51721ff716101ce89297a60561949e2023a6aa30`. Rust/build inputs remain unchanged after
`d57b6a9` through closeout.

[Source CI](https://github.com/joey-huckabee/background-file-mover/actions/runs/42748640512) passes 315 production and 319 qualification tests per
debug/release profile. Downloaded reports/native logs match the declared audits;
protected Unix ingress passes 70 requests and 11 unsafe cases per profile, with
cleanup exit 0 and all 83 source hashes matched. CI executable bytes were not
uploaded for independent local rehash. The 35 workflow Python checks pass.
The exact runtime head also passes
[PR CI 42748864165](https://github.com/joey-huckabee/background-file-mover/actions/runs/42748864165).
The documentation-only closeout preserves all Rust/build inputs.

Corrected-source scoped run `20261110T031906Z-2f00f399-nfs-qualification` passes
46 tests per profile and cleans up. Earlier scoped success at `34ba0ca` is narrower
historical evidence. The initial Clippy failure, independent watcher finding,
CI drain-race failure and interrupted obsolete local run remain recorded above
and in evidence; none is counted as a passing full run.

Independent review covers the watcher fix, executor integration, guides and the
actual-capacity drain fix/IPC v2; no remaining actionable findings were reported.
See the [finite service evaluation](evals/2026-11-09-tls-resource-isolation.md)
and [operator setup guide](NATIVE-HTTPS-SETUP.md). Two threads bound scheduling
concurrency, not CPU percentage, total process memory or realtime latency.

## Agent work split and limits

The local coordinator owns wiring, tests, failure resolution, SLES gates,
provenance and integration. The bounded specialist supplied the executor module
and three user guides on separate branches. The independent cloud reviewer
checked architecture, source and instructions without replacing target execution.
Final evidence review is required before integration; the PR records its outcome. No operational credentials/state, deployment, production NFS/deletion,
independent TLS-client interoperability or new bundle/shipping qualification is
introduced. All eight FR gates remain open.
