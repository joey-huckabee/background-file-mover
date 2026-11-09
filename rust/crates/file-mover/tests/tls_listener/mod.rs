//! Disposable real-service HTTP/TLS tests, executed only by the SLES gate.
use super::*;
use serde_json::{Value, json};
use std::{
    io::{Read, Write},
    os::unix::{fs::PermissionsExt, net::UnixStream},
    path::{Path, PathBuf},
    process::{Child, Command},
    sync::atomic::{AtomicU64, Ordering},
    time::Instant,
};
static NEXT: AtomicU64 = AtomicU64::new(0);
const UUID: &str = "b580ed41-283f-40de-89ec-8fb6b04d895f";
fn executable() -> String {
    std::env::var("FILE_MOVER_TEST_EXECUTABLE").expect("audited SLES service binary")
}
fn mode(path: &Path, value: u32) {
    fs::set_permissions(path, fs::Permissions::from_mode(value)).unwrap();
}
fn response(bytes: &[u8]) -> (u16, Value) {
    let end = bytes
        .windows(4)
        .position(|b| b == b"\r\n\r\n")
        .expect("complete HTTP reply");
    let head = std::str::from_utf8(&bytes[..end]).unwrap();
    let status = head.split_whitespace().nth(1).unwrap().parse().unwrap();
    (status, serde_json::from_slice(&bytes[end + 4..]).unwrap())
}
fn request(method: &str, path: &str, host: &str, headers: &str, body: &[u8]) -> Vec<u8> {
    let mut bytes = format!(
        "{method} {path} HTTP/1.1\r\nHost: {host}\r\nContent-Type: application/json\r\nContent-Length: {}\r\n{headers}\r\n",
        body.len()
    )
    .into_bytes();
    bytes.extend_from_slice(body);
    bytes
}
struct Fixture {
    root: PathBuf,
    address: std::net::SocketAddr,
    config: Value,
    child: Option<Child>,
}
impl Fixture {
    fn new(https: bool) -> Self {
        let root = std::env::temp_dir().join(format!(
            "native-{}-{}",
            std::process::id(),
            NEXT.fetch_add(1, Ordering::Relaxed)
        ));
        fs::create_dir(&root).unwrap();
        mode(&root, 0o700);
        for name in [
            "state",
            "operator",
            "credentials",
            "source",
            "source/current",
            "source/.file-mover",
            "destination",
            "destination/.file-mover",
        ] {
            fs::create_dir(root.join(name)).unwrap();
            mode(&root.join(name), 0o700);
        }
        let source = json!({"version":3,"coordinator_id":"test-owner","root_id":"local-source","endpoint_id":"test-local","marker_id":"test-marker","filesystem":"local","role":"source"});
        let destination = json!({"version":3,"coordinator_id":"test-owner","root_id":"configured-local","endpoint_id":"test-local-destination","marker_id":"test-destination-marker","filesystem":"local","role":"destination"});
        for (name, binding, marker) in [
            ("source", &source, "source-binding.json"),
            ("destination", &destination, "destination-binding.json"),
        ] {
            let area = root.join(name).join(".file-mover");
            fs::write(area.join("coordinator.lock"), b"").unwrap();
            mode(&area.join("coordinator.lock"), 0o600);
            fs::write(area.join(marker), serde_json::to_vec(binding).unwrap()).unwrap();
            mode(&area.join(marker), 0o600);
        }
        let address = std::net::TcpListener::bind("127.0.0.1:0")
            .unwrap()
            .local_addr()
            .unwrap();
        let native = if https {
            for name in ["server.der", "server.key.der", "ca.der"] {
                fs::write(root.join("credentials").join(name), fixture(name)).unwrap();
                mode(
                    &root.join("credentials").join(name),
                    if name.ends_with("key.der") {
                        0o600
                    } else {
                        0o400
                    },
                );
            }
            json!({"transport":"https","operator_socket":root.join("operator/api.sock"),"authority":format!("localhost:{}",address.port()),"server_certificates":[root.join("credentials/server.der")],"server_key":root.join("credentials/server.key.der"),"server_ca_certificates":[root.join("credentials/ca.der")],"client_ca_certificates":[root.join("credentials/ca.der")],"clients":[{"sha256":mover_fs::sha256_hex(&fixture("client.der")),"generator_id":"recorder"}]})
        } else {
            json!({"transport":"http","operator_socket":root.join("operator/api.sock")})
        };
        let config = json!({"bind":address.to_string(),"native_ingress":native,"generator_id":"recorder","source_root":root.join("source"),"destination_root":root.join("destination"),"state_database":root.join("state/jobs.sqlite"),"source_binding":source,"destination_binding":destination,"shutdown_wait_seconds":5});
        let f = Self {
            root,
            address,
            config,
            child: None,
        };
        f.save();
        f
    }
    fn save(&self) {
        fs::write(
            self.root.join("config.json"),
            serde_json::to_vec(&self.config).unwrap(),
        )
        .unwrap();
    }
    fn command(&self) -> Command {
        let mut c = Command::new(executable());
        c.env_remove("FILE_MOVER_TLS_FIXTURES");
        c
    }
    fn initialize(&self) {
        let result = self
            .command()
            .arg("--initialize-source")
            .arg(self.root.join("config.json"))
            .output()
            .unwrap();
        assert!(result.status.success(), "{result:?}");
    }
    fn start(&mut self) {
        self.start_paused(None);
    }
    fn start_paused(&mut self, pause: Option<(&str, &Path)>) {
        let log = fs::File::create(self.root.join("service.log")).unwrap();
        let mut command = self.command();
        if let Some((operation, path)) = pause {
            command
                .env("FILE_MOVER_QUALIFICATION_PAUSE", operation)
                .env("FILE_MOVER_QUALIFICATION_RENDEZVOUS", path);
            if operation == "claim_apply" {
                command.env("FILE_MOVER_QUALIFICATION_CLAIM_INDEX", "0");
            }
        }
        self.child = Some(
            command
                .arg(self.root.join("config.json"))
                .stdout(log.try_clone().unwrap())
                .stderr(log)
                .spawn()
                .unwrap(),
        );
        let until = Instant::now() + Duration::from_secs(15);
        loop {
            if fs::read_to_string(self.root.join("service.log"))
                .unwrap()
                .contains("Ready on native producer")
            {
                assert_eq!(self.operator("/healthz").0, 200);
                return;
            }
            assert!(
                self.child.as_mut().unwrap().try_wait().unwrap().is_none(),
                "{}",
                fs::read_to_string(self.root.join("service.log")).unwrap()
            );
            assert!(Instant::now() < until, "listener readiness timeout");
            std::thread::sleep(Duration::from_millis(20));
        }
    }
    fn operator(&self, path: &str) -> (u16, Value) {
        let mut s = UnixStream::connect(self.root.join("operator/api.sock")).unwrap();
        s.set_read_timeout(Some(Duration::from_secs(5))).unwrap();
        s.write_all(&request("GET", path, "localhost", "", &[]))
            .unwrap();
        let mut b = Vec::new();
        s.read_to_end(&mut b).unwrap();
        response(&b)
    }
    fn tls(
        &self,
        client: Option<&str>,
        version: &'static SupportedProtocolVersion,
        bytes: &[u8],
    ) -> Result<(u16, Value), String> {
        Self::tls_at(self.address, client, version, bytes)
    }
    fn tls_at(
        address: std::net::SocketAddr,
        client: Option<&str>,
        version: &'static SupportedProtocolVersion,
        bytes: &[u8],
    ) -> Result<(u16, Value), String> {
        let config = ClientConfig::builder_with_provider(tls::provider())
            .with_protocol_versions(&[version])
            .unwrap()
            .with_root_certificates(roots("ca.der"));
        let mut config = if let Some(client) = client {
            config
                .with_client_auth_cert(
                    vec![certificate(&format!("{client}.der"))],
                    key(&format!("{client}.key.der")),
                )
                .unwrap()
        } else {
            config.with_no_client_auth()
        };
        config.alpn_protocols = vec![b"http/1.1".to_vec()];
        config.resumption = Resumption::disabled();
        let socket =
            std::net::TcpStream::connect_timeout(&address, Duration::from_secs(5)).unwrap();
        socket
            .set_read_timeout(Some(Duration::from_secs(5)))
            .unwrap();
        socket
            .set_write_timeout(Some(Duration::from_secs(5)))
            .unwrap();
        let connection = rustls::ClientConnection::new(
            Arc::new(config),
            ServerName::try_from("localhost").unwrap(),
        )
        .unwrap();
        let mut stream = rustls::StreamOwned::new(connection, socket);
        let result = (|| {
            stream.write_all(bytes)?;
            stream.flush()?;
            let mut out = Vec::new();
            stream.read_to_end(&mut out)?;
            Ok::<_, std::io::Error>(out)
        })();
        match result {
            Ok(out) if out.starts_with(b"HTTP/1.1 ") => Ok(response(&out)),
            Ok(_) => Err("connection closed before HTTP response".into()),
            Err(e) => {
                assert!(
                    !matches!(
                        e.kind(),
                        std::io::ErrorKind::TimedOut | std::io::ErrorKind::WouldBlock
                    ),
                    "timeout is not refusal evidence: {e}"
                );
                Err(e.to_string())
            }
        }
    }
    fn https(&self, method: &str, path: &str, headers: &str, body: &Value) -> (u16, Value) {
        self.tls(
            Some("client"),
            &rustls::version::TLS13,
            &request(
                method,
                path,
                &format!("localhost:{}", self.address.port()),
                headers,
                &serde_json::to_vec(body).unwrap(),
            ),
        )
        .expect("authenticated HTTP reply")
    }
    fn input(&self) -> Value {
        json!({"recording_id":UUID,"generator_id":"recorder","source_directory":self.root.join("source/current"),"files":["a","sub/b"],"expected_sizes_bytes":{"a":"5","sub/b":"7"}})
    }
    fn stop(&mut self) {
        assert!(
            self.command()
                .arg("--stop")
                .arg(self.root.join("config.json"))
                .output()
                .unwrap()
                .status
                .success()
        );
        let until = Instant::now() + Duration::from_secs(10);
        loop {
            if let Some(s) = self.child.as_mut().unwrap().try_wait().unwrap() {
                assert!(s.success());
                self.child = None;
                return;
            }
            assert!(Instant::now() < until, "graceful stop timeout");
            std::thread::sleep(Duration::from_millis(20));
        }
    }
    fn refuse(&self) -> String {
        let log = fs::File::create(self.root.join("refusal.log")).unwrap();
        let mut child = self
            .command()
            .arg(self.root.join("config.json"))
            .stdout(log.try_clone().unwrap())
            .stderr(log)
            .spawn()
            .unwrap();
        let until = Instant::now() + Duration::from_secs(10);
        loop {
            if let Some(s) = child.try_wait().unwrap() {
                assert!(!s.success());
                break;
            }
            if Instant::now() >= until {
                child.kill().unwrap();
                child.wait().unwrap();
                panic!("unsafe startup did not refuse");
            }
            std::thread::sleep(Duration::from_millis(20));
        }
        let text = fs::read_to_string(self.root.join("refusal.log")).unwrap();
        assert!(!text.contains("Ready on"));
        text
    }
}
impl Drop for Fixture {
    fn drop(&mut self) {
        if let Some(mut child) = self.child.take() {
            let _ = child.kill();
            let _ = child.wait();
        }
        let _ = fs::remove_dir_all(&self.root);
    }
}

