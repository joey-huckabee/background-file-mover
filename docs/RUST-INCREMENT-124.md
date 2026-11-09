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

Independent source review through99474cd found no further actionable issue after
fixing the missing full-leaf mount exclusion. The regression uses the pinned OCI
runtime's individually mounted `/etc/hosts`, without creating mounts or using NFS.

The initial scoped core run `20261109T113255Z-87910c58` passes debug/release app
unit and TLS tests with `SCOPED_PASSED` and clean cleanup. It predates the final
mount fix and real-service reload tests and is diagnostic evidence only.
Fresh scoped and full production/qualification results remain pending.

See the [finite reload evaluation](evals/2026-11-09-live-tls-reload.md) and
[setup/reload instructions](NATIVE-HTTPS-SETUP.md). Actual gate IDs, counts,
source/binary hashes, native compiler audits and final CI will be recorded before
integration. No scoped result qualifies the complete service or offline bundle.

## Boundaries

No operational credentials/state, deployment, production NFS/deletion, dashboard
session/action implementation or release authorization. The existing HTTP and
protected Unix modes remain unchanged; there is no live HTTP/HTTPS mode switch or
TLS-error fallback. All eight release gates remain open. Stronger CPU isolation,
independent TLS-client interoperability, fresh disconnected packaging, crash
endpoint handling and supported systemd/account/shipping qualification remain
separate. SLES evidence targets pinned x86_64 SLES12SP5 userspace/glibc2.22; it
does not qualify every SLES kernel, filesystem, systemd version or FIPS mode.
