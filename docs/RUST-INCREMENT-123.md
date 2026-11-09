# Native producer HTTPS listener

2026-11-08. The user says "yes, proceed with the HTTPS listener" after PR11.
Base main `2c3ffd45348f12485fdbccd2c92fbf21c45c1848`; short-lived branch
`feature/native-https-listener`. Implements increment B of the native HTTPS plan,
with explicit loopback HTTP selection and user setup instructions. No deployment.

## Change and boundaries

Native ingress selects producer-only HTTP or HTTPS plus a private operator socket.
HTTPS supports remote binds with mandatory TLS1.2/1.3 client verification and exact
approved leaf SHA-256 to configured-generator mapping. Validate Host against the
configured authority and reject identity/proxy/cookie/Authorization assertions.
Keep the frozen producer route, parser/envelopes, UUID replay, current size policy,
custody/manifest-v2 and legacy-v1 recovery unchanged. Existing prototype and
protected Unix transports remain available, with ambiguous configurations refused.

Guard/control/lifetime admission precedes local credential reads. Retained-root
checks exclude credential/operator parents from every tracked payload root.
Descriptor-relative reads reject symlinks, unsafe ownership/modes, mounts/aliases,
hardlinks and size/custody changes. All DER entries are parsed; explicit server
roots verify chain/name/date/usage at startup. Strict PKCS8 and key matching are
required. Credentials do not enter SQLite, worker assignments or bundle inputs.
Only paths and public fingerprint mappings enter configuration. No new dependency.

Acquire six producer/eight total permits before any handshake. TLS runs in tracked
connection tasks with a five-second deadline; accept prioritizes private operators.
Flush TLS replies before bounded shutdown. Abort/drain connection tasks before
dropping endpoints/policy and workers. Slow handshakes cannot hold the accept loop.
No session resumption, early data, TLS-error fallback, plaintext remote exposure,
automatic retransmission or public operator route is added.

## Validation status

Implementation source review at8aa506c found no actionable issue. Eleven portable
certificate-fixture tests pass, including the same-CA unapproved client. Target
compilation and listener tests are in progress; no target pass is claimed yet.
Both full required SLES modes and final PR checks remain mandatory before merge.

Tests cover actual service TLS in both protocol versions, missing/untrusted/
expired/wrong-usage and same-CA unapproved clients, route/header/Host/generator/
scope denials, original measured payloads, immutable manifests and reordered replay
before/after restart with producer path reuse preserved. Further cases cover nine
credential startup refusals before bootstrap, nine invalid-config refusals before
state/endpoint creation, credential-free HTTP submission, and private operator/
stop responsiveness while six TLS handshakes remain incomplete. The safe reader
adds eight custody/size/descriptor regressions. Actual results will be recorded.

## User operation and remaining limits

See [setup instructions](NATIVE-HTTPS-SETUP.md) for exact configuration, DER
conversion, fingerprints, permissions and startup/refusal handling. HTTP remains
loopback-only, explicit and certificate-free. Configure credentials on a prepared
local filesystem separately from state, operators and current/retained payloads.

TLS policy loads once at startup. File edits do not reload/revoke a running policy;
live lifecycle/revocation races and stronger cryptographic CPU isolation remain
increment C. Independent TLS-client interoperability and new offline-bundle/shipping
qualification remain increment D. No real credentials, operational state, accounts,
proxy, production NFS/deletion or deployment are touched. All eight full-release
gates remain open. Container evidence is bounded to the pinned x86_64 SLES12SP5
userspace/glibc2.22 profile, not every kernel/systemd/NAS/FIPS environment.
