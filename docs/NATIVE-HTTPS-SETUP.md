# Native HTTPS and HTTP setup

Status: increment123 implements the native producer listener after increment122's
TLS dependency proof. Qualification status is recorded in
[increment123](RUST-INCREMENT-123.md); this is not deployment or release approval. See
[the implementation sequence](NATIVE-HTTPS-PLAN.md) and
[dependency proof results](RUST-INCREMENT-122.md).

The user requires one executable/service, no proxy, and configurable operation
without TLS. The existing loopback HTTP mode remains available without any
certificate files. Native mode uses the explicit HTTP/HTTPS configuration below.
A TLS setup error fails closed;
it must never switch to HTTP automatically.

## What works now: existing HTTP

Use the complete [local configuration example](../rust/config/local.example.json),
with the intended bindings, state and roots provisioned under the
[operator guide](RUST-OPERATOR-GUIDE.md). Its actual current HTTP setting is:

```json
"bind": "127.0.0.1:8080"
```

This is one field in the full configuration, not a standalone configuration file.
Leave `protected_ingress` absent to select the existing loopback prototype.
The optional Unix transport is documented separately in the operator guide.
Neither mode requires TLS keys, a CA file, OpenSSL installation or a proxy.

For a correctly provisioned disposable/local instance:

```sh
/path/to/file-mover --check-platform
/path/to/file-mover /path/to/config.json
```

`--check-platform` checks the platform and TLS provider's ability to obtain secure
randomness. It does not read a TLS configuration, start a listener, contact NFS,
open SQLite or prove HTTPS is enabled. Normal startup retains all existing
enrollment/custody checks. Do not change a live instance's roots/state to try this.

Current HTTP is loopback-only. Plain HTTP has no encryption or client-certificate
authentication. Neither HTTP configuration below allows remote plaintext access.

## Native producer HTTPS configuration

Complete starting files are [HTTPS](examples/native-https.example.json) and
[HTTP](examples/native-http.example.json). They use the same fresh/local binding
examples as the prototype. Replace them with actual provisioned values; never
replace an enrolled instance's roots, bindings or state with example values.

Start with the full local configuration and preserve its actual source,
destination, enrollment and state values. Add this top-level object and change
`bind` deliberately to the desired HTTPS address:

```json
"bind": "0.0.0.0:8443",
"native_ingress": {
  "transport": "https",
  "operator_socket": "/run/file-mover-api/operator.sock",
  "authority": "mover.example.internal:8443",
  "server_certificates": ["/etc/file-mover/tls/server.der"],
  "server_key": "/etc/file-mover/tls/server.key.der",
  "server_ca_certificates": ["/etc/file-mover/tls/server-root.der"],
  "client_ca_certificates": ["/etc/file-mover/tls/client-root.der"],
  "clients": [{
    "sha256": "0000000000000000000000000000000000000000000000000000000000000000",
    "generator_id": "recorder-host-a"
  }]
}
```

These are fields inside the full configuration, not a standalone JSON document.
Replace the hostname, paths and zero fingerprint with real approved values.
The top-level `generator_id`, each client mapping and the request generator must
agree. This first listener supports the existing one configured generator; several
approved certificates may map to it. A valid certificate from the trusted CA is
insufficient without its exact approved leaf fingerprint.

`authority` requires a lowercase DNS name or canonical IP plus explicit port
matching `bind`. IPv6 uses `[address]:port`. The server certificate must match the
name/IP and be valid for server authentication at startup. Clients must verify it
too. Requests must send exactly that authority in `Host`, including the port.

`server_certificates` is the leaf followed by necessary intermediates (1–8 DER
files). `server_ca_certificates` supplies explicit roots for startup verification;
`client_ca_certificates` supplies roots for authenticating recorders (1–16 each).
Every entry is parsed. Each certificate is at most 64 KiB. The key must be
unencrypted PKCS8 DER, at most 16 KiB, and match the server leaf. Client mappings
are bounded to 256 unique lowercase, 64-character SHA-256 values. No system trust
store is consulted. TLS 1.2/1.3 and HTTP/1.1 ALPN are required; early data, tickets
and session resumption are disabled.

