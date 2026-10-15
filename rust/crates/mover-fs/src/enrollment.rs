//! Persistent original-state pairing; neither export authentication nor fencing.
use super::*;
use serde::{Deserialize, Serialize};
use std::io::{Read, Write};

pub const SOURCE_RECEIPT: &str = "source-enrollment.json";

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct EnrollmentReceipt {
    pub version: u32,
    pub operation_id: String,
    pub state_instance_id: String,
    pub binding: SourceBinding,
    pub observation: String,
}
impl EnrollmentReceipt {
    pub fn new(instance: String, authorization: &SourceAuthorization) -> Self {
        Self {
            version: 1,
            operation_id: format!("{instance}-source-1"),
            state_instance_id: instance,
            binding: authorization.binding.clone(),
            observation: authorization.observation.clone(),
        }
    }
    pub fn encode(&self) -> String {
        serde_json::to_string(self).expect("enrollment serialization")
    }
    pub fn validate(&self, authorization: &SourceAuthorization) -> Result<()> {
        self.binding.validate()?;
        if self.version != 1
            || self.state_instance_id.len() != 32
            || !self
                .state_instance_id
                .bytes()
                .all(|b| b.is_ascii_hexdigit())
            || self.operation_id != format!("{}-source-1", self.state_instance_id)
            || self.binding != authorization.binding
            || self.observation != authorization.observation
        {
            return Err(ClaimError::Blocked("invalid source enrollment receipt"));
        }
        Ok(())
    }
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct EnrollmentAuthorization {
    pub receipt: String,
    pub object: String,
}

fn checked(area: &OwnedFd, fd: &impl rustix::fd::AsFd) -> Result<ObjectIdentity> {
    let stat = fs::fstat(fd)?;
    if FileType::from_raw_mode(stat.st_mode) != FileType::RegularFile
        || stat.st_size <= 0
        || stat.st_size > 8192
        || stat.st_uid != rustix::process::geteuid().as_raw()
        || stat.st_nlink != 1
        || stat.st_mode & 0o7777 != 0o400
        || stat.st_dev != fs::fstat(area)?.st_dev
    {
        return Err(ClaimError::Blocked("invalid source enrollment custody"));
    }
    Ok(observation(&stat))
}

impl EnrollmentAuthorization {
    pub fn validate(&self, path: &str, source: &SourceAuthorization) -> Result<()> {
        if self.receipt.len() > 8192 {
            return Err(ClaimError::Blocked("source enrollment too large"));
        }
        let receipt: EnrollmentReceipt = serde_json::from_str(&self.receipt)
            .map_err(|_| ClaimError::Blocked("invalid source enrollment"))?;
        receipt.validate(source)?;
        let area = namespace(&root(path)?)?;
        let mut file = std::fs::File::from(fs::openat(&area, SOURCE_RECEIPT, FILE, Mode::empty())?);
        let before = checked(&area, &file)?;
        let mut bytes = Vec::new();
        Read::by_ref(&mut file)
            .take(8193)
            .read_to_end(&mut bytes)
            .map_err(|_| ClaimError::Blocked("source enrollment read"))?;
        let named = fs::statat(&area, SOURCE_RECEIPT, AtFlags::SYMLINK_NOFOLLOW)?;
        if before.encode() != self.object
            || checked(&area, &file)? != before
            || observation(&named) != before
            || named.st_mode & 0o7777 != 0o400
            || bytes != self.receipt.as_bytes()
        {
            return Err(ClaimError::Blocked("source enrollment changed"));
        }
        Ok(())
    }
}

/// Only a new, explicitly provisioned protected namespace is eligible. A receipt
/// surviving uncertain creation is deliberately not adopted, even with equal bytes.
pub fn create_source_enrollment(
    path: &str,
    source: &SourceAuthorization,
    receipt: &str,
) -> Result<EnrollmentAuthorization> {
    source.validate(path)?;
    let decoded: EnrollmentReceipt = serde_json::from_str(receipt)
        .map_err(|_| ClaimError::Blocked("invalid source enrollment"))?;
    decoded.validate(source)?;
    if receipt.len() > 8192 {
        return Err(ClaimError::Blocked("source enrollment too large"));
    }
    let area = namespace(&root(path)?)?;
    for entry in fs::Dir::read_from(&area)? {
        let entry = entry?;
        if ![
            b".".as_slice(),
            b"..",
            SOURCE_MARKER.as_bytes(),
            COORDINATOR_LOCK.as_bytes(),
        ]
        .contains(&entry.file_name().to_bytes())
        {
            return Err(ClaimError::Blocked("source namespace is not unused"));
        }
    }
    let fd = fs::openat(
        &area,
        SOURCE_RECEIPT,
        OFlags::WRONLY | OFlags::CREATE | OFlags::EXCL | OFlags::NOFOLLOW | OFlags::CLOEXEC,
        Mode::RUSR | Mode::WUSR,
    )?;
    let mut file = std::fs::File::from(fd);
    qualification_pause("enrollment_created")?;
    file.write_all(receipt.as_bytes())
        .map_err(|_| ClaimError::Blocked("source enrollment write uncertain"))?;
    fs::fchmod(&file, Mode::RUSR)?;
    qualification_pause("enrollment_sync")?;
    fs::fsync(&file)?;
    fs::fsync(&area)?;
    qualification_pause("enrollment_receipt")?;
    let authorization = EnrollmentAuthorization {
        receipt: receipt.into(),
        object: checked(&area, &file)?.encode(),
    };
    source.validate(path)?;
    authorization.validate(path, source)?;
    Ok(authorization)
}

impl LocalClaimLock {
    /// Pure attachment after a supervised validation; performs no root I/O.
    pub fn attach_enrollment(&mut self, authorization: EnrollmentAuthorization) -> Result<()> {
        let source = self
            .authorization
            .as_mut()
            .ok_or(ClaimError::Blocked("source authorization missing"))?;
        source.enrollment = Some(authorization);
        Ok(())
    }
}
