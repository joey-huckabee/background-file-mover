# Native HTTPS and HTTP setup

Status: increment122 adds the TLS dependency/SLES handshake proof. It does not
yet add an HTTPS REST listener. Do not point production recorders at a TLS port
or add invented TLS JSON fields to the current configuration. See
[the implementation sequence](NATIVE-HTTPS-PLAN.md) and
[actual proof results](RUST-INCREMENT-122.md).

The user requires one executable/service, no proxy, and configurable operation
without TLS. The existing loopback HTTP mode remains available without any
certificate files. The later native listener increment will supply and test the
exact explicit HTTP/HTTPS configuration. A TLS setup error must fail closed;
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

Current HTTP is loopback-only. The approved future non-TLS option must be an
explicit transport selection. Plain HTTP has no encryption or client-certificate
authentication; its remote trust/authentication boundary must be documented and
tested before remote exposure. Selecting HTTP must not grant producer callers
operator/admin access or pretend a request header is a verified certificate.

## Prepare for the later HTTPS listener

Prepare these deployment values without changing the running service:

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
the exact configuration spelling will be supplied with the listener increment.
Do not infer a currently supported JSON field from these examples.

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
timeouts or panics are failures, not successful rejection evidence. This proves
the target dependency path, not REST routing, certificate-to-generator admission,
reload/revocation or production deployment. Those remain later increments.

## Operation and troubleshooting after listener integration

The next increment must add validated runnable configurations for both transport
modes, startup examples and a real recorder request. Subsequent lifecycle work
must document tested host-local reload/rotation/revocation and how to verify that
old credentials are denied while admitted transfers continue.

For now:

- A current unknown-field/TLS-listener configuration error means the listener is
  not implemented; do not disable configuration validation or widen plaintext bind.
- A proof certificate error is investigated using the gate's public inventory,
  host time, trust/name/usage checks and retained logs. Never send private keys.
- A scoped pass cannot replace either full gate or qualify an offline bundle.
- A compiler/GLIBC/native-library refusal blocks the proof; do not replace SLES
  glibc/loader or install an unqualified workstation TLS library on the target.

The support claim remains bounded x86_64 SLES12SP5 userspace/glibc2.22 under pinned
container execution. It does not establish every SLES12 service pack/kernel,
vendor systemd build or FIPS compliance. All eight release gates remain open;
production NFS, deletion, remote listener activation and deployment remain off.
