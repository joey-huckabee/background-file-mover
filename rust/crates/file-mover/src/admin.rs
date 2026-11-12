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
        config: &AdminIngress,
        record: crate::account::Record,
    ) -> Result<Self, Box<dyn std::error::Error>> {
        let chain = crate::native::certificates(&config.server_certificates)?;
        let server_ca = crate::native::certificates(&config.server_ca_certificates)?;
        let key = crate::native::private_key(&config.server_key)?;
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
                document,
                csp,
            }),
            listener,
        })
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

async fn handle(
    admin: &Admin,
    r: &http::Request,
    observer: &std::sync::mpsc::SyncSender<crate::OperatorWork>,
) -> Reply {
    // Boundary precedence: framing (done), unsupported headers, target authority,
    // route/method, then route-specific authentication before Origin/CSRF.
    if r.head.headers.keys().any(|h| {
        matches!(
            h.as_str(),
            "authorization" | "expect" | "forwarded" | "x-file-mover-generator"
        ) || h.starts_with("x-forwarded-")
            || h.starts_with("x-ssl-")
            || h.starts_with("x-client-")
    }) {
        return Reply::error(400, "invalid_http");
    }
    match header(r, "host") {
        None | Some(b"") => return Reply::error(400, "invalid_http"),
        Some(host) if !admin.hosts.iter().any(|h| h.as_bytes() == host) => {
            return Reply::forbidden();
        }
        Some(_) => (),
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
        b"/api/v2/admin/logout" => logout(admin, r),
        target => {
            let (path, query) = match target.iter().position(|b| *b == b'?') {
                Some(i) => (&target[..i], Some(&target[i + 1..])),
                None => (target, None),
            };
            if path == b"/api/v2/admin/jobs" {
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
            } else {
                // Includes job retention, resume and reset-missing: not admin routes.
                Reply::error(404, "not_found")
            }
        }
    }
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
fn history_query(query: Option<&[u8]>) -> Result<(usize, Option<(String, i64)>), Reply> {
    let mut limit = None;
    let mut cursor = None;
    let Some(query) = query else {
        return Ok((50, None));
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
    Ok((limit.unwrap_or(50), cursor))
}

fn parse_cursor(value: &str) -> Option<(String, i64)> {
    if value.is_empty() || value.len() > 1024 {
        return None;
    }
    let (instance, last) = value.strip_prefix("c1.")?.rsplit_once('.')?;
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
    Some((instance.to_owned(), last))
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
    let (limit, cursor) = match history_query(query) {
        Ok(q) => q,
        Err(reply) => return reply,
    };
    let (bound, after) = match cursor {
        Some((instance, last)) => (Some(instance), last),
        None => (None, 0),
    };
    from_operator(
        crate::operator_reply(observer, crate::Observation::Page(after, limit, bound)).await,
    )
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
    let Some(id) = std::str::from_utf8(id).ok().and_then(|s| {
        s.parse::<i64>()
            .ok()
            .filter(|n| *n > 0 && n.to_string() == s)
    }) else {
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

fn logout(admin: &Admin, r: &http::Request) -> Reply {
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
    if admin.sessions.logout_all().is_err() {
        return Reply::error(503, "service_stopping");
    }
    let mut reply = Reply::json(204, serde_json::json!({})).header(
        "Set-Cookie",
        &format!("{COOKIE}=; Max-Age=0; Secure; HttpOnly; Path=/; SameSite=Strict"),
    );
    reply.body.clear();
    reply
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
        assert_eq!(history_query(None).ok(), Some((50, None)));
        assert_eq!(q("limit=1").ok(), Some((1, None)));
        assert_eq!(q("limit=256").ok(), Some((256, None)));
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
            q("cursor=c1.abc-1.42").ok(),
            Some((50, Some(("abc-1".to_owned(), 42))))
        );
        for bad in [
            "c1.abc.0",
            "c1.abc.042",
            "c2.abc.1",
            "c1..1",
            "c1.a b.1",
            "c1.abc",
        ] {
            assert!(parse_cursor(bad).is_none(), "{bad}");
        }
        assert!(parse_cursor(&format!("c1.{}.1", "a".repeat(1100))).is_none());
        assert_eq!(q("confirm_action=cancel&job_ids=1").err(), Some(400));
        assert_eq!(
            parse_cursor(&crate::history_cursor("inst_1", 9)),
            Some(("inst_1".to_owned(), 9))
        );
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
