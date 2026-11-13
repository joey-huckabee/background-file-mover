//! Separate native admin HTTPS audience: one fixed sign-in/shell document and the
//! three session routes. No producer submission, operator routes, job reads or
//! actions are reachable here; every other target is 404.
use crate::{
    Config, http, ingress,
    session::{Activity, AuthError, LoginError, Sessions},
};
use serde::{Deserialize, Serialize};
use std::{net::SocketAddr, path::Path, sync::Arc, time::Duration};
use zeroize::Zeroizing;

const COOKIE: &str = "__Host-mover_admin";
const LOGIN_DEADLINE: Duration = Duration::from_secs(10);
const REQUEST_DEADLINE: Duration = Duration::from_secs(5);
/// Bound on waiting for admitted admin actions during logout.
const LOGOUT_SETTLE: Duration = Duration::from_secs(10);
/// Live-update streams (see docs/dashboard/LIVE-UPDATES-DESIGN.md).
const STREAMS: usize = crate::tls_executor::STREAM_JOBS;
const STREAM_HEARTBEAT: Duration = Duration::from_secs(15);
const STREAM_COALESCE: Duration = Duration::from_millis(250);
const STREAM_WRITE: Duration = Duration::from_secs(2);

#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct AdminIngress {
    pub bind: SocketAddr,
    pub authority: String,
    pub server_certificates: Vec<String>,
    pub server_key: String,
    pub server_ca_certificates: Vec<String>,
    pub account_directory: String,
    #[serde(default = "idle_default")]
    pub inactivity_timeout_seconds: u32,
}
fn idle_default() -> u32 {
    1800
}

fn overlaps(a: &Path, b: &Path) -> bool {
    a.starts_with(b) || b.starts_with(a)
}

impl AdminIngress {
    pub(crate) fn credential_paths(&self) -> Vec<&str> {
        self.server_certificates
            .iter()
            .chain(&self.server_ca_certificates)
            .map(String::as_str)
            .chain(std::iter::once(self.server_key.as_str()))
            .collect()
    }

    /// Account directory and credential parents must not overlap a current or
    /// retained payload root. Called for current roots here and for every
    /// retained root in the state preflight, before any credential I/O.
    pub(crate) fn validate_payload_root(&self, root: &str) -> Result<(), &'static str> {
        let root = Path::new(root);
        if overlaps(Path::new(&self.account_directory), root) {
            return Err("admin account directory overlaps payload scope");
        }
        for path in self.credential_paths() {
            let parent = Path::new(path)
                .parent()
                .ok_or("credential parent required")?;
            if overlaps(parent, root) {
                return Err("admin credentials overlap payload scope");
            }
        }
        Ok(())
    }

    pub(crate) fn validate(&self, c: &Config) -> Result<(), &'static str> {
        let Some(native) = &c.native_ingress else {
            return Err("admin_ingress requires native_ingress");
        };
        let (_, port) = crate::native::authority_name(&self.authority)?;
        if port != self.bind.port() || self.bind.port() == 0 {
            return Err("admin authority port must equal its explicit bind port");
        }
        if self.bind.port() == c.bind.port()
            && (self.bind.ip() == c.bind.ip()
                || self.bind.ip().is_unspecified()
                || c.bind.ip().is_unspecified())
        {
            return Err("admin listener must not share the producer listener");
        }
        if !(1..=8).contains(&self.server_certificates.len())
            || !(1..=16).contains(&self.server_ca_certificates.len())
            || !(1..=2_147_483_647).contains(&self.inactivity_timeout_seconds)
        {
            return Err("admin TLS policy or inactivity timeout exceeds bounds");
        }
        let account = Path::new(&self.account_directory);
        if !crate::absolute(&self.account_directory) || self.account_directory.len() > 4000 {
            return Err("canonical bounded admin account directory required");
        }
        let state = Path::new(&c.state_database)
            .parent()
            .ok_or("state parent required")?;
        let operator = Path::new(native.operator_socket())
            .parent()
            .ok_or("operator parent required")?;
        self.validate_payload_root(&c.source_root)?;
        self.validate_payload_root(&c.destination_root)?;
        let mut guarded = vec![state, operator];
        for path in native.credential_paths() {
            guarded.push(
                Path::new(path)
                    .parent()
                    .ok_or("credential parent required")?,
            );
        }
        if guarded.iter().any(|g| overlaps(account, g)) {
            return Err("admin account directory overlaps state, payload, operator or credentials");
        }
        for path in self.credential_paths() {
            if !crate::absolute(path) || path.len() > 4096 {
                return Err("canonical bounded admin credential path required");
            }
            let parent = Path::new(path)
                .parent()
                .ok_or("credential parent required")?;
            if overlaps(parent, account) || overlaps(parent, state) || overlaps(parent, operator) {
                return Err(
                    "admin credentials must be separate from account, state, operator and payload",
                );
            }
        }
        Ok(())
    }
}

/// Loaded startup policy: TLS acceptor, exact origin and the fixed document.
pub(crate) struct Admin {
    acceptor: tokio_rustls::TlsAcceptor,
    /// Accepted Host values: configured authority, plus the port-less form on 443.
    hosts: Vec<String>,
    /// Browser origin serialization (URL Standard): default port omitted.
    origin: String,
    idle_seconds: u32,
    pub(crate) sessions: Sessions,
    /// Read-only configuration snapshot taken at startup (no secrets).
    settings: serde_json::Value,
    /// "State may have changed" version, bumped by the store worker.
    changes: tokio::sync::watch::Sender<u64>,
    /// Concurrent live-update streams, separate from request budgets.
    streams: Arc<tokio::sync::Semaphore>,
    document: String,
    csp: String,
}

pub(crate) struct Prepared {
    admin: Arc<Admin>,
    listener: std::net::TcpListener,
}
pub(crate) struct Bound {
    pub(crate) admin: Arc<Admin>,
    pub(crate) listener: tokio::net::TcpListener,
}

