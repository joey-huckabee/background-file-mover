---
status: accepted
date: 2026-08-06
decision-makers: Joey
precedent: ADR-0012 (hand-rolled HTTP subset), ADR-0010 (SQLite for durable state)
constrains: C5 — REST control plane
---

# A bounded pool of connection handlers, not serial-accept and not an event loop

## Context and Problem Statement

C5 builds the socket server around the request-head parser ADR-0012 delivered.
The inherited design accepted one connection, served it to completion, closed
it, and looped. That is **serial-accept**, and the roadmap has carried it as an
open decision since triage because it cannot satisfy the requirements.

Two requirements govern this, and they are the whole of the problem:

> **L2-SEC-009** — Every potentially blocking system call on a managed file
> shall be subject to a configurable timeout.
>
> **L2-SEC-010** — A stalled or failed entry shall not block forward progress of
> other queued moves or of durable-state processing.

### Why serial-accept fails

One thread that accepts, reads, handles and replies means **one slow client is
a total outage of the control plane**. A client that opens a connection and
sends a single byte holds the only thread in `read()`. Nothing else is served:
not a status query, not a cancel, not the operator trying to work out why.

This needs no malice. A laptop that suspends mid-request, a reverse proxy that
dies, a monitoring probe that opens a socket and never writes — each produces
it. And the failure is invisible from inside the service: the process is
healthy, the queue is fine, the workers are idle, and every client hangs.

Note what C4 already fixed and what it did not. The worker pool means a stalled
*connection* no longer stalls file *movement* — moves continue on their own
threads. So the literal reading of `L2-SEC-010`, about queued moves, now holds
even with serial-accept. What does not hold is the ability to **observe or
control** the service while a connection is stalled, which is what the
requirement exists to protect. A control plane that cannot be reached during an
incident is not a control plane.

## Considered Options

* **A — serial-accept** (the inherited design)
* **B — single-threaded event loop** over `poll(2)` with non-blocking sockets
* **C — accept loop feeding a bounded pool of handler threads**
* **D — thread-per-connection, unbounded**

## Decision Outcome

**Chosen: option C.** An accept loop hands each accepted descriptor to a
bounded pool of handler threads. When every handler is busy the server replies
`503` and closes rather than queueing without limit.

### Why not the event loop (B)

This is the option worth arguing against, because it is otherwise attractive:
one thread, no locking between connections, timeouts fall out of the `poll`
budget for free.

It fails on **what a handler has to do**. A route handler calls into
`JobManager`, and those calls reach SQLite. A durable write blocks on
`busy_timeout` — five seconds by default — whenever another connection holds
the database write lock. In an event loop that is not one slow request; it is
**every** connection frozen for five seconds, because they all share the one
thread that is now parked inside `sqlite3_step`.

Making handlers non-blocking would mean posting every command to a worker and
resuming the connection on completion — a continuation for each route, and a
state machine per connection. That is a large amount of machinery to avoid
threads that C4 has already shown this project can run and verify under
ThreadSanitizer.

An event loop is the right answer when handlers are non-blocking. Ours are not,
and cannot cheaply be made so while the durable store is synchronous.

### Why not unbounded thread-per-connection (D)

It satisfies both requirements and is simpler than C by exactly one parameter.
It is rejected because the bound is the point: without it, the number of
threads is chosen by whoever is connecting. Ten thousand open sockets is ten
thousand stacks. The failure mode of D under load is process death; the failure
mode of C is `503`, which is a documented answer a client can act on.

### Consequences

**Good.**

* A stalled connection consumes one handler, not the service. With `N`
  handlers, `N` simultaneous stalls are needed to deny service, and each is
  bounded by its own timeouts.
* Handlers may block. They call `JobManager` directly, no continuations.
* `L2-SEC-009` is satisfied per syscall rather than per request, because each
  handler owns its descriptor and can set a receive and send timeout on it.
* The concurrency shape matches C4's, so the reasoning, the latch-based test
  technique and the TSan tier all transfer.

**Bad, and accepted.**

* Handler count is another thing to configure and get wrong. Mitigated by a
  documented default and validation, as `[jobs] workers` already has.
* Saturation returns `503`. That is a real behaviour a client must handle, and
  it must be documented in the CLI and API reference rather than discovered.
* Threads make the server testable only under TSan, which is slower than the
  default tier. This is already true of the manager.

**Explicitly out of scope.** Keep-alive. `L2-CTL-002` requires the connection
to close after each response, which caps the lifetime of a stalled connection
at one request and removes the hardest part of connection lifecycle management.
Do not add keep-alive without revisiting this ADR.

## Requirements this settles

`L2-SEC-009` (per-syscall timeouts, now expressible because a handler owns its
descriptor), `L2-SEC-010` (a stalled connection cannot block others), and the
concurrency half of `L2-CTL-001`. `L2-CTL-014` is unaffected and remains the
reason route handlers stay pure functions of request and manager view: the
concurrency model is deliberately outside them, so they are unit-testable
without a socket.
