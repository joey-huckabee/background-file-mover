# Native HTTPS implementation plan for SLES 12 SP5

2026-11-08. User decision: "No proxy, do HTTPS in the Rust app".
Original architecture-plan base: main
`10b4cb769d5a5ce72ccce67987bcc16f37677f6a` after PR9.
This implementation sequence supersedes the external-proxy portion of P03/D02
and the older remote access design. Increments122/123 record the implemented TLS
stack and native listener with their actual qualification results. The user has
authorized live TLS reload; [increment124](RUST-INCREMENT-124.md) records its
bounded implementation and actual full-mode qualification. Stronger CPU isolation
and shipping remain separate. This grants no deployment or release approval.

## Approved first implementation and non-TLS option

The user subsequently approved the TLS dependency/SLES handshake proof with
proper user setup instructions and required configurable operation without TLS.
See [increment122](RUST-INCREMENT-122.md) and [setup guide](NATIVE-HTTPS-SETUP.md).
Loopback HTTP stays usable without certificates. Increment123 implements explicit
native HTTP/HTTPS selection; HTTP is loopback-only and never claims mTLS or grants
public operator/admin access. Prototype HTTP and protected Unix transport remain
separate existing modes. Live TLS reload applies only to native HTTPS; it does
not switch transports. TLS configuration errors never select HTTP automatically.

## Result and preserved behavior

One file-mover executable and one service terminate producer HTTPS directly.
Recorder -> TLS in file-mover -> certificate-derived producer principal ->
existing UUID submission/custody/delivery pipeline. No reverse proxy is required.

Keep the previously selected producer mutual TLS policy: the recorder verifies
the server certificate/hostname; the mover verifies the client certificate and
an explicit approved-certificate-to-generator mapping. Moving TLS into Rust does
not replace client certificates with dashboard passwords or anonymous HTTPS.
The future admin dashboard retains its separate username/password/session policy.

Native producer HTTPS exposes only the frozen submission operation. Job reads,
retention, health details, admin actions and specialized operator commands remain
unavailable to producer clients. Existing private operator/control sockets remain
host-local. The native mode requires no producer socket, proxy UID/GID or trusted
HTTP identity header. Preserve the already qualified P02 Unix transport as a
separate explicit local mode; it is not a native-HTTPS deployment prerequisite.

Preserve UUID/body replay, current expected-size policy, original path/index
mapping, whole-set 202 custody, manifest-v2 integrity, tracked legacy-v1 recovery,
group-50 forgetting and independent transfer ownership. No database migration or
new public operation/job identifier is needed for this transport change.

## Increment A: dependency and SLES feasibility

Implemented stack: the pinned rustls/tokio-rustls AWS-LC profile recorded in
increment122, using the existing Tokio runtime and HTTP parser/handlers. Retain
its exact reviewed versions, transitive crates, licenses, checksums and features.
Do not silently inherit changing Cargo defaults or select another provider. The
requirements below explain the proof boundary; actual results belong to the
increment and gate reports, not to a dependency name or this plan alone.

Rustls documents TLS1.2/1.3, provider selection and Tokio integration; AWS-LC
documents GNU/Linux support and native compiler requirements. These establish
plausibility, not our glibc2.22 compatibility. Check the exact pinned releases'
build scripts rather than assuming current upstream/main documentation matches.
Do not choose experimental custom cryptography or claim FIPS certification.

Implement the smallest TLS handshake smoke path through the normal gated Rust
workspace, without exposing the production REST listener. Both debug/release
and production/qualification builds use `scripts/check-rust-sles.py`:

- Keep Rust1.99, cargo-libc0.2.4, x86_64 GNU/glibc2.22 and the pinned SLES12SP5
  runtime unless a separate reviewed toolchain change is required.
- Route all TLS-provider native C/assembly compilation through the intended
  target compiler/sysroot. Record actual compiler commands and archive inputs;
  a Rust target flag alone does not prove native-code compatibility.
- Audit every executable for the existing loader/library allowlist and maximum
  GLIBC2.22 symbols. Refuse new libssl/libcrypto or other unreviewed runtime
  dependencies, workstation library paths and a copied replacement glibc.
