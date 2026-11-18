//! Confirmed deletion of unfinished destination data
//! (docs/dashboard/DESTINATION-DELETION-DESIGN.md). Runs in the supervised
//! delivery worker under destination custody; never follows symlinks, never
//! touches `COMMITTED.json`, and only unlinks a name after the object behind it
//! was matched to the record (device, inode, uid). Like source discard, the
//! post-unlink link count is a check under the trusted private-namespace
//! assumption, not protection against a racing same-uid name swap.
use super::*;
use mover_core::{ManifestRecord, Transfer};

const COMMITTED: &str = "COMMITTED.json";
const MANIFEST_STAGING: &str = "COMMITTED.part";

/// Which records authorize the deletion.
pub enum DestinationTarget<'a> {
    /// A cancelled job's attempt `.part` (phase 0-2).
    Staging(&'a Transfer),
    /// A cancelled job's attempt moved into place (phase 3-4): final name and
    /// possibly the staging alias.
    Payload(&'a Transfer),
    /// A cancelled job's manifest staging.
    Manifest(&'a ManifestRecord),
    /// A delivered job's superseded attempt; `published` is the (device,
    /// inode) of every file's published final, each verified by
    /// [`published_identity`] in this custody session just before.
    Superseded {
        transfer: &'a Transfer,
        published: &'a [(u64, u64)],
    },
}

fn op(label: &'static str) -> impl Fn(Errno) -> ClaimError {
    move |e| ClaimError::Operation(label, e)
}

fn same_object(fd: &OwnedFd, expected: &ObjectIdentity) -> Result<()> {
    let s = fs::fstat(fd).map_err(op("destination_discard.stat"))?;
    if FileType::from_raw_mode(s.st_mode) != FileType::RegularFile
        || s.st_dev != expected.device
        || s.st_ino != expected.inode
        || s.st_uid != expected.uid
    {
        return Err(ClaimError::Blocked(
            "destination object changed; not deleted",
        ));
    }
    Ok(())
}

/// Open an existing name, or `None` when absent.
fn open_existing(dir: &OwnedFd, name: &str) -> Result<Option<OwnedFd>> {
    match fs::openat(dir, name, FILE, Mode::empty()) {
        Ok(fd) => Ok(Some(fd)),
        Err(Errno::NOENT) => Ok(None),
        Err(e) => Err(ClaimError::Operation("destination_discard.open", e)),
    }
}

fn open_directory(dir: &OwnedFd, name: &str) -> Result<Option<OwnedFd>> {
    match fs::openat(dir, name, DIRECTORY, Mode::empty()) {
        Ok(fd) => Ok(Some(fd)),
        Err(Errno::NOENT) => Ok(None),
        Err(e) => Err(ClaimError::Operation(
            "destination_discard.open_directory",
            e,
        )),
    }
}

/// Walk exactly the recorded relative name's folders from the area. Each is
/// owner-only and owned by this uid; the walk must end at the recorded
/// parent. Returns (parent fd, name, fd) per folder, or `None` if a folder is
/// absent (the chain can then not be authenticated).
type Chain = Vec<(OwnedFd, String, OwnedFd)>;
fn ancestors(area: &OwnedFd, t: &Transfer) -> Result<Option<Chain>> {
    let components: Vec<&str> = t.relative_name.split('/').collect();
    let mut chain = Chain::new();
    let mut current = rustix::io::dup(area).map_err(op("destination_discard.dup"))?;
    for component in &components[..components.len() - 1] {
        let Some(next) = open_directory(&current, component)? else {
            return Ok(None);
        };
        owned_directory(&next, true)?;
        let parent = rustix::io::dup(&next).map_err(op("destination_discard.dup"))?;
        chain.push((current, (*component).to_owned(), next));
        current = parent;
    }
    same_directory(&owned_directory(&current, true)?, &t.parent)?;
    Ok(Some(chain))
}

/// The final name's parent folder (the area itself for a top-level name).
fn final_parent(area: &OwnedFd, t: &Transfer) -> Result<Option<OwnedFd>> {
    match ancestors(area, t)? {
        None => Ok(None),
        Some(chain) => match chain.into_iter().last() {
            Some((_, _, fd)) => Ok(Some(fd)),
            None => {
                let fd = rustix::io::dup(area).map_err(op("destination_discard.dup"))?;
                same_directory(&owned_directory(&fd, true)?, &t.parent)?;
                Ok(Some(fd))
            }
        },
    }
}

fn final_name(t: &Transfer) -> &str {
    t.relative_name.rsplit('/').next().unwrap_or_default()
}

/// Remove an empty folder; a non-empty or absent one stays (Ok(false)).
fn remove_if_empty(parent: &OwnedFd, name: &str) -> Result<bool> {
    match fs::unlinkat(parent, name, AtFlags::REMOVEDIR) {
        Ok(()) => {
            fs::fsync(parent).map_err(op("destination_discard.sync_folder"))?;
            Ok(true)
        }
        Err(Errno::NOTEMPTY | Errno::EXIST | Errno::NOENT) => Ok(false),
        Err(e) => Err(ClaimError::Operation(
            "destination_discard.remove_folder",
            e,
        )),
    }
}

/// Unlink the recorded names behind one already-matched object, then require
/// the object to be gone (`nlink == 0`).
fn unlink_names(names: &[(&OwnedFd, &str)], object: &OwnedFd) -> Result<()> {
    for (i, (dir, name)) in names.iter().enumerate() {
        if i > 0 {
            // Qualification fault point between the two names of a payload.
            super::qualification_pause("destination_discard_between_names")?;
        }
        fs::unlinkat(*dir, *name, AtFlags::empty()).map_err(op("destination_discard.unlink"))?;
    }
    let links = fs::fstat(object)
        .map_err(op("destination_discard.verify"))?
        .st_nlink;
    if links != 0 {
        return Err(ClaimError::Blocked(
            "removed names were not the recorded object",
        ));
    }
    for (dir, _) in names {
        fs::fsync(*dir).map_err(op("destination_discard.sync"))?;
    }
    Ok(())
}

/// Delete one destination target. `anchor` is file 0's latest attempt (its
/// staging directory is `.staging`, its area the job's recording folder).
pub fn discard_unfinished_destination(
    target: DestinationTarget<'_>,
    anchor: &Transfer,
) -> Result<Discarded> {
    let delivered = matches!(target, DestinationTarget::Superseded { .. });
    let t = match &target {
        DestinationTarget::Staging(t) | DestinationTarget::Payload(t) => *t,
        DestinationTarget::Superseded { transfer, .. } => *transfer,
        DestinationTarget::Manifest(_) => anchor,
    };
    // Same job folder: identity is device, inode and owner (a folder's size
    // and times change as files are added).
    if t.job_id != anchor.job_id
        || t.recording_directory != anchor.recording_directory
        || t.destination_root != anchor.destination_root
        || same_directory(&t.area, &anchor.area).is_err()
        || same_directory(&t.root, &anchor.root).is_err()
    {
        return Err(ClaimError::Blocked("destination target scope changed"));
    }
    let root = root(&t.destination_root)?;
    same_directory(&owned_directory(&root, false)?, &t.root)?;
    let Some(area) = open_directory(&root, &t.recording_directory)? else {
        if delivered {
            return Err(ClaimError::Blocked(
                "delivered recording missing; nothing deleted",
            ));
        }
        fs::fsync(&root).map_err(op("destination_discard.sync_root"))?;
        return Ok(Discarded::AlreadyAbsent);
    };
    same_directory(&owned_directory(&area, true)?, &t.area)?;
    let committed = match fs::statat(&area, COMMITTED, AtFlags::SYMLINK_NOFOLLOW) {
        Ok(_) => true,
        Err(Errno::NOENT) => false,
        Err(e) => {
            return Err(ClaimError::Operation(
                "destination_discard.manifest_check",
                e,
            ));
        }
    };
    if committed != delivered {
        return Err(ClaimError::Blocked(if delivered {
            "delivered recording has no committed manifest; nothing deleted"
        } else {
            "committed manifest present; nothing deleted"
        }));
    }
    let staging_root = open_directory(&area, ".staging")?;
    if let Some(s) = &staging_root {
        same_directory(&owned_directory(s, true)?, &anchor.staging_directory)?;
    }
    // The attempt's own staging folder (`.staging` or `.staging/<index>`).
    let staging = match (&staging_root, t.file_index) {
        (None, _) => None,
        (Some(s), 0) => Some(rustix::io::dup(s).map_err(op("destination_discard.dup"))?),
        (Some(s), index) => match open_directory(s, &index.to_string())? {
            None => None,
            Some(d) => {
                same_directory(&owned_directory(&d, true)?, &t.staging_directory)?;
                Some(d)
            }
        },
    };
    let part = format!("{}.part", t.attempt);
    // Where a missing staging folder is absent.
    let container = staging_root.as_ref().unwrap_or(&area);
    let outcome = match &target {
        DestinationTarget::Staging(t) => single(staging.as_ref(), container, &part, &t.stage)?,
        DestinationTarget::Manifest(m) => {
            let object = m.object.as_ref().ok_or(ClaimError::Blocked(
                "manifest staging has no recorded object",
            ))?;
            single(staging_root.as_ref(), &area, MANIFEST_STAGING, object)?
        }
        DestinationTarget::Superseded {
            transfer,
            published,
        } => {
            let staging = staging.as_ref();
            // Every published final must be verifiable, and the target must be
            // none of them, before anything is unlinked.
            let candidate = match staging {
                Some(d) => open_existing(d, &part)?,
                None => None,
            };
            if published.is_empty() {
                return Err(ClaimError::Blocked("published files not verified"));
            }
            if let Some(fd) = &candidate {
                same_object(fd, &transfer.stage)?;
                let s = fs::fstat(fd).map_err(op("destination_discard.stat"))?;
                if published.contains(&(s.st_dev, s.st_ino)) {
                    return Err(ClaimError::Blocked(
                        "target is a published file; not deleted",
                    ));
                }
            }
            single(staging, container, &part, &transfer.stage)?
        }
        DestinationTarget::Payload(t) => {
            let parent = final_parent(&area, t)?;
            let final_fd = match &parent {
                Some(p) => open_existing(p, final_name(t))?,
                None => None,
            };
            let alias_fd = match &staging {
                Some(s) => open_existing(s, &part)?,
                None => None,
            };
            // Both names must be the recorded object before either is unlinked.
            for fd in final_fd.iter().chain(alias_fd.iter()) {
                same_object(fd, &t.stage)?;
            }
            let mut names: Vec<(&OwnedFd, &str)> = Vec::new();
            if let (Some(p), Some(_)) = (&parent, &final_fd) {
                names.push((p, final_name(t)));
            }
            if let (Some(s), Some(_)) = (&staging, &alias_fd) {
                names.push((s, part.as_str()));
            }
            let outcome = match final_fd.as_ref().or(alias_fd.as_ref()) {
                Some(object) => {
                    unlink_names(&names, object)?;
                    Discarded::Removed
                }
                None => Discarded::AlreadyAbsent,
            };
            // Both names' folders are synced whichever name was still there:
            // a rerun after an interrupted first unlink must make that earlier
            // removal durable too (and the absence of removed folders).
            for dir in parent
                .iter()
                .chain(staging.iter())
                .chain([&area, container])
            {
                fs::fsync(dir).map_err(op("destination_discard.sync"))?;
            }
            outcome
        }
    };
    // Folders: the attempt's staging subfolder and `.staging` when empty; on a
    // cancelled job also the final name's authenticated folders and the area.
    if let (Some(s), true) = (&staging_root, t.file_index > 0) {
        remove_if_empty(s, &t.file_index.to_string())?;
    }
    if !delivered && let Some(chain) = ancestors(&area, t)? {
        for (parent, name, _) in chain.iter().rev() {
            if !remove_if_empty(parent, name)? {
                break;
            }
        }
    }
    if staging_root.is_some() {
        remove_if_empty(&area, ".staging")?;
    }
    if !delivered {
        remove_if_empty(&root, &t.recording_directory)?;
    }
    Ok(outcome)
}

/// Open a delivered job's published final (identity-checked root, private job
/// folder and recorded parent) and require it to be the recorded object.
/// Returns its (device, inode), for the superseded-attempt check. One call per
/// file keeps every worker message bounded.
pub fn published_identity(p: &Transfer) -> Result<(u64, u64)> {
    let unverifiable = || ClaimError::Blocked("published file not verifiable");
    if p.phase != mover_core::TransferPhase::Published {
        return Err(unverifiable());
    }
    let root = root(&p.destination_root)?;
    same_directory(&owned_directory(&root, false)?, &p.root)?;
    let area = open_directory(&root, &p.recording_directory)?.ok_or_else(unverifiable)?;
    same_directory(&owned_directory(&area, true)?, &p.area)?;
    let parent = final_parent(&area, p)?.ok_or_else(unverifiable)?;
    let fd = open_existing(&parent, final_name(p))?.ok_or_else(unverifiable)?;
    same_object(&fd, &p.stage).map_err(|_| unverifiable())?;
    let s = fs::fstat(&fd).map_err(op("destination_discard.stat"))?;
    Ok((s.st_dev, s.st_ino))
}

/// One recorded name in `dir`. An absent name is acknowledged after syncing
/// its folder; an absent folder after syncing `container`, where it is absent.
fn single(
    dir: Option<&OwnedFd>,
    container: &OwnedFd,
    name: &str,
    expected: &ObjectIdentity,
) -> Result<Discarded> {
    let Some(dir) = dir else {
        fs::fsync(container).map_err(op("destination_discard.sync"))?;
        return Ok(Discarded::AlreadyAbsent);
    };
    match open_existing(dir, name)? {
        None => {
            fs::fsync(dir).map_err(op("destination_discard.sync"))?;
            Ok(Discarded::AlreadyAbsent)
        }
        Some(fd) => {
            same_object(&fd, expected)?;
            unlink_names(&[(dir, name)], &fd)?;
            Ok(Discarded::Removed)
        }
    }
}
