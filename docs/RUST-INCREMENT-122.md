# Native TLS dependency and SLES handshake proof

2026-11-08. User approves increment A of [the native HTTPS plan](NATIVE-HTTPS-PLAN.md),
requires user setup instructions and the ability to select non-TLS operation.
Base main `1dc912cfe4dff4e990afb94ce2f6a7c66dab68d0`; branch
`feature/native-tls-proof`. No production HTTPS REST listener or deployment.

## Implementation

Pin Rustls0.23.46 and Tokio-Rustls0.26.6 with explicit AWS-LC/std/TLS1.2 features;
provider AWS-LC-RS1.19.0/Sys0.47.0. No system libssl/libcrypto runtime dependency
is intended or allowed. Preserve Rust1.99, Cargo-libc0.2.4, GNU/glibc2.22, pinned
SLES12SP5 and the current ELF/library controls. Selected features/checksums and
the conservative Cargo metadata inventory are recorded in the dependency pins.
Tokio's empty default feature and cc parallel compilation are explicit changes.
Metadata includes an inactive weak optional ring node; target `cargo tree -i ring`
reports nothing selected. Do not describe this metadata node as a second active
TLS provider or silently remove it from the existing metadata graph comparison.

An owned DER-based server-policy helper requires client certificate validation,
TLS1.2/1.3, HTTP/1.1 ALPN, no early data and no session storage/tickets. It does not
load deployment credentials or create an application listener. The shipped
`--check-platform` path exercises provider initialization/OS randomness without
reading config, credentials, SQLite or transfer roots.

Four new target tests cover two positive encrypted mutual-TLS exchanges,
four invalid client cases in both versions, three invalid server cases in both
versions and four policy-construction refusals. Invalid peer cases must fail
during TLS; deadlines/panics never count as successful negative evidence. Known
payload bytes and exact peer certificates are checked on successful exchanges.
This is CA verification, not yet approved-leaf-to-generator REST authorization.

The gate generates fresh disposable P-256 credentials with the pinned builder's
existing OpenSSL/Python, transfers only DER fixtures in an ephemeral private tar,
checks numeric ownership/modes and public certificate hashes, and exposes them
only to the TLS test executable. No private test key enters source archives,
binaries, retained reports or installation material. Public inventory/tool
provenance is retained. Native AWS-LC static/cc-builder selection and verbose
compiler commands are recorded; actual target evidence remains mandatory.

`--tls-proof-only` provides scoped diagnostics with `SCOPED_PASSED`, never full
`PASSED`. Offline packaging and the actual-ingress checker reject scoped results.
Full gates still execute every suite, with unchanged API test timeouts and ELF
controls. CI includes helper/source changes and portable certificate checks.

## User instructions and optional HTTP

[Setup instructions](NATIVE-HTTPS-SETUP.md) cover existing usable loopback HTTP,
the diagnostic/full gates, certificate preparation, permissions, clock/trust
requirements and the later listener setup boundary. Current loopback HTTP stays
certificate-free. Explicit configurable HTTP/HTTPS is required for the listener
increment, with no automatic fallback after invalid TLS. Remote plaintext trust
and authentication cannot be inferred from TLS-off or from a body/header claim.
No new JSON transport fields are presented as implemented by this proof slice.

## Actual validation status

Pending final scoped and both full SLES gates. Initial portable Python suite:
75 tests passed, including11 fixture tests. Independent bounded source/dependency/
gate review found no actionable issue at96f90ed. Later changes and actual target
results must be recorded before integration. No TLS compatibility pass is inferred
from published platform support or a host compilation.

All eight release gates remain open. No operational credentials/state, admin
runtime, production NFS/deletion, dependency outside the reviewed graph, remote
REST listener, account provisioning or deployment is introduced. Shared-kernel
containers prove the selected userspace, not all kernels/systemd/NAS/FIPS profiles.
