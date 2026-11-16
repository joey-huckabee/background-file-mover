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
  100 ms socket timeouts for reading the request; strict JSON with
  `deny_unknown_fields`.

## Protocol (version 1)

1. **Status** `{"version":1,"command":"account-status","instance_id":ID}` ->
   `{"version":1,"instance_id":ID,"username":U,"active_revision":"N"}`.
   The CLI uses it as preflight (service running, instance unchanged, account
   active) before prompting.
2. **Replace** `{"version":1,"command":"password-replace","instance_id":ID,
   "base_revision":"N","verifier":PHC}`.
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
   - Activation: `Sessions::activate(record)` under the admission lock (no
     I/O or hashing there): every session and CSRF token is revoked and the
     generation advances before the reply; a login whose hashing began
     earlier cannot mint a session afterwards (existing ticket recheck).
3. **Replies** (exactly one; `outcome` field):
   - `activated` (`revision`): published and active; all sessions signed out.
   - `unchanged` (`code`: `revision_conflict`, `invalid_verifier`,
     `instance_changed`, `account_changed`, `refused`): nothing published or
     activated; the old password stays active.
   - `uncertain` (`code`: `publication_uncertain` or `activation_failed`):
     publication may have happened but activation did not; no automatic
     rollback or retry. The old password may still be active until restart;
     restart loads whatever was published. The CLI says so and points to
     status.

## CLI behavior

- Stopped service (instance free): today's offline flow, unchanged.
- Running service: preflight `account-status`, prompt, derive verifier, send
  `password-replace`, print the outcome. A lost reply or interrupt after sending
  reports "outcome uncertain; run --admin-account-status".
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