#[test]
fn native_https_submission_denials_replay_and_restart_preserve_original_bytes() {
    let mut f = Fixture::new(true);
    f.initialize();
    f.start();
    let body = f.input();
    let host = format!("localhost:{}", f.address.port());
    for version in [&rustls::version::TLS12, &rustls::version::TLS13] {
        for client in [
            None,
            Some("untrusted-client"),
            Some("expired-client"),
            Some("wrong-usage-client"),
        ] {
            assert!(
                f.tls(
                    client,
                    version,
                    &request(
                        "POST",
                        "/api/v2/jobs",
                        &host,
                        "",
                        &serde_json::to_vec(&body).unwrap()
                    )
                )
                .is_err()
            );
        }
        let denied = f
            .tls(
                Some("unapproved-client"),
                version,
                &request(
                    "POST",
                    "/api/v2/jobs",
                    &host,
                    "",
                    &serde_json::to_vec(&body).unwrap(),
                ),
            )
            .unwrap();
        assert_eq!(denied.0, 403);
        assert_eq!(denied.1["error"], "caller_not_authorized");
    }
    for path in [
        "/healthz",
        "/api/v2/retention",
        "/api/v2/jobs/1",
        "/api/v2/jobs/1/resume",
        "/api/v2/admin/logout",
        "/api/v2/jobs?x=1",
        "/api/v2/jobs/",
    ] {
        let r = f.https("GET", path, "", &json!(null));
        assert_eq!(r.0, 403);
        assert_eq!(r.1["error"], "producer_route_forbidden");
    }
    for header in [
        "X-File-Mover-Generator: recorder\r\n",
        "Authorization: anything\r\n",
        "Cookie: a=b\r\n",
        "Forwarded: for=x\r\n",
        "X-Forwarded-For: x\r\n",
        "X-Client-Cert: x\r\n",
    ] {
        assert_eq!(f.https("POST", "/api/v2/jobs", header, &body).0, 400);
    }
    assert_eq!(f.https("GET", "/api/v2/jobs", "", &body).0, 405);
    assert_eq!(
        f.tls(
            Some("client"),
            &rustls::version::TLS13,
            &request(
                "POST",
                "/api/v2/jobs",
                "wrong.invalid:443",
                "",
                &serde_json::to_vec(&body).unwrap()
            )
        )
        .unwrap()
        .0,
        400
    );
    let mut wrong = body.clone();
    wrong["generator_id"] = json!("other");
    assert_eq!(f.https("POST", "/api/v2/jobs", "", &wrong).0, 403);
    wrong = body.clone();
    wrong["source_directory"] = json!(f.root.join("destination"));
    assert_eq!(f.https("POST", "/api/v2/jobs", "", &wrong).0, 403);
    assert_eq!(
        f.operator("/api/v2/retention").1["details"]["retained_jobs"],
        0
    );
    assert!(!f.root.join("source/.file-mover/1-0").exists());
    fs::create_dir(f.root.join("source/current/sub")).unwrap();
    mode(&f.root.join("source/current/sub"), 0o700);
    fs::write(f.root.join("source/current/a"), b"alpha").unwrap();
    fs::write(f.root.join("source/current/sub/b"), b"bravo!!").unwrap();
    let first = f
        .tls(
            Some("client"),
            &rustls::version::TLS12,
            &request(
                "POST",
                "/api/v2/jobs",
                &host,
                "",
                &serde_json::to_vec(&body).unwrap(),
            ),
        )
        .expect("TLS1.2 producer acceptance");
    assert_eq!(first.0, 202);
    assert_eq!(first.1["job_id"], "1");
    let manifest = f.root.join(format!("destination/{UUID}/COMMITTED.json"));
    let until = Instant::now() + Duration::from_secs(15);
    while f.operator("/api/v2/jobs/1").1["state"] != "Committed" {
        assert!(Instant::now() < until);
        std::thread::sleep(Duration::from_millis(20));
    }
    let original = fs::read(&manifest).unwrap();
    let measured: Value = serde_json::from_slice(&original).unwrap();
    for (i, data) in [b"alpha".as_slice(), b"bravo!!".as_slice()]
        .iter()
        .enumerate()
    {
        assert_eq!(measured["files"][i]["size_bytes"], data.len().to_string());
        assert_eq!(measured["files"][i]["sha256"], mover_fs::sha256_hex(data));
    }
    fs::write(f.root.join("source/current/a"), b"replacement-a").unwrap();
    fs::write(f.root.join("source/current/sub/b"), b"replacement-b").unwrap();
    let mut reordered = body.clone();
    reordered["files"] = json!(["sub/b", "a"]);
    for restart in [false, true] {
        if restart {
            f.stop();
            f.start();
        }
        assert_eq!(f.https("POST", "/api/v2/jobs", "", &reordered), first);
        assert_eq!(fs::read(&manifest).unwrap(), original);
        for (name, data, replacement, index) in [
            ("a", b"alpha".as_slice(), b"replacement-a".as_slice(), 0),
            (
                "sub/b",
                b"bravo!!".as_slice(),
                b"replacement-b".as_slice(),
                1,
            ),
        ] {
            assert_eq!(
                fs::read(f.root.join("source/current").join(name)).unwrap(),
                replacement
            );
            assert_eq!(
                fs::read(f.root.join(format!("source/.file-mover/1-{index}/data"))).unwrap(),
                data
            );
            assert_eq!(
                fs::read(f.root.join(format!("destination/{UUID}/{name}"))).unwrap(),
                data
            );
        }
    }
    f.stop();
}

