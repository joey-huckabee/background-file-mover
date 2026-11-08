# P01 session and route access boundary — candidate

Current engineering authority: [increment-120 closeout](API-CONTRACT-CLOSEOUT.md).
It supersedes conflicting proposal details below, especially per-job receipt
identity/storage, bounds and replay scope. Group53 approves the four defaults and freezes the written v2 engineering
contract; unimplemented routes/security and runtime qualification remain separate.

2026-11-03. Engineering completion of proposal package 1/F06. This document is
a candidate contract, not a freeze, new product approval or working ingress.
Groups 25-29/46-48 already settle the account/session/logout behavior; those
choices are not reopened. Proxy selection/deployment/RA execution remains P02/P03.
The existing prototype does not implement the session or security mechanisms here.

## Proposed route separation

Keep the existing proposed fifteen-route inventory; adding this table does not
approve the remaining inventory/read schemas. An authenticated producer never
inherits admin or trusted-local operator access. The eventual ingress must
enforce the separation, not rely on hiding controls in the dashboard.

| Method and path | Required boundary | Mutation protection |
|---|---|---|
| POST /api/v2/jobs | Approved producer identity and generator binding | Producer trust, not dashboard cookie/CSRF |
| GET /healthz | Explicit deployment-probe access | No state change or inactivity renewal; do not expose it through producer ingress by accident |
| POST /api/v2/admin/login | Same-origin dashboard login | Exact Origin and JSON media type before credential checking; no existing session token required |
| POST /api/v2/admin/logout | Valid dashboard session | Origin plus session-bound CSRF token; revoke every session |
| GET /api/v2/admin/session | Valid dashboard session | Read-only; optional deliberate interaction follows the activity rule below |
| GET /api/v2/admin/jobs | Valid dashboard session | Read-only; activity rule below |
| GET /api/v2/jobs/{job_id} | Dashboard session or protected trusted-local operator transport | Dashboard activity rule below; no producer access |
| GET /api/v2/retention | Dashboard session or protected trusted-local operator transport | Same read rule; no filesystem probe |
| GET /api/v2/jobs/{job_id}/retention | Dashboard session or protected trusted-local operator transport | Same read rule; no post-clear inventory |
| POST /api/v2/admin/jobs/cancel | Valid dashboard session | Origin plus CSRF; selected-job confirmation remains separate |
| POST /api/v2/admin/jobs/retry | Valid dashboard session | Origin plus CSRF; frozen reviewed-state header remains separate |
| POST /api/v2/admin/jobs/clear-history | Valid dashboard session | Origin plus CSRF; existing clear confirmation/safe-stop requirements |
| POST /api/v2/admin/jobs/delete-data | Valid dashboard session | Origin plus CSRF; exact-file confirmation remains separate |
| POST /api/v2/jobs/{job_id}/resume | Protected trusted-local operator transport only | Existing audited command/preconditions; never exposed by producer or dashboard ingress |
| POST /api/v2/jobs/{job_id}/reset-missing | Protected trusted-local operator transport only | Existing audited command/preconditions; never exposed by producer or dashboard ingress |

Trusted-local transport authentication is not achieved merely by a caller
claiming to be local or supplying an identity header. The selected protected
transport/permissions and frontend allowlists must be qualified before exposure.
Do not invent an unauthenticated TCP fallback. Producer TLS/caller binding keeps
the separate [remote access obligations](../REMOTE-API-ACCESS-CONTRACT.md).

## Candidate cookie, Origin and CSRF contract

- Use the proposed opaque server-side `__Host-mover_admin` cookie with Secure,
  HttpOnly, Path=/, SameSite=Strict, no Domain and no persistent browser expiry.
  HTTPS is required for remote dashboard access. Server expiry/revocation wins
  over a browser-restored cookie. No session/cookie secret is returned in JSON.
- The configured dashboard origin is an explicit HTTPS scheme/host/port origin,
  not an origin inferred from an untrusted Host/forwarding header. Match against
  that configured origin; reject missing, `null`, multiple or mismatching Origin
  on login and cookie-authenticated mutations. No Referer-only fallback or CORS
  credential sharing is proposed. Validate the effective dashboard target authority
  against configuration through the trusted TLS/ingress boundary, including when
  GET omits Origin; a caller-provided Host value never defines the allowed origin.
  Forwarded identity/origin inputs require the
  selected trusted ingress boundary; a public caller cannot assert them.
- Successful login returns the already proposed `{"authenticated":true}` body,
  its session cookie and a `Mover-CSRF-Token` response header. Valid session GET
  also returns that header so a same-origin page reload can obtain it. Responses
  carrying authentication/session material use `Cache-Control: no-store`.
- CSRF tokens are unpredictable, session-bound server values. Require the token
  in a `Mover-CSRF-Token` request header for logout and all dashboard mutations;
  compare without timing-dependent text matching. Token presence is not itself
  session authentication. Never accept it from a URL/query string or use it as
  the retry review precondition or deletion confirmation.
