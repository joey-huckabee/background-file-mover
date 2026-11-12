# Increment 132: read-only admin retention view

The user authorized "the retention view" on 2026-11-11 after
[increment131](RUST-INCREMENT-131.md). This slice exposes the existing
reservation-ledger reads to the admin session and adds a Retention view to the
dashboard. No action, dependency, filesystem probe or real state.

## Implemented boundary

- **`GET /api/v2/retention`** and **`GET /api/v2/jobs/{id}/retention`** on the
  admin listener return exactly the operator `RetentionResponse` envelope from
  the existing `retention_response` through the bounded status thread. The global
  view includes the cached source-space observation; no read starts a probe.
- Same read authorization as other admin GETs: session first (401), then marked
  reads need CSRF and matching optional Origin/Fetch-Metadata (403). No query
  string is accepted (404). Non-canonical IDs are 400 `invalid_job_id`; unknown
  or cleared jobs are 404. Resume and reset-missing stay trusted-local only (404).
- **Retention view** (tab beside Job history): source and destination reserved
  bytes, retained/committed jobs, confirmed and source claims, unmeasured files,
  configured limits with meters, ledger headroom (with over-limit flag),
  destination attempts by phase, automatic reclamation, and the source free-space
  admission state and last cached observation. A note states these are ledger
  totals, not physical free space, and that unreceipted leftovers are not inventoried.
- **Per-job reservations** load on demand from the job detail panel.
- **Exact numbers.** u128 byte strings and u64 counts go through BigInt. Human
  units (KiB…EiB, two decimals) are computed in BigInt and rounded down, never
  overstated; the exact byte count is always shown. Meters use exact integer ratios.
- **Bounded reads.** One retention read in flight; a new read aborts the
  superseded one. Refresh refreshes the active view, one cycle at a time.

## Tests

- Admin unit: retention path matching.
- Real service over HTTPS: per-job retention equals the operator response
  exactly; global equals it except the cached sample age, which advances between
  reads; 404 for unknown jobs, 400 for non-canonical IDs, 405 for POST; query
  strings, resume and reset-missing are 404; both reads are 401 without a session
  and after global logout. The increment130 boundary test now expects 401 for
  both retention routes.
- Browser: `scripts/admin-ui/lossless-json.test.js` adds byte-formatting cases
  (0, 1023, 1024, 1.5 TiB, u64 max, u128 max) in the hygiene workflow.

## Not in this slice

Overview cards, page-local search/filters, all actions and confirmation previews,
and the UI trim/refinement pass.

## Validation status

PR30 CI run
[43152294937](https://github.com/joey-huckabee/background-file-mover/actions/runs/43152294937)
at `56b6ca1` passes both full modes on the first run: production **372 tests per
debug/release profile** and nfs-qualification **376/profile** (increment131's
371/375 plus the retention path unit test; the retention checks extend the
existing real-service history test). Independent review: no actionable findings.
Merged to main as `232c5cb`.
