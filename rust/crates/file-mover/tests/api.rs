use serde_json::{Value, json};
use std::{
    io::{Read, Write},
    net::{SocketAddr, TcpListener, TcpStream},
    os::unix::fs::PermissionsExt,
    path::PathBuf,
    process::{Child, Command, Stdio},
    sync::atomic::{AtomicU64, Ordering},
    time::{Duration, Instant},
};
static NEXT: AtomicU64 = AtomicU64::new(0);
struct Fixture {
    root: PathBuf,
    address: SocketAddr,
    child: Option<Child>,
}
impl Fixture {
    fn new(window: u32) -> Self {
        let root = loop {
            let p = std::env::temp_dir().join(format!(
                "file-mover-api-{}-{}",
                std::process::id(),
                NEXT.fetch_add(1, Ordering::Relaxed)
            ));
            match std::fs::create_dir(&p) {
                Ok(()) => break p,
                Err(e) if e.kind() == std::io::ErrorKind::AlreadyExists => continue,
                Err(e) => panic!("{e}"),
            }
        };
        for path in [
            root.clone(),
            root.join("source"),
            root.join("source/.file-mover"),
            root.join("source/current"),
            root.join("source/current/sub"),
            root.join("state"),
        ] {
            if path != root {
                std::fs::create_dir(&path).unwrap();
            }
            std::fs::set_permissions(&path, std::fs::Permissions::from_mode(0o700)).unwrap();
        }
        let address = TcpListener::bind("127.0.0.1:0")
            .unwrap()
            .local_addr()
            .unwrap();
        std::fs::write(root.join("config.json"),serde_json::to_vec(&json!({"bind":address.to_string(),"generator_id":"recorder","source_root":root.join("source"),"destination_root":root.join("destination"),"state_database":root.join("state/jobs.sqlite"),"missing_file_retry_window_seconds":window})).unwrap()).unwrap();
        let mut f = Self {
            root,
            address,
            child: None,
        };
        f.start();
        f
    }
    fn start(&mut self) {
        self.child = Some(
            Command::new(
                std::env::var("FILE_MOVER_TEST_EXECUTABLE")
                    .expect("SLES gate provides audited service binary"),
            )
            .arg(self.root.join("config.json"))
            .stdout(Stdio::null())
            .stderr(Stdio::piped())
            .spawn()
            .unwrap(),
        );
        let deadline = Instant::now() + Duration::from_secs(10);
        loop {
            if let Ok(mut stream) =
                TcpStream::connect_timeout(&self.address, Duration::from_millis(100))
            {
                stream
                    .set_read_timeout(Some(Duration::from_secs(1)))
                    .unwrap();
                stream
                    .write_all(b"GET /healthz HTTP/1.1\r\nHost: localhost\r\n\r\n")
                    .unwrap();
                let mut response = String::new();
                if stream.read_to_string(&mut response).is_ok()
                    && response.starts_with("HTTP/1.1 200 ")
                {
                    return;
                }
            }
            if let Some(status) = self.child.as_mut().unwrap().try_wait().unwrap() {
                let mut stderr = String::new();
                self.child
                    .as_mut()
                    .unwrap()
                    .stderr
                    .take()
                    .unwrap()
                    .read_to_string(&mut stderr)
                    .unwrap();
                panic!("startup {status}: {stderr}");
            }
            assert!(Instant::now() < deadline, "startup timeout");
            std::thread::sleep(Duration::from_millis(20));
        }
    }
    fn stop(&mut self) {
        let mut child = self.child.take().unwrap();
        assert!(
            Command::new("/bin/kill")
                .args([
                    if NEXT.load(Ordering::Relaxed).is_multiple_of(2) {
                        "-INT"
                    } else {
                        "-TERM"
                    },
                    &child.id().to_string()
                ])
                .status()
                .unwrap()
                .success()
        );
        let deadline = Instant::now() + Duration::from_secs(5);
        loop {
            if let Some(status) = child.try_wait().unwrap() {
                assert!(status.success());
                break;
            }
            if Instant::now() >= deadline {
                child.kill().unwrap();
                child.wait().unwrap();
                panic!("graceful shutdown timeout");
            }
            std::thread::sleep(Duration::from_millis(20));
        }
    }
    fn input(&self, id: &str, files: Value) -> Value {
        json!({"generator_id":"recorder","submission_id":id,"source_path":self.root.join("source/current"),"files":files})
    }
    fn write(&self, name: &str, bytes: &[u8]) {
        std::fs::write(self.root.join("source/current").join(name), bytes).unwrap();
    }
    fn raw(&self, bytes: &[u8]) -> (u16, Value) {
        exchange(self.address, bytes)
    }
    fn post(&self, body: &Value) -> (u16, Value) {
        self.raw(&post_bytes(body))
    }
}
impl Drop for Fixture {
    fn drop(&mut self) {
        if let Some(mut c) = self.child.take() {
            let _ = c.kill();
            let _ = c.wait();
        }
        std::fs::remove_dir_all(&self.root).unwrap();
    }
}
fn post_bytes(body: &Value) -> Vec<u8> {
    post_text(&serde_json::to_string(body).unwrap())
}
fn post_text(body: &str) -> Vec<u8> {
    format!("POST /api/v2/jobs HTTP/1.1\r\nHost: localhost\r\nContent-Type: application/json\r\nContent-Length: {}\r\n\r\n{}",body.len(),body).into_bytes()
}
fn exchange(address: SocketAddr, bytes: &[u8]) -> (u16, Value) {
    let mut s = TcpStream::connect(address).unwrap();
    s.set_read_timeout(Some(Duration::from_secs(15))).unwrap();
    s.write_all(bytes).unwrap();
    let mut response = String::new();
    s.read_to_string(&mut response).unwrap();
    let (head, body) = response.split_once("\r\n\r\n").unwrap();
    assert!(head.contains("Connection: close"));
    let declared: usize = head
        .lines()
        .find_map(|line| line.strip_prefix("Content-Length: "))
        .unwrap()
        .parse()
        .unwrap();
    assert_eq!(declared, body.len());
    (
        head.split_whitespace().nth(1).unwrap().parse().unwrap(),
        serde_json::from_str(body).unwrap(),
    )
}
#[test]
fn actual_executable_handoff_restart_replay_and_reused_paths() {
    let mut f = Fixture::new(300);
    f.write("sub/data", b"payload");
    f.write("empty", b"");
    let body = f.input(
        "first",
        json!([{"name":"sub/data"},{"name":"empty","size_bytes":0}]),
    );
    let (status, response) = f.post(&body);
    assert_eq!(status, 202);
    assert_eq!(response["state"], "Claimed");
    assert_eq!(response["source_paths_released"], true);
    assert!(f.root.join("source/current/sub").is_dir());
    assert!(!f.root.join("source/current/sub/data").exists());
    f.write("sub/data", b"new");
    f.stop();
    f.start();
    let (status, replay) = f.post(&body);
    assert_eq!(status, 202);
    assert_eq!(replay["job_id"], response["job_id"]);
    assert_eq!(
        std::fs::read(f.root.join("source/current/sub/data")).unwrap(),
        b"new"
    );
    let mut conflict = body.clone();
    conflict["files"] = json!([{"name":"sub/data"}]);
    assert_eq!(f.post(&conflict).0, 409);
    assert_eq!(
        f.post(&f.input("next", json!([{"name":"sub/data"}]))).0,
        202
    );
    f.stop();
    let store = mover_store::Store::open(f.root.join("state/jobs.sqlite")).unwrap();
    assert_eq!(store.job_count().unwrap(), 2);
}
#[test]
fn malformed_json_scope_and_http_framing_never_claim() {
    let mut f = Fixture::new(300);
    f.write("data", b"unchanged");
    let body = f.input("valid", json!([{"name":"data"}]));
    for change in ["destination_root", "unexpected"] {
        let mut b = body.clone();
        b[change] = json!("forbidden");
        assert_eq!(f.post(&b).0, 400);
    }
    let mut b = body.clone();
    b["generator_id"] = json!("other");
    assert_eq!(f.post(&b).0, 403);
    b = body.clone();
    b["source_path"] = json!(format!("{}-outside", f.root.join("source").display()));
    assert_eq!(f.post(&b).0, 403);
    for file in [
        json!({"name":"../data"}),
        json!({"name":"data","size_bytes":null}),
        json!({"name":"data","size_bytes":1.0}),
        json!({"name":"data","size_bytes":-1}),
    ] {
        let mut b = body.clone();
        b["files"] = json!([file]);
        assert_eq!(f.post(&b).0, 400);
    }
    assert_eq!(
        f.raw(&post_text(
            "{\"generator_id\":\"recorder\",\"generator_id\":\"recorder\"}"
        ))
        .0,
        400
    );
    for (request, status) in [
        (
            "POST /api/v2/jobs HTTP/1.1\r\nHost: h\r\nContent-Length: 2\r\ncontent-length: 2\r\n\r\n{}",
            400,
        ),
        (
            "POST /api/v2/jobs HTTP/1.1\r\nHost: h\r\nTransfer-Encoding: chunked\r\n\r\n",
            400,
        ),
        (
            "POST /api/v2/jobs HTTP/1.1\r\nHost: h\r\nContent-Length: 65537\r\n\r\n",
            413,
        ),
        (
            "POST /api/v2/jobs HTTP/1.1\r\nHost: h\r\nContent-Type: text/plain\r\nContent-Length: 2\r\n\r\n{}",
            415,
        ),
        ("GET /api/v2/jobs HTTP/1.1\r\nHost: h\r\n\r\n", 405),
        ("GET /other HTTP/1.1\r\nHost: h\r\n\r\n", 404),
    ] {
        assert_eq!(f.raw(request.as_bytes()).0, status);
    }
    assert!(f.root.join("source/current/data").exists());
    f.stop();
    let store = mover_store::Store::open(f.root.join("state/jobs.sqlite")).unwrap();
    assert_eq!(store.job_count().unwrap(), 0);
}
#[test]
fn partial_claim_missing_retry_and_persisted_expiry() {
    let mut f = Fixture::new(300);
    f.write("first", b"retained");
    let input = f.input("partial", json!([{"name":"first"},{"name":"missing"}]));
    let (status, pending) = f.post(&input);
    assert_eq!(status, 503);
    assert_eq!(pending["retryable"], true);
    assert_eq!(pending["source_paths_released"], false);
    assert!(f.root.join("source/.file-mover/1-0/data").exists());
    f.stop();
    f.start();
    f.write("missing", b"arrived");
    let (status, ready) = f.post(&input);
    assert_eq!(status, 202);
    assert_eq!(ready["job_id"], pending["job_id"]);
    f.stop();
    let mut expired = Fixture::new(0);
    let body = expired.input("late", json!([{"name":"missing"}]));
    let (status, blocked) = expired.post(&body);
    assert_eq!(status, 409);
    assert_eq!(blocked["retryable"], false);
    expired.stop();
    expired.start();
    expired.write("missing", b"late file");
    assert_eq!(expired.post(&body).0, 409);
    assert!(expired.root.join("source/current/missing").exists());
    expired.stop();
}
#[test]
fn slow_client_does_not_block_health_and_concurrent_replays_are_bounded() {
    let mut f = Fixture::new(300);
    let _slow = TcpStream::connect(f.address).unwrap();
    assert_eq!(f.raw(b"GET /healthz HTTP/1.1\r\nHost: h\r\n\r\n").0, 200);
    f.write("data", b"once");
    let bytes = post_bytes(&f.input("concurrent", json!([{"name":"data"}])));
    let threads: Vec<_> = (0..4)
        .map(|_| {
            let bytes = bytes.clone();
            let address = f.address;
            std::thread::spawn(move || exchange(address, &bytes))
        })
        .collect();
    let replies: Vec<_> = threads.into_iter().map(|t| t.join().unwrap()).collect();
    assert!(replies.iter().any(|r| r.0 == 202));
    assert!(replies.iter().all(|r| matches!(r.0, 202 | 503)));
    assert_eq!(f.raw(&bytes).0, 202);
    f.stop();
    let store = mover_store::Store::open(f.root.join("state/jobs.sqlite")).unwrap();
    assert_eq!(store.job_count().unwrap(), 1);
}
#[test]
fn unsafe_startup_configuration_is_rejected() {
    let c = file_mover::Config {
        bind: "0.0.0.0:8080".parse().unwrap(),
        generator_id: "g".into(),
        source_root: "/source".into(),
        destination_root: "/dest".into(),
        state_database: "/state/db".into(),
        missing_file_retry_window_seconds: 300,
        max_retained_jobs: 64,
        max_retained_bytes: 1024 * 1024 * 1024 * 1024,
    };
    assert!(c.validate().is_err());
    let mut c = c;
    c.bind = "127.0.0.1:8080".parse().unwrap();
    assert!(c.validate().is_ok());
    c.state_database = "/source/db".into();
    assert!(c.validate().is_err());
}

