//! Actual admin HTTPS listener against the real service binary: account-backed
//! sign-in, cookie/CSRF/Origin rules, global logout, rate limit, restart and
//! audience isolation. Disposable credentials and state only.
use super::*;

const PASSWORD: &str = "disposable admin fixture";

struct Admin {
    port: u16,
}

struct Reply {
    status: u16,
    head: String,
    body: Vec<u8>,
}
impl Reply {
    fn header(&self, name: &str) -> Option<&str> {
        let prefix = format!("{}:", name.to_ascii_lowercase());
        self.head.split("\r\n").find_map(|line| {
            line.to_ascii_lowercase()
                .starts_with(&prefix)
                .then(|| line[prefix.len()..].trim())
        })
    }
    fn json(&self) -> Value {
        serde_json::from_slice(&self.body).unwrap()
    }
    fn cookie(&self) -> String {
        let set = self.header("set-cookie").expect("Set-Cookie");
        set.split(';').next().unwrap().to_owned()
    }
}

impl Admin {
    fn origin(&self) -> String {
        format!("https://localhost:{}", self.port)
    }
    fn raw(&self, bytes: &[u8]) -> Reply {
        let mut config = ClientConfig::builder_with_provider(tls::provider())
            .with_protocol_versions(&[&rustls::version::TLS13])
            .unwrap()
            .with_root_certificates(roots("ca.der"))
            .with_no_client_auth();
        config.alpn_protocols = vec![b"http/1.1".to_vec()];
        config.resumption = Resumption::disabled();
        let address = std::net::SocketAddr::from(([127, 0, 0, 1], self.port));
        let socket =
            std::net::TcpStream::connect_timeout(&address, Duration::from_secs(5)).unwrap();
        socket
            .set_read_timeout(Some(Duration::from_secs(20)))
            .unwrap();
        let connection = rustls::ClientConnection::new(
            Arc::new(config),
            ServerName::try_from("localhost").unwrap(),
        )
        .unwrap();
        let mut stream = rustls::StreamOwned::new(connection, socket);
        stream.write_all(bytes).unwrap();
        stream.flush().unwrap();
        let mut out = Vec::new();
        stream.read_to_end(&mut out).unwrap();
        let end = out
            .windows(4)
            .position(|b| b == b"\r\n\r\n")
            .expect("complete HTTP reply");
        let head = String::from_utf8(out[..end].to_vec()).unwrap();
        let status = head.split_whitespace().nth(1).unwrap().parse().unwrap();
        Reply {
            status,
            head,
            body: out[end + 4..].to_vec(),
        }
    }
    fn call(&self, method: &str, path: &str, headers: &str, body: &[u8]) -> Reply {
        let mut bytes = format!(
            "{method} {path} HTTP/1.1\r\nHost: localhost:{}\r\nContent-Length: {}\r\n{headers}\r\n",
            self.port,
            body.len()
        )
        .into_bytes();
        bytes.extend_from_slice(body);
        self.raw(&bytes)
    }
    fn login(&self, username: &str, password: &str) -> Reply {
        let body = serde_json::to_vec(&json!({"username":username,"password":password})).unwrap();
        self.call(
            "POST",
            "/api/v2/admin/login",
            &format!(
                "Origin: {}\r\nContent-Type: application/json\r\n",
                self.origin()
            ),
            &body,
        )
    }
    fn session(&self, cookie: &str, extra: &str) -> Reply {
        self.call(
            "GET",
            "/api/v2/admin/session",
            &format!("Cookie: {cookie}\r\n{extra}"),
            &[],
        )
    }
    fn session_path(&self, path: &str, cookie: &str, extra: &str) -> Reply {
        self.call("GET", path, &format!("Cookie: {cookie}\r\n{extra}"), &[])
    }
    fn logout(&self, cookie: &str, extra: &str) -> Reply {
        self.call(
            "POST",
            "/api/v2/admin/logout",
            &format!("Cookie: {cookie}\r\n{extra}"),
            &[],
        )
    }
}

