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

The scoped run `20261109T015008Z-43cadb3d` returns `SCOPED_PASSED` with clean
cleanup: four TLS tests in each debug/release profile, no ignores, and maximum
GLIBC2.18 on its four audited executables. The coordinator rehashes all four
executables and independently checks the raw native logs: 397 AWS-LC source
compilations per profile through libc-cc and the glibc2.22 sysroot. This is not
a full service qualification.

The full production run `20261109T020157Z-f0143d15` returns `PASSED`:
273 tests per debug/release profile, five existing ignored cases per profile and
clean cleanup. Its API suites finish in 520.05/476.87 seconds against the unchanged
900-second ceiling. The qualification run
`20261109T024718Z-52525649-nfs-qualification` also returns `PASSED`, with 277 tests
and five existing ignored cases per profile, plus clean cleanup. Its API suites
pass 105 tests in 902.63/844.64 seconds against the unchanged 1,200-second
ceiling. These measured local durations include storage latency; no deadline or
assertion was weakened.

The final portable Python suite passes all 76 tests, including 11 fixture tests
and native compiler-audit refusal cases. Independent bounded source/dependency/
gate review found no actionable issue at96f90ed. Review caught a native-audit option-parser gap; split/equal/concatenated sysroot
overrides and dangling options now have negative cases, and the fix was reviewed
at44a44d0. No observed compile used the wrong sysroot. Cached dependency
source/notice extraction passes for all 58 metadata-listed
packages (174 source/notice members), without building an installation bundle.
A bounded published-advisory review found no applicable advisory among those
checked for the pinned TLS versions; it was not a complete automated lockfile
audit and does not establish absence of unpublished issues. No TLS compatibility pass is inferred
from published platform support or a host compilation.

CI run [42551738694](https://github.com/joey-huckabee/background-file-mover/actions/runs/42551738694)
passes both full gate modes (273/277 tests per profile) and both actual-UID
producer-ingress profiles, with 70 captured requests, 11 unsafe cases per profile
and cleanup exit 0. CI reports/native logs were inspected; CI executable bytes
were not uploaded for independent local rehashing.

Retain the earlier failed CI fixture-copy report. Both Rust gates passed there,
but Podman rejected the following ingress archive before any application profile
started. Local diagnostics reproduced the failure with pipe and regular-file
stdin. Removing only surplus tar record padding after the writer's recorded
member end plus the two standard end blocks makes the copy succeed with identical
payload hashes, ownership and modes. Commit7b0e90d implements that bounded fix;
its regression preserves legitimate zero-tailed member data. No copy error is
ignored. The passing CI run confirms the actual checker with the corrected tar.

The positive TLS proof uses Rustls/AWS-LC at both ends. Interoperability with an
independent TLS client implementation remains a later integration obligation.
No new installation bundle was built; existing bundles retain their prior version.

[Machine-readable evidence](NATIVE-TLS-EVIDENCE.json) records all 77 Rust source
hashes, dependency/toolchain pins, both full reports and all 44 local executable
hashes. The coordinator independently rehashes those executables and audits both
native compilation logs per mode: 397 AWS-LC source compilations per profile
through the intended compiler/sysroot. Raw local packs remain ignored under
`rust/validation/`; their absence from a cloud checkout is not a validation pass.
The final documentation/evidence commit still requires its applicable PR checks
before merge; no source changed after the qualified Rust tree
`2812aa80aae83f715ca3685547efb93e74dced0a`.

All eight release gates remain open. No operational credentials/state, admin
runtime, production NFS/deletion, dependency outside the reviewed graph, remote
REST listener, account provisioning or deployment is introduced. Shared-kernel
containers prove the selected userspace, not all kernels/systemd/NAS/FIPS profiles.