#[test]
fn explicit_native_http_needs_no_credentials_and_never_exposes_operator_routes() {
    let mut f = Fixture::new(false);
    f.initialize();
    f.start();
    let mut stream = std::net::TcpStream::connect(f.address).unwrap();
    stream
        .set_read_timeout(Some(Duration::from_secs(5)))
        .unwrap();
    stream
        .write_all(&request("GET", "/healthz", "localhost", "", &[]))
        .unwrap();
    let mut out = Vec::new();
    stream.read_to_end(&mut out).unwrap();
    assert_eq!(response(&out).0, 403);
    assert_eq!(f.operator("/healthz").0, 200);
    assert_eq!(fs::read_dir(f.root.join("credentials")).unwrap().count(), 0);
    fs::create_dir(f.root.join("source/current/sub")).unwrap();
    mode(&f.root.join("source/current/sub"), 0o700);
    fs::write(f.root.join("source/current/a"), b"alpha").unwrap();
    fs::write(f.root.join("source/current/sub/b"), b"bravo!!").unwrap();
    let mut stream = std::net::TcpStream::connect(f.address).unwrap();
    stream
        .set_read_timeout(Some(Duration::from_secs(15)))
        .unwrap();
    stream
        .write_all(&request(
            "POST",
            "/api/v2/jobs",
            "localhost",
            "",
            &serde_json::to_vec(&f.input()).unwrap(),
        ))
        .unwrap();
    let mut out = Vec::new();
    stream.read_to_end(&mut out).unwrap();
    assert_eq!(response(&out).0, 202);
    f.stop();
}