impl Prepared {
    /// Synchronous startup on the guarded supervisor: credentials, record, bind.
    pub(crate) fn load(
        service: &Config,
        config: &AdminIngress,
        record: crate::account::Record,
    ) -> Result<Self, Box<dyn std::error::Error>> {
        use crate::native::context;
        let chain = crate::native::certificates(&config.server_certificates)
            .map_err(|e| context("admin_ingress.server_certificates", e))?;
        let server_ca = crate::native::certificates(&config.server_ca_certificates)
            .map_err(|e| context("admin_ingress.server_ca_certificates", e))?;
        let settings = settings(service, config, &chain, &server_ca)?;
        let key = crate::native::private_key(&config.server_key)
            .map_err(|e| context("admin_ingress.server_key", e))?;
        crate::native::verify_server_chain(&config.authority, &chain, server_ca)?;
        let server = crate::tls::admin_server_config(chain, key)
            .map_err(|_| "admin TLS policy/key refused")?;
        let (document, csp) = document();
        let listener = std::net::TcpListener::bind(config.bind)?;
        listener.set_nonblocking(true)?;
        Ok(Self {
            admin: Arc::new(Admin {
                acceptor: tokio_rustls::TlsAcceptor::from(Arc::new(server)),
                hosts: browser_authority(&config.authority).0,
                origin: browser_authority(&config.authority).1,
                idle_seconds: config.inactivity_timeout_seconds,
                sessions: Sessions::new(
                    record,
                    Duration::from_secs(config.inactivity_timeout_seconds.into()),
                ),
                settings,
                changes: tokio::sync::watch::Sender::new(0),
                streams: Arc::new(tokio::sync::Semaphore::new(STREAMS)),
                document,
                csp,
            }),
            listener,
        })
    }
    /// Sender the store worker uses to signal "state may have changed".
    pub(crate) fn changes(&self) -> tokio::sync::watch::Sender<u64> {
        self.admin.changes.clone()
    }
    pub(crate) fn activate(self) -> std::io::Result<Bound> {
        Ok(Bound {
            admin: self.admin,
            listener: tokio::net::TcpListener::from_std(self.listener)?,
        })
    }
}
impl Bound {
    pub(crate) fn address(&self) -> std::io::Result<SocketAddr> {
        self.listener.local_addr()
    }
}

impl Admin {
    /// Server-authenticated TLS within the accepted-time deadline; HTTP/1.1 only.
    pub(crate) async fn accept(
        &self,
        stream: tokio::net::TcpStream,
        deadline: tokio::time::Instant,
    ) -> Option<ingress::Stream> {
        if tokio::time::Instant::now() >= deadline {
            return None;
        }
        let accept = self.acceptor.accept_with(stream, |connection| {
            connection.set_buffer_limit(Some(65536));
        });
        let stream = tokio::time::timeout_at(deadline, accept).await.ok()?.ok()?;
        if tokio::time::Instant::now() >= deadline
            || stream.get_ref().1.alpn_protocol() != Some(b"http/1.1")
        {
            return None;
        }
        Some(ingress::Stream::Tls(Box::new(stream)))
    }
}

/// One request per connection, then close.
pub(crate) async fn connection(
    mut stream: ingress::Stream,
    admin: Arc<Admin>,
    observer: std::sync::mpsc::SyncSender<crate::OperatorWork>,
    release_request_permits: Box<dyn FnOnce() + Send>,
) {
    let reply = match tokio::time::timeout(REQUEST_DEADLINE, crate::request(&mut stream)).await {
        Err(_) => Reply::error(408, "request_timeout"),
        Ok(Err(e)) => Reply::error(
            e.status,
            match e.error {
                Some(code @ ("request_too_large" | "request_headers_too_large")) => code,
                _ => "invalid_http",
            },
        ),
        Ok(Ok(request)) if request.head.target == b"/api/v2/admin/events" => {
            match boundary(&admin, &request) {
                Some(reply) => reply,
                None => return events(stream, admin, request, release_request_permits).await,
            }
        }
        Ok(Ok(request)) => handle(&admin, &request, &observer).await,
    };
    reply.write(&mut stream, &admin.csp).await;
}

struct Reply {
    status: u16,
    content_type: &'static str,
    body: Vec<u8>,
    /// May carry session secrets (Set-Cookie, CSRF); cleared on drop.
    headers: Zeroizing<String>,
    document: bool,
}
impl Reply {
    fn json(status: u16, body: serde_json::Value) -> Self {
        Self {
            status,
            content_type: "application/json",
            body: serde_json::to_vec(&body).expect("fixed response serialization"),
            headers: Zeroizing::new(String::new()),
            document: false,
        }
    }
    fn error(status: u16, code: &'static str) -> Self {
        Self::json(status, serde_json::json!({ "error": code }))
    }
    fn forbidden() -> Self {
        Self::error(403, "admin_request_forbidden")
    }
    fn unauthenticated() -> Self {
        Self::json(401, serde_json::json!({"error":"authentication_required"}))
    }
    fn method(allow: &'static str) -> Self {
        let mut r = Self::error(405, "method_not_allowed");
        r.headers.push_str(&format!("Allow: {allow}\r\n"));
        r
    }
    fn header(mut self, name: &str, value: &str) -> Self {
        self.headers.push_str(name);
        self.headers.push_str(": ");
        self.headers.push_str(value);
        self.headers.push_str("\r\n");
        self
    }
    async fn write(self, stream: &mut ingress::Stream, csp: &str) {
        let reason = match self.status {
            200 => "OK",
            202 => "Accepted",
            204 => "No Content",
            400 => "Bad Request",
            401 => "Unauthorized",
            403 => "Forbidden",
            404 => "Not Found",
            405 => "Method Not Allowed",
            408 => "Request Timeout",
            413 => "Content Too Large",
            415 => "Unsupported Media Type",
            429 => "Too Many Requests",
            431 => "Request Header Fields Too Large",
            503 => "Service Unavailable",
            _ => "Internal Server Error",
        };
        let body: &[u8] = if self.status == 204 { &[] } else { &self.body };
        let content = if self.status == 204 {
            String::new()
        } else {
            format!("Content-Type: {}\r\n", self.content_type)
        };
        let document = if self.document {
            format!(
                "Content-Security-Policy: {csp}\r\nX-Frame-Options: DENY\r\nCross-Origin-Opener-Policy: same-origin\r\n"
            )
        } else {
            String::new()
        };
        let head = Zeroizing::new(format!(
            "HTTP/1.1 {} {reason}\r\n{content}Content-Length: {}\r\nCache-Control: no-store\r\nX-Content-Type-Options: nosniff\r\nReferrer-Policy: no-referrer\r\nConnection: close\r\n{document}{}\r\n",
            self.status,
            body.len(),
            *self.headers,
        ));
        let _ = tokio::time::timeout(Duration::from_secs(2), async {
            stream.write_all(head.as_bytes()).await?;
            stream.write_all(body).await?;
            stream.flush().await?;
            stream.shutdown().await
        })
        .await;
    }
}

fn header<'a>(r: &'a http::Request, name: &str) -> Option<&'a [u8]> {
    r.head.headers.get(name).map(Vec::as_slice)
}

/// Exactly one `__Host-mover_admin` cookie; any ambiguity is unauthenticated.
fn session_cookie(r: &http::Request) -> Option<&str> {
    let text = std::str::from_utf8(header(r, "cookie")?).ok()?;
    let mut found = None;
    for pair in text.split(';') {
        if let Some((name, value)) = pair.trim_matches(' ').split_once('=')
            && name == COOKIE
        {
            if found.is_some() {
                return None;
            }
            found = Some(value);
        }
    }
    found
}

