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
    pub role: SourceRole,
}
impl SourceBinding {
    pub fn validate(&self) -> Result<()> {
        if self.version != 1
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
        Ok(())
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
}
impl SourceAuthorization {
    pub fn validate(&self, path: &str) -> Result<()> {
        if self.observation.len() > 2048 || observe(path, &self.binding)? != self.observation {
            return Err(ClaimError::Blocked("source binding observation changed"));
        }
        Ok(())
    }
}
fn observe(path: &str, expected: &SourceBinding) -> Result<String> {
    expected.validate()?;
    let root = root(path)?;
    let filesystem = fs::fstatfs(&root)?.f_type;
    if (filesystem == 0x6969) != (expected.filesystem == SourceFilesystem::Nfs) {
        return Err(ClaimError::Blocked("source filesystem binding mismatch"));
    }
    let area = namespace(&root)?;
    let marker = fs::openat(&area, SOURCE_MARKER, FILE, Mode::empty())?;
    let before = fs::fstat(&marker)?;
    if FileType::from_raw_mode(before.st_mode) != FileType::RegularFile
        || before.st_size <= 0
        || before.st_size > 4096
        || before.st_uid != rustix::process::geteuid().as_raw()
        || ![0o400, 0o600].contains(&(before.st_mode & 0o7777))
        || before.st_nlink != 1
        || before.st_dev != fs::fstat(&root)?.st_dev
    {
        return Err(ClaimError::Blocked("invalid source binding marker custody"));
    }
    let mut marker = std::fs::File::from(marker);
    let mut bytes = Vec::new();
    marker
        .by_ref()
        .take(4097)
        .read_to_end(&mut bytes)
        .map_err(|_| ClaimError::Blocked("source marker read"))?;
    let actual: SourceBinding = serde_json::from_slice(&bytes)
        .map_err(|_| ClaimError::Blocked("invalid source binding marker"))?;
    let after = fs::fstat(&marker)?;
    let named = fs::statat(&area, SOURCE_MARKER, fs::AtFlags::SYMLINK_NOFOLLOW)?;
    if &actual != expected
        || observation(&after) != observation(&before)
        || after.st_mode != before.st_mode
        || observation(&named) != observation(&after)
        || named.st_mode != after.st_mode
    {
        return Err(ClaimError::Blocked("source marker binding mismatch"));
    }
    let r = owned_directory(&root, false)?;
    let n = owned_directory(&area, true)?;
    Ok(format!(
        "1:{}:{}:{}:{}:{}:{}:{}:{}:{}",
        filesystem,
        fs::fstatvfs(&root)?.f_fsid,
        r.device,
        r.inode,
        r.uid,
        n.device,
        n.inode,
        n.uid,
        observation(&before).encode()
    ))
}
impl LocalClaimLock {
    pub fn acquire_bound(path: &str, binding: &SourceBinding) -> Result<Self> {
        // Validate before and after acquiring custody; never create a marker.
        let before = observe(path, binding)?;
        let mut lock = Self::acquire(path)?;
        let authorization = SourceAuthorization {
            binding: binding.clone(),
            observation: before,
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