#[test]
fn native_tls_startup_refuses_invalid_credentials_before_source_bootstrap() {
    let mut f = Fixture::new(true);
    f.initialize();
    let config = f.config.clone();
    let keypath = f.root.join("credentials/server.key.der");
    let certpath = f.root.join("credentials/server.der");
    let db = fs::read(f.root.join("state/jobs.sqlite")).unwrap();
    let source = fs::read(f.root.join("source/.file-mover/source-binding.json")).unwrap();
    for case in 0..9 {
        f.config = config.clone();
        fs::write(&keypath, fixture("server.key.der")).unwrap();
        mode(&keypath, 0o600);
        mode(&certpath, 0o600);
        fs::write(&certpath, fixture("server.der")).unwrap();
        match case {
            0 => {
                f.config["native_ingress"]["server_key"] =
                    json!(f.root.join("credentials/missing"));
            }
            1 => mode(&keypath, 0o644),
            2 => {
                fs::write(&certpath, b"invalid certificate").unwrap();
            }
            3 => {
                fs::write(&keypath, b"invalid key").unwrap();
            }
            4 => {
                fs::write(&keypath, fixture("client.key.der")).unwrap();
            }
            5 => {
                fs::write(&certpath, fixture("expired-server.der")).unwrap();
                fs::write(&keypath, fixture("expired-server.key.der")).unwrap();
            }
            6 => {
                f.config["native_ingress"]["authority"] =
                    json!(format!("wrong.invalid:{}", f.address.port()));
            }
            7 => {
                fs::write(&certpath, fixture("client.der")).unwrap();
                fs::write(&keypath, fixture("client.key.der")).unwrap();
            }
            _ => {
                fs::remove_file(&keypath).unwrap();
                std::os::unix::fs::symlink("server.der", &keypath).unwrap();
            }
        }
        f.save();
        let error = f.refuse();
        assert!(!error.contains("PRIVATE KEY"));
        assert_eq!(fs::read(f.root.join("state/jobs.sqlite")).unwrap(), db);
        assert_eq!(
            fs::read(f.root.join("source/.file-mover/source-binding.json")).unwrap(),
            source
        );
        assert!(!f.root.join("operator/api.sock").exists());
        if case == 8 {
            fs::remove_file(&keypath).unwrap();
        }
    }
}