/// Unsupported identity headers (400) and exact target authority (403), shared
/// by ordinary routes and the event stream.
fn boundary(admin: &Admin, r: &http::Request) -> Option<Reply> {
    if r.head.headers.keys().any(|h| {
        matches!(
            h.as_str(),
            "authorization" | "expect" | "forwarded" | "x-file-mover-generator"
        ) || h.starts_with("x-forwarded-")
            || h.starts_with("x-ssl-")
            || h.starts_with("x-client-")
    }) {
        return Some(Reply::error(400, "invalid_http"));
    }
    match header(r, "host") {
        None | Some(b"") => return Some(Reply::error(400, "invalid_http")),
        Some(host) if !admin.hosts.iter().any(|h| h.as_bytes() == host) => {
            // A person opening the page under another name gets directions; the
            // address shown is the configured origin, never the request's Host.
            if r.head.method == "GET" && r.head.target == b"/" {
                return Some(Reply {
                    status: 403,
                    content_type: "text/html; charset=utf-8",
                    body: wrong_address_page(&admin.origin).into_bytes(),
                    headers: Zeroizing::new(String::new()),
                    document: true,
                });
            }
            return Some(Reply::forbidden());
        }
        Some(_) => (),
    }
    None
}

async fn handle(
    admin: &Arc<Admin>,
    r: &http::Request,
    observer: &std::sync::mpsc::SyncSender<crate::OperatorWork>,
) -> Reply {
    // Boundary precedence: framing (done), unsupported headers, target authority,
    // route/method, then route-specific authentication before Origin/CSRF.
    if let Some(reply) = boundary(admin, r) {
        return reply;
    }
    match r.head.target.as_slice() {
        b"/" => {
            if r.head.method != "GET" {
                Reply::method("GET")
            } else if !r.body.is_empty() {
                Reply::error(400, "unexpected_body")
            } else {
                Reply {
                    status: 200,
                    content_type: "text/html; charset=utf-8",
                    body: admin.document.as_bytes().to_vec(),
                    headers: Zeroizing::new(String::new()),
                    document: true,
                }
            }
        }
        b"/api/v2/admin/login" if r.head.method != "POST" => Reply::method("POST"),
        b"/api/v2/admin/login" => login(admin, r).await,
        b"/api/v2/admin/session" if r.head.method != "GET" => Reply::method("GET"),
        b"/api/v2/admin/session" => session(admin, r),
        b"/api/v2/admin/logout" if r.head.method != "POST" => Reply::method("POST"),
        b"/api/v2/admin/logout" => logout(admin, r).await,
        b"/api/v2/admin/settings" if r.head.method != "GET" => Reply::method("GET"),
        b"/api/v2/admin/settings" => {
            if !r.body.is_empty() {
                return Reply::error(400, "unexpected_body");
            }
            match authorize_read(admin, r) {
                Ok(_) => Reply::json(200, admin.settings.clone()),
                Err(reply) => reply,
            }
        }
        target => {
            let (path, query) = match target.iter().position(|b| *b == b'?') {
                Some(i) => (&target[..i], Some(&target[i + 1..])),
                None => (target, None),
            };
            if path == b"/api/v2/admin/jobs/retry" && query.is_none() {
                if r.head.method != "POST" {
                    return Reply::method("POST");
                }
                retry(admin, r, observer).await
            } else if path == b"/api/v2/admin/jobs" {
                if r.head.method != "GET" {
                    return Reply::method("GET");
                }
                history(admin, r, query, observer).await
            } else if let Some(id) = path.strip_prefix(b"/api/v2/jobs/")
                && query.is_none()
                && !id.contains(&b'/')
            {
                if r.head.method != "GET" {
                    return Reply::method("GET");
                }
                detail(admin, r, id, observer).await
            } else if query.is_none()
                && let Some(scope) = retention_scope(path)
            {
                if r.head.method != "GET" {
                    return Reply::method("GET");
                }
                retention(admin, r, scope, observer).await
            } else {
                // Includes resume and reset-missing: trusted-local operator only.
                Reply::error(404, "not_found")
            }
        }
    }
}

enum Wake {
    Changed,
    Revoked,
    Heartbeat,
    Closed,
}

/// Wait for a state change, a revocation (logout, password activation,
/// shutdown) or the heartbeat interval, whichever comes first.
async fn wait(
    changes: &mut tokio::sync::watch::Receiver<u64>,
    revoked: &mut tokio::sync::watch::Receiver<u64>,
) -> Wake {
    use std::task::Poll;
    let mut changed = std::pin::pin!(changes.changed());
    let mut revocation = std::pin::pin!(revoked.changed());
    let mut heartbeat = std::pin::pin!(tokio::time::sleep(STREAM_HEARTBEAT));
    std::future::poll_fn(|cx| {
        if let Poll::Ready(result) = revocation.as_mut().poll(cx) {
            return Poll::Ready(if result.is_ok() {
                Wake::Revoked
            } else {
                Wake::Closed
            });
        }
        if let Poll::Ready(result) = changed.as_mut().poll(cx) {
            return Poll::Ready(if result.is_ok() {
                Wake::Changed
            } else {
                Wake::Closed
            });
        }
        if heartbeat.as_mut().poll(cx).is_ready() {
            return Poll::Ready(Wake::Heartbeat);
        }
        Poll::Pending
    })
    .await
}

/// One bounded write+flush; false means the client is gone or not reading.
async fn send(stream: &mut ingress::Stream, bytes: &[u8]) -> bool {
    matches!(
        tokio::time::timeout(STREAM_WRITE, async {
            stream.write_all(bytes).await?;
            stream.flush().await
        })
        .await,
        Ok(Ok(()))
    )
}

