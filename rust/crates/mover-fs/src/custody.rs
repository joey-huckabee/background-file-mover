//! Cooperative file-lock custody. This is not storage fencing or a takeover lease.
use super::*;
pub const COORDINATOR_LOCK: &str = "coordinator.lock";

fn identity(fd: &impl rustix::fd::AsFd) -> Result<ObjectIdentity> {
    let stat = fs::fstat(fd)?;
    if fs::fcntl_getfl(fd)? & OFlags::ACCMODE != OFlags::RDWR {
        return Err(ClaimError::Blocked("coordinator lock must be read/write"));
    }
    checked(&stat)
}

fn checked(stat: &Stat) -> Result<ObjectIdentity> {
    if FileType::from_raw_mode(stat.st_mode) != FileType::RegularFile
        || stat.st_size != 0
        || stat.st_uid != rustix::process::geteuid().as_raw()
        || stat.st_mode & 0o7777 != 0o600
        || stat.st_nlink != 1
    {
        return Err(ClaimError::Blocked("invalid coordinator lock custody"));
    }
    Ok(observation(stat))
}

pub(super) fn named_identity(area: &OwnedFd) -> Result<ObjectIdentity> {
    let named = fs::statat(area, COORDINATOR_LOCK, AtFlags::SYMLINK_NOFOLLOW)?;
    let observed = checked(&named)?;
    if observed.device != fs::fstat(area)?.st_dev {
        return Err(ClaimError::Blocked("coordinator lock device changed"));
    }
    Ok(observed)
}

pub(super) fn open(area: &OwnedFd) -> Result<OwnedFd> {
    let fd = fs::openat(
        area,
        COORDINATOR_LOCK,
        OFlags::RDWR | OFlags::NOFOLLOW | OFlags::NONBLOCK | OFlags::CLOEXEC,
        Mode::empty(),
    )?;
    validate(area, &fd)?;
    Ok(fd)
}

pub(super) fn validate(area: &OwnedFd, held: &impl rustix::fd::AsFd) -> Result<ObjectIdentity> {
    let observed = identity(held)?;
    if observed != named_identity(area)? {
        return Err(ClaimError::Blocked("coordinator lock binding changed"));
    }
    Ok(observed)
}

pub(super) fn exclusive(fd: &impl rustix::fd::AsFd) -> Result<()> {
    fs::flock(fd, fs::FlockOperation::NonBlockingLockExclusive)?;
    Ok(())
}