/// Native HTTPS fixture plus a provisioned account and a separate admin listener.
fn admin_fixture() -> (Fixture, Admin) {
    let mut f = Fixture::new(true);
    f.initialize();
    f.start(); // Records the active source pairing required by account commands.
    f.stop();
    let accounts = f.root.join("accounts");
    let credentials = f.root.join("admin-credentials");
    for dir in [&accounts, &credentials] {
        fs::create_dir(dir).unwrap();
        mode(dir, 0o700);
    }
    for name in ["server.der", "server.key.der", "ca.der"] {
        fs::write(credentials.join(name), fixture(name)).unwrap();
        mode(
            &credentials.join(name),
            if name.ends_with("key.der") {
                0o600
            } else {
                0o400
            },
        );
    }
    let port = std::net::TcpListener::bind("127.0.0.1:0")
        .unwrap()
        .local_addr()
        .unwrap()
        .port();
    f.config["admin_ingress"] = json!({
        "bind": format!("127.0.0.1:{port}"),
        "authority": format!("localhost:{port}"),
        "server_certificates": [credentials.join("server.der")],
        "server_key": credentials.join("server.key.der"),
        "server_ca_certificates": [credentials.join("ca.der")],
        "account_directory": accounts,
    });
    f.save();
    // No account yet: startup refuses before any listener is ready.
    let refusal = f.refuse();
    assert!(refusal.contains("provisioned admin account"), "{refusal}");
    // Readable form: names the configuration field; no Rust debug quoting.
    assert!(
        refusal.contains("file-mover: admin_ingress.account_directory:"),
        "{refusal}"
    );
    assert!(
        !refusal.contains("\\\"") && !refusal.contains("Error: "),
        "{refusal}"
    );
    let input = json!({"username":"admin","password":PASSWORD,"confirm_password":PASSWORD});
    let mut child = f
        .command()
        .arg("--admin-account-init")
        .arg(f.root.join("config.json"))
        .arg("--account-dir")
        .arg(&accounts)
        .arg("--stdin")
        .stdin(std::process::Stdio::piped())
        .stdout(std::process::Stdio::piped())
        .stderr(std::process::Stdio::piped())
        .spawn()
        .unwrap();
    child
        .stdin
        .take()
        .unwrap()
        .write_all(&serde_json::to_vec(&input).unwrap())
        .unwrap();
    let out = child.wait_with_output().unwrap();
    assert!(out.status.success(), "{out:?}");
    f.start();
    (f, Admin { port })
}