/// Server-Sent Events: "state may have changed" signals for the open page.
/// Authorized like other reads, never renews the session, closes on session
/// end, and swaps its request permits for one of the separate stream permits.
async fn events(
    mut stream: ingress::Stream,
    admin: Arc<Admin>,
    r: http::Request,
    release_request_permits: Box<dyn FnOnce() + Send>,
) {
    let reply = if r.head.method != "GET" {
        Some(Reply::method("GET"))
    } else if !r.body.is_empty() {
        Some(Reply::error(400, "unexpected_body"))
    } else {
        None
    };
    if let Some(reply) = reply {
        reply.write(&mut stream, &admin.csp).await;
        return;
    }
    // Subscribe before checking the session, so a revocation between the check
    // and the first event is never missed.
    let mut revoked = admin.sessions.revocations();
    let mut changes = admin.changes.subscribe();
    let Some(token) = session_cookie(&r).map(|t| Zeroizing::new(t.to_owned())) else {
        Reply::unauthenticated()
            .write(&mut stream, &admin.csp)
            .await;
        return;
    };
    let live = |token: &str| {
        admin
            .sessions
            .authorize(token, None, Activity::Background, std::time::Instant::now())
            .is_ok()
    };
    if !live(&token) {
        Reply::unauthenticated()
            .write(&mut stream, &admin.csp)
            .await;
        return;
    }
    if header(&r, "origin").is_some_and(|o| o != admin.origin.as_bytes())
        || header(&r, "sec-fetch-site").is_some_and(|s| s != b"same-origin")
    {
        Reply::forbidden().write(&mut stream, &admin.csp).await;
        return;
    }
    let Ok(_stream_permit) = admin.streams.clone().try_acquire_owned() else {
        Reply::error(503, "service_busy")
            .write(&mut stream, &admin.csp)
            .await;
        return;
    };
    // Recheck just before committing: a revocation since subscribing, or a
    // session that ended meanwhile, refuses the stream.
    if revoked.has_changed().unwrap_or(true) || !live(&token) {
        Reply::unauthenticated()
            .write(&mut stream, &admin.csp)
            .await;
        return;
    }
    // From here on this connection no longer counts against request budgets.
    release_request_permits();
    let version = *changes.borrow_and_update();
    let head = format!(
        "HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\nCache-Control: no-store\r\n\
         X-Content-Type-Options: nosniff\r\nConnection: close\r\n\r\n\
         retry: 5000\n\nevent: ready\ndata: {{\"version\":{version}}}\n\n"
    );
    if !send(&mut stream, head.as_bytes()).await {
        return;
    }
    loop {
        let wake = wait(&mut changes, &mut revoked).await;
        if matches!(wake, Wake::Closed) {
            break;
        }
        if matches!(wake, Wake::Revoked) || !live(&token) {
            let _ = send(&mut stream, b"event: signed-out\ndata: {}\n\n").await;
            break;
        }
        let sent = match wake {
            Wake::Changed => {
                // Coalesce a burst of writes into one event with the latest version.
                tokio::time::sleep(STREAM_COALESCE).await;
                let version = *changes.borrow_and_update();
                send(
                    &mut stream,
                    format!("event: changed\ndata: {{\"version\":{version}}}\n\n").as_bytes(),
                )
                .await
            }
            _ => send(&mut stream, b": keepalive\n\n").await,
        };
        if !sent {
            break;
        }
    }
    let _ = tokio::time::timeout(STREAM_WRITE, stream.shutdown()).await;
}

/// Session read authorization shared by every admin GET. Authentication (401)
/// precedes Origin/CSRF/Fetch-Metadata (403). Only a valid marked read renews.
fn authorize_read(admin: &Admin, r: &http::Request) -> Result<crate::session::Authorized, Reply> {
    let marked = match header(r, "mover-admin-activity") {
        None => false,
        Some(b"interaction") => true,
        Some(_) => return Err(Reply::error(400, "invalid_http")),
    };
    let token = session_cookie(r).ok_or_else(Reply::unauthenticated)?;
    let now = std::time::Instant::now();
    let authorized = admin
        .sessions
        .authorize(token, None, Activity::Background, now)
        .map_err(|_| Reply::unauthenticated())?;
    if !marked {
        return Ok(authorized);
    }
    if header(r, "origin").is_some_and(|o| o != admin.origin.as_bytes())
        || header(r, "sec-fetch-site").is_some_and(|s| s != b"same-origin")
    {
        return Err(Reply::forbidden());
    }
    let csrf = header(r, "mover-csrf-token")
        .and_then(|v| std::str::from_utf8(v).ok())
        .ok_or_else(Reply::forbidden)?;
    admin
        .sessions
        .authorize(token, Some(csrf), Activity::Deliberate, now)
        .map_err(|e| match e {
            AuthError::CsrfMismatch => Reply::forbidden(),
            AuthError::Unauthenticated => Reply::unauthenticated(),
        })
}

/// Strict list query: only `limit` and `cursor`, each at most once.
/// Parsed list query: limit, descending order and an optional bound cursor.
type HistoryQuery = (usize, bool, Option<(String, i64)>);

fn history_query(query: Option<&[u8]>) -> Result<HistoryQuery, Reply> {
    let mut limit = None;
    let mut cursor = None;
    let mut order = None;
    let Some(query) = query else {
        return Ok((50, false, None));
    };
    let text = std::str::from_utf8(query).map_err(|_| Reply::error(400, "invalid_http"))?;
    for pair in text.split('&') {
        let (key, value) = pair
            .split_once('=')
            .ok_or_else(|| Reply::error(400, "invalid_http"))?;
        match key {
            "limit" if limit.is_none() => {
                limit = Some(
                    value
                        .parse::<usize>()
                        .ok()
                        .filter(|n| (1..=256).contains(n) && n.to_string() == value)
                        .ok_or_else(|| Reply::error(400, "invalid_http"))?,
                );
            }
            "cursor" if cursor.is_none() => {
                cursor =
                    Some(parse_cursor(value).ok_or_else(|| Reply::error(400, "invalid_cursor"))?);
            }
            "order" if order.is_none() => {
                order = Some(match value {
                    "asc" => false,
                    "desc" => true,
                    _ => return Err(Reply::error(400, "invalid_http")),
                });
            }
            "confirm_action" | "job_ids" => {
                // Confirmation previews belong to the not-yet-implemented actions.
                return Err(Reply::json(
                    400,
                    serde_json::json!({"error":"invalid_selection","message":"Confirmation mode is not available."}),
                ));
            }
            _ => return Err(Reply::error(400, "invalid_http")),
        }
    }
    let descending = order.unwrap_or(false);
    let cursor = match cursor {
        // A cursor only continues the order it was issued for.
        Some((instance, cursor_desc, last)) if cursor_desc == descending => Some((instance, last)),
        Some(_) => return Err(Reply::error(400, "invalid_cursor")),
        None => None,
    };
    Ok((limit.unwrap_or(50), descending, cursor))
}

fn parse_cursor(value: &str) -> Option<(String, bool, i64)> {
    if value.is_empty() || value.len() > 1024 {
        return None;
    }
    let (head, last) = value.strip_prefix("c1.")?.rsplit_once('.')?;
    let (instance, order) = head.rsplit_once('.')?;
    let descending = match order {
        "a" => false,
        "d" => true,
        _ => return None,
    };
    let last = last
        .parse::<i64>()
        .ok()
        .filter(|n| *n > 0 && n.to_string() == last)?;
    if instance.is_empty()
        || !instance
            .bytes()
            .all(|b| b.is_ascii_alphanumeric() || b == b'-' || b == b'_')
    {
        return None;
    }
    Some((instance.to_owned(), descending, last))
}

