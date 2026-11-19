//! Exact verification of a delivered (committed) recording before move mode
//! removes the held source copies (docs/MOVE-MODE-DESIGN.md, step 4). Runs in
//! the supervised delivery worker under destination custody. No hash pass:
//! permissions and retention keep verified objects unchanged; size, mtime and
//! link count detect truncation or rewriting through the same inode.
use super::destination_discard::{final_name, final_parent, open_directory, open_existing};
use super::*;
use mover_core::{ManifestRecord, Transfer, TransferPhase};
use sha2::{Digest, Sha256};

const CHANGED: &str = "delivered recording changed; source kept";

/// Root and private job folder of a committed recording, identity-checked.
fn job_folder(t: &Transfer) -> Result<OwnedFd> {
    let root = root(&t.destination_root)?;
    same_directory(&owned_directory(&root, false)?, &t.root)?;
    let area =
        open_directory(&root, &t.recording_directory)?.ok_or(ClaimError::Blocked(CHANGED))?;
    same_directory(&owned_directory(&area, true)?, &t.area)?;
    Ok(area)
}

/// `COMMITTED.json` is exactly the persisted manifest: the recorded object
/// (device, inode, uid, size, mtime, single link) and the persisted bytes,
/// whose SHA-256 matches the stored digest; strictly parsed. Returns the
/// required set: every listed path, in file order (`files[i].file_id == i`),
/// so the caller can demand each one before any source effect.
pub fn verify_committed_manifest(anchor: &Transfer, m: &ManifestRecord) -> Result<Vec<String>> {
    if m.phase != 4
        || m.job_id != anchor.job_id
        || anchor.file_index != 0
        || m.bytes.len() > 131072
        || format!("{:x}", Sha256::digest(m.bytes.as_bytes())) != m.sha256
    {
        return Err(ClaimError::Blocked("invalid committed manifest record"));
    }
    let area = job_folder(anchor)?;
    let fd = open_existing(&area, "COMMITTED.json")?.ok_or(ClaimError::Blocked(CHANGED))?;
    let mut file = std::fs::File::from(fd);
    super::manifest::read_exact_manifest(&mut file, m).map_err(|_| ClaimError::Blocked(CHANGED))?;
    manifest_paths(m)
}

/// The listed paths of a (verified) manifest, in file order.
fn manifest_paths(m: &ManifestRecord) -> Result<Vec<String>> {
    let invalid = || ClaimError::Blocked("invalid committed manifest record");
    let value: serde_json::Value = serde_json::from_str(&m.bytes).map_err(|_| invalid())?;
    let files = value["files"]
        .as_array()
        .filter(|f| !f.is_empty() && f.len() <= 256)
        .ok_or_else(invalid)?;
    let mut paths = Vec::with_capacity(files.len());
    for (i, f) in files.iter().enumerate() {
        let id = match &f["file_id"] {
            serde_json::Value::String(s) => s.parse::<usize>().ok(),
            serde_json::Value::Number(n) => n.as_u64().and_then(|n| usize::try_from(n).ok()),
            _ => None,
        };
        let path = f["path"].as_str().filter(|p| !p.is_empty());
        match (id, path) {
            (Some(id), Some(path)) if id == i => paths.push(path.to_owned()),
            _ => return Err(invalid()),
        }
    }
    Ok(paths)
}

/// One listed file is exactly its recorded published object at its final
/// name: regular, owned, not group/other-writable, a single link, and the
/// recorded size and mtime (the check manifest commitment applies).
pub fn verify_published_exact(p: &Transfer) -> Result<()> {
    if p.phase != TransferPhase::Published {
        return Err(ClaimError::Blocked("file not published"));
    }
    let area = job_folder(p)?;
    let parent = final_parent(&area, p)?.ok_or(ClaimError::Blocked(CHANGED))?;
    let fd = open_existing(&parent, final_name(p))?.ok_or(ClaimError::Blocked(CHANGED))?;
    if source(&fd).map_err(|_| ClaimError::Blocked(CHANGED))? != p.stage {
        return Err(ClaimError::Blocked(CHANGED));
    }
    Ok(())
}