#[test]
fn admin_https_login_session_logout_and_boundary_precedence() {
    let (mut f, a) = admin_fixture();

    // Fixed offline document with strict headers.
    let page = a.call("GET", "/", "", &[]);
    assert_eq!(page.status, 200);
    assert_eq!(
        page.header("content-type"),
        Some("text/html; charset=utf-8")
    );
    assert_eq!(page.header("cache-control"), Some("no-store"));
    assert_eq!(page.header("x-content-type-options"), Some("nosniff"));
    let csp = page.header("content-security-policy").unwrap();
    assert!(csp.starts_with("default-src 'none'") && !csp.contains("unsafe"));
    assert!(String::from_utf8_lossy(&page.body).contains("Sign in to File Mover"));
    assert_eq!(a.call("POST", "/", "", &[]).status, 405);

    // Unauthenticated session read.
    let none = a.call("GET", "/api/v2/admin/session", "", &[]);
    assert_eq!(none.status, 401);
    assert_eq!(none.json(), json!({"error":"authentication_required"}));

    // Login boundary checks precede credential work (no rate-limit attempt used).
    let body = serde_json::to_vec(&json!({"username":"admin","password":PASSWORD})).unwrap();
    let json_type = "Content-Type: application/json\r\n";
    for origin in [
        String::new(),
        "Origin: null\r\n".into(),
        "Origin: https://evil.example\r\n".into(),
        format!("Origin: http://localhost:{}\r\n", a.port),
    ] {
        let r = a.call(
            "POST",
            "/api/v2/admin/login",
            &format!("{origin}{json_type}"),
            &body,
        );
        assert_eq!(r.status, 403, "{origin}");
        assert_eq!(r.json(), json!({"error":"admin_request_forbidden"}));
    }
    let origin = format!("Origin: {}\r\n", a.origin());
    let r = a.call(
        "POST",
        "/api/v2/admin/login",
        &format!("{origin}Content-Type: text/plain\r\n"),
        &body,
    );
    assert_eq!(r.status, 415);
    for bad in [
        b"not json".as_slice(),
        br#"{"username":"admin"}"#,
        br#"{"username":"admin","password":"x","extra":1}"#,
        br#"{"username":"","password":"x"}"#,
    ] {
        let r = a.call(
            "POST",
            "/api/v2/admin/login",
            &format!("{origin}{json_type}"),
            bad,
        );
        assert_eq!(r.status, 400);
        assert_eq!(r.json(), json!({"error":"invalid_json"}));
    }

    // Wrong password: exact generic message (attempt 1).
    let wrong = a.login("admin", "wrong");
    assert_eq!(wrong.status, 401);
    assert_eq!(
        wrong.json(),
        json!({"error":"invalid_credentials","message":"Invalid username or password."})
    );
    assert!(wrong.header("set-cookie").is_none());

    // Correct login (attempt 2).
    let ok = a.login("admin", PASSWORD);
    assert_eq!(ok.status, 200);
    assert_eq!(ok.json(), json!({"authenticated":true}));
    assert_eq!(ok.header("cache-control"), Some("no-store"));
    let set = ok.header("set-cookie").unwrap();
    assert!(set.starts_with("__Host-mover_admin="));
    assert!(set.ends_with("; Secure; HttpOnly; Path=/; SameSite=Strict"));
    assert!(!set.contains("Domain") && !set.contains("Expires") && !set.contains("Max-Age"));
    let csrf = ok.header("mover-csrf-token").unwrap().to_owned();
    assert_eq!(csrf.len(), 64);
    let cookie = ok.cookie();
    assert!(!String::from_utf8_lossy(&ok.body).contains(&csrf));

    // Session read returns the same CSRF and the configured timeout.
    let s = a.session(&cookie, "");
    assert_eq!(s.status, 200);
    assert_eq!(
        s.json(),
        json!({"authenticated":true,"inactivity_timeout_seconds":1800})
    );
    assert_eq!(s.header("mover-csrf-token"), Some(csrf.as_str()));

    // Marked deliberate read: CSRF required; supplied Origin/Fetch-Metadata must match.
    let marker = "Mover-Admin-Activity: interaction\r\n";
    assert_eq!(a.session(&cookie, marker).status, 403);
    let with_csrf = format!("{marker}Mover-CSRF-Token: {csrf}\r\n");
    assert_eq!(
        a.session(
            &cookie,
            &format!("{with_csrf}Origin: https://evil.example\r\n")
        )
        .status,
        403
    );
    assert_eq!(
        a.session(
            &cookie,
            &format!("{with_csrf}Sec-Fetch-Site: cross-site\r\n")
        )
        .status,
        403
    );
    assert_eq!(
        a.session(
            &cookie,
            &format!("{with_csrf}Sec-Fetch-Site: same-origin\r\n")
        )
        .status,
        200
    );
    assert_eq!(
        a.session(&cookie, "Mover-Admin-Activity: other\r\n").status,
        400
    );

    // Second, independent session (attempt 3).
    let other = a.login("admin", PASSWORD);
    assert_eq!(other.status, 200);
    let other_cookie = other.cookie();
    let other_csrf = other.header("mover-csrf-token").unwrap().to_owned();
    assert_ne!(other_cookie, cookie);

    // Admitted producer work before global logout must finish afterwards.
    prepare_payload(&f);
    let input = f.input();
    assert_eq!(f.https("POST", "/api/v2/jobs", "", &input).0, 202);

    // Logout: authentication first, then Origin and session-bound CSRF.
    assert_eq!(a.logout("__Host-mover_admin=00", &origin).status, 401);
    assert_eq!(
        a.logout(&cookie, &format!("Mover-CSRF-Token: {csrf}\r\n"))
            .status,
        403
    );
    assert_eq!(
        a.logout(
            &cookie,
            &format!("{origin}Mover-CSRF-Token: {other_csrf}\r\n")
        )
        .status,
        403,
        "session-swapped CSRF must fail"
    );
    let out = a.logout(&cookie, &format!("{origin}Mover-CSRF-Token: {csrf}\r\n"));
    assert_eq!(out.status, 204);
    assert!(out.body.is_empty());
    assert_eq!(
        out.header("set-cookie"),
        Some("__Host-mover_admin=; Max-Age=0; Secure; HttpOnly; Path=/; SameSite=Strict")
    );
    for c in [&cookie, &other_cookie] {
        assert_eq!(a.session(c, "").status, 401, "logout revokes every session");
    }
    wait_commit(&f);

    // Target authority, forwarded identity and unimplemented routes.
    let wrong_host = a.raw(b"GET / HTTP/1.1\r\nHost: evil.example\r\nContent-Length: 0\r\n\r\n");
    assert_eq!(wrong_host.status, 403);
    assert_eq!(
        a.call("GET", "/", "X-Forwarded-For: 10.0.0.1\r\n", &[])
            .status,
        400
    );
    // Read routes exist since increment131 and require a session.
    for path in [
        "/api/v2/jobs/1",
        "/api/v2/admin/jobs",
        "/api/v2/retention",
        "/api/v2/jobs/1/retention",
    ] {
        assert_eq!(a.call("GET", path, "", &[]).status, 401, "{path}");
    }
    for path in ["/api/v2/jobs", "/healthz", "/index.html"] {
        let r = a.call("GET", path, "", &[]);
        assert_eq!(r.status, 404, "{path}");
        assert_eq!(r.json(), json!({"error":"not_found"}));
    }

    // Producer and private operator audiences never serve admin routes.
    let producer = f.https("POST", "/api/v2/admin/login", "", &json!({}));
    assert_eq!(producer.0, 403);
    assert_ne!(f.operator("/api/v2/admin/session").0, 200);

    // Rolling limit: two more wrong attempts reach five; then even correct ones wait.
    assert_eq!(a.login("admin", "wrong").status, 401);
    assert_eq!(a.login("someone", "wrong").status, 401);
    let limited = a.login("admin", PASSWORD);
    assert_eq!(limited.status, 429);
    assert_eq!(limited.header("retry-after"), Some("60"));
    assert_eq!(limited.json(), json!({"error":"rate_limited"}));

    // Restart: empty session map and limiter; earlier sessions stay invalid.
    f.stop();
    f.start();
    let fresh = a.login("admin", PASSWORD);
    assert_eq!(fresh.status, 200);
    let fresh_cookie = fresh.cookie();
    f.stop();
    f.start();
    assert_eq!(a.session(&fresh_cookie, "").status, 401);

    // Logs never contain passwords or session secrets.
    let log = fs::read_to_string(f.root.join("service.log")).unwrap();
    for secret in [PASSWORD, &csrf, &cookie[19..], &fresh_cookie[19..]] {
        assert!(!log.contains(secret));
    }
    f.stop();
}

