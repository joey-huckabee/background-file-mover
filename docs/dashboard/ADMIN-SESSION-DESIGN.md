# Admin HTTPS, account custody and sessions

Implementation follow-up: the approved password primitive is implemented in
[increment127](../RUST-INCREMENT-127.md). Guarded offline account commands follow
in [increment128](../RUST-INCREMENT-128.md), with exact current validation status
and [user instructions](../ADMIN-ACCOUNT-SETUP.md). These do not activate sessions,
live account replacement, an admin listener or browser access. The design
checkpoint below governs the remaining integration; use the increments for
actual implementation and qualification claims.

Step 2 design, 2026-11-10. The user requests starting the next dashboard step
after the [field map](BACKEND-MAP.md). This document makes that implementation
concrete. It adds no runtime, dependency, listener, real account or operational
state. Proposed configuration/CLI spelling below is not an existing interface.

The [frozen API closeout](../api/API-CONTRACT-CLOSEOUT.md) and
[access contract](../api/ACCESS-BOUNDARY.candidate.md) govern product behavior.
No proxy, frontend library, account service or browser build tool is introduced.
Existing producer mTLS and private operator/control interfaces stay distinct.

## 1. Small implementation boundaries

1. Approve the password-library addition below, audit the exact resolved graph,
   then qualify the verifier and entropy/session primitives on both SLES modes.
   No network admin exposure in that first implementation slice.
2. Add guarded host-local provisioning/password replacement and bounded
   in-memory session state, including revocation/admission races. New files and
   control names require the same pre-stat mount and custody exclusions as TLS.
3. Add the separate native admin HTTPS listener, three session routes and
   embedded sign-in/shell assets; prove audience isolation using actual clients.
4. Connect read-only job/history/retention in the subsequent read increment.
   Do not expose unimplemented action buttons or invent empty successful reads.

Each slice requires independent review, applicable focused tests and both full
SLES gate modes on its final affected Rust inputs. No claim of completion from
unit tests alone. This design is not a deployment or full release approval.

## 2. Native admin audience

Propose an optional `admin_ingress` configuration with explicit bind address,
HTTPS authority/origin, DER server chain/key/trust paths and bounded inactivity
timeout (default 1800 seconds). A separate TCP listener/port terminates TLS in
the same executable. It uses server-authenticated HTTPS and account/password
authentication; producer client-certificate approval never creates an admin
identity. Requiring producer mTLS for browser sign-in is not part of this design.

Admin ingress has no plaintext mode or TLS-error fallback. Disabling this
optional listener disables remote dashboard access; the separately configured
producer's existing loopback HTTP option remains available. No new unauthenticated
TCP operator path. Admin startup refuses an invalid/unprovisioned account rather
than exposing a setup form or default password.

| Audience | Allowed in first network slice | Must refuse |
|---|---|---|
| Admin HTTPS | Fixed embedded dashboard assets; login POST, session GET, logout POST | Producer submission, private specialized resume/reset, stop/status/reload IPC; job reads/actions until their handlers are implemented |
| Producer HTTPS / protected producer Unix | Existing producer submission only | Admin assets/session/login/logout/job reads/actions |
| Private operator Unix | Existing explicitly permitted local operator reads/commands | New browser sessions, account provisioning and producer submission |
| Host-local account command | Provision/replace account through guarded local custody | Remote account reset/setup or any transfer/file action |

Use an explicit `Audience::Admin` equivalent, not a permissive prototype audience
or a producer variant with an exception. Authority and allowed origin come from
validated startup configuration, not forwarded headers. Reject asserted producer,
proxy and client-identity headers. Login/mutations require exact Origin; GET
activity follows the browser-compatible frozen rule. No credentialed CORS.

Embedded HTML/CSS/JS/inline original SVG remain offline. Use fixed asset paths,
strict MIME types, safe DOM text insertion, no directory traversal or runtime
asset directory. Treat these as document delivery, not new privileged API
operations. Login/session responses and authenticated views use no-store;
never put a password, session, CSRF or confirmation secret in a URL/log.

