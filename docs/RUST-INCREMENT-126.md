# Independent HTTPS client qualification

2026-11-10. Authorized after increment125/PR14-15. Base main
`ac8445f2d7f9ef6d541f23ba9908c0b6e12028fd`; branch
`feature/independent-tls-clients`. Implementation/results remain pending.

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