#[test]
fn native_handshake_slots_do_not_block_private_operator_or_local_stop() {
    let mut f = Fixture::new(true);
    f.initialize();
    f.start();
    let streams: Vec<_> = (0..6)
        .map(|_| std::net::TcpStream::connect(f.address).unwrap())
        .collect();
    std::thread::sleep(Duration::from_millis(100));
    let start = Instant::now();
    assert_eq!(f.operator("/healthz").0, 200);
    assert!(start.elapsed() < Duration::from_secs(2));
    f.stop();
    assert!(start.elapsed() < Duration::from_secs(5));
    drop(streams);
}

#[test]
fn invalid_native_transport_configurations_refuse_before_state_or_endpoint_creation() {
    let mut f = Fixture::new(true);
    let original = f.config.clone();
    for case in 0..9 {
        f.config = original.clone();
        match case {
            0 => {
                f.config["protected_ingress"] = json!({"producer_socket":f.root.join("p/api.sock"),"operator_socket":f.root.join("o/api.sock"),"proxy_uid":2000,"proxy_gid":2001});
            }
            1 => {
                f.config["native_ingress"]["transport"] = json!("http");
            }
            2 => {
                f.config["native_ingress"] =
                    json!({"transport":"http","operator_socket":f.root.join("operator/api.sock")});
                f.config["bind"] = json!("0.0.0.0:8080");
            }
            3 => {
                f.config["native_ingress"]["operator_socket"] =
                    json!(f.root.join("state/jobs.sqlite-journal"));
            }
            4 => {
                f.config["native_ingress"]["server_key"] =
                    json!(f.root.join("source/current/key.der"));
            }
            5 => {
                f.config["native_ingress"]["clients"][0]["generator_id"] = json!("other");
            }
            6 => {
                f.config["native_ingress"]["authority"] = json!("localhost:0");
            }
            7 => {
                f.config["native_ingress"]["clients"] = json!([]);
            }
            _ => {
                f.config["native_ingress"]["server_ca_certificates"] = json!([]);
            }
        }
        f.save();
        f.refuse();
        assert!(!f.root.join("state/instance.lock").exists());
        assert!(!f.root.join("state/jobs.sqlite").exists());
        assert!(!f.root.join("operator/api.sock").exists());
        assert!(
            !f.root
                .join("source/.file-mover/source-enrollment.json")
                .exists()
        );
    }
}