Provision the credential directory locally for the non-root service account:
exact mode0700 and the account's UID/GID. Key mode is exactly0600; certificates
allow0400,0444,0600 or0644 and must be owned by that UID with one link. Paths and
parents must be canonical, local, safely owned and free of symlinks/unsafe mount
aliases. Root-owned non-writable ancestors are permitted; a root-owned sticky
temporary ancestor is permitted for disposable tests. The operator directory must
be separately provisioned as0700 with the same UID/GID. Do not place either
directory in state or any current/retained payload scope. No directory, account,
port rule or credential is automatically installed by listener startup.
The current local mount-policy allowlist is ext2/3/4, tmpfs and overlay, including
traversed mounts. Other filesystems refuse; this increment does not qualify every
filesystem supported by SLES. Credential files never use NFS, even in the NFS
qualification build.

Leave `protected_ingress` absent. Mixing it with `native_ingress` refuses. The
private operator socket accepts only the service UID; the public producer port
serves only `POST /api/v2/jobs`. It exposes no operator health/status/retention,
admin actions or dashboard. Public identity/Authorization/cookie/proxy assertions
are rejected. The TLS peer certificate establishes producer identity.

For explicit native HTTP, replace the entire native object with:

```json
"bind": "127.0.0.1:8080",
"native_ingress": {
  "transport": "http",
  "operator_socket": "/run/file-mover-api/operator.sock"
}
```

This producer-only mode needs no credential files and retains the private operator
socket. HTTPS-only fields in HTTP mode refuse. Remote binds in HTTP mode refuse.
Loopback connectivity is the HTTP producer trust boundary: local processes that
can connect may submit the configured generator. Operator access requires the
service UID on its separate socket.
Leaving both ingress objects absent preserves the earlier trusted loopback
prototype; the protected Unix mode remains a separate option. No TLS failure
switches transport or opens a second plaintext listener.

## Prepare credentials

Prepare these deployment values before changing a running service:

- A stable DNS name (or explicitly supported IP identity) and chosen listen port.
- A server certificate chain for that identity and its matching private key.
- The permitted client CA chain and each manually approved recorder certificate.
- The leaf certificate fingerprint-to-generator mapping; CA membership or a
  certificate's displayed name alone does not authorize a recorder.
- Correct host time, local credential storage and the intended service account.

Producer mutual TLS means the recorder verifies the server and the mover verifies
the recorder. This is separate from the future admin username/password/session
policy. File transfers remain service-owned; changing credentials does not change
recording UUIDs or authorize cancellation/deletion.

Use your approved certificate issuer. It must issue the server certificate with
the correct SAN and serverAuth usage, and recorder certificates with clientAuth
usage. Include the necessary intermediate certificates. Obtain the issuer's trust
anchors through a trusted channel. Never disable hostname, chain or date checks
to work around a failed setup.

If OpenSSL is already available on the certificate administration workstation,
the following creates private P-256 keys and signing requests. These are preparation
examples, not certificate issuance, a production CA or service activation:

```sh
umask 077
openssl genpkey -algorithm EC -pkeyopt ec_paramgen_curve:P-256 -out mover.key.pem
openssl req -new -key mover.key.pem -subj /CN=mover.example.internal \
  -addext subjectAltName=DNS:mover.example.internal -out mover.csr.pem
openssl genpkey -algorithm EC -pkeyopt ec_paramgen_curve:P-256 -out recorder.key.pem
openssl req -new -key recorder.key.pem -subj /CN=recorder-host-a -out recorder.csr.pem
```

Replace the names with actual deployment values. Send CSRs, not private keys,
to the approved issuer. The issuer must apply the intended SAN/EKU policy; a CSR
request does not guarantee the resulting certificate contains it. Check issued
material on that administration workstation:

