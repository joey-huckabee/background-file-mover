//! Provisioned source identity; observations are strict session/restart pins,
//! not authenticated server identity or a distributed worker fence.
use super::{
    ClaimError, FILE, LocalClaimLock, Result, namespace, observation, owned_directory, root,
};
use rustix::fs::{self, FileType, Mode};
use serde::{Deserialize, Serialize};
use std::io::Read;

pub const SOURCE_MARKER: &str = "source-binding.json";
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum SourceFilesystem {
    Local,
    Nfs,
}
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum SourceRole {
    Source,
}
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct SourceBinding {
    pub version: u32,
    pub coordinator_id: String,
    pub root_id: String,
    pub endpoint_id: String,
    pub marker_id: String,
    pub filesystem: SourceFilesystem,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub nfs_mount: Option<super::NfsMountProfile>,
    pub role: SourceRole,
}
impl SourceBinding {
    pub fn validate(&self) -> Result<()> {
        if self.version != 3
            || [
                &self.coordinator_id,
                &self.root_id,
                &self.endpoint_id,
                &self.marker_id,
            ]
            .iter()
            .any(|id| {
                id.is_empty()
                    || id.len() > 128
                    || id.as_str() == "."
                    || id.as_str() == ".."
                    || !id
                        .bytes()
                        .all(|b| b.is_ascii_alphanumeric() || b"-_.".contains(&b))
            })
        {
            return Err(ClaimError::Blocked("invalid source binding"));
        }
        super::mount_profile::declaration(&self.filesystem, self.nfs_mount.as_ref())
    }
    pub fn encode(&self) -> String {
        serde_json::to_string(self).expect("source binding serialization")
    }
}
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct SourceAuthorization {
    pub binding: SourceBinding,
    pub observation: String,
    #[serde(default)]
    pub enrollment: Option<super::EnrollmentAuthorization>,
}
impl SourceAuthorization {
    pub fn validate(&self, path: &str) -> Result<()> {
        if self.observation.len() > 2048 || observe(path, &self.binding)? != self.observation {
            return Err(ClaimError::Blocked("source binding observation changed"));
        }
        if let Some(enrollment) = &self.enrollment {
            enrollment.validate(path, self)?;
        }
        Ok(())
    }
}
fn observe(path: &str, expected: &SourceBinding) -> Result<String> {
    expected.validate()?;
    observe_marker(
        path,
        expected,
        &expected.filesystem,
        expected.nfs_mount.as_ref(),
        SOURCE_MARKER,
    )
}
fn observe_marker<T: serde::de::DeserializeOwned + PartialEq>(
    path: &str,
    expected: &T,
    expected_filesystem: &SourceFilesystem,
    profile: Option<&super::NfsMountProfile>,
    marker_name: &str,
) -> Result<String> {
    super::mount_profile::declaration(expected_filesystem, profile)?;
    let mount = profile.map(|p| p.observe(path)).transpose()?;
    let root = root(path)?;
    if let Some(mount) = &mount {
        mount.validate_descriptor(&root)?;
    }
    let filesystem = fs::fstatfs(&root)?.f_type;
    if (filesystem == 0x6969) != (*expected_filesystem == SourceFilesystem::Nfs) {
        return Err(ClaimError::Blocked("endpoint filesystem binding mismatch"));
    }
    let area = namespace(&root)?;
    let marker = fs::openat(&area, marker_name, FILE, Mode::empty())?;
    let before = fs::fstat(&marker)?;
    if FileType::from_raw_mode(before.st_mode) != FileType::RegularFile
        || before.st_size <= 0
        || before.st_size > 4096
        || before.st_uid != rustix::process::geteuid().as_raw()
        || ![0o400, 0o600].contains(&(before.st_mode & 0o7777))
        || before.st_nlink != 1
        || before.st_dev != fs::fstat(&root)?.st_dev
    {
        return Err(ClaimError::Blocked(
            "invalid endpoint binding marker custody",
        ));
    }
    let mut marker = std::fs::File::from(marker);
    let mut bytes = Vec::new();
    marker
        .by_ref()
        .take(4097)
        .read_to_end(&mut bytes)
        .map_err(|_| ClaimError::Blocked("endpoint marker read"))?;
    let actual: T = serde_json::from_slice(&bytes)
        .map_err(|_| ClaimError::Blocked("invalid endpoint binding marker"))?;
    let after = fs::fstat(&marker)?;
    let named = fs::statat(&area, marker_name, fs::AtFlags::SYMLINK_NOFOLLOW)?;
    if &actual != expected
        || observation(&after) != observation(&before)
        || after.st_mode != before.st_mode
        || observation(&named) != observation(&after)
        || named.st_mode != after.st_mode
    {
        return Err(ClaimError::Blocked("endpoint marker binding mismatch"));
    }
    let r = owned_directory(&root, false)?;
    let n = owned_directory(&area, true)?;
    let mut result = format!(
        "3:{}:{}:{}:{}:{}:{}:{}:{}:{}:{}",
        filesystem,
        fs::fstatvfs(&root)?.f_fsid,
        r.device,
        r.inode,
        r.uid,
        n.device,
        n.inode,
        n.uid,
        observation(&before).encode(),
        super::custody::named_identity(&area)?.encode()
    );
    if let Some(before) = &mount {
        before.validate_descriptor(&root)?;
        if Some(
            profile
                .ok_or(ClaimError::Blocked("missing mount declaration"))?
                .observe(path)?,
        ) != mount
        {
            return Err(ClaimError::Blocked(
                "NFS mount changed during authorization",
            ));
        }
    }
    if let Some(mount) = mount {
        result.push_str(&format!(":nmp:{}", mount.pin));
    }
    Ok(result)
}
impl LocalClaimLock {
    pub fn acquire_bound(path: &str, binding: &SourceBinding) -> Result<Self> {
        // Validate before and after acquiring custody; never create a marker.
        let before = observe(path, binding)?;
        let mut lock = Self::acquire(path)?;
        let authorization = SourceAuthorization {
            binding: binding.clone(),
            observation: before,
            enrollment: None,
        };
        authorization.validate(path)?;
        lock.authorization = Some(authorization);
        lock.validate()?;
        Ok(lock)
    }
    pub fn source_authorization(&self) -> Option<&SourceAuthorization> {
        self.authorization.as_ref()
    }
}