fn copy_credential(f: &Fixture, name: &str) -> PathBuf {
    let path = f.root.join("credentials").join(name);
    fs::write(&path, fixture(name)).unwrap();
    mode(
        &path,
        if name.ends_with("key.der") {
            0o600
        } else {
            0o400
        },
    );
    path
}
fn tls_control(f: &Fixture, reload: bool, success: bool) -> Value {
    let out = f
        .command()
        .arg(if reload {
            "--reload-tls"
        } else {
            "--tls-status"
        })
        .arg(f.root.join("config.json"))
        .output()
        .unwrap();
    assert_eq!(out.status.success(), success, "{out:?}");
    serde_json::from_slice(&out.stdout).expect("private TLS control JSON")
}
fn warm_tls(f: &Fixture) -> rustls::StreamOwned<rustls::ClientConnection, std::net::TcpStream> {
    let mut c = ClientConfig::builder_with_provider(tls::provider())
        .with_protocol_versions(&[&rustls::version::TLS13])
        .unwrap()
        .with_root_certificates(roots("ca.der"))
        .with_client_auth_cert(vec![certificate("client.der")], key("client.key.der"))
        .unwrap();
    c.alpn_protocols = vec![b"http/1.1".to_vec()];
    c.resumption = Resumption::disabled();
    let socket = std::net::TcpStream::connect(f.address).unwrap();
    socket
        .set_read_timeout(Some(Duration::from_secs(5)))
        .unwrap();
    socket
        .set_write_timeout(Some(Duration::from_secs(5)))
        .unwrap();
    let mut s = rustls::StreamOwned::new(
        rustls::ClientConnection::new(Arc::new(c), ServerName::try_from("localhost").unwrap())
            .unwrap(),
        socket,
    );
    while s.conn.is_handshaking() {
        s.conn.complete_io(&mut s.sock).unwrap();
    }
    s
}
fn expect_closed(s: &mut std::net::TcpStream) {
    s.set_read_timeout(Some(Duration::from_secs(2))).unwrap();
    // TLS 1.3 tickets may already be buffered before cancellation. Require the
    // transport to reach EOF/reset, rather than mistaking buffered bytes for life.
    let until = Instant::now() + Duration::from_secs(2);
    let mut received = 0;
    loop {
        match s.read(&mut [0; 1024]) {
            Ok(0) => break,
            Ok(n) => {
                received += n;
                assert!(received <= 65536 && Instant::now() < until);
            }
            Err(e) => {
                assert!(
                    matches!(
                        e.kind(),
                        std::io::ErrorKind::ConnectionReset | std::io::ErrorKind::ConnectionAborted
                    ),
                    "stale connection did not close: {e}"
                );
                break;
            }
        }
    }
}
fn prepare_payload(f: &Fixture) {
    fs::create_dir(f.root.join("source/current/sub")).unwrap();
    mode(&f.root.join("source/current/sub"), 0o700);
    fs::write(f.root.join("source/current/a"), b"alpha").unwrap();
    fs::write(f.root.join("source/current/sub/b"), b"bravo!!").unwrap();
}
fn wait_commit(f: &Fixture) {
    let until = Instant::now() + Duration::from_secs(15);
    while f.operator("/api/v2/jobs/1").1["state"] != "Committed" {
        assert!(Instant::now() < until);
        std::thread::sleep(Duration::from_millis(20));
    }
}

