# Independent HTTPS client qualification

2026-11-10. Authorized after increment125/PR14-15. Base main
`ac8445f2d7f9ef6d541f23ba9908c0b6e12028fd`; branch
`feature/independent-tls-clients`. Bounded local qualification is recorded below; required PR checks and independent review gate integration.

Use the retained PASSED production gate artifacts in both debug/release profiles,
checking their source archive against current Git Rust blobs and rehashing their
executables/ELF reports. Rust/build inputs remain unchanged. Any required runtime
fix needs its own reviewed source diff and fresh applicable SLES gates.

Run a separately digest-pinned curl/OpenSSL container and the pinned SLES12SP5
server on an owned internal network, without published ports, capabilities or
real state. Existing cached tools require no installation. Record client image,
versions/binary hashes, server binary hashes and actual request/results/timings.
No disabled certificate verification, proxy or automatic request retries.

Finite cases: TLS1.2/1.3; valid server identity versus wrong hostname/trust;
missing/untrusted/expired/wrong-purpose and same-CA-unapproved client leaves;
certificate/generator binding, producer route separation and asserted-header
refusal; known payload/manifest bytes; discarded receipt followed by same-ID
replay; reordered files and reused producer leaves; original-state restart;
replacement server/client policy activation and old-client refusal; invalid
replacement preserving the active policy. Verify destination/private claims and
replacement producer files after every replay/restart/rotation stage.

Receipt-discard testing must state precisely what the client discards; do not
claim a deterministic pre-admission disconnect or literal network outage without
such a control. Negative TLS tests must fail for certificate/handshake reasons,
never timeouts, missing tools, connection refusal or process panic.

Use existing disposable fixture certificates without modifying the shared Rust
gate fixture generator. Not-yet-valid client leaves and unexercised broader RA
cells remain explicitly unqualified. No new encoding-only fixture workstream.

Update setup instructions with tested client requirements and commands. This
qualifies the modern external client against the SLES server; it does not replace
SLES system OpenSSL, prove every legacy client, full increment D, packaging,
systemd/NFS/FIPS or shipping. All eight FR gates remain open.


Development findings retained: first run `tls-clients-126-first.json` fails
before TLS testing because curl7.88.1 rejects long-option equals syntax
`--proto=https`. Use separate `--proto`, `=https` arguments. Containers/network
cleaned with exit0; this is not passing evidence. Independent review found that
a client-removal exception could bypass other cleanup. Each cleanup stage now
runs independently, including host-process reaping; a mocked timeout regression
requires server and network cleanup despite that first failure. Fresh proof is
required after these fixes.

