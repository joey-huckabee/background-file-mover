use crate::ObjectIdentity;

#[derive(Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord)]
pub enum TransferPhase {
    Intent = 0,
    Copied = 1,
    Verified = 2,
    PublishIntent = 3,
    Published = 4,
}
impl TransferPhase {
    pub fn decode(value: i64) -> Option<Self> {
        match value {
            0 => Some(Self::Intent),
            1 => Some(Self::Copied),
            2 => Some(Self::Verified),
            3 => Some(Self::PublishIntent),
            4 => Some(Self::Published),
            _ => None,
        }
    }
}
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Transfer {
    pub job_id: i64,
    pub file_index: usize,
    pub attempt: i64,
    pub destination_root: String,
    pub relative_name: String,
    pub root: ObjectIdentity,
    pub area: ObjectIdentity,
    pub parent: ObjectIdentity,
    pub staging_directory: ObjectIdentity,
    pub stage: ObjectIdentity,
    pub sha256: Option<String>,
    pub phase: TransferPhase,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ManifestRecord {
    pub job_id: i64,
    pub bytes: String,
    pub sha256: String,
    /// Intent, allocated, written, publication intent, committed.
    pub phase: i64,
    pub object: Option<ObjectIdentity>,
}