#[test]
fn invalid_admin_configuration_refuses_before_listening() {
    let (mut f, _) = admin_fixture();
    f.stop();
    let good = f.config["admin_ingress"].clone();
    let port = f.address.port();
    for (field, value) in [
        // Producer listener reused.
        ("bind", json!(format!("127.0.0.1:{port}"))),
        // Authority port differs from bind.
        ("authority", json!("localhost:1")),
        // Account directory inside state.
        ("account_directory", json!(f.root.join("state/accounts"))),
    ] {
        f.config["admin_ingress"] = good.clone();
        f.config["admin_ingress"][field] = value;
        f.save();
        f.refuse();
    }
    f.config["admin_ingress"] = good;
    f.save();
    f.start();
    f.stop();
}

#[test]
fn admin_paths_under_retained_payload_roots_refuse_before_credential_io() {
    let (mut f, _) = admin_fixture();
    prepare_payload(&f);
    let input = f.input();
    assert_eq!(f.https("POST", "/api/v2/jobs", "", &input).0, 202);
    wait_commit(&f);
    f.stop();
    let committed = f.root.join(format!("destination/{UUID}"));
    let snapshot = |dir: &Path| -> Vec<(PathBuf, Vec<u8>)> {
        let mut out = Vec::new();
        for e in fs::read_dir(dir).unwrap() {
            let p = e.unwrap().path();
            if p.is_file() {
                out.push((p.clone(), fs::read(&p).unwrap()));
            }
        }
        out.sort();
        out
    };
    let before = snapshot(&committed);
    assert!(!before.is_empty());
    let good = f.config.clone();
    // The tracked destination is no longer configured but still retained in state.
    f.config["destination_root"] = json!(f.root.join("different-destination"));
    let retained = f.root.join("destination/admin-tls");
    f.config["admin_ingress"]["server_certificates"] = json!([retained.join("server.der")]);
    f.config["admin_ingress"]["server_key"] = json!(retained.join("server.key.der"));
    f.config["admin_ingress"]["server_ca_certificates"] = json!([retained.join("ca.der")]);
    f.save();
    let text = f.refuse();
    assert!(
        text.contains("admin credentials overlap payload scope"),
        "{text}"
    );
    assert!(!retained.exists());
    f.config = good.clone();
    f.config["destination_root"] = json!(f.root.join("different-destination"));
    f.config["admin_ingress"]["account_directory"] = json!(f.root.join("destination/accounts"));
    f.save();
    let text = f.refuse();
    assert!(
        text.contains("admin account directory overlaps payload scope"),
        "{text}"
    );
    assert_eq!(snapshot(&committed), before);
    f.config = good;
    f.save();
    f.start();
    f.stop();
}