### Resource and ownership boundary

Keep the existing maximum six producer/eight total connections. Admit admin
connections within the non-producer budget, capped at one at a time in this
initial slice, leaving room for a private operator connection. Acquire permits
before TLS work. This is a bounded admission proposal to measure, not an already
implemented change or a reserved-CPU claim. Overload must refuse promptly rather
than build another queue. All listeners participate in one global budget.

Reuse fixed-budget TLS executor machinery and accepted-time handshake deadlines;
do not add an executor per listener or block the accept/control loop. If the TLS
pool is saturated, close/refuse the new connection under the existing bounded
wire rules. Prove operator/control responsiveness separately; do not promise
admin throughput under a full producer pool. Document the selected initial
admin concurrency when presenting actual evidence.

One separate password-verifier worker, one admitted request and no backlog of
password bodies. It retains instance/lifetime ownership until actual thread exit.
Timeout/cancellation cannot pretend synchronous hashing has stopped. A timed-out
request cannot later mint a session; its memory/permit remains owned until actual
completion. Partial startup, worker panic, stop and failed dispatch must drain or
refuse safely without releasing ownership early. Status/stop stay independent.

Validate account/control/TLS paths against current and all retained custody roots
and local mount metadata before named I/O. Register the lifetime epoch and keep
control available before blocking credential work. Reserve every new control
name consistently in InstanceGuard and client/server validation. Admin TLS uses
the already reviewed DER/PKCS8 chain/SAN/usage/key rules and provider; no system
OpenSSL dependency. Initial admin certificate changes use stop/restart. Existing
producer live reload must not falsely claim to reload the admin policy.

## 3. Password-library proposal and proof