- Execute real authenticated handshakes inside the pinned SLES userspace with
  actual target binaries. Exercise entropy, certificate signatures and encryption,
  not just `--version` or a TCP bind. Use a baseline x86_64 CPU build.
- Record complete dependency/features, sources/licenses, hashes and cleanup.

Exit: reviewed dependency/pin delta, both required gate modes and working target
handshakes. Failure blocks the next increment; it does not justify weakening the
glibc ceiling, substituting host tests or falling back to plaintext/OpenSSL.

## Increment B: native producer HTTPS

The user approved this increment after PR11. See
[increment123](RUST-INCREMENT-123.md) for implementation and actual qualification
status and [setup](NATIVE-HTTPS-SETUP.md) for exact configuration. The requirements
below remain the bounded implementation contract; they are not results by themselves.

Add an explicit HTTPS producer configuration: listen address/port, configured
server authority, server certificate chain/key, client trust anchors and bounded
certificate allowlist. The exact implemented fields are in the setup guide.
Reject ambiguous mode combinations with prototype/proxy-style ingress. Native
HTTPS must never start a plaintext producer fallback if TLS configuration fails.

Read credentials only from validated local files under trusted ownership and
parents: no symlink/unsafe mount traversal, private key readable only by the
intended service account, bounded files/chains/maps, matching certificate/key,
and valid usable policy. Close input descriptors after loading. Keep keys out of
SQLite, logs, worker assignments, environment variables, command arguments and
bundle contents. Use a dedicated local credential directory separate from state
and current/retained payload scopes. Audit worker launches and descriptor inheritance explicitly.
Perform local preflight under the existing instance/lifetime protocol before
payload bootstrap; do not perform credential filesystem I/O on the Tokio executor.

Use tokio-rustls to wrap accepted TCP streams and reuse the current HTTP parser,
response envelopes and submission handler. Explicitly flush TLS responses;
successful writes into a TLS buffer alone are not delivery evidence. Keep HTTP/1.1
and one request per connection. Retain TLS1.2/1.3 only, no TLS early data and no
session resumption for the implemented profile. No HTTP/2, QUIC,
redirects, response caching or automatic POST retransmission is introduced.

Build an owned producer principal from the verified client certificate, never
from a request header. Validate the CA chain, validity, client-auth usage and
signature, then require an exact SHA-256 fingerprint of the complete leaf DER
in the approved generator mapping. CA membership, certificate subject text,
source IP, Host or an asserted generator is insufficient authorization.

Require certificate mapping, configured generator, body generator and source
scope to agree before replay lookup/admission or file effects. Reject public
reserved identity/Authorization headers; no proxy-generated header is needed.
Validate Host against the configured HTTPS authority, rather than reusing the
Unix hop's literal localhost rule. Keep the frozen v2 producer schema and current
error registry; reconcile obsolete submission_id/body/error examples in the old
remote contract without reopening approved product behavior.

Exit: real HTTPS submission through the existing durable pipeline, direct TLS
identity isolation and complete denial coverage with original data preserved.

## Increment C: bounds, shutdown and certificate lifecycle

The native listener already counts unfinished TLS handshakes and active producer
HTTP requests within six producer/eight total HTTP slots, with separate private
operator/control access. Its handshake deadline is five seconds, alongside the
five-second HTTP read, ten-second handoff and bounded response write. The new
reload implementation is one bounded part of increment C; it does not complete
its broader load/shutdown obligations. Define and test maximum handshake/
certificate buffers and CPU work for the selected provider; bound TLS cryptographic work independently of
the shared executor so expensive handshakes cannot starve stop/status.

Preserve 8KiB/64-header, 64KiB JSON body and 256-file limits. Oversized, ambiguous,
incomplete and slowly dripped inputs fail without unbounded tasks, queues or body
files. Encrypted transport overhead must not silently shrink the valid body
limit. HTTP 429 retains the existing one-second retry guidance when an HTTP
response can be sent. A full pre-handshake budget can close a connection;
it cannot promise an encrypted 429 without completing TLS. No transport failure
grants path release or proves that previously admitted work rolled back.