pub const DESTINATION_MARKER: &str = "destination-binding.json";
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum DestinationRole {
    Destination,
}
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct DestinationBinding {
    pub version: u32,
    pub coordinator_id: String,
    pub root_id: String,
    pub endpoint_id: String,
    pub marker_id: String,
    pub filesystem: SourceFilesystem,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub nfs_mount: Option<super::NfsMountProfile>,
    pub role: DestinationRole,
}
impl DestinationBinding {
    /// Only an absent root/namespace is retryable; an observable wrong filesystem
    /// is a binding refusal even when its namespace has not been provisioned.
    pub fn unavailable(&self, path: &str) -> Result<bool> {
        self.validate()?;
        if let Some(profile) = &self.nfs_mount {
            profile.observe(path)?;
        }
        let result = (|| {
            let root = root(path)?;
            if (fs::fstatfs(&root)?.f_type == 0x6969) != (self.filesystem == SourceFilesystem::Nfs)
            {
                return Err(ClaimError::Blocked(
                    "destination filesystem binding mismatch",
                ));
            }
            namespace(&root).map(|_| ())
        })();
        match result {
            Ok(()) => Ok(false),
            Err(ClaimError::Io(rustix::io::Errno::NOENT)) => Ok(true),
            Err(e) => Err(e),
        }
    }
    pub fn validate(&self) -> Result<()> {
        SourceBinding {
            version: self.version,
            coordinator_id: self.coordinator_id.clone(),
            root_id: self.root_id.clone(),
            endpoint_id: self.endpoint_id.clone(),
            marker_id: self.marker_id.clone(),
            filesystem: self.filesystem.clone(),
            nfs_mount: self.nfs_mount.clone(),
            role: SourceRole::Source,
        }
        .validate()
    }
    pub fn encode(&self) -> String {
        serde_json::to_string(self).expect("destination binding serialization")
    }
}
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct DestinationAuthorization {
    pub binding: DestinationBinding,
    pub observation: String,
}
impl DestinationAuthorization {
    /// Observe provisioned custody without allocating or modifying storage.
    pub fn observe(path: &str, binding: &DestinationBinding) -> Result<Self> {
        binding.validate()?;
        Ok(Self {
            binding: binding.clone(),
            observation: observe_marker(
                path,
                binding,
                &binding.filesystem,
                binding.nfs_mount.as_ref(),
                DESTINATION_MARKER,
            )?,
        })
    }
    pub fn validate(&self, path: &str) -> Result<()> {
        self.binding.validate()?;
        if self.observation.len() > 2048
            || observe_marker(
                path,
                &self.binding,
                &self.binding.filesystem,
                self.binding.nfs_mount.as_ref(),
                DESTINATION_MARKER,
            )? != self.observation
        {
            return Err(ClaimError::Blocked(
                "destination binding observation changed",
            ));
        }
        Ok(())
    }
}
impl LocalClaimLock {
    pub fn acquire_destination(
        path: &str,
        binding: &DestinationBinding,
        expected: Option<&str>,
    ) -> Result<Self> {
        binding.validate()?;
        let observation = observe_marker(
            path,
            binding,
            &binding.filesystem,
            binding.nfs_mount.as_ref(),
            DESTINATION_MARKER,
        )?;
        if expected.is_some_and(|pin| pin != observation) {
            return Err(ClaimError::Blocked(
                "destination binding observation changed",
            ));
        }
        let mut lock = Self::acquire(path)?;
        lock.destination_authorization = Some(DestinationAuthorization {
            binding: binding.clone(),
            observation,
        });
        lock.validate()?;
        Ok(lock)
    }
    pub fn destination_authorization(&self) -> Option<&DestinationAuthorization> {
        self.destination_authorization.as_ref()
    }
}