#[test]
fn lost_response_retry_finds_one_durable_job() {
    let mut f = Fixture::new(300);
    f.write("data", b"retained");
    let body = f.input("lost-response", json!([{"name":"data"}]));
    let mut stream = TcpStream::connect(f.address).unwrap();
    stream.write_all(&post_bytes(&body)).unwrap();
    drop(stream);
    let deadline = Instant::now() + Duration::from_secs(5);
    while !f.root.join("source/.file-mover/1-0/data").exists() {
        assert!(
            Instant::now() < deadline,
            "disconnected request must finish claiming"
        );
        std::thread::sleep(Duration::from_millis(20));
    }
    assert_eq!(f.post(&body).0, 202);
    f.stop();
    let store = mover_store::Store::open(f.root.join("state/jobs.sqlite")).unwrap();
    assert_eq!(store.job_count().unwrap(), 1);
}

#[test]
fn actual_transfer_command_publishes_but_retains_claimed_source() {
    let mut f = Fixture::new(300);
    f.write("sub/data", b"abc");
    let (status, response) = f.post(&f.input("copy", json!([{"name":"sub/data"}])));
    assert_eq!(status, 202);
    f.stop();
    f.write("sub/data", b"new recording");
    for p in [
        f.root.join("destination"),
        f.root.join("destination/.file-mover"),
    ] {
        std::fs::create_dir(&p).unwrap();
        std::fs::set_permissions(p, std::fs::Permissions::from_mode(0o700)).unwrap();
    }
    let output = Command::new(std::env::var("FILE_MOVER_TEST_EXECUTABLE").unwrap())
        .arg("--transfer-one")
        .arg(f.root.join("config.json"))
        .arg(response["job_id"].as_str().unwrap())
        .output()
        .unwrap();
    assert!(output.status.success(), "{output:?}");
    let result: Value = serde_json::from_slice(&output.stdout).unwrap();
    assert_eq!(result["state"], "Published");
    assert_eq!(result["source_retained"], true);
    assert_eq!(result["committed"], false);
    assert_eq!(
        result["sha256"],
        "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    );
    assert_eq!(
        std::fs::read(f.root.join("destination/1/sub/data")).unwrap(),
        b"abc"
    );
    assert_eq!(
        std::fs::read(f.root.join("source/.file-mover/1-0/data")).unwrap(),
        b"abc"
    );
    assert_eq!(
        std::fs::read(f.root.join("source/current/sub/data")).unwrap(),
        b"new recording"
    );
}

fn provision_destination(f: &Fixture) {
    for p in [
        f.root.join("destination"),
        f.root.join("destination/.file-mover"),
    ] {
        std::fs::create_dir(&p).unwrap();
        std::fs::set_permissions(p, std::fs::Permissions::from_mode(0o700)).unwrap();
    }
}
fn wait_manifest(f: &Fixture, id: &str) -> Value {
    let path = f.root.join("destination").join(id).join("COMMITTED.json");
    let deadline = Instant::now() + Duration::from_secs(15);
    loop {
        if let Ok(bytes) = std::fs::read(&path) {
            return serde_json::from_slice(&bytes).unwrap();
        }
        assert!(Instant::now() < deadline, "background commitment timeout");
        std::thread::sleep(Duration::from_millis(50));
    }
}
#[test]
fn background_multi_file_delivery_commits_after_202_without_more_requests() {
    let mut f = Fixture::new(300);
    provision_destination(&f);
    f.write("sub/alpha", b"abc");
    f.write("sub/beta", b"other");
    f.write("empty", b"");
    let input = f.input(
        "automatic",
        json!([{"name":"sub/alpha"},{"name":"sub/beta"},{"name":"empty","size_bytes":0}]),
    );
    let (status, response) = f.post(&input);
    assert_eq!(status, 202);
    f.write("sub/alpha", b"producer reuse");
    let manifest = wait_manifest(&f, response["job_id"].as_str().unwrap());
    assert_eq!(manifest["files"].as_array().unwrap().len(), 3);
    assert_eq!(
        std::fs::read(f.root.join("destination/1/sub/alpha")).unwrap(),
        b"abc"
    );
    assert_eq!(
        std::fs::read(f.root.join("source/current/sub/alpha")).unwrap(),
        b"producer reuse"
    );
    assert_eq!(f.raw(b"GET /healthz HTTP/1.1\r\nHost: h\r\n\r\n").0, 200);
    f.stop();
    let s = mover_store::Store::open(f.root.join("state/jobs.sqlite")).unwrap();
    assert!(s.get(1).unwrap().unwrap().recording.is_committed());
    for i in 0..3 {
        assert!(
            f.root
                .join(format!("source/.file-mover/1-{i}/data"))
                .exists()
        );
    }
}
#[test]
fn restart_discovers_claimed_delivery_and_keeps_original_destination() {
    let mut f = Fixture::new(300);
    f.write("data", b"persisted");
    assert_eq!(f.post(&f.input("restart", json!([{"name":"data"}]))).0, 202);
    f.stop();
    provision_destination(&f);
    let path = f.root.join("config.json");
    let mut config: Value = serde_json::from_slice(&std::fs::read(&path).unwrap()).unwrap();
    config["destination_root"] = json!(f.root.join("replacement"));
    std::fs::write(&path, serde_json::to_vec(&config).unwrap()).unwrap();
    f.start();
    let manifest = wait_manifest(&f, "1");
    assert_eq!(manifest["files"][0]["size_bytes"], 9);
    assert!(!f.root.join("replacement/1").exists());
    f.stop();
    let output = Command::new(std::env::var("FILE_MOVER_TEST_EXECUTABLE").unwrap())
        .arg("--transfer-one")
        .arg(f.root.join("config.json"))
        .arg("1")
        .output()
        .unwrap();
    assert!(output.status.success(), "{output:?}");
    let state: Value = serde_json::from_slice(&output.stdout).unwrap();
    assert_eq!(state["committed"], true);
}
#[test]
fn retention_limits_refuse_new_work_without_false_release_or_orphan() {
    let mut f = Fixture::new(300);
    f.stop();
    let path = f.root.join("config.json");
    let mut config: Value = serde_json::from_slice(&std::fs::read(&path).unwrap()).unwrap();
    config["max_retained_jobs"] = json!(1);
    config["max_retained_bytes"] = json!(3);
    std::fs::write(&path, serde_json::to_vec(&config).unwrap()).unwrap();
    f.start();
    f.write("data", b"abcd");
    let body = f.input("limited", json!([{"name":"data"}]));
    let (status, response) = f.post(&body);
    assert_eq!(status, 503);
    assert_eq!(response["error"], "retention_capacity");
    assert_eq!(response["source_paths_released"], false);
    assert!(f.root.join("source/current/data").exists());
    assert!(!f.root.join("source/.file-mover/1-0").exists());
    f.stop();
    config["max_retained_bytes"] = json!(10);
    std::fs::write(path, serde_json::to_vec(&config).unwrap()).unwrap();
    f.start();
    assert_eq!(f.post(&body).0, 202);
    f.write("other", b"x");
    assert_eq!(f.post(&f.input("extra", json!([{"name":"other"}]))).0, 503);
    assert_eq!(f.post(&body).0, 202);
    f.stop();
}