The authorized implementation adds host-local `--reload-tls CANDIDATE.json` and
`--tls-status CONFIG.json`; see the [setup instructions](NATIVE-HTTPS-SETUP.md#live-tls-policy-reload).
The candidate is the full configuration (at most 16 KiB), not a partial TLS object.
Only server certificate chain/key, server/client roots and client allowlist may
change. HTTPS mode, authority, bind, operator socket and all non-TLS fields stay
fixed. Replacement files must remain within the set of immediate credential
parent directories recorded at original startup; versioned filenames in those
directories are supported, but later reloads cannot expand that set. Private
bytes stay in protected files, never arguments or logs. The loaded policy is an
in-memory replacement; no startup configuration file is rewritten.

A separate mode0600 private `tls-reload.sock` in the existing state directory serves
only the service UID. The unchanged lifecycle control provides owner discovery
and independent stop/status. A single reserved loader performs local credential
validation; status uses a short memory lock without credential/NFS/SQLite I/O.
Two tracked threads retain instance custody until joined. No public REST reload,
new dependency or TLS reload in HTTP/prototype/Unix modes is introduced.

Candidate validation completes before atomic policy activation. A validation
rejection preserves the active policy. Activation and actual `process` admission
share a short memory boundary. All old-generation unadmitted TLS connections are
revoked, and queued work cannot later use a stale authorization lease. The reload
acknowledgement waits for old unadmitted-connection exclusion, not for already
admitted process calls or transfers to finish. Client chain/usage/expiry and
current generation/allowlist are checked at actual admission. Deferral, including
a source-space probe retry, must re-enter admission; it cannot grandfather old
credentials. Existing source custody, UUID replay, whole-set 202 and admitted
service work remain unchanged. Disabled resumption leaves no old TLS tickets.

Public status includes the coordinator `PID:start`, process-local generation,
server/client leaf hashes and full `policy_sha256`. The full hash binds the public
HTTPS configuration/mappings and certificate/root hashes, excluding private bytes.
`loading` retains the prior active snapshot during validation; `draining` exposes
the activated new policy while old unadmitted connections exit; `applied` follows
that exclusion. `busy` means the loader is reserved/running and is distinct from
`draining`. `ready`, `rejected` and `stopping` complete the result labels. Queued
and admitted connection counts are observations, not job receipts.

The client reads generation then sends one reload with that expected generation.
A valid successful acknowledgement requires the next generation, `applied` and
no remaining draining. Reload has a thirty-second overall CLI budget; status has
one second. Lost responses/timeouts are outcome unknown, without automatic
mutating retry. Compare the complete intended public policy hash and `PID:start`
using `--tls-status`. Generation or a later result label alone proves no particular
command: status is current memory, not historical command-replay evidence. A
restart resets the generation. Do not infer rollback from a failed response.

Qualification and independent review of these reload/admission/stop boundaries
are recorded in increment124. Existing increment122/123 passes alone do not establish
live revocation, sustained cryptographic CPU isolation, independent-client
interoperability, fresh bundle delivery or shipping lifecycle readiness.

Retain the first monotonic shutdown deadline and lifetime exclusion through all
Store/worker and TLS/key-loading thread closure. A TLS accept, read or write
cannot postpone stop indefinitely.
Private operator-socket crash leftovers still need separately qualified safe
handling; native HTTPS does not close that existing shipping lifecycle gap.

Exit: bounded adversarial load and reload/revocation/shutdown race evidence,
with transfer independence and the existing recovery rules preserved.

## Increment D: end-to-end evidence, offline delivery and instructions

Use a private disposable test network: the real SLES-target mover serves HTTPS;
a separately pinned independent client checks server identity and exercises TLS.
Use throwaway test credentials only. Neither test keys nor deployment keys enter
the installation archive. No production NFS or operational database is involved.

Map the existing RA-01-16 obligations to the direct-TLS boundary. Proxy-specific
UID/header/hop cases become certificate-principal/native-listener cases; do not
call old P02 transport results proof of TLS. Keep still-relevant historical
results authentic and explicitly identify remaining NFS/systemd/physical limits.

| Acceptance family | Required cases/results |
|---|---|
| TLS interoperability | Independent client, TLS1.2 and1.3, correct server name/chain; wrong name/untrusted server fails |
| Client authentication | Missing, untrusted, expired, not-yet-valid, wrong-usage and unapproved same-CA leaf refuse |
| Principal binding | Approved leaf succeeds; spoofed headers/body generator/out-of-scope paths refuse before lookup/effects |
| Route separation | Enumerate frozen route/method/path variants; no producer operator/admin access, no plaintext fallback |
| Submission integrity | Nested paths and valid maximum requests; known bytes/sizes/hashes and immutable v2 manifest |
| Replay/recovery | Lost response, reordered files, producer path reuse and original-state restart retain original custody/receipt |
| Credential lifecycle | Old leaf denied after reload, new leaf for same generator replays original job; invalid reload preserves old policy |
| Races and resource bounds | Slow/partial handshake and HTTP, over-limit inputs, concurrent flood, policy change during request and bounded stop/status |
| Failure boundaries | TLS disconnect before/after admission, listener death and missing credentials preserve state; no fabricated 202 |
| Packaging | Disconnected install/verification, absent/corrupt credentials refuse, existing state preserved and no target compiler/OpenSSL install |

Record concrete raw inputs, expected results, measured timings, binary/source/
dependency hashes, both profiles and cleanup in `docs/evals/` and retained raw
packs. No additional encoding-only fixture workstream or automatic new NFS lab.

Update the offline bundle to the exact production-mode HTTPS executable,
dependency sources/licenses and verification material. Runtime requires the same
qualified OS loader/libraries, one service, configuration and locally provisioned
certificate files. No Rust/compiler/Python, external proxy or replacement OS TLS
library is an installation requirement. Validate these claims in the minimal
SLES image rather than inferring them from static linking or a successful build.

Document certificate request/import, trust, hostname/clock prerequisites,
permissions, renewal/revocation/reload, client retry behavior, startup/refusal and
recovery. A stale clock can invalidate certificates; do not bypass verification.
Provide service/port examples compatible with the selected supported manager;
do not assume modern systemd directives work on SLES12. Port/account/privilege
setup remains explicit deployment work, not an installer side effect.

## Delivery and limits

Each implementation slice uses a short-lived branch, independent review and
applicable required SLES gates before merge. The local coordinator owns one
sequential heavy WSL queue; cloud review/portable work cannot replace target
qualification. Native TLS code must preserve the workspace unsafe-code policy.

The initial compatibility claim is x86_64 SLES12SP5 userspace/glibc2.22, tested
inside the pinned container. Shared-kernel containers do not prove every SLES12
service pack/kernel, vendor systemd package, NAS or FIPS configuration. State
these limits; no real SLES installation is added as a prerequisite.

The dependency/native-listener implementations and their results remain scoped
to increments122/123. Live reload source is present; increment124's qualification
record is in increment124, not implied by this plan alone. Stronger cryptographic CPU
isolation, independent-client interoperability, new offline-bundle validation and
shipping qualification remain separate obligations. No proxy deployment,
admin/session/action activation, operational state conversion, production
NFS/deletion or release approval is introduced. All eight FR release gates remain
open; retain the reviewed dependency graph rather than changing it through setup
instructions.

Primary technical references: [Rustls](https://docs.rs/rustls/latest/rustls/),
[Tokio Rustls](https://docs.rs/tokio-rustls/latest/tokio_rustls/),
[client certificate verification](https://docs.rs/rustls/latest/rustls/server/struct.WebPkiClientVerifier.html),
[AWS-LC Linux requirements](https://aws.github.io/aws-lc-rs/requirements/linux.html)
and [platform support](https://aws.github.io/aws-lc-rs/platform_support.html).
These describe available mechanisms, not a passing SLES qualification.
