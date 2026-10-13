# Dashboard and status design notes

Use these requirements and review findings when designing the Rust operator
surface. They are distilled from C7 at
`af7af20b51f54f98ce5f6270d1d779fecf0c28cb`, whose original source is retained
under `archive/c7-dashboard`. No C++ implementation is adopted into the Rust tree.
The [branch review](BRANCH-REVIEW.md) records its source inventory and provenance.

## Behaviors to retain

- Serve a self-contained offline dashboard from the executable. Require no CDN,
  remotely fetched script/style, runtime asset directory or frontend service.
- Specify HTML UTF-8 explicitly. Treat filenames, paths and error messages as
  hostile text; insert them with textContent/createTextNode, never HTML-parsing
  sinks or evaluated code. Preserve L2-DASH-001 through L2-DASH-003 obligations.
- Show coordinator state, runnable/active work, state totals and a recent-job
  view. Present unreachable, unavailable and malformed-response states clearly.
- Bound the API response independently of caller-selected sizes. Include explicit
  limit/pagination information rather than implying a small view is the whole backlog.
- Keep status reads outside scheduler/manager coordination locks, and isolate
  observation failures from authoritative job behavior.
- Keep the dashboard available when the manager is unavailable, so operators can
  see the incident. Return unavailable status rather than a misleading empty backlog.

## Correct the limitations rather than copying them

The C7 router caps `/api/status` at 50 jobs, but its manager reads all state
batches, merges and sorts all jobs before truncating. Bound database queries and
intermediate allocations, not only the serialized response. Define pagination,
ordering and consistency with the single-owner scheduler/local database design.

C7 encodes truncated as returned size >= limit. Exactly 50 available jobs can
therefore look truncated even when no job was omitted. Derive truncation from
limit-plus-one queries or suitable count evidence. Test below, at and above the cap.

C7 starts a request every two seconds without a request timeout or in-flight
guard. Bound pending requests, use a deadline and define refresh/error behavior
so slow/unavailable servers cannot accumulate overlapping requests or overwrite
newer state with late responses. The two-second cadence and 50-row cap are
reference choices, not fixed requirements for Rust.

The snapshot combines scheduler counts and later database reads. Define how the
Rust API describes consistency rather than promising an atomic cross-layer view.
Lazy construction avoids unnecessary pre-main initialization, but Rust should
choose straightforward embedded assets without inheriting C++ initialization machinery.

## Acceptance scenarios for the Rust implementation

- Hostile names/errors containing markup, quotes and control characters render
  as text and cannot execute script. Check the served artifact as well as source.
- The dashboard works on a disconnected network with the intended content type;
  accidental external assets or dangerous DOM sinks fail relevant checks.
- Root/status methods, error responses and HEAD wire behavior obey the API
  contract. Router-only tests do not establish correct body suppression on the wire.
- An unavailable manager does not hide the dashboard; status reports the failure.
- Status limits and truncation are correct for zero, below-limit, exactly-limit
  and over-limit rows. A large backlog does not drive query memory without bound.
- Slow, failed or malformed refresh responses preserve a clear operator state;
  only bounded requests remain in flight and stale responses do not win.
- Backend queries do not hold scheduler locks or delay transfer/claim progress.

Expand the operator model for the new protocol: distinguish Accepted and Claimed,
transfer phase, desired pause/cancel intent, operational blocked/reconcile state,
recording-set commitment and pending source cleanup. Separate liveness, readiness,
storage health and progress. Choose controls, diagnostics and metrics after those
contracts are settled; the old dashboard is a reference, not the new API schema.
