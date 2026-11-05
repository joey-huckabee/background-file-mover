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
    pub fn create(path: &str, excluded: &[String]) -> BackupResult<Self> {
        let p = canonical(path)?;
        for root in excluded {
            let root = canonical(root)?;
            if p.starts_with(root) || root.starts_with(p) {
                return Err("backup overlaps state or payload scope".into());
            }
        }
        instance::backup_local(p)?;
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
            if !suffix.is_empty()
                && fs::statat(
                    &current_dir,
                    format!("state.sqlite{suffix}").as_str(),
                    AtFlags::SYMLINK_NOFOLLOW,
                )
                .is_ok()
            {
                return Err("unexpected snapshot sidecar".into());
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
}