fn from_operator(response: crate::Response) -> Reply {
    match response.status {
        200 => Reply::json(200, response.details.unwrap_or(serde_json::Value::Null)),
        status => Reply::error(status, response.error.unwrap_or("internal_error")),
    }
}

async fn history(
    admin: &Admin,
    r: &http::Request,
    query: Option<&[u8]>,
    observer: &std::sync::mpsc::SyncSender<crate::OperatorWork>,
) -> Reply {
    if !r.body.is_empty() {
        return Reply::error(400, "unexpected_body");
    }
    if let Err(reply) = authorize_read(admin, r) {
        return reply;
    }
    let (limit, descending, cursor) = match history_query(query) {
        Ok(q) => q,
        Err(reply) => return reply,
    };
    let (bound, cursor) = match cursor {
        Some((instance, last)) => (Some(instance), Some(last)),
        None => (None, None),
    };
    let request = crate::PageRequest {
        cursor,
        limit,
        descending,
        bound,
    };
    from_operator(crate::operator_reply(observer, crate::Observation::Page(request)).await)
}

/// `/api/v2/retention` → Some(None); `/api/v2/jobs/{id}/retention` → Some(Some(id)).
fn retention_scope(path: &[u8]) -> Option<Option<&[u8]>> {
    if path == b"/api/v2/retention" {
        return Some(None);
    }
    let id = path
        .strip_prefix(b"/api/v2/jobs/")?
        .strip_suffix(b"/retention")?;
    (!id.contains(&b'/')).then_some(Some(id))
}

fn canonical_job_id(id: &[u8]) -> Option<i64> {
    std::str::from_utf8(id).ok().and_then(|s| {
        s.parse::<i64>()
            .ok()
            .filter(|n| *n > 0 && n.to_string() == s)
    })
}

/// Existing reservation-ledger reads, byte-for-byte the operator envelope.
/// Global reads include the cached source-space observation; no probe starts.
async fn retention(
    admin: &Admin,
    r: &http::Request,
    scope: Option<&[u8]>,
    observer: &std::sync::mpsc::SyncSender<crate::OperatorWork>,
) -> Reply {
    if !r.body.is_empty() {
        return Reply::error(400, "unexpected_body");
    }
    if let Err(reply) = authorize_read(admin, r) {
        return reply;
    }
    let id = match scope {
        None => None,
        Some(bytes) => match canonical_job_id(bytes) {
            Some(id) => Some(id),
            None => return Reply::error(400, "invalid_job_id"),
        },
    };
    let response = crate::operator_reply(observer, crate::Observation::Retention(id)).await;
    if response.status == 200 {
        Reply::json(
            200,
            serde_json::to_value(&response).expect("retention serialization"),
        )
    } else {
        from_operator(response)
    }
}

async fn detail(
    admin: &Admin,
    r: &http::Request,
    id: &[u8],
    observer: &std::sync::mpsc::SyncSender<crate::OperatorWork>,
) -> Reply {
    if !r.body.is_empty() {
        return Reply::error(400, "unexpected_body");
    }
    if let Err(reply) = authorize_read(admin, r) {
        return reply;
    }
    let Some(id) = canonical_job_id(id) else {
        return Reply::error(400, "invalid_job_id");
    };
    let response = crate::operator_reply(observer, crate::Observation::Status(id)).await;
    if response.status == 200 {
        // Existing JobStatus envelope, byte-for-byte the operator shape.
        Reply::json(
            200,
            serde_json::to_value(&response).expect("status serialization"),
        )
    } else {
        from_operator(response)
    }
}

/// Reviewed delivery retry (docs/api/RETRY-HEADER.candidate.md). Authentication
/// (401) precedes Origin/CSRF (403), media type (415) and context validation.
/// The whole request is validated before any occurrence; each occurrence then
/// rechecks the session and commits its own receipt, audit and scheduling.
async fn retry(
    admin: &Arc<Admin>,
    r: &http::Request,
    observer: &std::sync::mpsc::SyncSender<crate::OperatorWork>,
) -> Reply {
    use crate::retry_context::{self as ctx, ContextError};
    let Some(token) = session_cookie(r) else {
        return Reply::unauthenticated();
    };
    let now = std::time::Instant::now();
    if admin
        .sessions
        .authorize(token, None, Activity::Background, now)
        .is_err()
    {
        return Reply::unauthenticated();
    }
    if header(r, "origin") != Some(admin.origin.as_bytes())
        || header(r, "sec-fetch-site").is_some_and(|s| s != b"same-origin")
    {
        return Reply::forbidden();
    }
    let Some(csrf) = header(r, "mover-csrf-token").and_then(|v| std::str::from_utf8(v).ok()) else {
        return Reply::forbidden();
    };
    // No renewal yet: rejected requests, replays and batches without newly
    // admitted work leave the inactivity clock unchanged.
    let principal = match admin
        .sessions
        .authorize(token, Some(csrf), Activity::Background, now)
    {
        Ok(authorized) => authorized.principal,
        Err(AuthError::CsrfMismatch) => return Reply::forbidden(),
        Err(AuthError::Unauthenticated) => return Reply::unauthenticated(),
    };
    if header(r, "content-type") != Some(b"application/json") {
        return Reply::error(415, "unsupported_media_type");
    }
    // Instance and high-water mark are read once for whole-request validation.
    let scope = crate::operator_reply(observer, crate::Observation::RetryScope).await;
    let (instance, high_water) = match scope.details.as_ref().filter(|_| scope.status == 200) {
        Some(d) => (
            d["instance_id"].as_str().unwrap_or_default().to_owned(),
            d["high_water"].as_i64().unwrap_or(i64::MAX),
        ),
        None => return from_operator(scope),
    };
    // Framing already refused duplicate headers and heads over 8192 bytes.
    let values: Vec<&[u8]> = header(r, "mover-retry-context").into_iter().collect();
    let context = match ctx::decode(&r.body, &values, &instance, None) {
        Ok(context) => context,
        Err(
            ContextError::HeadTooLarge
            | ContextError::ValueTooLarge
            | ContextError::DecodedTooLarge,
        ) => return Reply::error(431, "request_headers_too_large"),
        Err(ContextError::InvalidSelection) => return Reply::error(400, "invalid_selection"),
        Err(ContextError::InstanceMismatch) => return Reply::error(409, "review_conflict"),
        Err(_) => return Reply::error(400, "invalid_retry_context"),
    };
    // A non-null epoch can only have been observed for an allocated job ID.
    if context
        .job_ids
        .iter()
        .zip(&context.review_epochs)
        .any(|(id, epoch)| epoch.is_some() && *id > high_water)
    {
        return Reply::error(400, "invalid_retry_context");
    }
    let key = ctx::receipt_key(&principal, &context);
    let (mut accepted, mut failed, mut skipped) = (0_u16, 0_u16, 0_u16);
    for (occurrence, (job_id, epoch)) in context
        .job_ids
        .iter()
        .zip(&context.review_epochs)
        .enumerate()
    {
        // Revocation wins before every new occurrence or receipt disclosure:
        // the store decision runs under the session lock that logout takes.
        let gate_admin = Arc::clone(admin);
        let gate_token = Zeroizing::new(token.to_owned());
        let gate: crate::RetryGate = Box::new(move |work| {
            gate_admin
                .sessions
                .while_authorized(&gate_token, work)
                .is_ok()
        });
        let work = crate::Observation::Retry(
            mover_store::RetryOccurrence {
                job_id: *job_id,
                context_key: key.clone(),
                principal: principal.clone(),
                instance_id: context.instance_id.clone(),
                review_epoch: *epoch,
                reason: context.reason.clone(),
                occurrence: occurrence as u16,
            },
            gate,
        );
        let response = crate::operator_reply(observer, work).await;
        if response.status == 401 {
            return Reply::unauthenticated();
        }
        match response.details.as_ref().filter(|_| response.status == 200) {
            Some(d) => match d["outcome"].as_str() {
                Some("accepted") => {
                    accepted += 1;
                    if d["replay"] == false {
                        // Each newly admitted action renews at once, so a later
                        // occurrence's error cannot drop the renewal.
                        let _ = admin.sessions.authorize(
                            token,
                            Some(csrf),
                            Activity::Deliberate,
                            std::time::Instant::now(),
                        );
                    }
                }
                Some("failed") => failed += 1,
                _ => skipped += 1,
            },
            // No fabricated counts: earlier occurrences stay committed and an
            // unchanged resend replays them.
            None => return from_operator(response),
        }
    }
    Reply::json(
        202,
        serde_json::json!({"accepted_count":accepted,"failed_count":failed,"skipped_count":skipped}),
    )
}