- In OpenAPI, cookie and CSRF schemes for a mutation appear in **one** security
  requirement object (AND). Separate objects would mean OR and are incorrect.
  Origin is a separate required header/precondition; OpenAPI security metadata
  alone cannot prove the server enforces it.
- Successful logout clears the browser cookie and revokes all server sessions
  and their CSRF tokens before the approved 204 response. Host-local password
  changes and service restart likewise invalidate all previous sessions.

Exact entropy/encoding, secure credential storage, login throttling and bounded
session storage remain implementation/security design obligations. They are not
permission to ship weak tokens, plaintext passwords or unbounded login traffic.
This candidate does not select a proxy, new account feature or token framework.

## Inactivity and deliberate interaction

Keep the approved configurable 30-minute default. Login starts the server-side
monotonic inactivity clock. Successful authorized dashboard actions renew it;
logout revokes instead. Failed authentication, rejected actions, polling,
auto-refresh and trusted-local operator/producer traffic do not renew it. Exact
transport replay and a batch with no newly admitted action do not renew it either;
a fresh deliberate view/navigation can use the read activity signal.

For a deliberate dashboard read/navigation, propose the request header
`Mover-Admin-Activity: interaction`. Such a read renews only after a valid session,
valid CSRF token and the configured dashboard target authority are checked.
Do not require Origin on GET: ordinary same-origin browser GET fetches omit it
and scripts cannot set that forbidden header. If Origin is present, require an
exact configured-origin match. If Sec-Fetch-Site is present, require same-origin;
its absence is not a substitute for the mandatory session-bound CSRF token.
Cross-origin credentialed CORS/preflight remains disabled, so an attacker cannot
obtain the token or submit the custom activity/CSRF headers through allowed CORS.
The ordinary GET remains read-only without the activity marker. Unknown/multiple marker values are validation
errors, not implicit activity. Background polling and automatic retransmissions must omit the marker; the UI
must not keep submitting it during an idle open tab. This marker is an activity
signal, not proof of a human gesture, a job identifier or an authorization token.
No new activity endpoint is added to the fifteen-route inventory.

Activity, token refresh and session renewal must never refresh an already frozen
retry context or deletion confirmation. They must not change command identity,
release a later review or restart a transfer.

## Global revocation and action admission

Each new durable action decision must be authorized against the current session
expiry/account revocation generation at its admission boundary. Revocation and
admission must have a defined serialization point; checking only at HTTP parse
time is insufficient for a delayed/queued batch. If logout wins first, no new
occurrence may be admitted with that old session. Earlier durably admitted work
can finish. Do not fabricate a complete count summary after a partial batch loses
authorization; subsequent requests require sign-in.

Authenticate exact retry replays before disclosing stored receipts. Session
renewal does not change the trusted account principal or the original frozen
command context. Reads likewise require valid authorization before selecting
protected state/receipt results. Responses already authorized/sent cannot be
recalled from a browser or network buffer. Global sign-out prevents subsequent
authorization; it is not file erasure or a transfer cancellation mechanism.

Transfers belong to the service. Logout, inactivity expiry, password changes
and session revocation never pause, cancel or restart already admitted transfers.

## Proposed denial precedence and remaining proof

1. Enforce transport/framing/aggregate limits before effects. Proxy/TLS failures
   need not have a mover JSON body; existing transport/no-response cases remain.
2. For protected operations authenticate before any job/receipt disclosure.
   Missing/expired/revoked sessions retain approved 401/sign-in behavior.
3. Login checks its same-origin/media-type boundary before checking credentials.
   For valid sessions reject failed Origin/CSRF/activity protection with candidate
   403 `admin_request_forbidden`, without changing job/session activity state.
   Marked GETs use their CSRF/optional-browser-header rule above; missing Origin
   alone is not a failure for those reads.
   Malformed bounded bodies remain separate whole-request validation errors.
4. Validate complete action context/selection/confirmation, recognize authorized
   exact retry receipts, then make transactional per-occurrence state decisions.
   Preserve receipt-before-new-eligibility and no side effects from invalid context.

The [route schemas and error registry candidate](ROUTE-SCHEMAS.candidate.md) now
supplies the fifteen-operation wire proposal and bounds. Required future tests include cross-origin login/logout,
missing/wrong/session-swapped CSRF tokens, idle polling versus deliberate reads,
global revocation racing queued/bulk actions, revoked-session receipt disclosure,
unchanged frozen retry intent after renewal, and producer/local/admin segregation.
No authenticated HTTP, transaction-race or remote deployment test is claimed here.

Security rationale: [OWASP CSRF prevention guidance](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html)
recommends server-validated protection for cookie-authenticated mutations.
This project-specific candidate still requires implementation and adversarial tests.

Browser compatibility: [Fetch request Origin rules](https://fetch.spec.whatwg.org/#append-a-request-origin-header)
and [forbidden request headers](https://fetch.spec.whatwg.org/#forbidden-request-header)
explain why marked same-origin GETs cannot require a script-supplied Origin.