#[test]
fn live_tls_rotation_revokes_old_connections_changes_trust_and_preserves_uuid_replay() {
    let mut f = Fixture::new(true);
    f.initialize();
    f.start();
    prepare_payload(&f);
    let input = f.input();
    let first = f.https("POST", "/api/v2/jobs", "", &input);
    assert_eq!(first.0, 202);
    wait_commit(&f);
    let manifest = f.root.join(format!("destination/{UUID}/COMMITTED.json"));
    let bytes = fs::read(&manifest).unwrap();
    let initial = tls_control(&f, false, true);
    assert_eq!(initial["status"]["generation"], 1);
    let mut raw = std::net::TcpStream::connect(f.address).unwrap();
    let mut established = warm_tls(&f);
    f.config["native_ingress"]["server_certificates"] =
        json!([copy_credential(&f, "replacement-server.der")]);
    f.config["native_ingress"]["server_key"] =
        json!(copy_credential(&f, "replacement-server.key.der"));
    f.config["native_ingress"]["clients"] = json!([{"sha256":mover_fs::sha256_hex(&fixture("unapproved-client.der")),"generator_id":"recorder"}]);
    f.save();
    let rotated = tls_control(&f, true, true);
    assert_eq!(rotated["status"]["generation"], 2);
    assert_eq!(rotated["instance_id"], initial["instance_id"]);
    assert_eq!(rotated["status"]["draining"], false);
    assert_ne!(
        rotated["status"]["policy_sha256"],
        initial["status"]["policy_sha256"]
    );
    assert_eq!(
        rotated["status"]["server_sha256"],
        mover_fs::sha256_hex(&fixture("replacement-server.der"))
    );
    expect_closed(&mut raw);
    expect_closed(&mut established.sock);
    assert_eq!(f.https("POST", "/api/v2/jobs", "", &input).0, 403);
    let req = request(
        "POST",
        "/api/v2/jobs",
        &format!("localhost:{}", f.address.port()),
        "",
        &serde_json::to_vec(&input).unwrap(),
    );
    assert_eq!(
        f.tls(Some("unapproved-client"), &rustls::version::TLS13, &req)
            .unwrap(),
        first
    );
    f.config["native_ingress"]["client_ca_certificates"] =
        json!([copy_credential(&f, "other-ca.der")]);
    f.config["native_ingress"]["clients"] = json!([{"sha256":mover_fs::sha256_hex(&fixture("untrusted-client.der")),"generator_id":"recorder"}]);
    f.save();
    let trust = tls_control(&f, true, true);
    assert_eq!(trust["status"]["generation"], 3);
    assert_ne!(
        trust["status"]["policy_sha256"],
        rotated["status"]["policy_sha256"]
    );
    assert!(
        f.tls(Some("unapproved-client"), &rustls::version::TLS12, &req)
            .is_err()
    );
    assert_eq!(
        f.tls(Some("untrusted-client"), &rustls::version::TLS12, &req)
            .unwrap(),
        first
    );
    assert_eq!(fs::read(&manifest).unwrap(), bytes);
    for (name, data, index) in [
        ("a", b"alpha".as_slice(), 0),
        ("sub/b", b"bravo!!".as_slice(), 1),
    ] {
        assert_eq!(
            fs::read(f.root.join(format!("destination/{UUID}/{name}"))).unwrap(),
            data
        );
        assert_eq!(
            fs::read(f.root.join(format!("source/.file-mover/1-{index}/data"))).unwrap(),
            data
        );
    }
    assert_eq!(
        f.operator("/api/v2/retention").1["details"]["retained_jobs"],
        1
    );
    f.stop();
}

#[test]
fn invalid_live_reloads_preserve_the_working_policy_and_existing_tls_connection() {
    let mut f = Fixture::new(true);
    f.initialize();
    f.start();
    let initial = tls_control(&f, false, true);
    let original = f.config.clone();
    let mut warm = warm_tls(&f);
    for case in 0..5 {
        f.config = original.clone();
        match case {
            0 => {
                f.config["native_ingress"]["server_key"] =
                    json!(f.root.join("credentials/missing.der"))
            }
            1 => f.config["check_expected_sizes"] = json!(true),
            2 => {
                f.config["native_ingress"]["authority"] =
                    json!(format!("other.invalid:{}", f.address.port()))
            }
            3 => {
                f.config["native_ingress"]["server_key"] =
                    json!(copy_credential(&f, "client.key.der"))
            }
            _ => {
                f.config["native_ingress"]["server_key"] =
                    json!(f.root.join("other-credentials/server.key.der"))
            }
        }
        f.save();
        let reply = tls_control(&f, true, false);
        assert_eq!(reply["status"]["generation"], 1);
        assert_eq!(
            reply["status"]["policy_sha256"],
            initial["status"]["policy_sha256"]
        );
    }
    warm.write_all(&request(
        "GET",
        "/healthz",
        &format!("localhost:{}", f.address.port()),
        "",
        &[],
    ))
    .unwrap();
    warm.flush().unwrap();
    let mut out = Vec::new();
    warm.read_to_end(&mut out).unwrap();
    assert_eq!(response(&out).0, 403);
    f.config = original;
    f.save();
    assert_eq!(tls_control(&f, false, true)["status"]["generation"], 1);
    f.stop();
}