```sh
openssl verify -purpose sslserver -verify_hostname mover.example.internal \
  -CAfile server-ca.pem mover.cert.pem
openssl verify -purpose sslclient -CAfile client-ca.pem recorder.cert.pem
openssl x509 -in recorder.cert.pem -outform DER | openssl dgst -sha256
```

Supply intermediate chains to the verification tool when your issuer requires
them. Also inspect SAN, purpose and validity, and confirm that each certificate
matches its key. The fingerprint command is the SHA-256 of the complete leaf DER;
use the fingerprint as the native `clients[].sha256` value above.

Convert issued material on the certificate administration workstation:

```sh
umask 077
openssl x509 -in mover.cert.pem -outform DER -out server.der
openssl pkcs8 -topk8 -nocrypt -in mover.key.pem -outform DER -out server.key.der
openssl x509 -in server-ca.pem -outform DER -out server-root.der
openssl x509 -in client-ca.pem -outform DER -out client-root.der
chmod 600 server.key.der
chmod 400 server.der server-root.der client-root.der
```

Convert each intermediate separately and append its DER path after the server
leaf. The administration tool must support these commands; it need not run on
SLES. Move files through your approved secure channel and set ownership/modes for
the actual service account. The service reads DER directly and requires no
OpenSSL installation. Do not copy recorder private keys to the mover.

After explicit local provisioning/enrollment, start the audited executable with
the full configuration path. From a recorder with approved credentials, a request
using a JSON submission file can be sent with a TLS-capable client. For example,
save `submission.json` with actual immutable recording values:

```json
{
  "recording_id": "d1c725e3-1634-47b1-9938-0cd397d38758",
  "generator_id": "recorder-host-a",
  "source_directory": "/srv/file-mover/source/current",
  "files": ["video.dat"]
}
```

Use a fresh UUID for each new recording; reuse it only for an exact recording
retry. Paths name files inside the configured source scope. If expected-size
checking is enabled, also supply a complete `expected_sizes_bytes` map with
canonical decimal-string sizes. Preserve the original map on retries even when
comparison is disabled. See the [producer contract](api/PRODUCER-MANIFEST-CONTRACT.md).

```sh
curl --cacert server-ca.pem --cert recorder.cert.pem --key recorder.key.pem \
  --http1.1 -H 'Host: mover.example.internal:8443' -H 'Content-Type: application/json' \
  --data-binary @submission.json https://mover.example.internal:8443/api/v2/jobs
```

This is an administration/client example, not an additional target dependency or
an independent-client qualification claim. Keep private key bytes out of command
arguments and logs (the command names files only); protect those files. A 202
retains its existing durable custody meaning. After a disconnect, retry the same
UUID and immutable assertions; do not assume the request rolled back.
Set the Host header to the exact configured authority even when a client would
normally omit a default port. The TLS URL name must still match the certificate;
changing Host does not replace certificate/hostname verification.

Check the mover locally with the existing independent control command:

```sh
/path/to/file-mover --status /path/to/config.json
```

Public `/healthz` requests are forbidden in native producer mode. If curl is
already available locally, the service account can read private HTTP health using
`curl --unix-socket /run/file-mover-api/operator.sock http://localhost/healthz`.
This is not a remote monitoring endpoint or an additional installation dependency.

The mover host will need its server key only; a recorder keeps its own client key.
An offline archive must contain neither. Keep real keys out of Git, logs, command
arguments, environment variables, SQLite, transfer roots and support attachments.
Use a trusted local credential directory separate from state and current/retained
payload roots, with restrictive ownership and permissions (directory0700 and
private key0600 for the intended account). Installation of accounts/ports and
credentials is a deliberate deployment procedure, not a bundle side effect.
OpenSSL is a possible administration tool, not a target runtime dependency.

## Reproduce the disposable SLES proof

