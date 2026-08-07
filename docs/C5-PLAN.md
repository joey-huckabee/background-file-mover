# C5 — REST control plane

The socket server and routing layer, on top of the request-head parser and JSON
codec already delivered. **Advances `L2-CTL-001..016`.**

The concurrency model — the decision the roadmap has carried open since triage
— is settled in **ADR-0013**: an accept loop feeding a bounded pool of handler
threads. Read that first; this plan assumes it.

---

## 1. The two C4 lessons, and why C5 is where they bite

These are carried forward as *mechanism*, not as advice. Advice in a document is
what the C1 apparatus audit found had already failed twice.

### 1.1 No timed condition wait on a mutex that also guards data

**What happened.** `JobManager::wait_idle` used
`std::condition_variable::wait_until`. That is correct C++. ThreadSanitizer
cannot model it: after a timed wait, TSan believes the mutex is still held
following an explicit `unlock()`, reports a phantom "double lock", and treats
every access that mutex guards as unsynchronised. It produced 32 warnings whose
two sides were *both* recorded as holding the same mutex — an impossibility that
took three passes to read correctly. Measured in isolation, one binary, three
ways: `wait()` 0 warnings, `wait_until()` 11–19, bounded poll 0.

**Why C5 walks into it.** C5 needs timeouts. `L2-SEC-009` demands a timeout on
every potentially blocking syscall, and `L2-CTL-012` wants a periodic liveness
signal. A timed condition wait is the obvious reach for both — a handler waiting
for work with a deadline, a liveness thread ticking on a schedule.

**What to do instead.**

| Need | Correct mechanism |
|---|---|
| Socket read/write deadline (`L2-SEC-009`) | `SO_RCVTIMEO` / `SO_SNDTIMEO` on the descriptor, or `poll(2)` with a timeout before each operation. The timeout belongs on the syscall it bounds. |
| Accept loop that must notice shutdown | `poll(2)` on the listening descriptor with a timeout, or a self-pipe made readable by `shutdown()` |
| Periodic liveness tick (`L2-CTL-012`) | A dedicated thread that `nanosleep`s, holding no mutex |
| Handler waiting for a free slot | Do not wait. Saturation returns `503` (ADR-0013) |

Note the pattern: in every case the timeout attaches to the thing that can
block, not to a condition variable guarding shared state. That is a better
design independent of ThreadSanitizer — a socket deadline enforced by a condvar
is a deadline on the *wait*, not on the *syscall*, which is not what
`L2-SEC-009` asks for.

**Mechanism.** `scripts/assert-no-timed-condwait.sh` fails the build if
`wait_for` or `wait_until` appears in `src/` or `include/`. Negative-tested.
Wired into `check-ci` and the pre-commit hook. If a future need genuinely
requires one, the gate is the place to record why — deleting it is a decision
with a diff, which is the point.

### 1.2 No store call with the manager mutex held

**What happened.** `submit()` held the manager mutex across
`store.record_intent()`. A durable write blocks on `busy_timeout` — five
seconds — whenever a worker holds the database write lock, and that mutex is
what every worker takes to pick up its next job. One badly timed submit could
stall the whole pool for five seconds.

**Why C5 walks into it.** Route handlers are the new callers of `JobManager`,
and C5 will want manager methods that do not exist yet: list jobs, fetch one
job's detail, report counts for a dashboard. Every one of those is a *read from
the store*, and the natural implementation — take the manager mutex, query the
store, return — reintroduces the defect on the read path. Worse than the write
path, because a dashboard polling status every second would degrade throughput
continuously rather than occasionally.

**The invariant.** *Never call the store, or take `store_mutex`, while holding
the manager mutex.* The permitted nesting is the other way round: `store_mutex`
may be held while taking the manager mutex, which is what `retry()` does when it
probes for a free id against both the durable record and the live maps.

**Mechanism.** A debug-build assertion, not a comment. `Impl` records the thread
id that currently holds the manager mutex; the accessor that hands out the
store asserts the calling thread is not that thread. Compiled in for the default
and sanitizer tiers, compiled out for release. The assertion is negative-tested
by a test that deliberately violates the order and expects the abort — the same
technique the gate scripts use.

