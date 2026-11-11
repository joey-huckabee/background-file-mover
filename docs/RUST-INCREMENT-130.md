# Increment 130: separate admin HTTPS listener and sign-in

The user authorized the next dashboard step on 2026-11-11 and confirmed the
separate-listener design (audience isolation; no producer client certificate for
browsers). This slice connects the [session core](RUST-INCREMENT-129.md) to a
native admin HTTPS listener. It adds no dependency, job read, action, proxy or
real state. [Setup guide](ADMIN-HTTPS-SETUP.md).

## Implemented boundary

- **Configuration.** Optional `admin_ingress`: own bind/port (port must equal the
  authority port and differ from the producer listener), exact authority, server
  DER chain/PKCS8 key/trust anchors, account directory and inactivity timeout
  (default 1800 s). Requires `native_ingress`. Path overlap checks keep the
  account directory and admin credentials apart from state, operator, payload and
  producer credential scopes. Account commands also exclude admin credential parents.
- **Startup.** On the guarded supervisor, after state compatibility: load the
  account through the existing account-file custody checks, validate it against
  the state instance, load and verify the server chain against the authority,
  bind. A missing or invalid account or credential refuses startup.
- **TLS.** Server-authenticated only (no client certificates), TLS 1.3/1.2,
  ALPN `http/1.1`, no tickets, early data or session cache. Same provider and
  credential readers as the producer listener.
- **Admission.** The listener shares the fixed TLS executor and the global
  8-connection budget, plus a 1-connection admin permit. Permits are taken before
  TLS work; saturation closes the connection without a plaintext reply. Accept
  order is private operator, admin, then producer. Handshakes use the existing
  5-second accepted-time deadline and watchdog.
- **Routes.** `GET /` (fixed document), `POST /api/v2/admin/login`,
  `GET /api/v2/admin/session`, `POST /api/v2/admin/logout`. Every other target,
  including producer, operator and job routes, is 404. The producer listener
  already refuses admin routes (403) and cookies; the operator socket has no admin routes.
- **Precedence.** Framing → forwarded/identity headers (400) → exact `Host` (403)
  → route/method (404/405) → for session and logout, authentication (401) before
  Origin/CSRF (403). Login checks exact Origin (403) and `application/json` (415)
  before parsing (400 `invalid_json`) and before any verification.
- **Login.** Strict `{username,password}`, byte bounds, no trimming. 200
  `{"authenticated":true}` with `__Host-mover_admin` (Secure, HttpOnly, Path=/,
  SameSite=Strict, no Domain/expiry) and `Mover-CSRF-Token`. 401 exact
  `Invalid username or password.`; 429 `rate_limited` with `Retry-After: 60`;
  503 `service_busy` for slot/capacity, a lost revocation race or the 10 s
  verification deadline; 500 for entropy/verifier failure.
- **Session.** 200 `{"authenticated":true,"inactivity_timeout_seconds":N}` plus
  the CSRF header. Unmarked reads never renew. `Mover-Admin-Activity: interaction`
  requires the session CSRF token; supplied Origin must match and supplied
  `Sec-Fetch-Site` must be `same-origin`; only then does activity renew. Other
  marker values are 400.
- **Logout.** Requires exact Origin and the session's own CSRF token, then revokes
  every session; 204 with an expiring cookie. Transfers are unaffected.
- **Responses.** All carry `Cache-Control: no-store`, `nosniff`,
  `Referrer-Policy: no-referrer` and `Connection: close`. The document adds a CSP
  admitting exactly its inline style and script by SHA-256, `frame-ancestors
  'none'`, `X-Frame-Options: DENY` and COOP.
- **Page.** One self-contained document (inline CSS/JS, no external assets, no
  `innerHTML`). Sign-in form and a signed-in shell with **Sign out everywhere**.
  It states that job views are not connected; it shows no sample data.
- **Shutdown.** After the TLS executor exits, the session manager is closed and
  any running verifier is joined before the instance guard is released.

## Not in this slice

- Job/history/retention reads and actions (next increments).
- Live password activation over IPC; password changes still need a stop/restart.
- Admin certificate live reload.
- Browser automation evidence; the tests below use a real TLS client against the
  real service, not a browser.

## Tests

Unit: RFC 4648 base64 vectors and CSP hash form; the document inlines its assets
with a CSP admitting only them and no external references; exactly-one-cookie parsing.

Real service over HTTPS (`tests/tls_listener/admin.rs`, SLES gate):

- Startup refuses without a provisioned account; invalid admin configurations
  (shared producer listener, authority/bind port mismatch, account inside state)
  refuse before listening.
- Document headers/CSP; 401 without a session; login Origin (missing, `null`,
  foreign, `http://`), media type and malformed/unknown/out-of-bounds JSON refused
  before verification; exact 401 body; cookie attributes and CSRF header.
- Session read, marked-read CSRF/Origin/Fetch-Metadata rules and invalid marker.
- Two sessions; logout refuses missing Origin, wrong and session-swapped CSRF;
  global logout revokes both; an admitted producer transfer still commits.
- Wrong Host 403, forwarded header 400, producer/job/operator/health routes 404
  on the admin listener; admin routes refused on producer and operator audiences.
- Five-attempt limit then 429 with `Retry-After: 60`, independent of username.
- Restart clears sessions; logs contain no password, CSRF or session token.

Design rows covered at service level: A08 (startup part), A12-A15, A20 (rate
limit), A22-A23, A26 (offline document/CSP; keyboard behavior not browser-tested),
A27. Still open: A16-A19 races and expiry are proven at unit level only (increment129);
A21 64-session limit at unit level; A24-A25 TLS saturation/panic paths for the
admin listener are not separately tested.

## Validation status

Pending PR CI for both full SLES modes and independent review.
