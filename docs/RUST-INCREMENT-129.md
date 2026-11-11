# Increment 129: bounded in-memory admin session core

The user authorized continuing the dashboard sequence on 2026-11-11, after the
account commands in [increment128](RUST-INCREMENT-128.md). This slice implements
step 2's remaining session state from the
[admin/session design](dashboard/ADMIN-SESSION-DESIGN.md). It adds no listener,
route, cookie, configuration, dependency, account file I/O or real state.

## Implemented boundary

`rust/crates/file-mover/src/session.rs` (`Sessions`):

- **One verifier slot.** Each admitted login runs the fixed Argon2id verifier
  on its own named thread. The slot stays held until that thread actually exits,
  including after a caller timeout or dropped future. A late result cannot mint:
  the login deadline is absolute and is rechecked under the minting lock after
  entropy, so slow entropy or lock waits cannot mint past it either.
  The thread is spawned under the admission lock so no second admission can slip
  between the slot check and handle registration. Hashing and entropy never run
  under the lock.
- **Equal work for wrong usernames.** Every admitted login runs the real verifier.
  The username is compared in constant time after it; both must match.
- **Rate limit.** At most five admitted attempts per rolling 60 seconds per
  instance, independent of username, checked before hashing.
- **Capacity.** At most 64 sessions. A full map refuses at admission and again
  at minting. Existing sessions are never evicted.
- **Authority recheck.** Admission captures credential revision and revocation
  generation. Minting rechecks both under the lock. A login that loses a race
  against logout or password activation returns `Superseded` and mints nothing.
- **Tokens.** 32-byte session and CSRF values from the existing TLS provider's
  secure random source, canonical lowercase hex, constant-time comparison and a
  full scan on lookup. Entropy failure issues nothing. Duplicates are redrawn
  up to four times, then refused.
- **Global revocation.** `logout_all` and `activate` clear every session and
  advance the generation. Generation exhaustion closes the manager instead of
  wrapping. `activate` accepts only a newer revision of the same instance,
  principal and username, already validated outside the lock.
- **Precedence.** Session authentication is checked before CSRF. An unknown,
  expired or revoked session is unauthenticated whatever CSRF value it carries.
- **Inactivity.** Monotonic `Instant`, default 1800 seconds. Only
  `Activity::Deliberate` renews; background polling does not. Activity never
  moves backwards.
- **Shutdown.** `shutdown` refuses further work, clears sessions and returns the
  verifier thread handle. The owner must join it before releasing instance
  ownership. As a fallback, dropping `Sessions` closes it and blocks until a
  running verifier actually exits; the thread is never detached.

`Record::verify` (crate-private) exposes verification to the session worker
without exposing verifier bytes.

## Deliberately not in this slice

- HTTP status, cookie and header mapping (`__Host-mover_admin`,
  `Mover-CSRF-Token`, 401/429/503 bodies). Outcomes are typed so the listener
  increment maps them to the frozen contract.
- The admin HTTPS listener, routes, Origin/Sec-Fetch checks and embedded assets.
- **Live password activation over IPC.** The in-memory `activate` primitive
  exists, but no running-daemon control path calls it. Password changes still
  require a stopped mover. Restart starts with an empty session map, which
  already invalidates every session. A reviewed account-control IPC remains future work.
- Daemon wiring: nothing constructs `Sessions` at startup yet.

## Tests (design rows A04-A07, A16-A21 at unit level)

Fifteen unit tests: exact-credential issue, wrong username/password and
non-canonical tokens; rolling rate limit; slot held until real worker exit;
timeout never mints; logout/activation during verification; revocation after
authorization; activation principal/revision rules; monotonic expiry with
background vs deliberate activity; 64-session cap without eviction; entropy
failure, token/CSRF collision and duplicate redraw; generation exhaustion;
minting past the deadline; authentication-before-CSRF precedence; drop waiting
for a running verifier; and canonical hex.

These are unit-level proofs on the session core. Rows that need actual HTTPS
clients, browsers or the running service (A12-A15, A22-A27) stay open for the
listener increment.

## Validation status

Focused native checks on the WSL test clone: `cargo fmt --check`, `cargo clippy
--all-targets -D warnings` and the 15 session tests pass. Independent review
found three P2 defects (post-deadline minting, CSRF-before-auth precedence,
detached verifier on drop); all three are fixed with regression tests. PR24 CI run
[43026367714](https://github.com/joey-huckabee/background-file-mover/actions/runs/43026367714)
at `3a6d526` passes both full modes: production **359 tests per debug/release
profile** and nfs-qualification **363/profile** (increment128's 344/348 plus the
15 session tests). Merged to main as `30808c2`. The reviewer's re-check of the
fixes found no actionable findings. No real credentials, state,
deployment, production NFS/deletion or release are involved. All eight FR gates
remain open.
