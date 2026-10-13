# Generator registration and access draft

The recorder will contact a remote mover. This proposal adds registered generator
identity, token issuance and configurable tokenless submission to the
[REST contract](REST-API-DRAFT.md). Enrollment and tokenless policy are proposals
for review; remote submission is the confirmed deployment use case. Supporting
local clients uses the same API and handoff semantics.

## Source access on remote deployments

**Confirmed deployment:** the remote mover has access to the source NFS mount.
It performs claiming directly against that shared filesystem; no REST payload
upload or source-side transfer agent is required for this use case. Qualify the
export/mount behavior and confirm path mapping before implementation.

Remote REST carries metadata, not file contents. The mover must directly access
the submitted source files, for example through the same NFS export used by the
generator. If mount paths differ, define an administrator-approved mapping of
generator-visible roots to mover-visible roots and normalize both to the same
source reservation/custody scope. Never derive unrestricted mount locations
from a client's registration payload.

The 202 handoff still requires all same-filesystem claims and durable receipts.
Generator parents/writers remain unchanged until 202, even though claim operations
occur from another host. NFS consistency/durability and custody must be qualified
for the actual shared export. If the source exists only on the generator host,
this metadata API cannot claim it remotely: a source-side agent or explicit upload
protocol is a separate design decision, not an HTTP-authentication feature.

## Token authentication

Use an opaque per-generator token in the standard header:

```http
Authorization: Bearer <generator-token>
```

The token resolves to a registered identity and permissions. No separate generator
identity header is necessary. A matching body `generator_id` remains supported;
it may be omitted when authentication or an explicitly configured tokenless
profile supplies identity. Any supplied identity must match the authorized one.
Scope retries by resolved generator identity and submission ID, not token text,
so credential rotation does not duplicate jobs.

Use HTTPS for remote clients, with the existing external TLS/proxy boundary unless
the TLS architecture is separately revised. Restrict the backend to that proxy;
accept forwarded identity only from a trusted authenticated proxy configuration.
Local clients may use the same token/HTTPS API. Local plaintext is only within a
deliberately protected loopback/IPC boundary, not a substitute for remote TLS.
Bearer tokens require protection in transport and storage.
[RFC 6750](https://www.rfc-editor.org/rfc/rfc6750).

Generate high-entropy opaque secrets using qualified secure randomness; persist
only token verifiers and nonsecret metadata. Redact Authorization, enrollment
credentials and issuance responses from logs. Support revoke/rotate, bounded
rate limits and separate operator privileges. Registration does not grant admin
access or let a generator choose source permissions/destinations. SDK/runtime
dependencies for these facilities remain unqualified; no OAuth server, JWT or
identity platform is automatically required for this small token registry.

## Proposed registration contract

An operator first authorizes the generator identity, allowed source roots, route
and permissions, and supplies a scoped enrollment credential out of band. The
generator can then obtain its normal submission token through REST:

```http
POST /api/v2/generators/register HTTP/1.1
Authorization: Bearer <scoped-enrollment-credential>
Content-Type: application/json

{
  "generator_id": "recorder-host-a",
  "registration_id": "enrollment-001"
}
```

```json
{
  "generator_id": "recorder-host-a",
  "token_type": "Bearer",
  "access_token": "<issued-generator-token>"
}
```

Issue the response with 201, Cache-Control: no-store and a durable registry entry
before exposing the credential. The generator securely stores the token and
then uses it for submissions; it does not register for each recording. Bind the
enrollment credential to the preauthorized identity and scope, with expiration
and controlled use. Arbitrary unauthenticated registration must not obtain a
trusted existing generator identity or unrestricted file-moving permissions.

Define lost issuance-response recovery before implementing one-use enrollment:
the client cannot reconstruct a token from a stored verifier. A minimal initial
recovery is operator re-enrollment that revokes the orphaned issuance. Automatic
safe registration replay is an alternative requiring an explicit secret-delivery
design; registration_id alone does not justify returning a secret to any caller.
The normal recording submission replay contract is unchanged.

## Requests without headers or tokens

The service handles missing credentials according to explicit startup policy:

| Request | Handling |
|---|---|
| Valid token, body identity omitted | Resolve generator from token and process within its source scope |
| Valid token and matching body identity | Process as that generator |
| Invalid/revoked token or conflicting identity | Reject; never fall back to tokenless privileges |
| No token, body identity provided | Accept only if an operator-enabled tokenless profile authorizes that identity/source scope within its configured trust boundary |
| No token and no identity | Resolve an explicitly configured restricted default profile, or reject; never guess a registered generator |

Tokenless support is additive, disabled by default and independently configurable
for local/remote ingress. It does not permit self-asserted identity to gain a
registered token owner's permissions. Restrict its source namespace, routes,
admission budgets and submission capabilities; do not expose operator controls
or registration-token issuance through it. Record its identity as tokenless,
not cryptographically authenticated. Remote tokenless access requires an explicit
deployment trust decision or another authenticated transport/proxy boundary.
Loopback address alone does not identify which local process made the request.

Return structured authentication/authorization errors (401 for missing/invalid
required credentials, 403 for an authenticated principal outside its permission
scope). These are correction errors for the recorder, not temporary retry loops.
Apply authorization to every read/control route as well as submission, without
leaking other generators' jobs. Authentication mode cannot change claiming,
source-retention, manifest or 202 guarantees.

## Decisions before implementation

Confirm source path mapping; choose enrollment bootstrap and
lost-response recovery; set token lifetime/rotation and secure recorder storage;
define local/remote tokenless profiles and operator roles. Derive requirements,
threat/failure tests and dependency qualification once those choices are settled.
