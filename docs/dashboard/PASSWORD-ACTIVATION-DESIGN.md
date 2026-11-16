# Live admin password activation: IPC design (proposal)

Status: proposal for review before implementation (required by
[ADMIN-SESSION-DESIGN](ADMIN-SESSION-DESIGN.md) section 4). Today a password
change needs a stopped service ([increment 128](../RUST-INCREMENT-128.md)); the
running service loads the account once at startup
(`account_cli::load_record`) and `Sessions::activate` (increment 129) already
switches an in-memory record and revokes every session under the admission
lock. This proposal adds only the path from the host-local command to a
running service.

## Goals and non-goals

- `--admin-password-change CONFIG.json` works while the service runs, with the
  same prompts (no-echo, repeated entry) or explicit `--stdin` as today.
- The running service publishes the new record itself (it owns the account
  directory while running; no lock-free CLI write racing the daemon) and
  activates it before reporting success. A disk rename alone is never success.
- No HTTP route; no producer, private-operator or lifecycle-socket audience.
- Not in scope: username change, account initialization while running (still
  offline only), multiple accounts.

## Transport

- A dedicated Unix socket `account.sock` in the local state directory, created
  only when `admin_ingress` is configured: same custody checks as
  `control.sock` (socket type, mode 0600, single link, owner = state-directory
  owner, recreated only after its identity is checked), plus `SO_PEERCRED`: the
  peer uid must equal the service's effective uid.
- Served by its own thread (`mover-account`), one request at a time, so
  `--status`/`--stop` on `control.sock` stay responsive and account work never
  runs on the lifecycle thread or the async executor.
- Bounded frames: request at most 2048 bytes, reply at most 1024 bytes,
  strict JSON with `deny_unknown_fields`. Each connection has an **absolute
  deadline** of 1 s to deliver the whole request (per-read timeouts are taken
  from the remaining deadline, so trickling bytes cannot hold the thread), and
  reply writes have their own 1 s bound. A connection that misses either is
  closed with no effect if the request was incomplete.
- The account thread holds the instance guard (`Arc<InstanceGuard>`) and is
  joined before the service releases instance/epoch ownership. It stops
  accepting at the first stop request; a request already admitted finishes.
  A publication blocked in local storage at shutdown is waited for under the
  existing lifecycle rule (one original deadline, `ShutdownIncomplete` while it
  remains, ownership kept until the thread has actually exited).

## Protocol (version 1)

1. **Status** `{"version":1,"command":"account-status","instance_id":ID,
   "change_id":C?}` -> `{"version":1,"instance_id":ID,"username":U,
   "active_revision":"N","published_revision":"M"|null,"change":OUTCOME|null}`.
   - `published_revision` is read back from the account file on the account
     thread (custody-checked, under `account.lock`); `null` if it cannot be
     read safely. `M != N` means disk and memory differ (see Reconciliation).
   - With a `change_id`, `change` is the service's retained record of that
     change: `{"outcome":O,"revision":"R"|null,"settled":B|null}` where
     `outcome` is `activated` (R = the revision it installed), `unchanged` or
     `uncertain`. The last 16 changes are retained in memory and cleared by
     restart, so `change` = `null` means **not retained** (evicted, restarted,
     or never received), never proof that it was not received.
   - For an `activated` change the reply adds `"standing"`, derived from the
     active revision first and the published read-back second:
     `active` (active = R and published = R), `superseded` (active > R: a later
     change is active), or `unverified` (active = R but the published record is
     unreadable or differs, e.g. a later change was published but not
     activated). `unverified` never says the password is gone: memory still
     uses R.
   - The CLI uses status as preflight (service running, instance unchanged,
     consistent account) before prompting, and to resolve a lost reply.