#[test]
fn admin_connection_flood_does_not_starve_producer_or_operator() {
    let (mut f, a) = admin_fixture();
    /// Stops and joins every flood thread on success or unwind; never detaches.
    struct Flood {
        stop: Arc<std::sync::atomic::AtomicBool>,
        threads: Vec<std::thread::JoinHandle<u64>>,
    }
    impl Flood {
        fn finish(&mut self) -> u64 {
            self.stop.store(true, Ordering::Relaxed);
            self.threads.drain(..).map(|t| t.join().unwrap_or(0)).sum()
        }
    }
    impl Drop for Flood {
        fn drop(&mut self) {
            self.finish();
        }
    }
    let address = std::net::SocketAddr::from(([127, 0, 0, 1], a.port));
    // Guard exists before the first spawn, so partial startup also joins.
    let mut flood = Flood {
        stop: Arc::new(std::sync::atomic::AtomicBool::new(false)),
        threads: Vec::with_capacity(4),
    };
    for _ in 0..4 {
        let stop = flood.stop.clone();
        flood.threads.push(std::thread::spawn(move || {
            let mut opened = 0_u64;
            while !stop.load(Ordering::Relaxed) {
                if std::net::TcpStream::connect_timeout(&address, Duration::from_millis(200))
                    .is_ok()
                {
                    opened += 1;
                }
            }
            opened
        }));
    }
    std::thread::sleep(Duration::from_millis(300));
    let host = format!("localhost:{}", f.address.port());
    for _ in 0..5 {
        let started = Instant::now();
        let reply = f
            .tls(
                Some("client"),
                &rustls::version::TLS13,
                &request("GET", "/api/v2/jobs", &host, "", &[]),
            )
            .expect("producer accepted during admin flood");
        assert_eq!(reply.0, 405);
        assert!(started.elapsed() < Duration::from_secs(5));
        assert_eq!(f.operator("/healthz").0, 200);
    }
    let opened = flood.finish();
    assert!(opened > 20, "flood must actually have run: {opened}");
    // The admin listener still serves after the flood.
    assert_eq!(a.call("GET", "/", "", &[]).status, 200);
    f.stop();
}

