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

Implementation source review at8aa506c and follow-up through0715233 found no
actionable issue. All 76 portable Python tests pass, including 11 certificate
fixture tests and the same-CA unapproved client.

[Source CI run42563593572](https://github.com/joey-huckabee/background-file-mover/actions/runs/42563593572)
passes both full SLES modes: 286 production/290 qualification tests per profile,
including all nine TLS test functions, with clean cleanup. Both native compiler
logs per mode independently reproduce 397 AWS-LC source compilations through the
intended glibc2.22 compiler/sysroot. The actual protected-ingress checker passes
both profiles with 70 captured requests and cleanup exit0. These retain existing
local Unix coverage; they do not substitute for the new native TLS tests.

Local full production `20261109T044618Z-22770080` returns `PASSED`: 286 tests and
five existing ignored cases in each profile, clean cleanup, all 80 source hashes
matched and all 22 executables independently rehashed. API suites pass in
513.83/448.19 seconds against the unchanged 900-second ceiling.

Local qualification `20261109T053022Z-4193003f-nfs-qualification` also returns
`PASSED`: 290 tests and five existing ignored cases per profile, with clean
cleanup. API suites pass 105 tests in 891.01/868.80 seconds within the unchanged
1,200-second ceiling. All nine TLS test functions pass in each mode/profile.

[Machine-readable evidence](NATIVE-HTTPS-EVIDENCE.json) records all 80 Rust input
hashes and pins, both full reports and all 44 local executable hashes. The
coordinator independently rehashes every executable and repeats the native
compiler-log audit for both modes/profiles. Raw packs remain ignored under
`rust/validation/`; a cloud checkout's absence of those packs is not a validation
pass. CI executable bytes were not uploaded for independent local rehash.
Final-head PR checks remain mandatory before merge. No runtime source changed
after qualified Rust tree `65a4ca5d2682b543ada306f2e5b720163f33afac`.

Tests cover actual service TLS in both protocol versions, missing/untrusted/
expired/wrong-usage and same-CA unapproved clients, route/header/Host/generator/
scope denials, original measured payloads, immutable manifests and reordered replay
before/after restart with producer path reuse preserved. Further cases cover nine
credential startup refusals before bootstrap, nine invalid-config refusals before
state/endpoint creation, credential-free HTTP submission, and private operator/
stop responsiveness while six TLS handshakes remain incomplete. The safe reader
adds eight custody/size/descriptor regressions. These cases pass in both full
local modes and the recorded CI profiles.

Retain the initial strict-lint failures (collapsible-if and unused import) and
the scoped debug run's seven passes/two failures: the test client omitted JSON
Content-Type and correctly received415. Correcting the client header preserved
server validation and all assertions. Initial acceptance now explicitly uses
TLS1.2, with TLS1.3 replay before/after restart. See the
[finite endpoint evaluation](evals/2026-11-08-native-https-listener.md).

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
