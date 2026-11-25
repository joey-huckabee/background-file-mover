# Increment 172: configurable logging

Implementation PR [#115](https://github.com/joey-huckabee/background-file-mover/pull/115)
implements the [approved design](LOGGING-DESIGN.md): exact legacy output and no
logger resources when OFF; explicitly enabled, leveled journal and private
rotating-file sinks, bounded non-blocking queues, counted drops and one 250 ms
logging shutdown budget. No new dependencies. See [logging instructions](LOGGING.md)
and the [operator guide](RUST-OPERATOR-GUIDE.md#logging).

## Coordinator local checks

Reported 2026-11-25, WSL private namespace with gate SQLite flags. These are
local debug-build results, not SLES qualification. The coordinator pushed
`cargo fmt` commit `6a12634` on top of implementation `5241198`.

- API parallel run: reported 130/135 passing. The four investigated failures
  (three known InstanceGuard ownership races and sustained load under parallel
  load) all passed individually. This is not a clean full parallel-suite pass.
- TLS/admin: 32/32 passed.
- mover-fs: all passed except three known environment-dependent failures that
  fail identically on main.
- file-mover units: all passed except five known fixture-dependent reload tests.
- The coordinator reports Clippy clean after the byte-string fix and pushed
  follow-up `d9d269d`. This predates the review fixes below; their Rust execution
  remains for the coordinator.

## Coordinator local performance

Debug build, WSL ext4; OFF/info runs alternate within each comparison. Negative
slowdown means info was faster. Aggregates below are coordinator-reported;
individual delivery-pair timings and raw packs were not supplied here.

**Fixed-work delivery comparison (passes):** `logging_fixed_work_delivery_benchmark`,
eight jobs / eight MiB per run, ten alternating OFF/info pairs. Total elapsed
OFF **138.26 s**, info **136.08 s**. Paired slowdown median **−2.0%**, mean
**−1.5%**, standard deviation **3.2 percentage points**; upper 95% slowdown bound
about **+0.8%**. This comparison passes the approved 2% limit. It does not alone
establish overall performance acceptance, or qualify other hosts or SLES modes.

**Sustained-load regression comparison:** five OFF/info pairs of the existing
sender-load test, comparing `late_claim_seconds`:

| Pair | OFF (s) | Info (s) |
|---|---:|---:|
| 1 | 24.66 | 18.47 |
| 2 | 20.43 | 17.19 |
| 3 | 18.50 | 23.32 |
| 4 | 19.66 | 20.13 |
| 5 | 19.26 | 21.29 |

Reported paired slowdown median **+2.4%**, mean **−0.4%**. This timing is too
noisy to establish a 2% bound and is **inconclusive**. **Overall performance
acceptance is pending:** the approved design requires both comparisons to meet
the 2% bound. The coordinator will rerun more sustained-load pairs after the
operation/errno fix. Transfer correctness assertions were not relaxed.

## Remaining validation and limits

Debug-*logging-level* and saturated-sink performance runs were not done (the
runs above used debug *builds* with OFF/info levels). Both SLES gate modes,
actual systemd PRIORITY observation, independent review and further planned
performance instrumentation remain separate. No new Rust execution, fmt or
Clippy run was performed in the cloud worker; its portable checks are reported
with the revision. No release, operational deployment, production NFS or deletion
approval is implied.

## Review fixes

Enabled diagnostic events now carry the available validated native/worker
operation text (at most 240 printable ASCII characters) and optional numeric
errno. Raw error Display strings are excluded; persistence errors use safe typed
categories. Payload/reconciliation, claim, cleanup, source-space and retry sites
supply the metadata they hold. OFF retains each original print expression;
detail closures are not evaluated when OFF or below threshold. Periodic warning
summaries also report limiter contention, coalescing and eviction deltas.

New unit regressions target an enabled info payload-failure line containing the
operation and errno=28, invalid/secret diagnostics, lazy OFF/filter behavior and
all four loss summaries. These new Rust regressions have not run in the cloud.
