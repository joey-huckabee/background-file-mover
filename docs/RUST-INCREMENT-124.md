# Live TLS policy reload

2026-11-09. The user authorizes live certificate reload after increment123/PR12.
Base main `847b5337c8a8aa0a10586fc44ed8d2073e90c8ec`; short-lived branch
`feature/live-tls-reload`. This delivers the bounded credential lifecycle part
of increment C; stronger cryptographic CPU isolation remains separate.

## Implementation

`--reload-tls CONFIG.json` sends a complete proposed configuration over a separate
service-UID-only `state/tls-reload.sock`. `--tls-status CONFIG.json` reads current
public policy identity and loader status. The endpoint is not a public REST route.
No new dependency, database schema or producer identity format is added.

Only HTTPS server certificate/key, server/client roots and approved client mappings
may change. The bind, authority, operator socket, generator, state, roots and all
other configuration stay fixed. New credential files must remain in the exact
credential parent directories validated at startup. This conservative boundary
avoids SQLite/NFS reads during reload and preserves exclusions for retained roots.
The existing safe credential reader and full certificate/key validation apply.
Invalid candidates preserve the active policy and established connections.

Policy activation, connection registration and each actual worker admission share
one brief in-memory lock. The worker revalidates the peer chain/date/usage before
admission. A queued request cannot keep stale authority; an already admitted
`process` invocation can finish. Source-space deferral resets admission, so a later
attempt needs a fresh generation check. UUID replay and custody remain unchanged.

Activation cancels old unadmitted handshakes, HTTP reads and queued reply waits.
Success waits for their connection tasks to exit, independently of stale Work
entries left in the queue. Already admitted work and its terminal reply may finish.
A second reload is refused while the loader is busy. Credential I/O stays off the
accept/status thread and outside the activation lock. Stop serializes with
activation under the existing first-stop lock and never resets its deadline.
Both IPC threads retain instance/lifetime ownership through their actual exit.

The private client pins socket/guard identity, peer PID/UID and PID:start, and
sends a mutating request once. A lost response is outcome unknown: inspect current
full public policy hash and instance identity; never automatically resend. Status
is a current snapshot, not a historical receipt. The public hash includes proposed
TLS descriptors and all certificate/root hashes, with no private-key bytes/hash.
Key matching binds the private key to the verified public server certificate.

The reload endpoint is excluded using proc mount metadata before any named I/O,
on server/client/cleanup paths. It is also reserved in instance/control/database
name admission. Stale/foreign endpoint names are preserved and refused; no
automatic stale-socket repair is introduced.

## Verification

Both full local SLES modes return `PASSED`, with five existing ignored cases per
profile and clean cleanup. Each mode builds/audits/tests debug and release:

| Run | Mode | Passed per profile | API seconds debug/release |
|---|---|---:|---|
| `20261109T115316Z-8e943177` | production | 301 | 502.31/478.16 |
| `20261109T124144Z-0980a622-nfs-qualification` | nfs-qualification | 305 | 884.46/809.38 |

Production retains its 900-second API ceiling; qualification retains 1,200 seconds.
All thirteen TLS functions and nineteen app unit tests pass in every profile.
Two qualification-only integration bodies actually execute only in that mode;
their production function counts do not prove execution of those pause races.

[Machine-readable evidence](NATIVE-TLS-RELOAD-EVIDENCE.json) records all 82 Rust
input hashes, seven pins, both full reports and all 44 local executable hashes.
The coordinator compares each archived source byte and independently rehashes
every executable. Repeating both native compiler-log audits per mode reproduces
397 AWS-LC source compilations through the intended glibc2.22 compiler/sysroot in
each audit. The final runtime Rust tree is `8ee490b0f2c3bd013c1b957d4a616e70d326f274`.
No Rust/build inputs change after source `99474cd` during closeout.

[Source CI run 42612394880](https://github.com/joey-huckabee/background-file-mover/actions/runs/42612394880)
passes both full modes at 301/305 tests per debug/release profile. Downloaded
reports/native logs independently match the declared audits. Its protected-ingress
checker passes 70 captured requests with cleanup exit 0 and all 82 Rust inputs and checker-driver
hashes matched. That Unix check does not claim TLS-client interoperability. CI
executable bytes were not uploaded for local rehash. Final-head PR checks remain
mandatory before merge.

All 35 relevant portable Python tests pass, including 11 certificate-fixture tests.
The diagnostic core scoped run 20261109T113255Z-87910c58 predates the mount fix and
integration tests. Updated qualification scope 20261109T114332Z-bc33e058-nfs-qualification
passes 32 tests per profile with clean cleanup. Scoped results cannot qualify the
complete service or installation bundle.

Independent review found a missing complete endpoint mount exclusion. Source `99474cd`
fixes server/client/cleanup pre-stat checks and reserves `tls-reload.sock` in the
instance/control/database paths. Its regression uses the pinned OCI runtime's
individually mounted `/etc/hosts`, without creating mounts or using NFS. Follow-up
source and instruction reviews found no further actionable issue.

See the [finite reload evaluation](evals/2026-11-09-live-tls-reload.md) and
[setup/reload instructions](NATIVE-HTTPS-SETUP.md). The qualification checkpoint
proves local ordering/responsiveness, not physical uninterruptible I/O. Certificate
expiry coverage uses explicit future verification time in a unit test, without
changing host time or adding a runtime clock override.

## Agent work split

The coordinator owns policy/admission integration, real-service tests and local
qualification. One bounded specialist supplied the private IPC module and later
the two setup/plan documents on separate branches with exclusive file ownership.
The existing reviewer independently found the missing full-leaf mount exclusion
and reviewed its correction, integration tests and instructions. This fan-out
produced a concrete safety fix and parallel documentation; it does not claim a
fixed quality percentage or replace executable qualification.

## Boundaries

No operational credentials/state, deployment, production NFS/deletion, dashboard
session/action implementation or release authorization. The existing HTTP and
protected Unix modes remain unchanged; there is no live HTTP/HTTPS mode switch or
TLS-error fallback. All eight release gates remain open. Stronger CPU isolation,
independent TLS-client interoperability, fresh disconnected packaging, crash
endpoint handling and supported systemd/account/shipping qualification remain
separate. SLES evidence targets pinned x86_64 SLES12SP5 userspace/glibc2.22; it
does not qualify every SLES kernel, filesystem, systemd version or FIPS mode.
