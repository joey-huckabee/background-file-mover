# Bounded native TLS executor isolation

2026-11-09. Authorized after increment124/PR13. Base main
`c18148f5d22caf3ea16f60aecfe13cc100ad5fc6`; branch
`feature/tls-resource-isolation`. Implementation and qualification are pending.

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