async fn login(admin: &Admin, r: &http::Request) -> Reply {
    #[derive(Deserialize)]
    #[serde(deny_unknown_fields)]
    struct Input {
        username: crate::account::SecretText,
        password: crate::account::SecretText,
    }
    if header(r, "origin") != Some(admin.origin.as_bytes()) {
        return Reply::forbidden();
    }
    if header(r, "content-type") != Some(b"application/json") {
        return Reply::error(415, "unsupported_media_type");
    }
    let Ok(input) = serde_json::from_slice::<Input>(&r.body) else {
        return Reply::error(400, "invalid_json");
    };
    if crate::password::validate_username(&input.username.0).is_err() {
        return Reply::error(400, "invalid_json");
    }
    let Ok(password) = crate::password::Password::new(input.password.0.as_bytes().to_vec()) else {
        return Reply::error(400, "invalid_json");
    };
    match admin
        .sessions
        .login(&input.username.0, password, LOGIN_DEADLINE)
        .await
    {
        Ok(issued) => {
            let cookie = Zeroizing::new(format!(
                "{COOKIE}={}; Secure; HttpOnly; Path=/; SameSite=Strict",
                *issued.session
            ));
            Reply::json(200, serde_json::json!({"authenticated":true}))
                .header("Set-Cookie", &cookie)
                .header("Mover-CSRF-Token", &issued.csrf)
        }
        Err(LoginError::InvalidCredentials) => Reply::json(
            401,
            serde_json::json!({"error":"invalid_credentials","message":"Invalid username or password."}),
        ),
        Err(LoginError::RateLimited) => {
            Reply::error(429, "rate_limited").header("Retry-After", "60")
        }
        // A concurrent logout/password activation or slow verifier: retry later.
        Err(LoginError::Busy | LoginError::Superseded | LoginError::TimedOut) => {
            Reply::error(503, "service_busy")
        }
        Err(LoginError::Unavailable) => Reply::error(500, "internal_error"),
    }
}

fn session(admin: &Admin, r: &http::Request) -> Reply {
    if !r.body.is_empty() {
        return Reply::error(400, "unexpected_body");
    }
    match authorize_read(admin, r) {
        Ok(authorized) => Reply::json(
            200,
            serde_json::json!({"authenticated":true,"inactivity_timeout_seconds":admin.idle_seconds}),
        )
        .header("Mover-CSRF-Token", &authorized.csrf),
        Err(reply) => reply,
    }
}

async fn logout(admin: &Admin, r: &http::Request) -> Reply {
    if !r.body.is_empty() {
        return Reply::error(400, "unexpected_body");
    }
    let Some(token) = session_cookie(r) else {
        return Reply::unauthenticated();
    };
    let now = std::time::Instant::now();
    if admin
        .sessions
        .authorize(token, None, Activity::Background, now)
        .is_err()
    {
        return Reply::unauthenticated();
    }
    if header(r, "origin") != Some(admin.origin.as_bytes()) {
        return Reply::forbidden();
    }
    let Some(csrf) = header(r, "mover-csrf-token").and_then(|v| std::str::from_utf8(v).ok()) else {
        return Reply::forbidden();
    };
    match admin
        .sessions
        .authorize(token, Some(csrf), Activity::Background, now)
    {
        Ok(_) => (),
        Err(AuthError::CsrfMismatch) => return Reply::forbidden(),
        Err(AuthError::Unauthenticated) => return Reply::unauthenticated(),
    }
    // Global revocation is authoritative even if another request revoked first.
    // Ordered with admitted admin actions (see Sessions::while_authorized):
    // 204 means no admitted action is still deciding. Sessions are revoked
    // even when storage is too slow to confirm that in time.
    match tokio::time::timeout(LOGOUT_SETTLE, admin.sessions.logout_all_serialized()).await {
        Ok(Ok(_)) => (),
        Ok(Err(_)) => return Reply::error(503, "service_stopping"),
        Err(_) => return Reply::error(503, "storage_unavailable"),
    }
    let mut reply = Reply::json(204, serde_json::json!({})).header(
        "Set-Cookie",
        &format!("{COOKIE}=; Max-Age=0; Secure; HttpOnly; Path=/; SameSite=Strict"),
    );
    reply.body.clear();
    reply
}