Recommend the RustCrypto `argon2` crate pinned to **0.5.3**, defaults disabled,
features `std,zeroize`, using Argon2id v19. This is a specific candidate for
review/qualification, not a claim that it is the latest release. Published
[manifest](https://docs.rs/crate/argon2/0.5.3/source/Cargo.toml) declares pure Rust,
MIT OR Apache-2.0 and Rust 1.65 minimum. None of those facts proves target safety.

Candidate profile: m=19456 KiB, t=2, p=1, random 16-byte salt and 32-byte output.
The memory/iteration floor follows the
[OWASP recommendation](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html).
[RFC 9106](https://www.rfc-editor.org/rfc/rfc9106.html) supplies algorithm/test-vector
authority, with different recommended operating profiles; do not call the OWASP
floor the RFC's recommended profile. Measure actual target time, memory and
control responsiveness before accepting this cost. Do not automatically lower
cost or calibrate it differently per machine to pass a deadline.

[Exact candidate package metadata](ADMIN-AUTH-DEPENDENCIES.candidate.json)
records registry checksums/licenses for five expected new packages: argon2
0.5.3, blake2 0.10.6, password-hash 0.5.0, base64ct 1.8.3 and rand_core 0.6.4.
The latter is pulled by password-hash's default feature even though argon2's
`rand` feature is disabled; do not claim a four-package addition. Reuse existing
locked digest/cpufeatures/subtle/zeroize dependencies. Direct use of existing
subtle and zeroize may add dependency edges, but not new package versions.
Use the existing Rustls provider's secure_random for application salt/session/CSRF
entropy. The selected feature chain also enables `argon2/std -> password-hash/std
-> rand_core/std -> getrandom` and `getrandom/std`: the locked getrandom 0.2.17
is expected to satisfy that edge. This is additional selected dependency/feature
surface to audit, even though getrandom is not a sixth new package. Do not claim
the graph excludes an OS-randomness dependency. The primary
[password-hash manifest](https://raw.githubusercontent.com/RustCrypto/traits/password-hash-v0.5.0/password-hash/Cargo.toml)
and [rand_core manifest](https://docs.rs/crate/rand_core/0.6.4/source/Cargo.toml)
establish that chain.

No manifests/lockfiles/pins have changed. Approval of this addition is required
before resolution/build integration. Then freeze the complete selected graph,
checksum/source/license/advisory review and gate pins. Available primary-source
research did not establish a complete advisory verdict; no advisory-clear claim
is made. No package/compiler/OpenSSL installation is required on target: approved
Rust dependencies compile into the executable and go in source/license/offline
build inputs. This does not make the executable FIPS qualified.

Verify through the library API, including its constant-time verifier comparison;
do not implement Argon2 or a fast SHA-256 password scheme. Accept only the exact
supported algorithm/version/cost/salt/tag shape in the credential record. Bound
and validate parameters before invoking the library so a modified PHC record
cannot request enormous allocation or work. Future cost upgrades need explicit
compatibility/qualification, not opportunistic login-time rewrites.

## 4. Host-local account record

One stable admin principal. Proposed record: strict version, existing mover
instance identity, stable random account-principal ID, exact username, monotonic
credential revision and bounded PHC verifier. No plaintext password, session,
CSRF, recording IDs or file inventory. Password replacement preserves the
principal so existing per-job audit/replay identity does not change with sessions.

Use a dedicated mover-owned 0700 local directory, single-link 0600 regular file,
no symlink/unsafe ancestor, NFS, root overlap or arbitrary writable path. Reuse
the reviewed credential-reader checks with an account-specific small byte bound;
do not equate atime changes with content mutation. Foreign instance, unsupported
record, revision overflow or invalid verifier refuses. Missing account prevents
admin exposure; no automatic account initialization or copied-state adoption.

Proposed CLI concepts: `--admin-account-init CONFIG.json` (must not overwrite an
account) and `--admin-password-change CONFIG.json` (existing account only). Final
names/transport receive implementation review. Both require already supported,
initialized local state/instance ownership; neither initializes/migrates a
database or touches source/destination payloads. Accept exact UTF-8 username
1–128 bytes and password 1–4096 bytes without trimming/normalization. No additional
password-complexity rule. Default input is a no-echo local prompt with repeated
new-password entry. Never use password argv or an environment variable. Any
automation stdin mode must be explicit, bounded and documented for secret-safe use.

When stopped, hold the instance guard/epoch through account I/O and actual worker
exit. When running, the host-local command uses a dedicated protected account
control path whose peer/account custody is checked; it must not race a lock-free
write against the daemon or inherit the producer/private-operator audience.
That IPC design must be reviewed before activation. No HTTP password-change route.

Prepare and validate a complete record before exclusive atomic publication with
file/parent sync. Initial creation is no-clobber. Replacement is serialized with
other account changes and cannot silently reset the stable principal/revision.
Before publication failure preserves old credentials. After uncertain publication
or sync, report outcome unknown and require inspection; do not automatically
restore or retry. Never log verifier/password/secret payloads.

For a running daemon, local publication and activation are an acknowledged
protocol. Activate the verified revision under the same admission/revocation lock
used by sessions; revoke all old sessions before success. No I/O/hash work under
that lock. A successful disk rename alone is not successful live activation.
If persistence succeeds but activation is uncertain, the command must report
uncertainty. Restart loads the published record and invalidates all sessions;
the operator must not infer which password is active from an unsuccessful reply.

## 5. Session implementation invariants

Use at least 32 OS-random bytes each for opaque session and CSRF values, bounded
canonical encoding and comparison via the reviewed constant-time primitive.
Keep sessions only in memory; at most 64, no silent eviction. OS-entropy failure
issues no token. Preserve approved cookie `__Host-mover_admin`, Secure, HttpOnly,
SameSite=Strict, Path=/, no Domain or persistent expiry. Successful login returns
200 `authenticated:true`, cookie and `Mover-CSRF-Token`; session GET returns the
same contract token header after authorization. Incorrect credentials return 401
with exactly `Invalid username or password.` No username-enumeration error.

Serialize verification through one slot. Before hashing, enforce the existing
five-attempt rolling 60-second limit per instance, independent of username;
excess is 429 with Retry-After:60. Full verification/session capacity returns
503 service_busy. Invalid framing/origin/media type does not consume a password
verification; admitted incorrect usernames still execute equivalent bounded
verification work against a valid dummy/real verifier. No permanent account lock.
Invalid input never causes unbounded body allocation or credential logging.

Associate every session with current credential revision, revocation generation,
stable account principal and monotonic last-authorized activity. Recheck revision,
generation, expiry, capacity and request liveness after hash completion and before
session insertion under the admission lock. A login started before password
activation/global logout cannot mint an old-authority session afterward. Duplicate
tokens regenerate with a bound or fail; never overwrite another session.

Logout under that lock revokes all sessions/CSRF and advances the generation
before 204 and cookie clearing. Session authorization and future action admission
use the same serialization discipline. If authorization wins before revocation,
already-authorized output cannot be recalled; subsequent admission must fail.
Already-admitted transfers continue independently. On restart the map is empty;
no durable session recovery. Use a nonwrapping generation/refuse overflow.

Inactivity uses the monotonic clock (default 30 minutes). Background GET polling,
failed login/actions and exact transport replay do not renew. Only successful
authorized new activity or a valid deliberate-read marker renews. Do not require
Origin on ordinary same-origin GET; marked reads require session-bound CSRF and
configured target authority, optional Origin must match and supplied Sec-Fetch-Site
must be same-origin. POST login/mutations require strict Origin. Preserve header
duplicate rejection, byte limits and frozen error/denial precedence.

Zeroize owned password buffers using the library where feasible; document copies
made by HTTP parsing/allocators and do not claim guaranteed erasure. No raw secret
Debug formatting or fixture-secret logs. A 401 discards client CSRF/in-flight
intent and returns to sign-in; it does not cancel jobs.

## 6. Finite proof matrix before exposure

Use disposable test credentials/local state only. The first dependency proof
needs library known answers and measured SLES execution; later rows require the
actual service/CLI, not a synthetic replacement endpoint.

| Cases | Required evidence |
|---|---|
| A01–03 | Argon2id published known answer; valid/invalid exact UTF-8 password including bounds; independent salt creates distinct verifier |
| A04–05 | Reject malformed/huge PHC cost before hashing; fail entropy without issuing session/credential |
| A06–07 | Target single-slot time/memory observations and stop/status responsiveness; timeout retains ownership until real verifier exit |
| A08–09 | Local init no-clobber; foreign/unsafe/mounted account/control paths refuse before I/O/payload effects |
| A10–11 | Durable replacement prepublication failure preserves old; publication/activation uncertainty never claims automatic rollback or success |
| A12–13 | Correct and wrong credentials over actual admin HTTPS; strict cookie, no-store, CSRF and exact approved status/message |
| A14–15 | Logout across two browsers/sessions; password-change and restart invalidate every old session while admitted transfer data/results remain intact |
| A16–17 | Queued login vs logout/password revision; session read vs revocation races use explicit barriers and prove ordering |
| A18–19 | Monotonic expiry despite wall-clock change; repeated background polling does not extend inactivity, deliberate navigation can |
| A20–21 | Five attempts/60 seconds and slot contention; 64-session limit without silent eviction; bounded request/response and secret-free diagnostics |
| A22–23 | Cross-origin/null/missing/duplicate POST Origin, wrong Host/CSRF and GET browser omission; no CORS or producer/private-operator privilege crossover |
| A24–25 | TLS slow/saturated peers with actual private control response; startup failure/shutdown/panic retain lifetime ownership through actual exits |
| A26–27 | Embedded offline sign-in/shell, MIME/CSP/text safety and keyboard states; unimplemented job/action routes never return fake successful data |

Keep exact input hashes, both production/qualification debug/release results,
native/ELF audits, actual client/CLI transcripts without secrets, cleanup exits
and a bounded evaluation report. Container SLES userspace evidence does not
prove physical kernel/NFS/systemd/FIPS/deployment behavior. All eight FR gates
remain open. No live account/state operation is authorized by this design.