This is worth the machinery because the failure is silent. Nothing crashes,
nothing races, no test fails; throughput just quietly degrades under a load
pattern that a unit test does not produce.

---

## 2. What gets built

Four pieces, in dependency order.

**2.1 The listening socket.** `socket`/`bind`/`listen` on the configured bind
address and port, defaulting to loopback (`L2-CTL-001`; the default is the whole
of the access control at v1.0.0 and `L2-CTL-016` forbids in-process TLS).
`SO_REUSEADDR` so a restart does not wait out `TIME_WAIT`. `O_CLOEXEC` on every
descriptor.

**2.2 The accept loop and handler pool** (ADR-0013). One thread accepts and
dispatches; `N` handlers serve. Saturation replies `503` and closes. Shutdown
must be prompt and clean — the accept loop wakes on a self-pipe rather than
waiting out a poll timeout, and in-flight handlers finish their current request.
This mirrors `JobManager::shutdown`, deliberately.

**2.3 Per-connection I/O with timeouts** (`L2-SEC-009`). Receive and send
deadlines on each accepted descriptor. A read that times out fails that
connection and nothing else. The declared `Content-Length` is read exactly;
bytes beyond it are a `400` — no pipelining, no smuggled second request — and
the body is capped by `http.max_body_bytes`, already in the configuration.

**2.4 Routing and handlers** (`L2-CTL-005`, `L2-CTL-014`). A route table mapping
method and path to a handler; unknown route `404`, wrong method on a known route
`405` with `Allow`, malformed JSON `400`, each with a JSON error body.
**Handlers stay pure functions of request and manager view** so the whole route
matrix is unit-testable without opening a socket — which is `L2-CTL-014` and is
also what keeps the hostile battery cheap to extend.

`CommandResult` already maps onto status codes without parsing prose, which is
why it was made a typed enum in C4: `Ok` → 200/202, `UnknownJob` → 404,
`InvalidState` → 409, `NotRunning` → 503, `StoreError` → 500.

---

## 3. Verification

**The hostile battery runs first**, then the same server instance completes a
real job. That ordering is the point: it proves the server is not merely
rejecting bad input but is still *working* afterwards.

| Case | Expected |
|---|---|
| Garbage bytes | `400`, connection closed, service alive |
| Head larger than the cap | `431` |
| `Content-Length` of a gigabyte | `413`, without reading a gigabyte |
| `Transfer-Encoding: chunked` | `400` (`L2-CTL-002` forbids chunked) |
| Trailing bytes past `Content-Length` | `400` |
| Unknown route / bad method / bad JSON | `404` / `405` + `Allow` / `400` |

**Concurrency tests, latch-based as in C4:**

1. A client that connects and never writes is disconnected by the read timeout,
   and other clients are served throughout — `L2-SEC-009` and `L2-SEC-010`
   together, and the direct refutation of serial-accept.
2. `N+1` simultaneous connections against `N` handlers: the extra gets `503`,
   not a hang, and no thread is leaked.
3. Shutdown while a handler is held mid-request: the request completes, the
   listener stops accepting, every thread joins.
4. A handler blocked in the store does not prevent other connections being
   served — the ADR-0013 argument against the event loop, asserted rather than
   claimed.

**All of it green under ThreadSanitizer**, which is now meaningful: C4 proved
the tier catches a real race, having first caught a negative test that silently
tested nothing.

---

## 4. Sequence

1. The two mechanisms in §1 — the gate and the assertion — **before** the server
   exists. They are cheap now and awkward to retrofit.
2. Listening socket and its configuration.
3. Accept loop and handler pool; shutdown; the concurrency tests.
4. Per-connection timeouts; the stalled-client test.
5. Routing and handlers; the hostile battery.
6. Trace matrix, CHANGELOG, ROADMAP, merge.

Step 1 first for the same reason C1 vendored SQLite before using it: the
constraint is worth more installed than remembered.

---

## 5. Deliberately not in C5

The daemon entry point (`main`, signal handling, the singleton lock of
`L2-CTL-008`, service-manager readiness of `L2-CTL-011/012`) is **C6**. C5
delivers a server that a test can start and stop in-process. Resisting the urge
to write `main` here is what keeps the hostile battery running in the test
harness rather than against a spawned process.