/// Certificate rows for the Settings page: path, subject CN and expiry.
fn cert_rows(
    role: &str,
    paths: &[String],
    ders: &[rustls::pki_types::CertificateDer<'_>],
) -> Vec<serde_json::Value> {
    paths
        .iter()
        .zip(ders)
        .map(|(path, der)| {
            let (subject, not_after) = crate::cert_info::summary(der.as_ref());
            serde_json::json!({"role": role, "path": path, "subject": subject, "not_after": not_after})
        })
        .collect()
}

/// Read-only configuration snapshot for the admin Settings page. Paths and
/// policy only: never key material, verifiers or file contents.
fn settings(
    c: &Config,
    admin: &AdminIngress,
    admin_chain: &[rustls::pki_types::CertificateDer<'static>],
    admin_ca: &[rustls::pki_types::CertificateDer<'static>],
) -> Result<serde_json::Value, Box<dyn std::error::Error>> {
    use crate::native::NativeIngress;
    let key = |path: &str| serde_json::json!({"role": "Private key", "path": path, "subject": null, "not_after": null});
    let mut dashboard_certs = cert_rows(
        "Server certificate",
        &admin.server_certificates,
        admin_chain,
    );
    dashboard_certs.extend(cert_rows(
        "Server CA",
        &admin.server_ca_certificates,
        admin_ca,
    ));
    dashboard_certs.push(key(&admin.server_key));
    let producer = match &c.native_ingress {
        Some(NativeIngress::Https {
            operator_socket,
            authority,
            server_certificates,
            server_key,
            server_ca_certificates,
            client_ca_certificates,
            clients,
        }) => {
            let mut certs = cert_rows(
                "Server certificate",
                server_certificates,
                &crate::native::certificates(server_certificates)?,
            );
            certs.extend(cert_rows(
                "Server CA",
                server_ca_certificates,
                &crate::native::certificates(server_ca_certificates)?,
            ));
            certs.extend(cert_rows(
                "Client CA",
                client_ca_certificates,
                &crate::native::certificates(client_ca_certificates)?,
            ));
            certs.push(key(server_key));
            serde_json::json!({"transport": "HTTPS", "bind": c.bind.to_string(), "authority": authority,
                "operator_socket": operator_socket, "approved_clients": clients, "certificates": certs})
        }
        Some(NativeIngress::Http { operator_socket }) => serde_json::json!({
            "transport": "HTTP (loopback only)", "bind": c.bind.to_string(), "authority": null,
            "operator_socket": operator_socket, "approved_clients": [], "certificates": []}),
        None => serde_json::json!(null),
    };
    let config_file = std::env::args().nth(1).filter(|a| !a.starts_with("--"));
    let loaded_at = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_secs())
        .unwrap_or(0);
    Ok(serde_json::json!({
        "config_file": config_file,
        "loaded_at": loaded_at,
        "transfers": {
            "source_root": c.source_root,
            "destination_root": c.destination_root,
            "generator_id": c.generator_id,
            "transfer_mode": "Copy",
            "check_expected_sizes": c.check_expected_sizes,
            "missing_file_retry_window_seconds": c.missing_file_retry_window_seconds,
            "shutdown_wait_seconds": c.shutdown_wait_seconds,
        },
        "storage": {
            "max_retained_jobs": c.max_retained_jobs,
            "max_retained_bytes": c.max_retained_bytes.to_string(),
            "source_space_admission": serde_json::to_value(&c.source_space_admission)?,
        },
        "producer": producer,
        "dashboard": {
            "bind": admin.bind.to_string(),
            "authority": admin.authority,
            "inactivity_timeout_seconds": admin.inactivity_timeout_seconds,
            "account_directory": admin.account_directory,
            "certificates": dashboard_certs,
        },
        "internal": {
            "state_database": c.state_database,
            "source_binding": serde_json::to_value(&c.source_binding)?,
            "destination_binding": serde_json::to_value(&c.destination_binding)?,
            "protected_ingress": serde_json::to_value(&c.protected_ingress)?,
        },
    }))
}

/// Static page for a browser that used an address other than the configured
/// one. No styles or scripts, so the document CSP still applies unchanged.
fn wrong_address_page(origin: &str) -> String {
    let escaped: String = origin
        .chars()
        .map(|c| match c {
            '&' => "&amp;".to_owned(),
            '<' => "&lt;".to_owned(),
            '>' => "&gt;".to_owned(),
            '"' => "&quot;".to_owned(),
            '\'' => "&#39;".to_owned(),
            c => c.to_string(),
        })
        .collect();
    format!(
        "<!doctype html>\n<html lang=\"en\">\n<meta charset=\"utf-8\">\n<title>File Mover</title>\n\
         <h1>Wrong address</h1>\n<p>This dashboard is served at \
         <a href=\"{escaped}/\">{escaped}/</a>. Open that address instead.</p>\n</html>\n"
    )
}

/// Exact accepted Host values and the browser-serialized origin for a validated
/// canonical `host:port` authority. Browsers omit `:443` from both Origin and
/// Host; other ports stay explicit.
fn browser_authority(authority: &str) -> (Vec<String>, String) {
    match authority.strip_suffix(":443") {
        Some(host) => (
            vec![authority.to_owned(), host.to_owned()],
            format!("https://{host}"),
        ),
        None => (vec![authority.to_owned()], format!("https://{authority}")),
    }
}

const TEMPLATE: &str = include_str!("admin/index.html");
const STYLE: &str = include_str!("admin/admin.css");
const SCRIPT: &str = include_str!("admin/admin.js");

/// Assemble the fixed offline document and a CSP that admits exactly its inline
/// style and script by hash. No external or runtime asset directory exists.
fn document() -> (String, String) {
    let html = TEMPLATE
        .replacen("/*STYLE*/", STYLE, 1)
        .replacen("/*SCRIPT*/", SCRIPT, 1);
    let csp = format!(
        "default-src 'none'; style-src '{}'; script-src '{}'; connect-src 'self'; img-src data:; form-action 'none'; frame-ancestors 'none'; base-uri 'none'",
        sha256_source(STYLE),
        sha256_source(SCRIPT)
    );
    (html, csp)
}

fn sha256_source(text: &str) -> String {
    let hex = mover_fs::sha256_hex(text.as_bytes());
    let bytes: Vec<u8> = hex
        .as_bytes()
        .chunks(2)
        .map(|p| u8::from_str_radix(std::str::from_utf8(p).unwrap_or("00"), 16).unwrap_or(0))
        .collect();
    format!("sha256-{}", base64(&bytes))
}

fn base64(bytes: &[u8]) -> String {
    const TABLE: &[u8; 64] = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    let mut out = String::with_capacity(bytes.len().div_ceil(3) * 4);
    for chunk in bytes.chunks(3) {
        let n = (u32::from(chunk[0]) << 16)
            | (u32::from(*chunk.get(1).unwrap_or(&0)) << 8)
            | u32::from(*chunk.get(2).unwrap_or(&0));
        for i in 0..4 {
            if i <= chunk.len() {
                out.push(TABLE[((n >> (18 - 6 * i)) & 63) as usize] as char);
            } else {
                out.push('=');
            }
        }
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn base64_matches_rfc4648_vectors() {
        for (input, output) in [
            ("", ""),
            ("f", "Zg=="),
            ("fo", "Zm8="),
            ("foo", "Zm9v"),
            ("foob", "Zm9vYg=="),
            ("fooba", "Zm9vYmE="),
            ("foobar", "Zm9vYmFy"),
        ] {
            assert_eq!(base64(input.as_bytes()), output);
        }
        // sha256("") in CSP source form.
        assert_eq!(
            sha256_source(""),
            "sha256-47DEQpj8HBSa+/TImW+5JCeuQeRkm5NMpJWZG3hSuFU="
        );
    }

    #[test]
    fn document_inlines_assets_and_csp_admits_only_them() {
        let (html, csp) = document();
        assert!(html.contains(STYLE) && html.contains(SCRIPT));
        assert!(!html.contains("/*STYLE*/") && !html.contains("/*SCRIPT*/"));
        for external in ["http://", "https://", "src=\"", "href=\"http"] {
            assert!(!html.contains(external), "external reference {external}");
        }
        assert!(csp.contains(&sha256_source(STYLE)) && csp.contains(&sha256_source(SCRIPT)));
        assert!(!csp.contains("unsafe"));
        // The script never writes HTML from data.
        assert!(!SCRIPT.contains("innerHTML") && !SCRIPT.contains("insertAdjacentHTML"));
    }

    #[test]
    fn default_https_port_uses_browser_serialization() {
        assert_eq!(
            browser_authority("mover.example:443"),
            (
                vec!["mover.example:443".to_owned(), "mover.example".to_owned()],
                "https://mover.example".to_owned()
            )
        );
        assert_eq!(
            browser_authority("[::1]:443"),
            (
                vec!["[::1]:443".to_owned(), "[::1]".to_owned()],
                "https://[::1]".to_owned()
            )
        );
        assert_eq!(
            browser_authority("mover.example:9443"),
            (
                vec!["mover.example:9443".to_owned()],
                "https://mover.example:9443".to_owned()
            )
        );
        // A port merely ending in 443 keeps its explicit form.
        assert_eq!(
            browser_authority("mover.example:8443").1,
            "https://mover.example:8443"
        );
    }

    #[test]
    fn history_query_and_cursor_are_strict() {
        let q = |s: &str| history_query(Some(s.as_bytes())).map_err(|r| r.status);
        assert_eq!(history_query(None).ok(), Some((50, false, None)));
        assert_eq!(q("limit=1").ok(), Some((1, false, None)));
        assert_eq!(q("limit=256").ok(), Some((256, false, None)));
        assert_eq!(q("order=desc").ok(), Some((50, true, None)));
        assert_eq!(q("order=asc&limit=2").ok(), Some((2, false, None)));
        for bad in ["order=up", "order=asc&order=desc"] {
            assert_eq!(q(bad).err(), Some(400), "{bad}");
        }
        // A cursor continues only the order it was issued for.
        assert_eq!(
            q("order=desc&cursor=c1.abc.d.9").ok(),
            Some((50, true, Some(("abc".to_owned(), 9))))
        );
        assert_eq!(q("cursor=c1.abc.d.9").err(), Some(400));
        for bad in [
            "limit=0",
            "limit=257",
            "limit=01",
            "limit=",
            "limit=1&limit=2",
            "x=1",
            "limit",
            "",
        ] {
            assert_eq!(q(bad).err(), Some(400), "{bad}");
        }
        assert_eq!(
            q("cursor=c1.abc-1.a.42").ok(),
            Some((50, false, Some(("abc-1".to_owned(), 42))))
        );
        for bad in [
            "c1.abc.a.0",
            "c1.abc.a.042",
            "c2.abc.a.1",
            "c1..a.1",
            "c1.a b.a.1",
            "c1.abc.a",
            "c1.abc.1",
            "c1.abc.x.1",
        ] {
            assert!(parse_cursor(bad).is_none(), "{bad}");
        }
        assert!(parse_cursor(&format!("c1.{}.a.1", "a".repeat(1100))).is_none());
        assert_eq!(q("confirm_action=cancel&job_ids=1").err(), Some(400));
        assert_eq!(
            parse_cursor(&crate::history_cursor("inst_1", true, 9)),
            Some(("inst_1".to_owned(), true, 9))
        );
    }

    #[test]
    fn retention_scope_matches_only_exact_paths() {
        assert_eq!(retention_scope(b"/api/v2/retention"), Some(None));
        assert_eq!(
            retention_scope(b"/api/v2/jobs/7/retention"),
            Some(Some(b"7".as_slice()))
        );
        for bad in [
            b"/api/v2/retention/".as_slice(),
            b"/api/v2/jobs/7/retention/x",
            b"/api/v2/jobs/7/x/retention",
            b"/api/v2/jobs/retention",
        ] {
            assert!(
                retention_scope(bad)
                    .is_none_or(|s| s.is_some_and(|id| canonical_job_id(id).is_none())),
                "{}",
                String::from_utf8_lossy(bad)
            );
        }
    }

    #[test]
    fn wrong_address_page_shows_only_the_escaped_configured_origin() {
        let page = wrong_address_page("https://mover.example:9443");
        assert!(
            page.contains(
                "<a href=\"https://mover.example:9443/\">https://mover.example:9443/</a>"
            )
        );
        assert!(!page.contains("<script") && !page.contains("<style") && !page.contains(" style="));
        let hostile = wrong_address_page("https://x\"><script>");
        assert!(!hostile.contains("<script>") && hostile.contains("&quot;&gt;&lt;script&gt;"));
    }

    #[test]
    fn session_cookie_requires_exactly_one_named_value() {
        fn request(cookie: &str) -> http::Request {
            let mut headers = std::collections::BTreeMap::new();
            headers.insert("cookie".to_owned(), cookie.as_bytes().to_vec());
            http::Request {
                head: http::Head {
                    method: "GET".into(),
                    target: b"/".to_vec(),
                    headers,
                    consumed: 0,
                },
                body: Vec::new(),
            }
        }
        assert_eq!(
            session_cookie(&request("__Host-mover_admin=ab")),
            Some("ab")
        );
        assert_eq!(
            session_cookie(&request("x=1; __Host-mover_admin=ab; y=2")),
            Some("ab")
        );
        assert_eq!(
            session_cookie(&request("__Host-mover_admin=a; __Host-mover_admin=b")),
            None
        );
        assert_eq!(session_cookie(&request("mover_admin=ab")), None);
    }
}
