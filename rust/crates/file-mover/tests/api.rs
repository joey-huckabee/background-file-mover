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
fn payload_child(
    source: &mover_fs::LocalClaimLock,
    destination: &mover_fs::LocalClaimLock,
) -> (Child, std::os::unix::net::UnixStream) {
    effect_child(source, destination, "--internal-payload-worker")
}
fn effect_child(
    source: &mover_fs::LocalClaimLock,
    destination: &mover_fs::LocalClaimLock,
    mode: &str,
) -> (Child, std::os::unix::net::UnixStream) {
    let (channel, worker) = std::os::unix::net::UnixStream::pair().unwrap();
    channel
        .set_read_timeout(Some(Duration::from_secs(5)))
        .unwrap();
    let child = Command::new(std::env::var("FILE_MOVER_TEST_EXECUTABLE").unwrap())
        .arg(mode)
        .stdin(Stdio::from(source.inherit().unwrap()))
        .stdout(Stdio::from(destination.inherit().unwrap()))
        .stderr(Stdio::from(std::os::fd::OwnedFd::from(worker)))
        .spawn()
        .unwrap();
    (child, channel)
}
fn child_reply(
    source: &mover_fs::LocalClaimLock,
    destination: &mover_fs::LocalClaimLock,
    mode: &str,
    body: &Value,
) -> Value {
    let (mut child, mut channel) = effect_child(source, destination, mode);
    channel
        .write_all(&serde_json::to_vec(body).unwrap())
        .unwrap();
    channel.shutdown(std::net::Shutdown::Write).unwrap();
    assert!(child.wait().unwrap().success());
    let mut bytes = Vec::new();
    channel.read_to_end(&mut bytes).unwrap();
    serde_json::from_slice(&bytes).unwrap()
}
fn claim_from_wire(c: &Value) -> mover_core::ClaimIntent {
    let object =
        |i: usize| mover_core::ObjectIdentity::decode(c["objects"][i].as_str().unwrap()).unwrap();
    mover_core::ClaimIntent {
        job_id: c["job_id"].as_i64().unwrap(),
        file_index: c["file_index"].as_u64().unwrap() as usize,
        root_path: c["root_path"].as_str().unwrap().into(),
        source_name: c["source_name"].as_str().unwrap().into(),
        private_name: c["private_name"].as_str().unwrap().into(),
        root: object(0),
        parent: object(1),
        area: object(2),
        source: object(3),
    }
}
#[test]
fn claim_children_preserve_intent_receipt_order_and_reconcile_lost_reply() {
    let mut f = Fixture::new(300);
    let input = f.input("child-claim", json!([{"name":"data"}]));
    assert_eq!(f.post(&input).0, 503);
    f.stop();
    f.write("data", b"claim data");
    let store = mover_store::Store::open(f.root.join("state/jobs.sqlite")).unwrap();
    let guard = mover_fs::LocalClaimLock::acquire(f.root.join("source").to_str().unwrap()).unwrap();
    let observed = child_reply(
        &guard,
        &guard,
        "--internal-claim-worker",
        &json!({"operation":"observe","version":1,"job_id":1,"file_index":0,"root_path":f.root.join("source"),"source_name":"current/data","expected_size":null}),
    );
    assert!(observed["error"].is_null());
    assert_eq!(
        observed["claim"]["objects"][3]
            .as_str()
            .map(mover_core::ObjectIdentity::decode)
            .unwrap()
            .unwrap()
            .size,
        10
    );
    assert!(store.claim_intent(1, 0).unwrap().is_none());
    assert!(!f.root.join("source/.file-mover/1-0").exists());
    store.claim_capacity(10).unwrap();
    let allocated = child_reply(
        &guard,
        &guard,
        "--internal-claim-worker",
        &json!({"operation":"allocate","version":1,"claim":observed["claim"]}),
    );
    let intent = claim_from_wire(&allocated["claim"]);
    assert!(store.claim_intent(1, 0).unwrap().is_none());
    assert!(f.root.join("source/current/data").exists());
    store.begin_claim(&intent).unwrap();
    let body = json!({"operation":"apply","version":1,"claim":allocated["claim"]});
    let first = child_reply(&guard, &guard, "--internal-claim-worker", &body);
    assert_eq!(claim_from_wire(&first["claim"]), intent);
    assert_eq!(
        store.claim_intent(1, 0).unwrap(),
        Some((intent.clone(), false))
    );
    assert!(!f.root.join("source/current/data").exists());
    assert_eq!(
        std::fs::read(f.root.join("source/.file-mover/1-0/data")).unwrap(),
        b"claim data"
    );
    // Discard the first result without an applied database receipt, then reconcile.
    let replay = child_reply(&guard, &guard, "--internal-claim-worker", &body);
    assert_eq!(claim_from_wire(&replay["claim"]), intent);
    store.finish_claim(&intent).unwrap();
    drop(guard);
    drop(store);
    f.write("data", b"producer reuse");
    f.start();
    assert_eq!(f.post(&input).0, 202);
    assert_eq!(
        std::fs::read(f.root.join("source/current/data")).unwrap(),
        b"producer reuse"
    );
}
#[test]
fn claim_child_reports_missing_and_refuses_changed_observation_before_allocation() {
    let mut f = Fixture::new(300);
    f.stop();
    let guard = mover_fs::LocalClaimLock::acquire(f.root.join("source").to_str().unwrap()).unwrap();
    let body = json!({"operation":"observe","version":1,"job_id":1,"file_index":0,"root_path":f.root.join("source"),"source_name":"current/data","expected_size":null});
    let missing = child_reply(&guard, &guard, "--internal-claim-worker", &body);
    assert_eq!(missing["error"], "missing_source");
    f.write("data", b"old");
    let observed = child_reply(&guard, &guard, "--internal-claim-worker", &body);
    f.write("data", b"changed size");
    let refused = child_reply(
        &guard,
        &guard,
        "--internal-claim-worker",
        &json!({"operation":"allocate","version":1,"claim":observed["claim"]}),
    );
    assert_eq!(refused["error"], "expected_size_mismatch");
    assert!(!f.root.join("source/.file-mover/1-0").exists());
    assert_eq!(
        std::fs::read(f.root.join("source/current/data")).unwrap(),
        b"changed size"
    );
}
#[test]
fn publication_child_reconciles_file_and_manifest_effects_without_database_receipts() {
    let mut f = Fixture::new(300);
    f.write("data", b"publication");
    assert_eq!(
        f.post(&f.input("publish-child", json!([{"name":"data"}])))
            .0,
        202
    );
    f.stop();
    provision_destination(&f);
    let store = mover_store::Store::open(f.root.join("state/jobs.sqlite")).unwrap();
    let source =
        mover_fs::LocalClaimLock::acquire(f.root.join("source").to_str().unwrap()).unwrap();
    let destination =
        mover_fs::LocalClaimLock::acquire(f.root.join("destination").to_str().unwrap()).unwrap();
    let t = mover_fs::prepare_transfer(&store, 1).unwrap();
    let t = mover_fs::copy_stage(&store, &t).unwrap();
    let t = mover_fs::verify_stage(&store, &t).unwrap();
    let mut t = mover_fs::authorize_publication(&store, &t).unwrap();
    let claim = store.claim_intent(1, 0).unwrap().unwrap().0;
    for _ in 0..2 {
        let r = child_reply(
            &source,
            &destination,
            "--internal-payload-worker",
            &payload_assignment(&t, &claim),
        );
        assert_eq!(r["phase"], 4);
        assert_eq!(r["stage"], t.stage.encode());
        assert_eq!(store.transfer(1, 0).unwrap(), Some(t.clone()));
        assert_eq!(
            std::fs::read(f.root.join("destination/1/data")).unwrap(),
            b"publication"
        );
        assert!(!f.root.join("destination/1/.staging/1.part").exists());
    }
    t.phase = mover_core::TransferPhase::Published;
    store.save_transfer(&t).unwrap();
    let interrupted = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
        mover_fs::commit_manifest_with_checkpoints(&store, 1, |point| {
            if point == "authorized" {
                panic!("before manifest publication");
            }
        })
        .unwrap();
    }));
    assert!(interrupted.is_err());
    let m = store.manifest(1).unwrap().unwrap();
    assert_eq!(m.phase, 3);
    let mut body = payload_assignment(&t, &claim);
    body["manifest"] = json!({"job_id":m.job_id,"bytes":m.bytes,"sha256":m.sha256,"phase":m.phase,"object":m.object.as_ref().unwrap().encode()});
    for _ in 0..2 {
        let r = child_reply(&source, &destination, "--internal-payload-worker", &body);
        assert_eq!(r["phase"], 4);
        assert_eq!(r["sha256"], m.sha256);
        assert_eq!(store.manifest(1).unwrap(), Some(m.clone()));
        assert!(!store.get(1).unwrap().unwrap().recording.is_committed());
        assert_eq!(
            std::fs::read_to_string(f.root.join("destination/1/COMMITTED.json")).unwrap(),
            m.bytes
        );
    }
    let mut committed = m;
    committed.phase = 4;
    store.save_manifest(&committed).unwrap();
    assert!(store.get(1).unwrap().unwrap().recording.is_committed());
    assert!(f.root.join("source/.file-mover/1-0/data").exists());
}
fn payload_assignment(t: &mover_core::Transfer, c: &mover_core::ClaimIntent) -> Value {
    json!({"version":1,"job_id":t.job_id,"file_index":t.file_index,"attempt":t.attempt,"phase":t.phase as i64,
        "destination_root":t.destination_root,"relative_name":t.relative_name,
        "transfer_objects":[t.root.encode(),t.area.encode(),t.parent.encode(),t.staging_directory.encode(),t.stage.encode()],
        "sha256":t.sha256,"source_root":c.root_path,"source_name":c.source_name,"private_name":c.private_name,
        "claim_objects":[c.root.encode(),c.parent.encode(),c.area.encode(),c.source.encode()]})
}
#[test]
fn payload_children_copy_verify_without_database_access_or_publication() {
    let mut f = Fixture::new(300);
    f.write("data", b"child payload");
    assert_eq!(f.post(&f.input("payload", json!([{"name":"data"}]))).0, 202);
    f.stop();
    provision_destination(&f);
    let store = mover_store::Store::open(f.root.join("state/jobs.sqlite")).unwrap();
    let source =
        mover_fs::LocalClaimLock::acquire(f.root.join("source").to_str().unwrap()).unwrap();
    let destination =
        mover_fs::LocalClaimLock::acquire(f.root.join("destination").to_str().unwrap()).unwrap();
    let mut transfer = mover_fs::prepare_transfer(&store, 1).unwrap();
    let (claim, done) = store.claim_intent(1, 0).unwrap().unwrap();
    assert!(done);
    for phase in [
        mover_core::TransferPhase::Copied,
        mover_core::TransferPhase::Verified,
    ] {
        let before = transfer.clone();
        let (mut child, mut channel) = payload_child(&source, &destination);
        channel
            .write_all(&serde_json::to_vec(&payload_assignment(&transfer, &claim)).unwrap())
            .unwrap();
        channel.shutdown(std::net::Shutdown::Write).unwrap();
        assert!(child.wait().unwrap().success());
        let mut bytes = Vec::new();
        channel.read_to_end(&mut bytes).unwrap();
        let receipt: Value = serde_json::from_slice(&bytes).unwrap();
        assert_eq!(receipt["phase"], phase as i64);
        assert_eq!(receipt["job_id"], 1);
        assert_eq!(receipt["attempt"], before.attempt);
        assert_eq!(store.transfer(1, 0).unwrap(), Some(before));
        transfer.phase = phase;
        transfer.stage =
            mover_core::ObjectIdentity::decode(receipt["stage"].as_str().unwrap()).unwrap();
        transfer.sha256 = Some(receipt["sha256"].as_str().unwrap().to_owned());
        store.save_transfer(&transfer).unwrap();
        assert!(!f.root.join("destination/1/data").exists());
        assert!(!f.root.join("destination/1/COMMITTED.json").exists());
    }
    assert_eq!(
        std::fs::read(f.root.join("destination/1/.staging/1.part")).unwrap(),
        b"child payload"
    );
    assert!(f.root.join("source/.file-mover/1-0/data").exists());
}
#[test]
fn live_payload_child_retains_both_locks_after_parent_descriptors_close() {
    let mut f = Fixture::new(300);
    f.stop();
    provision_destination(&f);
    let source_path = f.root.join("source");
    let destination_path = f.root.join("destination");
    let source = mover_fs::LocalClaimLock::acquire(source_path.to_str().unwrap()).unwrap();
    let destination =
        mover_fs::LocalClaimLock::acquire(destination_path.to_str().unwrap()).unwrap();
    let (mut child, channel) = payload_child(&source, &destination);
    drop(source);
    drop(destination);
    assert!(mover_fs::LocalClaimLock::acquire(source_path.to_str().unwrap()).is_err());
    assert!(mover_fs::LocalClaimLock::acquire(destination_path.to_str().unwrap()).is_err());
    child.kill().unwrap();
    assert!(!child.wait().unwrap().success());
    drop(channel);
    assert!(mover_fs::LocalClaimLock::acquire(source_path.to_str().unwrap()).is_ok());
    assert!(mover_fs::LocalClaimLock::acquire(destination_path.to_str().unwrap()).is_ok());
}
#[test]
fn malformed_payload_assignments_preserve_stage_and_source() {
    let mut f = Fixture::new(300);
    f.write("data", b"protected");
    assert_eq!(
        f.post(&f.input("invalid-payload", json!([{"name":"data"}])))
            .0,
        202
    );
    f.stop();
    provision_destination(&f);
    let store = mover_store::Store::open(f.root.join("state/jobs.sqlite")).unwrap();
    let source =
        mover_fs::LocalClaimLock::acquire(f.root.join("source").to_str().unwrap()).unwrap();
    let destination =
        mover_fs::LocalClaimLock::acquire(f.root.join("destination").to_str().unwrap()).unwrap();
    let transfer = mover_fs::prepare_transfer(&store, 1).unwrap();
    let claim = store.claim_intent(1, 0).unwrap().unwrap().0;
    for body in [
        b"{}".to_vec(),
        vec![b'x'; 32769],
        {
            let mut input = payload_assignment(&transfer, &claim);
            input["phase"] = json!(3);
            serde_json::to_vec(&input).unwrap()
        },
        {
            let mut input = payload_assignment(&transfer, &claim);
            input["private_name"] = json!("../foreign");
            serde_json::to_vec(&input).unwrap()
        },
    ] {
        let (mut child, mut channel) = payload_child(&source, &destination);
        channel.write_all(&body).unwrap();
        channel.shutdown(std::net::Shutdown::Write).unwrap();
        assert!(!child.wait().unwrap().success());
        assert_eq!(store.transfer(1, 0).unwrap(), Some(transfer.clone()));
        assert_eq!(
            std::fs::metadata(f.root.join("destination/1/.staging/1.part"))
                .unwrap()
                .len(),
            0
        );
        assert_eq!(
            std::fs::read(f.root.join("source/.file-mover/1-0/data")).unwrap(),
            b"protected"
        );
    }
}
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
fn status(f: &Fixture, id: &str) -> (u16, Value) {
    f.raw(format!("GET /api/v2/jobs/{id} HTTP/1.1\r\nHost: h\r\n\r\n").as_bytes())
}
fn retention(f: &Fixture, id: Option<&str>) -> (u16, Value) {
    let path = id.map_or_else(
        || "/api/v2/retention".to_owned(),
        |id| format!("/api/v2/jobs/{id}/retention"),
    );
    f.raw(format!("GET {path} HTTP/1.1\r\nHost: h\r\n\r\n").as_bytes())
}
#[test]
fn retention_api_reports_admission_headroom_and_committed_retained_sources() {
    let mut f = Fixture::new(300);
    let (code, r) = retention(&f, None);
    assert_eq!(code, 200);
    assert_eq!(r["details"]["retained_jobs"], 0);
    assert_eq!(r["details"]["global_headroom"]["new_job_slots"], 64);
    let body = f.input("accounting", json!([{"name":"data"},{"name":"late"}]));
    f.write("data", b"abc");
    assert_eq!(f.post(&body).0, 503);
    let (_, r) = retention(&f, Some("1"));
    assert_eq!(r["details"]["source_reserved_bytes"], "3");
    assert_eq!(r["details"]["unmeasured_files"], 1);
    assert_eq!(r["details"]["confirmed_claims"], 1);
    assert!(r["details"]["global_headroom"].is_null());
    f.write("late", b"xy");
    assert_eq!(f.post(&body).0, 202);
    f.stop();
    provision_destination(&f);
    f.start();
    wait_manifest(&f, "1");
    f.stop();
    f.start();
    let (_, r) = retention(&f, None);
    assert_eq!(r["details"]["source_reserved_bytes"], "5");
    assert_eq!(r["details"]["destination_reserved_bytes"], "5");
    assert_eq!(r["details"]["committed_jobs"], 1);
    assert_eq!(
        r["details"]["destination_attempts_by_phase"]["Published"],
        2
    );
    assert_eq!(
        r["details"]["global_headroom"]["source_bytes"],
        (1099511627776_u64 - 5).to_string()
    );
    assert_eq!(r["details"]["filesystem_inspected"], false);
    assert_eq!(r["details"]["automatic_reclamation_enabled"], false);
    assert!(f.root.join("source/.file-mover/1-0/data").exists());
    assert_eq!(retention(&f, Some("999")).0, 404);
    assert_eq!(retention(&f, Some("01")).0, 400);
    assert_eq!(
        f.raw(b"POST /api/v2/retention HTTP/1.1\r\nHost: h\r\n\r\n")
            .0,
        405
    );
    assert_eq!(
        f.raw(b"GET /api/v2/retention HTTP/1.1\r\nHost: h\r\nContent-Length: 1\r\n\r\nx")
            .0,
        400
    );
    assert_eq!(
        f.raw(b"POST /api/v2/jobs/1/retention HTTP/1.1\r\nHost: h\r\n\r\n")
            .0,
        405
    );
}
#[test]
fn retention_api_charges_interrupted_attempts_and_does_not_claim_to_find_orphans() {
    let mut f = Fixture::new(300);
    f.write("data", b"abc");
    assert_eq!(
        f.post(&f.input("attempt-accounting", json!([{"name":"data"}])))
            .0,
        202
    );
    f.stop();
    provision_destination(&f);
    {
        let s = mover_store::Store::open(f.root.join("state/jobs.sqlite")).unwrap();
        let t = mover_fs::prepare_transfer(&s, 1).unwrap();
        mover_fs::restart_transfer(&s, &t).unwrap();
        // Allocation without a receipt cannot be attributed by database accounting.
        std::fs::write(
            f.root.join("destination/1/.staging/unreceipted.part"),
            b"unknown bytes",
        )
        .unwrap();
        for time in [100, 105, 110] {
            s.delivery_failed(1, time).unwrap();
        }
    }
    f.start();
    let (_, r) = retention(&f, Some("1"));
    assert_eq!(r["details"]["destination_reserved_bytes"], "6");
    assert_eq!(r["details"]["destination_attempts_by_phase"]["Intent"], 2);
    assert_eq!(r["details"]["unreceipted_allocations_accounted"], false);
    assert_eq!(
        std::fs::read(f.root.join("destination/1/.staging/unreceipted.part")).unwrap(),
        b"unknown bytes"
    );
    assert_eq!(status(&f, "1").1["details"]["condition"], "ReviewRequired");
    assert_eq!(f.raw(b"GET /healthz HTTP/1.1\r\nHost: h\r\n\r\n").0, 200);
}
fn reset_body(epoch: u32, file: &str, seconds: u32) -> Value {
    json!({"command_id":format!("missing-{epoch}"),"expected_missing_review_epoch":epoch,"file_id":file,"retry_window_seconds":seconds,"reason":"Confirmed recorder has not reused the pending source paths"})
}
fn reset_bytes(body: &str) -> Vec<u8> {
    format!("POST /api/v2/jobs/1/reset-missing HTTP/1.1\r\nHost: h\r\nContent-Type: application/json\r\nContent-Length: {}\r\n\r\n{body}",body.len()).into_bytes()
}
fn reset(f: &Fixture, body: &Value) -> (u16, Value) {
    f.raw(&reset_bytes(&body.to_string()))
}
#[test]
fn missing_reset_lost_response_survives_restart_and_partial_claims_complete() {
    let mut f = Fixture::new(0);
    f.write("data", b"abc");
    let submission = f.input("missing-reset", json!([{"name":"data"},{"name":"late"}]));
    assert_eq!(f.post(&submission).0, 409);
    assert_eq!(status(&f, "1").1["details"]["files"][0]["phase"], "Claimed");
    let body = reset_body(0, "1", 300);
    let mut stream = TcpStream::connect(f.address).unwrap();
    stream.write_all(&reset_bytes(&body.to_string())).unwrap();
    drop(stream);
    let deadline = Instant::now() + Duration::from_secs(3);
    loop {
        if status(&f, "1").1["details"]["missing_review_epoch"] == 1 {
            break;
        }
        assert!(Instant::now() < deadline);
        std::thread::sleep(Duration::from_millis(20));
    }
    let (_, s) = status(&f, "1");
    let new_deadline = s["details"]["missing"][0]["deadline"].clone();
    assert_eq!(s["source_paths_released"], false);
    assert_eq!(s["details"]["latest_missing_reset"]["file_id"], "1");
    f.stop();
    f.start();
    let (code, r) = reset(&f, &body);
    assert_eq!(code, 200);
    assert_eq!(r["details"]["replay"], true);
    assert_eq!(r["source_paths_released"], false);
    assert_eq!(r["details"]["new_deadline"], new_deadline);
    assert_eq!(f.post(&submission).0, 503);
    assert_eq!(
        status(&f, "1").1["details"]["missing"][0]["deadline"],
        new_deadline
    );
    assert!(!f.root.join("source/current/data").exists());
    f.write("late", b"later");
    assert_eq!(f.post(&submission).0, 202);
    f.write("data", b"producer reuse");
    f.stop();
    let s = mover_store::Store::open(f.root.join("state/jobs.sqlite")).unwrap();
    assert_eq!(
        s.get(1).unwrap().unwrap().recording.handoff(),
        mover_core::Handoff::Ready202
    );
    assert_eq!(s.status(1).unwrap().unwrap().missing_review_epoch, 1);
    assert_eq!(
        std::fs::read(f.root.join("source/.file-mover/1-0/data")).unwrap(),
        b"abc"
    );
    assert_eq!(
        std::fs::read(f.root.join("source/.file-mover/1-1/data")).unwrap(),
        b"later"
    );
}
#[test]
fn missing_reset_expiry_requires_new_epoch_and_rejects_bad_requests() {
    let mut f = Fixture::new(0);
    let submission = f.input("expiry", json!([{"name":"absent"}]));
    assert_eq!(f.post(&submission).0, 409);
    for file in ["01", "-1", "+0", "4294967296"] {
        assert_eq!(reset(&f, &reset_body(0, file, 10)).0, 400);
    }
    for seconds in [0, 86401] {
        assert_eq!(reset(&f, &reset_body(0, "0", seconds)).0, 400);
    }
    for body in [
        "{}",
        r#"{"command_id":"x","command_id":"y","file_id":"0","expected_missing_review_epoch":0,"retry_window_seconds":10,"reason":"fix"}"#,
        r#"{"command_id":"x","file_id":"0","expected_missing_review_epoch":0,"retry_window_seconds":10,"reason":"fix","extra":true}"#,
    ] {
        assert_eq!(f.raw(&reset_bytes(body)).0, 400);
    }
    assert_eq!(
        f.raw(b"GET /api/v2/jobs/1/reset-missing HTTP/1.1\r\nHost: h\r\n\r\n")
            .0,
        405
    );
    let body = reset_body(0, "0", 1);
    let (code, r) = reset(&f, &body);
    assert_eq!(code, 200);
    let deadline = r["details"]["new_deadline"].clone();
    let limit = Instant::now() + Duration::from_secs(4);
    loop {
        if status(&f, "1").1["details"]["condition"] == "ReviewRequired" {
            break;
        }
        assert!(Instant::now() < limit);
        std::thread::sleep(Duration::from_millis(20));
    }
    // Expiry visibility need not have persisted blocked yet; reset/replay handles both.
    assert_eq!(reset(&f, &body).1["details"]["new_deadline"], deadline);
    assert_eq!(f.post(&submission).0, 409);
    let mut stale = body.clone();
    stale["command_id"] = json!("stale-new-command");
    assert_eq!(reset(&f, &stale).1["error"], "review_conflict");
    let mut conflict = body.clone();
    conflict["retry_window_seconds"] = json!(10);
    assert_eq!(reset(&f, &conflict).1["error"], "command_conflict");
    assert_eq!(reset(&f, &reset_body(1, "0", 300)).0, 200);
    f.stop();
    f.start();
    assert_eq!(f.post(&submission).0, 503);
    assert_eq!(status(&f, "1").1["details"]["missing_review_epoch"], 2);
}
#[test]
fn missing_reset_rejects_unexpired_claimed_and_committed_files() {
    let mut f = Fixture::new(300);
    let submission = f.input("unexpired", json!([{"name":"data"}]));
    assert_eq!(f.post(&submission).0, 503);
    let (_, before) = status(&f, "1");
    assert_eq!(
        reset(&f, &reset_body(0, "0", 300)).1["error"],
        "review_conflict"
    );
    assert_eq!(status(&f, "1").1, before);
    f.write("data", b"abc");
    assert_eq!(f.post(&submission).0, 202);
    assert_eq!(reset(&f, &reset_body(0, "0", 300)).0, 409);
    f.stop();
    provision_destination(&f);
    f.start();
    wait_manifest(&f, "1");
    f.stop();
    f.start();
    assert_eq!(reset(&f, &reset_body(0, "0", 300)).0, 409);
    assert_eq!(status(&f, "1").1["details"]["missing_review_epoch"], 0);
    assert!(f.root.join("source/.file-mover/1-0/data").exists());
}
fn resume_body(epoch: u32) -> Value {
    json!({"command_id":format!("resume-{epoch}"),"expected_review_epoch":epoch,"reason":"Inspected protected staging and destination"})
}
fn resume_bytes(id: &str, body: &str) -> Vec<u8> {
    format!("POST /api/v2/jobs/{id}/resume HTTP/1.1\r\nHost: h\r\nContent-Type: application/json\r\nContent-Length: {}\r\n\r\n{body}",body.len()).into_bytes()
}
fn resume(f: &Fixture, id: &str, body: &Value) -> (u16, Value) {
    f.raw(&resume_bytes(id, &body.to_string()))
}
fn seed_review(f: &Fixture) {
    let s = mover_store::Store::open(f.root.join("state/jobs.sqlite")).unwrap();
    for time in [100, 105, 110] {
        s.delivery_failed(1, time).unwrap();
    }
}
#[test]
fn operator_resume_keeps_collision_safe_and_reconciles_same_verified_attempt() {
    let mut f = Fixture::new(300);
    f.write("data", b"abc");
    assert_eq!(f.post(&f.input("resume", json!([{"name":"data"}]))).0, 202);
    f.stop();
    provision_destination(&f);
    f.write("data", b"producer reuse");
    {
        let s = mover_store::Store::open(f.root.join("state/jobs.sqlite")).unwrap();
        let t = mover_fs::prepare_transfer(&s, 1).unwrap();
        let t = mover_fs::copy_stage(&s, &t).unwrap();
        let t = mover_fs::verify_stage(&s, &t).unwrap();
        mover_fs::authorize_publication(&s, &t).unwrap();
    }
    let final_path = f.root.join("destination/1/data");
    std::fs::write(&final_path, b"foreign recording").unwrap();
    seed_review(&f);
    f.start();
    assert_eq!(status(&f, "1").1["details"]["review_epoch"], 0);
    let (code, r) = resume(&f, "1", &resume_body(0));
    assert_eq!(code, 200);
    assert_eq!(r["details"]["replay"], false);
    let deadline = Instant::now() + Duration::from_secs(3);
    loop {
        if status(&f, "1").1["details"]["delivery_retry"]["failures"] == 1 {
            break;
        }
        assert!(Instant::now() < deadline);
        std::thread::sleep(Duration::from_millis(20));
    }
    assert_eq!(std::fs::read(&final_path).unwrap(), b"foreign recording");
    assert!(!f.root.join("destination/1/COMMITTED.json").exists());
    f.stop();
    seed_review(&f);
    f.start();
    // Replaying an earlier successful command does not unblock a newer review.
    assert_eq!(
        resume(&f, "1", &resume_body(0)).1["details"]["replay"],
        true
    );
    assert_eq!(status(&f, "1").1["details"]["condition"], "ReviewRequired");
    let mut stale = resume_body(0);
    stale["command_id"] = json!("different-stale");
    assert_eq!(resume(&f, "1", &stale).0, 409);
    f.stop();
    // Remove only this test's deliberately created foreign collision fixture.
    std::fs::remove_file(&final_path).unwrap();
    f.start();
    assert_eq!(resume(&f, "1", &resume_body(1)).0, 200);
    wait_manifest(&f, "1");
    f.stop();
    let s = mover_store::Store::open(f.root.join("state/jobs.sqlite")).unwrap();
    assert!(s.get(1).unwrap().unwrap().recording.is_committed());
    assert_eq!(s.transfer(1, 0).unwrap().unwrap().attempt, 1);
    assert_eq!(s.status(1).unwrap().unwrap().review_epoch, 2);
    assert_eq!(std::fs::read(&final_path).unwrap(), b"abc");
    assert_eq!(
        std::fs::read(f.root.join("source/current/data")).unwrap(),
        b"producer reuse"
    );
    assert_eq!(
        std::fs::read(f.root.join("source/.file-mover/1-0/data")).unwrap(),
        b"abc"
    );
}
#[test]
fn operator_resume_lost_reply_survives_restart_and_invalid_requests_do_not_reset() {
    let mut f = Fixture::new(300);
    f.write("data", b"abc");
    assert_eq!(
        f.post(&f.input("resume-lost", json!([{"name":"data"}]))).0,
        202
    );
    assert_eq!(resume(&f, "1", &resume_body(0)).0, 409);
    assert_eq!(resume(&f, "999", &resume_body(0)).0, 404);
    let mut wrong_key = String::from_utf8(resume_bytes("1", &resume_body(0).to_string())).unwrap();
    wrong_key = wrong_key.replace("Host: h\r\n", "Host: h\r\nIdempotency-Key: different\r\n");
    assert_eq!(
        f.raw(wrong_key.as_bytes()).1["error"],
        "idempotency_key_conflict"
    );
    for body in [
        "{}",
        r#"{"command_id":"a","expected_review_epoch":0,"reason":"","extra":true}"#,
        r#"{"command_id":"a","command_id":"b","expected_review_epoch":0,"reason":"fix"}"#,
        r#"{"command_id":"a","expected_review_epoch":-1,"reason":"fix"}"#,
    ] {
        assert_eq!(f.raw(&resume_bytes("1", body)).0, 400);
    }
    f.stop();
    seed_review(&f);
    f.start();
    let mut stream = TcpStream::connect(f.address).unwrap();
    stream
        .write_all(&resume_bytes("1", &resume_body(0).to_string()))
        .unwrap();
    drop(stream);
    let deadline = Instant::now() + Duration::from_secs(3);
    loop {
        if status(&f, "1").1["details"]["review_epoch"] == 1 {
            break;
        }
        assert!(Instant::now() < deadline);
        std::thread::sleep(Duration::from_millis(20));
    }
    f.stop();
    f.start();
    let (code, r) = resume(&f, "1", &resume_body(0));
    assert_eq!(code, 200);
    assert_eq!(r["details"]["replay"], true);
    let (_, s) = status(&f, "1");
    assert_eq!(s["details"]["latest_resume"]["command_id"], "resume-0");
    assert_eq!(
        s["details"]["latest_resume"]["actor"],
        "trusted-loopback-operator"
    );
    let mut conflict = resume_body(0);
    conflict["reason"] = json!("changed reason");
    assert_eq!(resume(&f, "1", &conflict).1["error"], "command_conflict");
    f.stop();
}
#[test]
fn operator_resume_rejects_unclaimed_and_committed_jobs() {
    let mut f = Fixture::new(0);
    let body = f.input("not-claimed", json!([{"name":"missing"}]));
    assert_eq!(f.post(&body).0, 409);
    let (_, before) = status(&f, "1");
    assert_eq!(
        resume(&f, "1", &resume_body(0)).1["error"],
        "review_conflict"
    );
    assert_eq!(status(&f, "1").1, before);
    assert_eq!(
        f.raw(b"GET /api/v2/jobs/1/resume HTTP/1.1\r\nHost: h\r\n\r\n")
            .0,
        405
    );
    assert_eq!(
        f.raw(b"POST /api/v2/jobs/1/resume HTTP/1.1\r\nHost: h\r\n\r\n")
            .0,
        415
    );
    provision_destination(&f);
    f.write("data", b"abc");
    assert_eq!(
        f.post(&f.input("complete", json!([{"name":"data"}]))).0,
        202
    );
    wait_manifest(&f, "2");
    f.stop();
    f.start();
    assert_eq!(status(&f, "2").1["state"], "Committed");
    assert_eq!(
        resume(&f, "2", &resume_body(0)).1["error"],
        "review_conflict"
    );
    assert_eq!(status(&f, "2").1["details"]["review_epoch"], 0);
    assert!(f.root.join("source/.file-mover/2-0/data").exists());
}
#[test]
fn operator_status_observes_partial_claims_outage_and_committed_restart() {
    let mut f = Fixture::new(300);
    f.write("data", b"abc");
    let body = f.input("status", json!([{"name":"data"},{"name":"empty"}]));
    assert_eq!(f.post(&body).0, 503);
    let (code, pending) = status(&f, "1");
    assert_eq!(code, 200);
    assert_eq!(pending["state"], "Accepted");
    assert_eq!(pending["source_paths_released"], false);
    assert_eq!(pending["details"]["files"][0]["size_bytes"], 3);
    assert_eq!(pending["details"]["files"][1]["phase"], "Pending");
    assert_eq!(pending["details"]["missing"].as_array().unwrap().len(), 1);
    f.write("empty", b"");
    assert_eq!(f.post(&body).0, 202);
    let deadline = Instant::now() + Duration::from_secs(3);
    loop {
        let (_, s) = status(&f, "1");
        if s["details"]["condition"] == "Retrying" {
            assert_eq!(
                s["details"]["delivery_retry"]["code"],
                "destination_unavailable"
            );
            assert_eq!(s["source_paths_released"], true);
            break;
        }
        assert!(Instant::now() < deadline);
        std::thread::sleep(Duration::from_millis(20));
    }
    f.stop();
    provision_destination(&f);
    f.start();
    wait_manifest(&f, "1");
    let deadline = Instant::now() + Duration::from_secs(3);
    loop {
        let (_, s) = status(&f, "1");
        if s["state"] == "Committed" {
            assert_eq!(s["details"]["manifest_phase"], 4);
            assert_eq!(s["details"]["source_cleanup_enabled"], false);
            assert_eq!(s["details"]["files"][1]["size_bytes"], 0);
            assert_eq!(s["details"]["files"][0]["transfer_phase"], "Published");
            break;
        }
        assert!(Instant::now() < deadline);
        std::thread::sleep(Duration::from_millis(20));
    }
    f.stop();
    f.start();
    assert_eq!(status(&f, "1").1["state"], "Committed");
    assert!(f.root.join("source/.file-mover/1-0/data").exists());
}
#[test]
fn operator_status_rejects_invalid_routes_and_reports_review_without_reset() {
    let mut f = Fixture::new(0);
    assert_eq!(status(&f, "999").0, 404);
    for id in [
        "0",
        "-1",
        "01",
        "+1",
        "1?x=1",
        "1/files",
        "9223372036854775808",
    ] {
        assert_eq!(status(&f, id).0, 400, "{id}");
    }
    assert_eq!(
        f.raw(b"POST /api/v2/jobs/1 HTTP/1.1\r\nHost: h\r\n\r\n").0,
        405
    );
    assert_eq!(
        f.raw(b"GET /api/v2/jobs/1 HTTP/1.1\r\nHost: h\r\nContent-Length: 1\r\n\r\nx")
            .0,
        400
    );
    assert_eq!(
        f.post(&f.input("missing", json!([{"name":"absent"}]))).0,
        409
    );
    assert_eq!(status(&f, "1").1["details"]["condition"], "ReviewRequired");
    f.stop();
    f.start();
    let (_, s) = status(&f, "1");
    assert_eq!(s["details"]["condition"], "ReviewRequired");
    assert_eq!(s["source_paths_released"], false);
    assert_eq!(s["details"]["missing"][0]["blocked"], true);
}
fn wait_manifest(f: &Fixture, id: &str) -> Value {
    let path = f.root.join("destination").join(id).join("COMMITTED.json");
    let deadline = Instant::now() + Duration::from_secs(15);
    loop {
        if let Ok(bytes) = std::fs::read(&path) {
            // Consumer visibility can precede the coordinator's applied receipt.
            // Tests that stop/reopen the service must wait for both boundaries.
            let manifest = serde_json::from_slice(&bytes).unwrap();
            let (code, job) = status(f, id);
            if code == 200 && job["state"] == "Committed" {
                return manifest;
            }
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