On the prepared build host, use the committed native WSL clone and cached pinned
builder/runtime described in [the agent workflow](AGENT-WORKFLOW.md).
The target installer still requires no Rust, compiler or Python.

Existing offline bundles remain their recorded version. This increment checks
dependency source/notice collection but does not build a new installation bundle.
Use the [offline installation procedure](OFFLINE-INSTALL.md) with a fresh full
production-gate report when producing a new bundle; never package a scoped proof.

For a short diagnostic run:

```sh
python3 scripts/check-rust-sles.py --offline --tls-proof-only
```

Require `SCOPED_PASSED` and clean cleanup. This builds/audits target executables
and runs the TLS tests in SLES12SP5/glibc2.22, but deliberately does not run the
complete existing service suites. It cannot be used to package or qualify the
service. If locked TLS sources are missing, offline mode refuses. Provision the
locked cache on the prepared connected build host with the same scoped command
without `--offline`; do not bypass lock/hash checks or enable build networking.

Full qualification still requires both sequential commands:

```sh
python3 scripts/check-rust-sles.py --offline
python3 scripts/check-rust-sles.py --offline --qualification
```

Require full `PASSED` reports and no cleanup errors. Gate generation uses the
builder's existing Python/OpenSSL only for fresh disposable certificates. No
private test fixtures are checked in or embedded in binaries/source archives.
An ephemeral private tar transfers them to the isolated SLES container as numeric
UID/GID1000 with private key0600; it is not retained in validation packs/bundles.
Only public certificate hashes/dates and tool provenance are recorded. The gate
removes its containers and signing material, including on failure.

TLS1.2/1.3 handshakes exchange known bytes and check both peer certificates.
Missing/untrusted/expired/wrong-purpose clients and invalid servers must fail;
timeouts or panics are failures, not successful rejection evidence. The current
scoped TLS suite also includes selected native REST routing, certificate mapping,
replay/restart and refusal cases. It still cannot replace full service regression
qualification or qualify reload/revocation or deployment. Native listener results
are recorded in increment123.

## Operation and troubleshooting

Credentials and approved mappings are loaded once during guarded startup, before
source bootstrap. Changing files does not update a running policy. There is no
live TLS reload/revocation command in this increment. Until lifecycle integration
is qualified, a deliberate original-state service stop/start is required to load
a replacement policy. Follow the operator restart guide; surviving workers can
block restart. Do not claim immediate revocation from editing a file. This
limitation blocks shipping qualification, not credential verification at startup.

Six producer slots include unfinished TLS handshakes; two other HTTP slots remain
available for private operators. Handshake timeout is five seconds, request read
five seconds and response flush/shutdown two seconds. HTTP framing and handoff
limits are unchanged. A connection rejected before handshake may close without
an HTTP response. Slow-handshake/stop checks do not qualify sustained cryptographic
CPU floods; stronger CPU isolation and lifecycle races remain subsequent work.

For now:

- A configuration error may indicate a predecessor executable or mixed/invalid
  transport fields. Check the exact installed version; do not bypass validation.
- A credential startup refusal leaves the listener unready; check local custody,
  DER/PKCS8 format, chain/name/date/usage and key matching. Never switch to HTTP
  automatically or send private keys in support attachments.
- A same-CA unapproved recorder receives403; compare the complete leaf DER
  fingerprint and configured generator. Headers do not replace certificate identity.
- A proof certificate error is investigated using the gate's public inventory,
  host time, trust/name/usage checks and retained logs. Never send private keys.
- A scoped pass cannot replace either full gate or qualify an offline bundle.
- A compiler/GLIBC/native-library refusal blocks the proof; do not replace SLES
  glibc/loader or install an unqualified workstation TLS library on the target.

The support claim remains bounded x86_64 SLES12SP5 userspace/glibc2.22 under pinned
container execution. It does not establish every SLES12 service pack/kernel,
vendor systemd build or FIPS compliance. All eight release gates remain open;
production NFS, deletion and deployment remain off.
