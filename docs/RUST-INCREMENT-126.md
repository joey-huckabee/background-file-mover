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
