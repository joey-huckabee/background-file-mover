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
        "{method} {path} HTTP/1.1\r\nHost: {host}\r\nContent-Length: {}\r\n{headers}\r\n",
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
        let log = fs::File::create(self.root.join("service.log")).unwrap();
        self.child = Some(
            self.command()
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
            std::net::TcpStream::connect_timeout(&self.address, Duration::from_secs(5)).unwrap();
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
            Ok(out) => Ok(response(&out)),
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
    let first = f.https("POST", "/api/v2/jobs", "", &body);
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