Second run `tls-clients-126-second.json` establishes an actual missing-client
TLS alert but the classifier initially omitted curl's specific code98
(`CURLE_SSL_CLIENTCERT`). It now requires that code, like35/56, to accompany an
explicit certificate alert and no HTTP reply. Timeouts, DNS/connect failures,
local certificate-loading errors and empty successful exits still fail.
See the [libcurl error registry](https://curl.se/libcurl/c/libcurl-errors.html).
Client-CA replacement now also uses the existing other-CA fixture, without
changing the shared generator. Server-leaf rotation remains under its original
server CA; server-CA rollover remains unqualified.

Third run `tls-clients-126-third.json` stops at the expired-client case:
curl/OpenSSL maps its peer's TLS1.2 certificate-expired alert to generic code60.
A focused disposable probe confirms valid clients get202 under both protocols;
expired clients get an incoming certificate-expired alert (TLS1.2 code60,
TLS1.3 code56). The final classifier requires a direction-tagged incoming
certificate alert, no HTTP, and code35/56/60/98. A local outgoing verification
alert, generic code60, timeout or connection error never qualifies. Negative
curl trace output is limited to disposable fixtures, bounded, and checked for
session/key markers before recording. This diagnostic is not full qualification.

Fourth run stops on curl7.88's missing-client alert label `unknown (628)`, with
OpenSSL's accompanying decode `certificate required`. That exact incoming trace
plus peer decode is now recognized; generic unknown alerts still fail. The
focused matrix also found that the initial OpenSSL command omitted ALPN.
Native `Policy::accept` requires negotiated `http/1.1`; add `-alpn http/1.1`
instead of weakening the server. Curl already negotiates it. The focused matrix
is diagnostic, not passing full qualification. All ordinary run cleanup exits
remain recorded in the raw reports.

Fifth run stops because an informational OpenSSL verification diagnostic is
missing from OCI stderr despite a successful process exit. The focused probe
confirms valid requests return202 with verified chains, and wrong-name/wrong-CA
requests fail; some OCI stderr captures are empty. Capture diagnostics in a
private mode0600 client file, read it after the tool exits, preserve its original
exit code, and retain the same verification assertions. A real-process unit case
checks exact status/bytes and file mode. This changes test transport only.


## Verification

The unchanged Rust workspace tree is
`51721ff716101ce89297a60561949e2023a6aa30`. The checker source is
`b97c4cac56e2802b44c3848f279f9c1bcd401918`; documentation closeout preserves every
Rust, build and checker input. The retained production gate
`20261110T033036Z-4fafb36f` passed 315 tests/profile with ELF audits and clean cleanup
as recorded in increment125. This increment does not pretend to rebuild Rust
locally: it rechecks all 83 archived workspace inputs against Git, both executable
hashes and ELF records, current build inputs, and executable identity after copy.

Local report `tls-clients-126-sixth.json` returns `PASSED` for both production
profiles with all owned container/network cleanup exits 0. Independent collection
rehashes the two actual executables and verifies both pinned client binaries.
[Machine-readable evidence](NATIVE-TLS-CLIENT-EVIDENCE.json) embeds the public
report, raw-report hash, source/driver/pin identities, counts and retained failed
run summaries. No private keys or TLS session data appear in the evidence.

| Per production profile | Actual result |
|---|---:|
| Independent client operations | 70 (curl 39, s_client 31) |
| Exact TLS versions | TLS1.2: 32; TLS1.3: 38 |
| HTTP202 receipts | 25 |
| HTTP denials | 15 |
| TLS certificate/verification refusals | 29 |
| Application-discarded receipt | 1 |
| Full source/claim/output/manifest preservation stages | 7 |

The total is 140 operations across debug/release. Both frontends exercise both TLS
versions; the raw matrix identifies the selected frontend/version for each case.
Boundary-only checks use curl/TLS1.3 rather than implying every row runs under
every combination. 22 portable parser/process/safety tests pass on WSL with no
skips. Ordinary failed development runs remain `FAILED`, not qualification.

The workflow runs those portable tests, both existing full Rust SLES modes and
the actual independent checker after the production gate. Required results are
recorded on [PR16](https://github.com/joey-huckabee/background-file-mover/pull/16)
before integration; no required check is bypassed for this increment.

See the [finite evaluation](evals/2026-11-10-independent-tls-clients.md) and
[client instructions](NATIVE-HTTPS-CLIENTS.md). Curl and s_client use the same
OpenSSL backend, independent of the Rustls server. This is not proof of every
backend/legacy client. Fresh EC P-256 handshakes are tested; persisted client
session resumption, 0-RTT, future-valid client leaves and server-CA rollover remain
unqualified. Root/client-leaf rotation tests do not authorize real CA operations.
Offline bundle, service/account/confinement, physical SLES/kernel/NFS/FIPS,
operational conversion, deployment and full release remain separate.
All eight FR gates remain open.

## Agent work split

The coordinator owns the driver, private network/artifact integration, diagnosis,
local target runs, CI integration, evidence and final delivery. The bounded cloud
specialist supplied the pure client argument/parser module and its tests,
including the compatibility and ALPN fixes. The existing reviewer checks source,
cleanup, interpretation of alerts, verified-name/authority and evidence limits.
Cloud review does not replace target execution or coordinator artifact rehashing.

CI production also passes 315 tests per profile plus the full 140-operation
independent-client checker. Downloaded reports match the pinned client binaries,
all 83 Rust inputs, all 8 driver-input hashes and the local case families. The
synthetic PR checkout tree equals the qualified source tree; its commit is
recorded separately from the branch head. Both native compiler-log audits
reproduce 397 compilations through the intended glibc2.22 compiler/sysroot.
The evidence includes this CI summary and its raw-report hashes; CI executable
bytes were not uploaded for independent rehash. The same CI run also passes the
full qualification mode at 319 tests per profile; both native compiler-log audits
were reproduced from its downloaded logs. Final evidence review remains an
integration requirement, recorded on PR16.
