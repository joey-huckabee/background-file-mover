# Remote producer API access contract

Design baseline, increment 39, 2026-10-16. **Specified, not implemented or
qualified.** This defines a proposed first remote profile within FR-01;
registration, bearer-token issuance and automatic enrollment remain deferred.
The current service is still a trusted loopback prototype, rejects non-loopback
binding and rejects Authorization headers. Adding a reverse proxy to that
prototype does not implement this contract. Production NFS and deletion stay off.

## Remote admin dashboard: additional requirement, protection pending

The user requires dashboard access from another computer (2026-10-23,
[group 24/API-E100/SC-152](REST-ERROR-SCENARIOS.md#admin-dashboard-access-from-another-computer-group-24)).
The producer-only profile below must not grant dashboard/admin access. Its
trusted-host local-operator statement describes the existing separate interface,
not a restriction of the new dashboard to the mover host. Group 25 now selects simple admin username/password
([API-E101/SC-153](REST-ERROR-SCENARIOS.md#simple-admin-usernamepassword-for-the-first-release-group-25)),
with SSO and advanced account features deferred. Keep ordinary HTTPS/password/
session hygiene and finalize minimal credential setup and wire details. No
remote admin listener, login implementation or account-registration system is
implemented by these decisions. Existing operation eligibility/confirmation and
production NFS/deletion gates remain unchanged.

## Selected design profile and trust boundary

Use an external HTTPS proxy on the mover host with mandatory mutual TLS (client
certificates). An operator manually provisions the recorder certificate/key and
proxy allowlist. The proxy verifies the certificate and maps an explicitly
approved certificate to the one generator configured for this mover instance.
Trusting any certificate signed by a broad CA is insufficient. Certificate
identity must come from validated certificate material, not an HTTP header,
claimed host name, source IP or request body.

The proxy forwards only producer submissions through a protected pathname Unix
stream socket, for example `/run/file-mover/producer.sock`. The future mover
listener validates Linux SO_PEERCRED against the configured dedicated non-root proxy worker UID,
then requires exactly one proxy-generated `X-File-Mover-Generator` header. Socket
and parent ownership/permissions restrict access to the mover and approved proxy;
reject missing/unsafe ownership, writable parents, symlink replacement and wrong
peer UID. An abstract socket or an unrestricted loopback backend is not this
profile. Validate path custody before readiness and define safe stale-socket
handling before implementation; never unlink an arbitrary existing socket/name.

The proxy UID must be dedicated: peer credentials identify a UID, not a particular
executable. A compromised proxy, another process with that UID, privileged host
administrator or compromised recorder key remains within the trusted/compromised
boundary; this contract does not claim protection from them. Service/OS accounts,
namespace visibility and confinement must be qualified in the deployment matrix.
The local operator interface remains separate from the producer socket and retains
its explicit trusted-host scope. Never give the proxy access to operator ingress.

This proposal keeps TLS/certificate parsing outside the Rust binary. It does add
an external deployment component and manual credential administration. No proxy
product/version or configuration is qualified here; NGINX documentation below
illustrates primitives, not a complete working allowlist/configuration. Selecting
and testing the exact proxy/TLS package and protected-socket implementation are
release prerequisites. Any Rust API/features needed for peer credentials must
pass the normal dependency/license and SLES gates; no new dependency is chosen.

## Recorder contract

The recorder still sends metadata and waits for 202. It needs a configured HTTPS
URL, a trusted server CA and its manually provisioned client certificate/key.
It verifies the mover's server name/certificate. It sends no bearer token,
registration request or trusted identity header. Normal operation requires no
certificate parsing in recorder application code; its HTTP transport uses the
provisioned files. Setup/rotation is an operator duty, not a per-recording call.

```http
POST /api/v2/jobs HTTP/1.1
Host: mover.example.internal
Content-Type: application/json

{
  "generator_id": "recorder-host-a",
  "submission_id": "recording-0042",
  "source_path": "/mnt/recordings/current",
  "files": [
    {"name": "video/camera.bin"},
    {"name": "events.bin", "size_bytes": 0}
  ]
}
```

The HTTP client supplies framing/Content-Length. Files and folders stay unchanged,
with writers closed and completed data synchronized, until 202. Sizes remain
optional assertions, subfolders stay explicit and the destination comes from
startup configuration. `source_path` uses the mover-visible absolute path; the
mover must already have access to the source mount. No uploads, arbitrary remote
mounts or automatic generator-to-mover path rewriting are introduced. Different
mount naming requires separately configured/qualified mapping before use.

The body generator_id remains required in this profile and must equal both the
proxy identity and configured generator. Missing body identity is 400 invalid
submission; authenticated mismatch is 403 generator_not_authorized. There is no
new default identity and no implicit registry entry. The remote profile uses a
startup-validated ASCII identifier matching `[A-Za-z0-9][A-Za-z0-9._-]{0,127}`;
this does not retroactively change current local IDs. Multi-generator routing,
header-only identity and tokenless anonymous remote access are outside this slice.

After 202, the recorder may reuse original paths and has no delivery polling or
resume duty. On a missing response/temporary error, resend the same generator,
submission ID and equivalent body. Never generate a replacement ID to hide an
uncertain outcome. Authentication/permission/correction errors require logging
and operator correction; repeated retries never authorize source-path reuse.

## Binding and authorization sequence

1. At the edge, require verified server/client TLS, an approved certificate and
   the configured generator mapping. Disable TLS early-data submission. Missing,
   invalid, expired or unapproved credentials never fall back to body identity,
   source-IP trust, HTTP plaintext or the future tokenless profile.
2. Reject client-supplied `X-File-Mover-*` headers and Authorization with 400;
   a bearer credential is not supported here and is never silently downgraded.
   Strip unneeded forwarding/authentication metadata. Construct exactly one
   X-File-Mover-Generator from the approved mapping. Forwarded/X-Forwarded-For,
   certificate-subject headers and Host never grant identity or permissions.
3. Require the protected socket and approved proxy peer UID at the mover. Reject
   unknown peer with 403 caller_not_authorized. On a trusted peer, absent identity
   gives 403 caller_context_required; duplicate, empty, malformed, unknown-reserved
   or multiple-valued caller context gives 400 invalid_caller_context. No fallback
   to local operator privileges. Retain bounded, case-insensitive header parsing.
4. Match the resolved caller to the configured generator and validate the body,
   allowed source root and relative file mapping before store replay/admission or
   any source claim effect. Valid absolute paths outside that scope give 403
   source_not_authorized; malformed paths remain 400 input errors. Preserve the
   existing descriptor-relative traversal, symlink/mount refusal and root bindings.
5. Only after current authorization, use the existing generator/submission
   idempotency identity and replay-first acceptance. Certificate text/fingerprint,
   proxy connection and key rotation never become the submission key. Persist
   original routing/claim evidence; caller authorization cannot redirect a job.
   Revoked callers cannot replay even an existing job; accepted jobs retain their
   state/custody and normal background delivery. Authorization failure never
   cancels a job or deletes files.

The proxy and mover must each enforce the producer route boundary. A proxy
configuration mistake must not expose operator commands through the producer
listener. Sharing parsing/business logic does not mean sharing privileges.

| Ingress | Allowed operations | Other operations |
|---|---|---|
| Remote producer HTTPS, then producer Unix socket | Exact POST /api/v2/jobs with application/json | GET/other method on the exact jobs endpoint: 405; every other path/query variant: 404, no job existence disclosure |
| Existing protected local operator ingress | Current qualified health/status/retention/resume/reset routes and trusted-local submission | No additional remote operator role, registration or new controls granted |
| Direct remote connection to mover backend | None | No remote TCP producer listener; socket unavailable outside approved local boundary |

In particular job reads/lists, global retention, health details, resume,
reset-missing, registration and future controls are not exposed to the recorder.
Proxy health probes use separately authorized local access. Keep CORS disabled,
accept no browser/cookie authority and do not redirect producer POSTs.

## Errors, response integrity and bounded work

| Result | Recorder interpretation |
|---|---|
| 202 from the configured authenticated endpoint | All claims confirmed; paths may be reused. The mover includes its normal job/release receipt for optional logging; no delivery polling is required. Proxy never manufactures/caches this result. |
| TLS/server verification/connection failure, no HTTP response | No release evidence. Log and retry the same body/ID; provision/expiry errors need operator correction. TLS errors need not have JSON. |
| 400 malformed input/caller context or unsupported credential headers | Correction/configuration error; no path release. |
| 403 unapproved verified certificate, caller/body/source permission refusal | No path release; fix credentials/configuration. No tokenless fallback. |
| 404 denied route, 405 unsupported method | Correct the integration; do not infer job existence. |
| Edge 413 oversized or backend strict framing/input refusal | Correct the request; no path release. |
| 429 bounded ingress busy | Retry same ID/body after bounded delay; no path release. |
| Existing mover 503 temporary errors including handoff_pending/source_space_low/source_space_unavailable | Preserve current retry/review classification and exact body; no non-202 grants path release. |
| Edge 502/503/504, disconnect or response timeout | Outcome may be unknown, including already accepted/claimed work. Retry same ID/body; never infer rollback or discard state. |
| Existing 409 submission/review conflict | Preserve original work and use existing correction/operator-review rules; no new release evidence. |

Application authorization errors use the existing error envelope with stable
codes, retryable=false, source_paths_released=false and no job_id. Route refusal
also exposes no job details. Edge-generated auth/input errors use equivalent
minimal JSON when HTTP is possible; transport failures may have no JSON or an
unparseable intermediary response. The recorder never treats such a response as
202 or as proof that the mover did nothing.

Preserve exact upstream status/body for mover replies; no success rewriting,
response caching, automatic upstream POST retries, request mirroring, or redirects.
Proxy sends a single canonical HTTP/1.1 request with one Content-Length, no
Transfer-Encoding/Expect and a fixed backend Host. It rejects ambiguous framing
before forwarding and preserves JSON bytes, submission ID and optional matching
Idempotency-Key. Retain hostile HTTP/JSON and duplicate-field tests at both hops.

Carry forward 8 KiB/64-header, 64 KiB body, 256-file and 128-byte ID limits, with
reserved proxy-header overhead counted at the backend. Proposed ingress bounds:
no more than six active producer requests within the service's eight-connection
budget, reserving two for local operations; no unbounded proxy request queue or
temporary body files. Reject excess with 429. Retain the service's five-second
request read and ten-second total claim/probe handoff budget. Proposed proxy
request-body read budget is five seconds, upstream response budget thirty seconds,
and recorder end-to-end timeout forty-five seconds. These are design values to
qualify, not measured latency/SLOs. Existing admission/job/byte limits still apply.

## Credential lifecycle and operational failure

Provision keys/certificates and proxy mappings out of band; protect private keys
and never log credentials, full certificate material, Authorization or request
bodies. Use bounded nonsecret principal/result/correlation diagnostics. The
proxy's authenticated identity is separate from NFS authorization/ownership.
HTTPS success cannot authorize takeover, bypass source/destination pins or prove
that old NFS effects are fenced.

For initial rotation/revocation, stop new ingress, close existing TLS sessions
and finish/stop admitted HTTP requests before replacing approved certificate
mappings. Restart the proxy with the reviewed mapping and verify denied old
credentials, including session resumption; disable resumption until that is
qualified. Accepted jobs continue under original state. A new approved certificate
mapped to the same generator can retry a lost response against the original job.
No hot revocation, automatic certificate enrollment/renewal, issuance recovery or
service-issued secret storage is implied. Recovery from a compromised key is an
operator procedure; do not activate a second mover or replace its database.

## Finite acceptance matrix (pending)

All cases below are obligations, **not passing tests**. RA IDs refine SC-043 and
SC-082–086; they do not replace requirement IDs. L1-SEC-008 binds authorization;
L1-API-007/008/009/010 retain body, handoff, replay and error obligations.

| Case | Required evidence before enabling this profile |
|---|---|
| RA-01 | Default-off/current loopback behavior unchanged; unsafe/missing socket ownership, UID, principal or config refuses before readiness; no stale socket clobber. |
| RA-02 | Approved TLS client -> exact proxy principal -> allowed source: 202 only after all claims, nested/optional-size behavior and destination pins unchanged. |
| RA-03 | Missing/untrusted/expired certificate, incorrect server identity and unmapped otherwise-valid client certificate: denied before submission; no job/effects/identity fallback. |
| RA-04 | No Authorization/identity HTTP header from a valid certificate client succeeds; body-only identity without approved transport fails. Missing body ID is 400, mismatch is 403. |
| RA-05 | Spoofed reserved/forwarded headers, duplicate/case-variant context and unsupported bearer credentials cannot gain another caller; fixed mapping/body match enforced. |
| RA-06 | Wrong local UID, abstract/foreign/replaced socket and direct TCP bypass fail, including a local unprivileged attacker; same-UID/root trust limits documented. |
| RA-07 | Allowed and out-of-root/malformed paths, symlink and mount escapes: reject before store effects; body never grants route/source permissions. |
| RA-08 | Enumerate every current read/control/health/registration route and path/query/encoding variant at both hops; producer gets no operator access or cross-job information. |
| RA-09 | Rotate to a new approved cert for same generator after a lost 202; same ID/body resolves to original job/destination without duplicate claims. Old/expired credentials and resumed sessions refuse after controlled revocation. |
| RA-10 | Revoke a caller after partial/complete acceptance: no authenticated replay while revoked; original state/source and background recovery retained. No false path release or automatic cancellation. |
| RA-11 | Proxy death/timeouts before forwarding, during partial claim and after 202 generation: same-ID recovery, no manufactured success, no automatic duplicate POST and no data loss. |
| RA-12 | Both hops reject malformed lengths, transfer framing, duplicate JSON and oversize/slow input; one request cannot be interpreted as two; normal reply fields preserved. |
| RA-13 | Finite concurrent producer flooding/slow clients: six producer/eight total bounds, bounded buffering, 429 and responsive local status/control without filesystem work on Tokio. |
| RA-14 | Native source-low/unavailable and destination outage after admission retain existing errors, claim/review/retry behavior, producer path reuse and manifest semantics. |
| RA-15 | Exact proxy/TLS package, account/socket confinement, credential provisioning/restart, TLS settings and secret-redaction logs qualified in pinned SLES-container deployment; report shared-kernel limits. |
| RA-16 | Every changed Rust build/test through production and qualification GNU/glibc-2.22 zigbuild/ELF/exact-target gates; requalify any new crate feature/native dependency. Record actual end-to-end profile evidence and DOC-01/04/05 instructions. |

## References and next implementation boundary

Linux documents pathname-socket permissions and SO_PEERCRED for connected Unix
stream sockets in [unix(7)](https://man7.org/linux/man-pages/man7/unix.7.html).
NGINX documents certificate verification in its
[SSL module](https://nginx.org/en/docs/http/ngx_http_ssl_module.html) and Unix
upstreams/header construction in its
[proxy module](https://nginx.org/en/docs/http/ngx_http_proxy_module.html).
These support available mechanisms; the composed access policy above is this
project's design and is not validated by those references.

Next resolve NFS authority/fencing for FR-03 and select the exact remote proxy
package/provisioning profile. Before any remote enablement, implement a narrow
producer ingress with peer/principal/route enforcement and RA-01/04/05/06/08
local denial tests, then qualify the real TLS/proxy chain and remaining matrix.
Do not simply widen Config.bind or enable the current operator listener remotely.
