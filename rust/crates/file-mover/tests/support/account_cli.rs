use super::*;
#[test]
fn account_helper_excludes_replacement_until_actual_exit_after_input_owner_is_gone() {
    use std::io::BufRead;
    let mut f = Fixture::new(300);
    f.stop();
    let dir = directory(&f);
    struct Owned(Child);
    impl Drop for Owned {
        fn drop(&mut self) {
            let _ = self.0.kill();
            let _ = self.0.wait();
        }
    }
    let mut helper = Owned(
        Command::new(std::env::var("FILE_MOVER_TEST_EXECUTABLE").unwrap())
            .arg("--internal-admin-account-worker")
            .arg("--admin-account-init")
            .arg(f.root.join("config.json"))
            .arg("--account-dir")
            .arg(&dir)
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::null())
            .spawn()
            .unwrap(),
    );
    let mut output = std::io::BufReader::new(helper.0.stdout.take().unwrap());
    let mut line = String::new();
    output.read_line(&mut line).unwrap();
    assert_eq!(
        serde_json::from_str::<Value>(&line).unwrap(),
        json!({"account_ready":true})
    );
    let pid = helper.0.id();
    let stat = std::fs::read_to_string(format!("/proc/{pid}/stat")).unwrap();
    let tail = stat
        .rsplit_once(')')
        .unwrap()
        .1
        .split_whitespace()
        .collect::<Vec<_>>();
    assert_eq!(
        tail[2].parse::<u32>().unwrap(),
        pid,
        "helper must own its own recorded process group"
    );
    assert!(
        Command::new("/bin/kill")
            .args(["-STOP", &pid.to_string()])
            .status()
            .unwrap()
            .success()
    );
    drop(helper.0.stdin.take()); // EOF from a dead input owner; stopped helper still exists.
    let refused = command(&f, &dir, "--admin-account-status", None);
    assert!(!refused.status.success());
    assert!(String::from_utf8_lossy(&refused.stderr).contains("owns state"));
    assert!(!dir.join("admin-account.json").exists());
    assert!(
        Command::new("/bin/kill")
            .args(["-CONT", &pid.to_string()])
            .status()
            .unwrap()
            .success()
    );
    assert!(!helper.0.wait().unwrap().success());
    let admitted = command(&f, &dir, "--admin-account-status", None);
    assert!(admitted.status.success());
    assert_eq!(
        serde_json::from_slice::<Value>(&admitted.stdout).unwrap(),
        json!({"provisioned":false})
    );
}
fn directory(f: &Fixture) -> PathBuf {
    let p = f.root.join("accounts");
    std::fs::create_dir(&p).unwrap();
    std::fs::set_permissions(&p, std::fs::Permissions::from_mode(0o700)).unwrap();
    p
}
fn command(
    f: &Fixture,
    dir: &std::path::Path,
    action: &str,
    input: Option<&[u8]>,
) -> std::process::Output {
    let mut c = Command::new(std::env::var("FILE_MOVER_TEST_EXECUTABLE").unwrap());
    c.arg(action)
        .arg(f.root.join("config.json"))
        .arg("--account-dir")
        .arg(dir)
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());
    if input.is_some() {
        c.arg("--stdin");
    }
    let mut child = c.spawn().unwrap();
    if let Some(input) = input {
        let _ = child.stdin.take().unwrap().write_all(input);
    } else {
        drop(child.stdin.take());
    }
    child.wait_with_output().unwrap()
}
#[test]
fn local_account_initialization_change_and_status_preserve_files_and_exact_identity() {
    let mut f = Fixture::new(300);
    f.stop();
    let dir = directory(&f);
    let db = f.root.join("state/jobs.sqlite");
    let original_db = std::fs::read(&db).unwrap();
    let receipt = f.root.join("source/.file-mover/source-enrollment.json");
    let original_receipt = std::fs::read(&receipt).unwrap();
    let first=br#"{"username":" admin ","password":"disposable-old","confirm_password":"disposable-old"}"#;
    let out = command(&f, &dir, "--admin-account-init", Some(first));
    assert!(out.status.success(), "{out:?}");
    let record_path = dir.join("admin-account.json");
    let a: Value = serde_json::from_slice(&std::fs::read(&record_path).unwrap()).unwrap();
    assert_eq!(a["revision"], 1);
    assert_eq!(a["username"], " admin ");
    assert_eq!(
        std::fs::metadata(&record_path)
            .unwrap()
            .permissions()
            .mode()
            & 0o7777,
        0o600
    );
    assert!(!String::from_utf8_lossy(&out.stdout).contains("argon2"));
    assert!(!String::from_utf8_lossy(&out.stdout).contains("disposable-old"));
    assert!(
        !command(&f, &dir, "--admin-account-init", Some(first))
            .status
            .success()
    );
    // Account commands inspect stored pairing only, even if both payload roots vanish.
    std::fs::rename(f.root.join("source"), f.root.join("source-offline")).unwrap();
    if f.root.join("destination").exists() {
        std::fs::rename(
            f.root.join("destination"),
            f.root.join("destination-offline"),
        )
        .unwrap();
    }
    let change = br#"{"password":"disposable-new","confirm_password":"disposable-new"}"#;
    let out = command(&f, &dir, "--admin-password-change", Some(change));
    assert!(out.status.success(), "{out:?}");
    let b: Value = serde_json::from_slice(&std::fs::read(&record_path).unwrap()).unwrap();
    assert_eq!(b["account_id"], a["account_id"]);
    assert_eq!(b["instance_id"], a["instance_id"]);
    assert_eq!(b["username"], a["username"]);
    assert_eq!(b["revision"], 2);
    assert_ne!(b["verifier"], a["verifier"]);
    let new = file_mover::password::Verifier::from_encoded(b["verifier"].as_str().unwrap().into())
        .unwrap();
    assert!(
        new.verify(&file_mover::password::Password::new(b"disposable-new".to_vec()).unwrap())
            .unwrap()
    );
    assert!(
        !new.verify(&file_mover::password::Password::new(b"disposable-old".to_vec()).unwrap())
            .unwrap()
    );
    let status = command(&f, &dir, "--admin-account-status", None);
    assert!(status.status.success());
    let status: Value = serde_json::from_slice(&status.stdout).unwrap();
    assert_eq!(status["revision"], "2");
    assert_eq!(status.as_object().unwrap().len(), 4);
    assert!(status.get("verifier").is_none());
    assert_eq!(std::fs::read(db).unwrap(), original_db);
    assert_eq!(
        std::fs::read(
            f.root
                .join("source-offline/.file-mover/source-enrollment.json")
        )
        .unwrap(),
        original_receipt
    );
}
#[test]
fn account_refuses_running_owner_missing_state_and_payload_overlap_before_publication() {
    let mut f = Fixture::new(300);
    let dir = directory(&f);
    let input = br#"{"username":"admin","password":"fixture","confirm_password":"fixture"}"#;
    let live = command(&f, &dir, "--admin-account-init", Some(input));
    assert!(!live.status.success());
    assert!(String::from_utf8_lossy(&live.stderr).contains("owns state"));
    assert!(!dir.join("account.lock").exists());
    f.stop();
    let overlap = command(
        &f,
        &f.root.join("source"),
        "--admin-account-init",
        Some(input),
    );
    assert!(!overlap.status.success());
    assert!(!f.root.join("source/admin-account.json").exists());
    let missing = Fixture::uninitialized(300);
    let empty = directory(&missing);
    assert!(
        !command(&missing, &empty, "--admin-account-init", Some(input))
            .status
            .success()
    );
    assert!(!missing.root.join("state/jobs.sqlite").exists());
    assert!(!empty.join("account.lock").exists());
}
#[test]
fn account_invalid_secret_input_and_foreign_record_never_echo_or_overwrite() {
    let mut f = Fixture::new(300);
    f.stop();
    let dir = directory(&f);
    for input in [br#"{"username":"admin","password":"DO_NOT_ECHO","confirm_password":"different"}"#.as_slice(),br#"{"username":"admin","password":"DO_NOT_ECHO","confirm_password":"DO_NOT_ECHO","DO_NOT_ECHO":true}"#,br#"{"username":"admin","password":"DO_NOT_ECHO","password":"DO_NOT_ECHO","confirm_password":"DO_NOT_ECHO"}"#]{let out=command(&f,&dir,"--admin-account-init",Some(input));assert!(!out.status.success());assert!(!String::from_utf8_lossy(&out.stdout).contains("DO_NOT_ECHO"));assert!(!String::from_utf8_lossy(&out.stderr).contains("DO_NOT_ECHO"));assert!(!dir.join("admin-account.json").exists());}
    let input = br#"{"username":"admin","password":"fixture","confirm_password":"fixture"}"#;
    assert!(
        command(&f, &dir, "--admin-account-init", Some(input))
            .status
            .success()
    );
    let path = dir.join("admin-account.json");
    let mut record: Value = serde_json::from_slice(&std::fs::read(&path).unwrap()).unwrap();
    record["instance_id"] = json!("foreign");
    let foreign = serde_json::to_vec(&record).unwrap();
    std::fs::write(&path, &foreign).unwrap();
    assert!(
        !command(
            &f,
            &dir,
            "--admin-password-change",
            Some(br#"{"password":"replacement","confirm_password":"replacement"}"#)
        )
        .status
        .success()
    );
    assert_eq!(std::fs::read(path).unwrap(), foreign);
}