2. **Replace** `{"version":1,"command":"password-replace","instance_id":ID,
   "change_id":C,"base_revision":"N","verifier":PHC}`. `change_id` is 32
   random bytes (hex) chosen by the CLI. A `change_id` still in the retained
   history is refused. After eviction or restart an exact old request is
   still refused by the base-revision check: its `base_revision` is no longer
   the active revision once it (or anything later) was applied, so a resend
   can never apply a change twice.
   - The CLI derives the verifier itself (`Verifier::create`, the fixed
     Argon2id profile m=19456,t=2,p=1, 16-byte salt, 32-byte tag). **The
     password never leaves the CLI process**; only the verifier crosses the
     socket. Hashing cost stays out of the service.
   - The service checks, in order, refusing with no effect: instance id;
     `base_revision` equals the active revision (else `revision_conflict`);
     `Verifier::from_encoded` (exact profile, canonical encoding, bounded; a
     weaker or malformed verifier is refused); revision overflow.
   - Publication (on the account thread, never under the session lock): open
     the account directory with the startup custody/exclusion checks and its
     persistent `account.lock`; read the record and require it to equal the
     active one (same principal, username, revision, verifier); build
     `revision + 1` with the same principal and username; publish with the
     existing exclusive atomic replacement and file/parent sync; release.
   - Activation: a new **serialized activation**, modelled on
     `logout_all_serialized`: under the session state lock (no I/O or
     hashing there) recheck the active record is still the base, install the
     new record, revoke every session and CSRF token and advance the
     generation, so no later login, read or action can use old authority; then
     wait for the admission write guard, i.e. until every action admitted
     before the revocation has finished, bounded by the existing logout settle
     time. Login tickets captured before the revocation fail their
     revision/generation recheck before minting (existing behavior, now
     tested for this path).
   - Success is acknowledged only after that wait. If the bound elapses the
     new password is still active and every session revoked, and the reply is
     `activated` with `"settled":false` ("earlier admitted actions are still
     finishing"), never a plain success.
3. **Replies** (exactly one; `outcome` field):
   - `activated` (`revision`, `settled`): published and active; all
     sessions signed out; `settled` says whether earlier admitted actions had
     finished.
   - `unchanged` (`code`: `revision_conflict`, `invalid_verifier`,
     `instance_changed`, `account_changed`, `refused`): nothing published or
     activated; the old password stays active.
   - `uncertain` (`code`: `publication_uncertain` or `activation_failed`):
     publication may have happened but activation did not; no automatic
     rollback or retry. The old password may still be active until restart;
     restart loads whatever was published. The CLI says so and points to
     status.

## Reconciliation

| Status after an uncertain or lost reply | Meaning | Guidance |
| --- | --- | --- |
| `change` = `activated`, `standing` = `active` | Your password is the active one | Done; sign in with the new password. If `settled` is false, earlier admitted actions were still finishing when it was acknowledged |
| `change` = `activated`, `standing` = `superseded` | A later change is active | Your password is no longer active; sign in with the latest password or change it again |
| `change` = `activated`, `standing` = `unverified` | Your password is still active in the running service, but the published record is unreadable or differs | Sign-in works with your password now; a restart would load the published record. Inspect `published_revision`: if higher, a later change was published but not activated (see the next row) |
| `change` = `unchanged` | Your change had no effect | It does not say which password is active now (another change may have happened); compare `active_revision` with your base: equal means the password you started from is still active |
| `change` = `uncertain`, or `published_revision` != `active_revision` | Disk and memory may differ | Do not retry (a new change is refused while they differ); restart the service: it loads the published record and ends all sessions; then check which password works |
| `change` = `null` (not retained), `active_revision` above your base | Applied by you or by someone else; the record is no longer retained | Not attributable: sign in to check, or change the password again |
| `change` = `null` (not retained), `active_revision` equal to your base | Not applied (if it had been, the revision would have advanced) | Nothing changed; retry |

A new `password-replace` is refused (`account_changed`) while the published and
active revisions differ, so a mismatch is never silently overwritten.

## CLI behavior

- Stopped service (instance free): today's offline flow, unchanged.
- Running service: preflight `account-status` (refused if published and
  active differ), prompt, derive verifier, send `password-replace`, print the
  outcome. A lost reply or interrupt after sending queries status with the
  same `change_id` once; if that fails too it prints the change id and
  "outcome uncertain; run --admin-account-status --change-id ID".
- `--admin-account-status` while running uses `account-status` (active
  revision); offline it reads the file as today.
- Owner unavailable or shutting down: refused ("service is stopping; retry
  after it stops"), never a lock-free file write.

## Failure and concurrency notes

- Two concurrent changes: serialized by the account thread; the second sees a
  revision conflict.
- A change racing logout or another activation: `Sessions` serializes; the
  base revision check prevents silently replacing a newer password.
- Shutdown: the account thread stops accepting on stop; a request admitted
  before stop completes or reports `uncertain`. Restart always loads the
  published record and starts with no sessions.
- Diagnostics never include passwords or verifiers.

## Proof (maps to ADMIN-SESSION-DESIGN A10-A11, A14, A16)

Additional cases from review:
- Serialized activation with an admitted action blocked in its storage
  decision: activation revokes immediately (new requests refused), the reply
  waits for the action, `settled` reflects whether it finished within the
  bound.
- A login whose hashing started before activation cannot mint a session after
  it.
- Trickled request bytes are cut off at the absolute deadline; the account
  thread then serves the next request.
- Post-rename / post-sync publication failure (existing account-file fault
  controls): reply `uncertain`; status shows the published and active
  revisions; a further replace is refused until restart.
- Lost reply: the reply is dropped after activation; status with the change id
  reports `activated` and `standing` `active`. Concurrent changes: the second gets
  `revision_conflict`. A repeated change id is refused while retained.
- Superseded: change A then change B; status for A reports `activated`,
  `superseded`; status for B `active`.
- Unverified, unreadable: after A activates, the published record cannot be
  read (account file custody fault): status for A reports `unverified` with
  `published_revision` null, never `superseded`.
- Unverified, divergence: after A activates R, B publishes R+1 but activation
  fails (`uncertain`): status for A reports `unverified` with
  `published_revision` R+1 and `active_revision` R.
- Eviction: after 16 newer changes, A's id reports `null`; resending A's exact
  request is refused by the base-revision check (no second application).
- Restart: retained history is empty; an exact old request is refused the
  same way.

- Unit: request/reply bounds and decoding; base-revision conflict; weak and
  non-canonical verifiers refused; activation revokes sessions (existing).
- Real service over HTTPS: sign in, change the password through the CLI while
  running, the old session is refused (401), the old password is refused, the
  new password signs in, active revision advanced; status reports it.
- Refusals: stale base revision, wrong instance id, oversize frame, a socket of
  wrong mode/owner, service without `admin_ingress` (no socket).
- Restart after a live change loads the new record.
- Publication failure before rename keeps the old record active (fault test
  where feasible); uncertain outcomes are reported as such.