#[test]
fn reload_excludes_queued_work_without_waiting_for_an_admitted_claim() {
    if !cfg!(feature = "nfs-qualification") {
        return;
    }
    let mut f = Fixture::new(true);
    f.initialize();
    prepare_payload(&f);
    fs::write(f.root.join("source/current/later"), b"later").unwrap();
    let checkpoint = f.root.join("claim-pause");
    fs::create_dir(&checkpoint).unwrap();
    mode(&checkpoint, 0o700);
    f.start_paused(Some(("claim_apply", &checkpoint)));
    let req = |body: &Value| {
        request(
            "POST",
            "/api/v2/jobs",
            &format!("localhost:{}", f.address.port()),
            "",
            &serde_json::to_vec(body).unwrap(),
        )
    };
    let address = f.address;
    let first = req(&f.input());
    let first = std::thread::spawn(move || {
        Fixture::tls_at(address, Some("client"), &rustls::version::TLS13, &first)
    });
    let until = Instant::now() + Duration::from_secs(5);
    while !checkpoint.join("ready").exists() {
        assert!(Instant::now() < until);
        std::thread::sleep(Duration::from_millis(5));
    }
    let mut next = f.input();
    next["recording_id"] = json!("f64a49e8-027c-4ec7-88e1-72b960511b55");
    next["files"] = json!(["later"]);
    next["expected_sizes_bytes"] = json!({"later":"5"});
    let second = req(&next);
    let second = std::thread::spawn(move || {
        Fixture::tls_at(address, Some("client"), &rustls::version::TLS13, &second)
    });
    let until = Instant::now() + Duration::from_secs(3);
    loop {
        let s = tls_control(&f, false, true);
        if s["status"]["queued_connections"] == 1 && s["status"]["admitted_connections"] == 1 {
            break;
        }
        assert!(Instant::now() < until, "{s}");
        std::thread::sleep(Duration::from_millis(5));
    }
    f.config["native_ingress"]["clients"] = json!([{"sha256":mover_fs::sha256_hex(&fixture("unapproved-client.der")),"generator_id":"recorder"}]);
    f.save();
    assert_eq!(tls_control(&f, true, true)["status"]["generation"], 2);
    assert!(!first.is_finished());
    assert!(!checkpoint.join("go").exists());
    assert!(second.join().unwrap().is_err());
    fs::write(checkpoint.join("go"), b"continue").unwrap();
    assert_eq!(first.join().unwrap().unwrap().0, 202);
    wait_commit(&f);
    assert_eq!(
        f.operator("/api/v2/retention").1["details"]["retained_jobs"],
        1
    );
    assert_eq!(
        fs::read(f.root.join("source/current/later")).unwrap(),
        b"later"
    );
    f.stop();
}

#[test]
fn loader_pause_keeps_status_and_stop_available_and_stop_wins_before_activation() {
    if !cfg!(feature = "nfs-qualification") {
        return;
    }
    let mut f = Fixture::new(true);
    f.initialize();
    let checkpoint = f.root.join("reload-pause");
    fs::create_dir(&checkpoint).unwrap();
    mode(&checkpoint, 0o700);
    f.start_paused(Some(("tls_reload_validated", &checkpoint)));
    let pending = f
        .command()
        .arg("--reload-tls")
        .arg(f.root.join("config.json"))
        .stdout(std::process::Stdio::piped())
        .stderr(std::process::Stdio::piped())
        .spawn()
        .unwrap();
    let until = Instant::now() + Duration::from_secs(5);
    while !checkpoint.join("ready").exists() {
        assert!(Instant::now() < until);
        std::thread::sleep(Duration::from_millis(5));
    }
    let started = Instant::now();
    let status = tls_control(&f, false, true);
    assert_eq!(status["busy"], true);
    assert_eq!(status["status"]["generation"], 1);
    assert_eq!(status["status"]["last_result"], "loading");
    assert!(started.elapsed() < Duration::from_secs(2));
    let busy = tls_control(&f, true, false);
    assert_eq!(busy["error"], "reload_busy");
    assert_eq!(f.operator("/healthz").0, 200);
    let mut stop = f
        .command()
        .arg("--stop")
        .arg(f.root.join("config.json"))
        .stdout(std::process::Stdio::null())
        .stderr(std::process::Stdio::null())
        .spawn()
        .unwrap();
    let until = Instant::now() + Duration::from_secs(2);
    loop {
        let status = f
            .command()
            .arg("--status")
            .arg(f.root.join("config.json"))
            .output()
            .unwrap();
        let v: Value = serde_json::from_slice(&status.stdout).unwrap();
        if v["phase"] == "Draining" {
            break;
        }
        assert!(Instant::now() < until);
    }
    fs::write(checkpoint.join("go"), b"continue").unwrap();
    let result = pending.wait_with_output().unwrap();
    assert!(!result.status.success());
    let result: Value = serde_json::from_slice(&result.stdout).unwrap();
    assert_eq!(result["status"]["generation"], 1);
    assert_eq!(result["status"]["last_result"], "stopping");
    assert!(stop.wait().unwrap().success());
    let mut child = f.child.take().unwrap();
    assert!(child.wait().unwrap().success());
    let _guard =
        mover_fs::InstanceGuard::for_database(f.root.join("state/jobs.sqlite").to_str().unwrap())
            .unwrap();
}