#[test]
fn admin_history_pages_and_detail_match_operator_status() {
    let (mut f, a) = admin_fixture();
    // Two committed jobs with distinct recording UUIDs.
    prepare_payload(&f);
    let first = f.input();
    assert_eq!(f.https("POST", "/api/v2/jobs", "", &first).0, 202);
    wait_commit(&f);
    let second_uuid = "6f1c2c1e-9d2b-4e8a-a7f1-2b5d3c4e5f60";
    fs::create_dir_all(f.root.join("source/current/sub")).unwrap();
    fs::write(f.root.join("source/current/a"), b"alpha2").unwrap();
    fs::write(f.root.join("source/current/sub/b"), b"bravo2!!").unwrap();
    let mut second = f.input();
    second["recording_id"] = json!(second_uuid);
    second["expected_sizes_bytes"] = json!({"a":"6","sub/b":"8"});
    assert_eq!(f.https("POST", "/api/v2/jobs", "", &second).0, 202);
    let until = Instant::now() + Duration::from_secs(15);
    while f.operator("/api/v2/jobs/2").1["state"] != "Committed" {
        assert!(Instant::now() < until);
        std::thread::sleep(Duration::from_millis(20));
    }

    // Unauthenticated reads disclose nothing.
    for path in ["/api/v2/admin/jobs", "/api/v2/jobs/1"] {
        let r = a.call("GET", path, "", &[]);
        assert_eq!(r.status, 401, "{path}");
        assert_eq!(r.json(), json!({"error":"authentication_required"}));
    }
    let ok = a.login("admin", PASSWORD);
    let cookie = ok.cookie();
    let csrf = ok.header("mover-csrf-token").unwrap().to_owned();
    let get = |path: &str, extra: &str| a.session_path(path, &cookie, extra);

    // Full page.
    let page = get("/api/v2/admin/jobs", "");
    assert_eq!(page.status, 200);
    assert_eq!(page.header("cache-control"), Some("no-store"));
    let body = page.json();
    assert_eq!(body["next_cursor"], Value::Null);
    assert_eq!(body["confirmation"], Value::Null);
    let items = body["items"].as_array().unwrap();
    assert_eq!(items.len(), 2);
    let instance = items[0]["retry_review"]["instance_id"]
        .as_str()
        .unwrap()
        .to_owned();
    assert_eq!(instance.len(), 32);
    assert_eq!(
        items[0],
        json!({"job_id":"1","generator_id":"recorder","recording_id":UUID,"state":"Committed",
            "condition":"Committed","source_paths_released":true,
            "retry_review":{"instance_id":instance,"job_id":"1","review_epoch":null},
            "cancellation":{"state":"NotRequested","requested_at":null,"stopped_at":null},
            "deletion":null})
    );
    assert_eq!(items[1]["job_id"], "2");
    assert_eq!(items[1]["recording_id"], second_uuid);

    // Cursor pagination, ascending, bound to this instance.
    let one = get("/api/v2/admin/jobs?limit=1", "").json();
    assert_eq!(one["items"].as_array().unwrap().len(), 1);
    assert_eq!(one["items"][0]["job_id"], "1");
    let cursor = one["next_cursor"].as_str().unwrap().to_owned();
    let next = get(&format!("/api/v2/admin/jobs?limit=1&cursor={cursor}"), "").json();
    assert_eq!(next["items"][0]["job_id"], "2");
    assert_eq!(next["next_cursor"], Value::Null);
    let foreign = get(
        &format!("/api/v2/admin/jobs?cursor=c1.{}.1", "f".repeat(32)),
        "",
    );
    assert_eq!(foreign.status, 400);
    assert_eq!(foreign.json(), json!({"error":"invalid_cursor"}));
    for (query, code) in [
        ("limit=0", "invalid_http"),
        ("limit=1&limit=1", "invalid_http"),
        ("state=Committed", "invalid_http"),
        ("cursor=bogus", "invalid_cursor"),
        ("confirm_action=cancel&job_ids=1", "invalid_selection"),
    ] {
        let r = get(&format!("/api/v2/admin/jobs?{query}"), "");
        assert_eq!(r.status, 400, "{query}");
        assert_eq!(r.json()["error"], code, "{query}");
    }
    assert_eq!(
        a.call(
            "POST",
            "/api/v2/admin/jobs",
            &format!("Cookie: {cookie}\r\n"),
            &[]
        )
        .status,
        405
    );

    // Detail is exactly the operator's status for the same job.
    let detail = get("/api/v2/jobs/1", "");
    assert_eq!(detail.status, 200);
    assert_eq!(detail.json(), f.operator("/api/v2/jobs/1").1);
    assert_eq!(
        get("/api/v2/jobs/999", "").json(),
        json!({"error":"not_found"})
    );
    assert_eq!(get("/api/v2/jobs/999", "").status, 404);
    assert_eq!(
        get("/api/v2/jobs/01", "").json(),
        json!({"error":"invalid_job_id"})
    );
    for path in [
        "/api/v2/jobs/1/resume",
        "/api/v2/jobs/1/reset-missing",
        "/api/v2/jobs/1?x=1",
        "/api/v2/retention?x=1",
    ] {
        assert_eq!(get(path, "").status, 404, "{path}");
    }

    // Retention: per-job identical to the operator; global identical except the
    // cached source-space sample age, which advances between two reads.
    let job = get("/api/v2/jobs/1/retention", "");
    assert_eq!(job.status, 200);
    assert_eq!(job.json(), f.operator("/api/v2/jobs/1/retention").1);
    assert_eq!(job.json()["details"]["scope"], "Job");
    let mut admin_global = get("/api/v2/retention", "").json();
    let mut operator_global = f.operator("/api/v2/retention").1;
    for v in [&mut admin_global, &mut operator_global] {
        v["details"]["source_space_admission"]["sample_age_ms"] = Value::Null;
    }
    assert_eq!(admin_global, operator_global);
    assert_eq!(admin_global["details"]["scope"], "Global");
    assert_eq!(admin_global["details"]["retained_jobs"], 2);
    assert_eq!(admin_global["details"]["filesystem_inspected"], false);
    assert_eq!(get("/api/v2/jobs/999/retention", "").status, 404);
    assert_eq!(
        get("/api/v2/jobs/01/retention", "").json(),
        json!({"error":"invalid_job_id"})
    );
    assert_eq!(
        a.call(
            "POST",
            "/api/v2/retention",
            &format!("Cookie: {cookie}\r\n"),
            &[]
        )
        .status,
        405
    );

    // Deliberate reads need the session CSRF token.
    let marker = "Mover-Admin-Activity: interaction\r\n";
    assert_eq!(get("/api/v2/admin/jobs", marker).status, 403);
    assert_eq!(
        get(
            "/api/v2/jobs/1",
            &format!("{marker}Mover-CSRF-Token: {csrf}\r\n")
        )
        .status,
        200
    );

    // After global logout nothing is readable with the old cookie.
    let origin = format!("Origin: {}\r\n", a.origin());
    assert_eq!(
        a.logout(&cookie, &format!("{origin}Mover-CSRF-Token: {csrf}\r\n"))
            .status,
        204
    );
    assert_eq!(get("/api/v2/admin/jobs", "").status, 401);
    assert_eq!(get("/api/v2/jobs/1", "").status, 401);
    assert_eq!(get("/api/v2/retention", "").status, 401);
    assert_eq!(get("/api/v2/jobs/1/retention", "").status, 401);
    f.stop();
}
