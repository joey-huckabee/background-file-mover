//! Versioned observations bound to a protected local claim namespace.
//! Numeric identities alone are never authorization to adopt foreign files.

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ObjectIdentity {
    pub device: u64,
    pub inode: u64,
    pub uid: u32,
    pub size: u64,
    pub modified_seconds: i64,
    pub modified_nanos: u64,
    pub links: u64,
}

impl ObjectIdentity {
    pub fn encode(&self) -> String {
        format!(
            "1:{}:{}:{}:{}:{}:{}:{}",
            self.device,
            self.inode,
            self.uid,
            self.size,
            self.modified_seconds,
            self.modified_nanos,
            self.links
        )
    }
    pub fn decode(value: &str) -> Option<Self> {
        let parts: Vec<_> = value.split(':').collect();
        if parts.len() != 8 || parts[0] != "1" {
            return None;
        }
        let result = Self {
            device: parts[1].parse().ok()?,
            inode: parts[2].parse().ok()?,
            uid: parts[3].parse().ok()?,
            size: parts[4].parse().ok()?,
            modified_seconds: parts[5].parse().ok()?,
            modified_nanos: parts[6].parse().ok()?,
            links: parts[7].parse().ok()?,
        };
        (result.modified_nanos < 1_000_000_000 && result.encode() == value).then_some(result)
    }
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ClaimIntent {
    pub job_id: i64,
    pub file_index: usize,
    pub root_path: String,
    pub source_name: String,
    /// Exclusive directory below the administrator-provisioned .file-mover.
    pub private_name: String,
    pub root: ObjectIdentity,
    pub parent: ObjectIdentity,
    pub area: ObjectIdentity,
    pub source: ObjectIdentity,
}
