//! Private offline backup artifacts; never restores, converts or adopts state.
use super::*;
use mover_store::StateInspection;
use sha2::{Digest, Sha256};
use std::{
    fs::File,
    io::{Read, Seek, SeekFrom, Write},
    path::{Component, Path},
};
type BackupResult<T> = std::result::Result<T, Box<dyn std::error::Error>>;

/// Stored evidence only. Does not inspect or activate source enrollment.
pub fn validate_inspected_state(state: &StateInspection) -> BackupResult<&'static str> {
    let enrollment = state.enrollment()?;
    let ownership = state.ownership()?;
    let pairing = match (enrollment, ownership) {
        (None, None) => "Unenrolled",
        (None, Some(_)) => return Err("ownership without enrollment".into()),
        (Some(e), o) => {
            let binding: SourceBinding = serde_json::from_str(&e.binding)?;
            binding.validate()?;
            if e.state_instance_id != state.summary().instance_id {
                return Err("enrollment instance mismatch".into());
            }
            match o {
                None => "OwnershipMissing",
                Some(o) => {
                    let receipt: EnrollmentReceipt = serde_json::from_str(&o.receipt)?;
                    receipt.validate(&SourceAuthorization {
                        binding,
                        observation: e.observation,
                        enrollment: None,
                    })?;
                    if receipt.state_instance_id != e.state_instance_id {
                        return Err("receipt instance mismatch".into());
                    }
                    if let Some(object) = o.object {
                        let object =
                            ObjectIdentity::decode(&object).ok_or("invalid receipt object")?;
                        if object.size != o.receipt.len() as u64 || object.links != 1 {
                            return Err("invalid receipt size/links".into());
                        }
                        "RecordedActive"
                    } else {
                        "Prepared"
                    }
                }
            }
        }
    };
    state.visit_jobs(|job, m, t| {
        super::manifest::validate_inspected_manifest(job, m, t, &state.summary().instance_id)
    })?;
    Ok(pairing)
}
fn canonical(path: &str) -> BackupResult<&Path> {
    let p = Path::new(path);
    if !p.is_absolute()
        || path == "/"
        || path.contains("//")
        || path.contains('\\')
        || path.chars().any(char::is_control)
        || path.ends_with('/')
        || path
            .split('/')
            .skip(1)
            .any(|c| c == "." || c == ".." || c.is_empty())
        || p.components()
            .any(|c| !matches!(c, Component::RootDir | Component::Normal(_)))
    {
        return Err("canonical absolute backup path required".into());
    }
    Ok(p)
}
pub struct BackupOutput {
    path: String,
    parent_path: String,
    name: String,
    parent: OwnedFd,
    directory: OwnedFd,
    database: File,
    parent_identity: ObjectIdentity,
    directory_identity: ObjectIdentity,
    database_identity: ObjectIdentity,
}
impl BackupOutput {
    /// Exclusions are checked lexically before touching the output. Include all
    /// configured and stored payload roots and the entire live state directory.
    pub fn check_location(path: &str, excluded: &[String]) -> BackupResult<()> {
        let p = canonical(path)?;
        for root in excluded {
            let root = canonical(root)?;
            if p.starts_with(root) || root.starts_with(p) {
                return Err("backup overlaps state or payload scope".into());
            }
        }
        instance::backup_local(p)?;
        Ok(())
    }
    pub fn create(path: &str, excluded: &[String]) -> BackupResult<Self> {
        Self::check_location(path, excluded)?;
        let p = canonical(path)?;
        let parent_path = p
            .parent()
            .and_then(Path::to_str)
            .ok_or("backup parent required")?
            .to_owned();
        let name = p
            .file_name()
            .and_then(|s| s.to_str())
            .ok_or("backup name required")?
            .to_owned();
        let parent = instance::local_parent_for_epoch(&parent_path)?;
        let parent_identity = owned_directory(&parent, true)?;
        fs::mkdirat(&parent, name.as_str(), Mode::from_raw_mode(0o700))?;
        let directory = fs::openat(&parent, name.as_str(), DIRECTORY, Mode::empty())?;
        let directory_identity = owned_directory(&directory, true)?;
        let database = File::from(fs::openat(
            &directory,
            "state.sqlite",
            OFlags::RDWR | OFlags::CREATE | OFlags::EXCL | OFlags::NOFOLLOW | OFlags::CLOEXEC,
            Mode::from_raw_mode(0o600),
        )?);
        let database_identity = observation(&fs::fstat(&database)?);
        let output = Self {
            path: path.into(),
            parent_path,
            name,
            parent,
            directory,
            database,
            parent_identity,
            directory_identity,
            database_identity,
        };
        output.validate()?;
        if output.database.metadata()?.len() != 0 {
            return Err("snapshot must start empty".into());
        }
        fs::fsync(&output.directory)?;
        fs::fsync(&output.parent)?;
        Ok(output)
    }
    pub fn database_path(&self) -> String {
        format!("{}/state.sqlite", self.path)
    }
    pub fn validate(&self) -> BackupResult<()> {
        instance::backup_local(Path::new(&self.path))?;
        let current_parent = instance::local_parent_for_epoch(&self.parent_path)?;
        same_directory(
            &owned_directory(&current_parent, true)?,
            &self.parent_identity,
        )?;
        let current_dir = fs::openat(
            &current_parent,
            self.name.as_str(),
            DIRECTORY,
            Mode::empty(),
        )?;
        same_directory(
            &owned_directory(&current_dir, true)?,
            &self.directory_identity,
        )?;
        for suffix in ["", "-wal", "-shm", "-journal"] {
            let candidate = format!("{}{suffix}", self.database_path());
            instance::backup_local(Path::new(&candidate))?;
            if !suffix.is_empty() {
                match fs::statat(
                    &current_dir,
                    format!("state.sqlite{suffix}").as_str(),
                    AtFlags::SYMLINK_NOFOLLOW,
                ) {
                    Ok(_) => return Err("unexpected snapshot sidecar".into()),
                    Err(Errno::NOENT) => (),
                    Err(error) => return Err(error.into()),
                }
            }
        }
        let named = fs::statat(&current_dir, "state.sqlite", AtFlags::SYMLINK_NOFOLLOW)?;
        let actual = fs::fstat(&self.database)?;
        if observation(&named) != observation(&actual)
            || actual.st_ino != self.database_identity.inode
            || actual.st_dev != self.database_identity.device
            || actual.st_nlink != 1
            || actual.st_uid != rustix::process::geteuid().as_raw()
            || actual.st_mode & 0o7777 != 0o600
            || FileType::from_raw_mode(actual.st_mode) != FileType::RegularFile
            || actual.st_dev != fs::fstat(&current_dir)?.st_dev
        {
            return Err("snapshot file identity changed".into());
        }
        Ok(())
    }
    pub fn copy(&self, state: &StateInspection) -> BackupResult<()> {
        self.validate()?;
        fault("copy")?;
        fault("copy_enospc")?;
        state.snapshot_into(&self.database_path())?;
        super::qualification_pause("backup_after_copy")?;
        self.validate()?;
        state.verify_snapshot(self.database_path())?;
        self.validate()
    }
    /// Success requires snapshot verification and every publication sync. A
    /// failed final sync may leave a receipt name; callers must require success.
    pub fn finish(
        mut self,
        state: &StateInspection,
        pairing: &str,
    ) -> BackupResult<serde_json::Value> {
        self.validate()?;
        state.verify_snapshot(self.database_path())?;
        if validate_inspected_state(state)? != pairing {
            return Err("pairing report changed".into());
        }
        fault("file_sync")?;
        self.database.sync_all()?;
        let snapshot_sha256 = hash_file(&mut self.database)?;
        let executable_sha256 = hash_file(&mut File::open("/proc/self/exe")?)?;
        let receipt = serde_json::json!({"version":1,"schema_version":state.summary().schema_version,
            "application_id":0x42464d52u32,"instance_id":state.summary().instance_id,
            "retained_jobs":state.summary().retained_jobs,"pairing_state":pairing,
            "snapshot":"state.sqlite","snapshot_sha256":snapshot_sha256,
            "tool_version":env!("CARGO_PKG_VERSION"),"executable_sha256":executable_sha256,
            "qualification_build":super::nfs_qualification_enabled(),"migration_apply_enabled":false,
            "payload_filesystem_inspected":false});
        fault("receipt_write")?;
        let mut file = File::from(fs::openat(
            &self.directory,
            "receipt.next",
            OFlags::WRONLY | OFlags::CREATE | OFlags::EXCL | OFlags::NOFOLLOW | OFlags::CLOEXEC,
            Mode::from_raw_mode(0o600),
        )?);
        file.write_all(&serde_json::to_vec(&receipt)?)?;
        file.sync_all()?;
        fault("directory_sync")?;
        fs::fsync(&self.directory)?;
        self.validate()?;
        fs::renameat_with(
            &self.directory,
            "receipt.next",
            &self.directory,
            "VERIFIED.json",
            RenameFlags::NOREPLACE,
        )?;
        fault("postpublish_sync")?;
        fs::fsync(&self.directory)?;
        fs::fsync(&self.parent)?;
        Ok(receipt)
    }
}
fn hash_file(file: &mut File) -> BackupResult<String> {
    file.seek(SeekFrom::Start(0))?;
    let mut hash = Sha256::new();
    let mut buffer = [0; 65536];
    loop {
        let n = file.read(&mut buffer)?;
        if n == 0 {
            break;
        }
        hash.update(&buffer[..n]);
    }
    Ok(format!("{:x}", hash.finalize()))
}
fn fault(_stage: &str) -> BackupResult<()> {
    #[cfg(feature = "nfs-qualification")]
    if std::env::var("FILE_MOVER_QUALIFICATION_BACKUP_FAULT")
        .ok()
        .as_deref()
        == Some(_stage)
    {
        return Err(
            std::io::Error::from_raw_os_error(if _stage == "copy_enospc" { 28 } else { 5 }).into(),
        );
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::os::unix::fs::{PermissionsExt, symlink};
    static NEXT: std::sync::atomic::AtomicU64 = std::sync::atomic::AtomicU64::new(0);
    struct Fixture(std::path::PathBuf);
    impl Fixture {
        fn new() -> Self {
            let p = std::env::temp_dir().join(format!(
                "backup-{}-{}",
                std::process::id(),
                NEXT.fetch_add(1, std::sync::atomic::Ordering::Relaxed)
            ));
            std::fs::create_dir(&p).unwrap();
            std::fs::set_permissions(&p, std::fs::Permissions::from_mode(0o700)).unwrap();
            Self(p)
        }
        fn path(&self, name: &str) -> String {
            self.0.join(name).to_str().unwrap().into()
        }
    }
    impl Drop for Fixture {
        fn drop(&mut self) {
            std::fs::remove_dir_all(&self.0).unwrap();
        }
    }
    #[test]
    fn backup_refuses_existing_overlapping_and_replaced_paths() {
        let f = Fixture::new();
        let excluded = vec![f.path("payload"), f.path("state")];
        for name in ["payload", "payload/sub", "state/sub"] {
            assert!(BackupOutput::create(&f.path(name), &excluded).is_err());
            assert!(!Path::new(&f.path(name)).exists());
        }
        assert!(BackupOutput::create(f.0.to_str().unwrap(), &excluded).is_err());
        let original = f.path("original");
        std::fs::write(&original, b"preserve").unwrap();
        symlink(&original, f.path("symlink")).unwrap();
        assert!(BackupOutput::create(&f.path("symlink"), &[]).is_err());
        assert_eq!(std::fs::read(&original).unwrap(), b"preserve");
        let out = BackupOutput::create(&f.path("backup"), &excluded).unwrap();
        assert!(BackupOutput::create(&f.path("backup"), &excluded).is_err());
        std::fs::rename(out.database_path(), f.path("old")).unwrap();
        std::fs::write(out.database_path(), b"replacement").unwrap();
        assert!(out.validate().is_err());
        assert_eq!(std::fs::read(f.path("old")).unwrap(), b"");
        for path in [
            "relative",
            "/tmp//backup",
            "/tmp/../backup",
            "/tmp/./backup",
            "/tmp/backup/",
            "/tmp/backup\\bad",
        ] {
            assert!(BackupOutput::create(path, &[]).is_err());
        }
    }
    #[test]
    fn backup_verifies_before_receipt_and_records_digest_with_private_modes() {
        let f = Fixture::new();
        drop(Store::open(f.path("live.sqlite")).unwrap());
        let inspected = StateInspection::open(f.path("live.sqlite")).unwrap();
        let pairing = validate_inspected_state(&inspected).unwrap();
        let empty = BackupOutput::create(&f.path("incomplete"), &[]).unwrap();
        assert!(empty.finish(&inspected, pairing).is_err());
        assert!(!Path::new(&f.path("incomplete/VERIFIED.json")).exists());
        let out = BackupOutput::create(&f.path("backup"), &[]).unwrap();
        out.copy(&inspected).unwrap();
        assert!(!Path::new(&f.path("backup/VERIFIED.json")).exists());
        let receipt = out.finish(&inspected, pairing).unwrap();
        let mut file = File::open(f.path("backup/state.sqlite")).unwrap();
        assert_eq!(receipt["snapshot_sha256"], hash_file(&mut file).unwrap());
        for (name, mode) in [
            ("backup", 0o700),
            ("backup/state.sqlite", 0o600),
            ("backup/VERIFIED.json", 0o600),
        ] {
            assert_eq!(
                std::fs::metadata(f.path(name))
                    .unwrap()
                    .permissions()
                    .mode()
                    & 0o7777,
                mode
            );
        }
        assert_eq!(receipt["migration_apply_enabled"], false);
    }
    fn migration_fixture(f: &Fixture) {
        std::fs::create_dir(f.path("state")).unwrap();
        std::fs::set_permissions(f.path("state"), std::fs::Permissions::from_mode(0o700)).unwrap();
        let c = rusqlite::Connection::open(f.path("state/jobs.sqlite")).unwrap();
        c.execute_batch("PRAGMA journal_mode=WAL; PRAGMA foreign_keys=ON;")
            .unwrap();
        for sql in [
            include_str!("../../mover-store/src/jobs_v11.sql"),
            include_str!("../../mover-store/src/schema.sql"),
            include_str!("../../mover-store/src/claims.sql"),
            include_str!("../../mover-store/src/missing.sql"),
            include_str!("../../mover-store/src/transfers.sql"),
            include_str!("../../mover-store/src/coordination.sql"),
            include_str!("../../mover-store/src/operators.sql"),
            include_str!("../../mover-store/src/missing_resets.sql"),
            include_str!("../../mover-store/src/source_enrollment.sql"),
            include_str!("../../mover-store/src/destination_bindings.sql"),
            include_str!("../../mover-store/src/source_ownership.sql"),
            include_str!("../../mover-store/src/capacity_retries.sql"),
        ] {
            c.execute_batch(sql).unwrap();
        }
        c.execute_batch("PRAGMA application_id=1111903570; PRAGMA user_version=11;
            INSERT INTO metadata VALUES('instance_id','0123456789abcdef0123456789abcdef');
            INSERT INTO jobs VALUES(7,'g','11111111-2222-3333-4444-555555555555','/unavailable-source/current','recordings','/unavailable-source','current','archive','/unavailable-destination',0,0,300,1);
            INSERT INTO files VALUES(7,0,'Data',NULL);
            INSERT INTO reservations VALUES('recordings','current/Data',7,0);
            INSERT INTO missing VALUES(7,0,400,1);
            UPDATE sqlite_sequence SET seq=99 WHERE name='jobs';").unwrap();
        drop(c);
        std::fs::set_permissions(
            f.path("state/jobs.sqlite"),
            std::fs::Permissions::from_mode(0o600),
        )
        .unwrap();
        let binding = serde_json::json!({"version":3,"coordinator_id":"test-owner","root_id":"local-source","endpoint_id":"test-local","marker_id":"test-marker","filesystem":"local","role":"source"});
        let destination = serde_json::json!({"version":3,"coordinator_id":"test-owner","root_id":"configured-local","endpoint_id":"test-local-destination","marker_id":"test-destination-marker","filesystem":"local","role":"destination"});
        std::fs::write(f.path("config.json"),serde_json::to_vec(&serde_json::json!({"bind":"127.0.0.1:0","generator_id":"g","source_root":"/unavailable-source","source_binding":binding,"destination_binding":destination,"destination_root":"/unavailable-destination","state_database":f.path("state/jobs.sqlite")})).unwrap()).unwrap();
    }
    fn migrate_command(f: &Fixture, confirm: bool) -> std::process::Command {
        let mut c = std::process::Command::new(
            std::env::var("FILE_MOVER_TEST_EXECUTABLE").expect("audited SLES executable"),
        );
        c.args([
            "--migrate-state",
            &f.path("config.json"),
            "--backup-dir",
            &f.path("snapshot"),
        ]);
        if confirm {
            c.arg("--confirm");
        }
        c.stdout(std::process::Stdio::piped())
            .stderr(std::process::Stdio::piped());
        c
    }
    #[test]
    fn migration_cli_previews_converts_once_and_preserves_original_job_without_payload_roots() {
        let f = Fixture::new();
        migration_fixture(&f);
        let original = std::fs::read(f.path("state/jobs.sqlite")).unwrap();
        let preview = migrate_command(&f, false).output().unwrap();
        assert!(preview.status.success(), "{preview:?}");
        assert_eq!(
            std::fs::read(f.path("state/jobs.sqlite")).unwrap(),
            original
        );
        assert!(!Path::new(&f.path("snapshot")).exists());
        let result = migrate_command(&f, true)
            .env(
                "FILE_MOVER_QUALIFICATION_MIGRATION_FAULT",
                if nfs_qualification_enabled() {
                    "unused"
                } else {
                    "after_drop"
                },
            )
            .output()
            .unwrap();
        assert!(result.status.success(), "{result:?}");
        let body: serde_json::Value = serde_json::from_slice(&result.stdout).unwrap();
        assert_eq!(body["converted"], true);
        assert_eq!(body["schema_version"], 14);
        assert!(Path::new(&f.path("snapshot/VERIFIED.json")).exists());
        let s = Store::open(f.path("state/jobs.sqlite")).unwrap();
        let job = s.get(7).unwrap().unwrap();
        assert_eq!(
            job.recording.submission().submission_id(),
            "11111111-2222-3333-4444-555555555555"
        );
        assert_eq!(
            s.accept(job.recording.submission(), &job.context)
                .unwrap()
                .job_id,
            7
        );
        drop(s);
        let again = migrate_command(&f, true).output().unwrap();
        assert!(again.status.success(), "{again:?}");
        let body: serde_json::Value = serde_json::from_slice(&again.stdout).unwrap();
        assert_eq!(body["converted"], false);
        assert_eq!(body["conversion_required"], false);
        assert_eq!(
            rusqlite::Connection::open_with_flags(
                f.path("snapshot/state.sqlite"),
                rusqlite::OpenFlags::SQLITE_OPEN_READ_ONLY
            )
            .unwrap()
            .pragma_query_value::<i64, _>(None, "user_version", |r| r.get(0))
            .unwrap(),
            11
        );
    }
    #[test]
    fn migration_cli_requires_fresh_verified_backup_and_ignores_fault_controls_in_production() {
        for stage in [
            "copy",
            "copy_enospc",
            "file_sync",
            "receipt_write",
            "directory_sync",
            "postpublish_sync",
        ] {
            let f = Fixture::new();
            migration_fixture(&f);
            let out = migrate_command(&f, true)
                .env("FILE_MOVER_QUALIFICATION_BACKUP_FAULT", stage)
                .output()
                .unwrap();
            assert_eq!(
                out.status.success(),
                !nfs_qualification_enabled(),
                "{stage}: {out:?}"
            );
            assert_eq!(
                StateInspection::open(f.path("state/jobs.sqlite"))
                    .unwrap()
                    .summary()
                    .schema_version,
                if nfs_qualification_enabled() { 11 } else { 14 }
            );
            if nfs_qualification_enabled() {
                assert!(!migrate_command(&f, true).output().unwrap().status.success());
            }
        }
    }
    #[cfg(feature = "nfs-qualification")]
    #[test]
    fn migration_cli_kill_reopens_original_or_committed_state_without_restore() {
        use std::time::{Duration, Instant};
        for stage in [
            "before_create",
            "after_create",
            "after_copy",
            "after_drop",
            "after_rename",
            "after_indexes",
            "after_sequence",
            "after_validation",
            "before_commit",
            "after_commit",
        ] {
            let f = Fixture::new();
            migration_fixture(&f);
            std::fs::create_dir(f.path("rendezvous")).unwrap();
            std::fs::set_permissions(f.path("rendezvous"), std::fs::Permissions::from_mode(0o700))
                .unwrap();
            let mut child = migrate_command(&f, true)
                .env("FILE_MOVER_QUALIFICATION_PAUSE", stage)
                .env("FILE_MOVER_QUALIFICATION_RENDEZVOUS", f.path("rendezvous"))
                .spawn()
                .unwrap();
            let until = Instant::now() + Duration::from_secs(10);
            while !Path::new(&f.path("rendezvous/ready")).exists() {
                if let Some(status) = child.try_wait().unwrap() {
                    panic!("migration exited before {stage}: {status}");
                }
                if Instant::now() > until {
                    let _ = child.kill();
                    let output = child.wait_with_output().unwrap();
                    panic!("no checkpoint {stage}: {output:?}");
                }
                std::thread::sleep(Duration::from_millis(10));
            }
            assert!(
                !migrate_command(&f, true).output().unwrap().status.success(),
                "live owner at {stage}"
            );
            child.kill().unwrap();
            child.wait().unwrap();
            let recovered = StateInspection::open(f.path("state/jobs.sqlite")).unwrap();
            let version = if stage == "after_commit" { 12 } else { 11 };
            assert_eq!(recovered.summary().schema_version, version, "{stage}");
            if version == 11 {
                recovered
                    .verify_snapshot(f.path("snapshot/state.sqlite"))
                    .unwrap();
            }
            let original = rusqlite::Connection::open(f.path("snapshot/state.sqlite")).unwrap();
            let current = rusqlite::Connection::open(f.path("state/jobs.sqlite")).unwrap();
            for sql in [
                "SELECT job_id,generator_id,submission_id,source_directory,source_root_id,source_root_path,source_relative_directory,destination_id,destination_path,group_by_generator,delete_source_after_commit,missing_retry_seconds,file_count FROM jobs ORDER BY job_id",
                "SELECT * FROM files ORDER BY job_id,file_index",
                "SELECT * FROM missing ORDER BY job_id,file_index",
                "SELECT * FROM reservations ORDER BY job_id,file_index",
                "SELECT * FROM sqlite_sequence ORDER BY name",
            ] {
                fn values(c: &rusqlite::Connection, sql: &str) -> Vec<Vec<rusqlite::types::Value>> {
                    let mut s = c.prepare(sql).unwrap();
                    let n = s.column_count();
                    s.query_map([], |r| (0..n).map(|i| r.get(i)).collect())
                        .unwrap()
                        .collect::<rusqlite::Result<_>>()
                        .unwrap()
                }
                assert_eq!(
                    values(&current, sql),
                    values(&original, sql),
                    "{stage} {sql}"
                );
            }
            drop(current);
            drop(original);
            drop(recovered);
            // The same backup directory is never reused: an interrupted 11->12
            // step needs a fresh backup, and so do the remaining 12->13->14 steps.
            let retry = migrate_command(&f, true).output().unwrap();
            assert!(
                !retry.status.success(),
                "same output cannot be reused: {retry:?}"
            );
        }
    }
}
