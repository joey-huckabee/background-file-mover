//! Transfer progress: a best-effort, in-memory side channel from a delivery
//! child to its coordinator, for the dashboard's live transfer speed.
//!
//! Requirement: status must not affect copy performance. Each session has its
//! own `SOCK_SEQPACKET` pair, so an update is one whole message or nothing
//! (never a partial frame on the control channel). The child sends without
//! waiting, at most about once a second; an update the coordinator cannot take
//! right now is dropped (the next one carries the complete totals). Nothing is
//! written to disk or the database. Per copied chunk the copy loop adds only a
//! counter update and a clock check.
use rustix::{
    fd::{AsFd, OwnedFd},
    io::Errno,
    net::{
        self, AddressFamily, RecvAncillaryBuffer, RecvAncillaryMessage, RecvFlags,
        SendAncillaryBuffer, SendAncillaryMessage, SendFlags, SocketFlags, SocketType,
    },
};
use std::{
    io::{IoSlice, IoSliceMut},
    mem::MaybeUninit,
    os::unix::net::UnixStream,
    time::{Duration, Instant},
};

/// Minimum spacing of updates from one child.
pub const PROGRESS_INTERVAL: Duration = Duration::from_secs(1);
const SIZE: usize = 24;

/// What a delivery child is doing with one file.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ProgressPhase {
    /// Copying from held source to staging (reading and writing).
    Copying,
    /// Re-reading the staged copy to verify its digest.
    Verifying,
}
/// One progress sample: bytes done of `total` for one file.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct ProgressUpdate {
    pub file_index: u32,
    pub phase: ProgressPhase,
    pub done: u64,
    pub total: u64,
}
impl ProgressUpdate {
    fn encode(&self) -> [u8; SIZE] {
        let mut b = [0; SIZE];
        b[0] = match self.phase {
            ProgressPhase::Copying => 1,
            ProgressPhase::Verifying => 2,
        };
        b[4..8].copy_from_slice(&self.file_index.to_le_bytes());
        b[8..16].copy_from_slice(&self.done.to_le_bytes());
        b[16..24].copy_from_slice(&self.total.to_le_bytes());
        b
    }
    fn decode(b: &[u8]) -> Option<Self> {
        if b.len() != SIZE || b[1..4] != [0, 0, 0] {
            return None;
        }
        let phase = match b[0] {
            1 => ProgressPhase::Copying,
            2 => ProgressPhase::Verifying,
            _ => return None,
        };
        let u = Self {
            file_index: u32::from_le_bytes(b[4..8].try_into().ok()?),
            phase,
            done: u64::from_le_bytes(b[8..16].try_into().ok()?),
            total: u64::from_le_bytes(b[16..24].try_into().ok()?),
        };
        (u.done <= u.total).then_some(u)
    }
}

/// A new session's channel: (coordinator end, nonblocking; child end).
pub fn progress_pair() -> std::io::Result<(OwnedFd, OwnedFd)> {
    let (coordinator, child) = net::socketpair(
        AddressFamily::UNIX,
        SocketType::SEQPACKET,
        SocketFlags::CLOEXEC | SocketFlags::NONBLOCK,
        None,
    )?;
    Ok((coordinator, child))
}

/// Coordinator: hand the child end to the session child over its control
/// channel (one marker byte with the descriptor).
pub fn send_progress_channel(channel: &UnixStream, child_end: &OwnedFd) -> std::io::Result<()> {
    let mut space = [MaybeUninit::uninit(); rustix::cmsg_space!(ScmRights(1))];
    let mut control = SendAncillaryBuffer::new(&mut space);
    let descriptors = [child_end.as_fd()];
    if !control.push(SendAncillaryMessage::ScmRights(&descriptors)) {
        return Err(std::io::Error::other("progress descriptor encoding"));
    }
    if net::sendmsg(
        channel,
        &[IoSlice::new(b"P")],
        &mut control,
        SendFlags::NOSIGNAL,
    )? != 1
    {
        return Err(std::io::Error::other("progress channel handoff"));
    }
    Ok(())
}

/// Child: receive the progress channel sent by `send_progress_channel`.
pub fn receive_progress_channel(channel: &UnixStream) -> std::io::Result<ProgressSender> {
    let mut byte = [0];
    let mut space = [MaybeUninit::uninit(); rustix::cmsg_space!(ScmRights(2))];
    let mut control = RecvAncillaryBuffer::new(&mut space);
    let received = net::recvmsg(
        channel,
        &mut [IoSliceMut::new(&mut byte)],
        &mut control,
        RecvFlags::CMSG_CLOEXEC,
    )?;
    let mut fd = None;
    for message in control.drain() {
        match message {
            RecvAncillaryMessage::ScmRights(fds) => {
                for f in fds {
                    if fd.replace(f).is_some() {
                        return Err(std::io::Error::other("extra progress descriptor"));
                    }
                }
            }
            _ => {
                return Err(std::io::Error::other(
                    "unexpected progress ancillary message",
                ));
            }
        }
    }
    if received.bytes != 1 || byte != *b"P" {
        return Err(std::io::Error::other("invalid progress handoff"));
    }
    let fd = fd.ok_or_else(|| std::io::Error::other("missing progress descriptor"))?;
    if net::sockopt::socket_type(&fd)? != SocketType::SEQPACKET {
        return Err(std::io::Error::other(
            "progress channel is not a packet socket",
        ));
    }
    Ok(ProgressSender { fd, last: None })
}

/// The child's sending end. `report` never waits and never fails the copy.
pub struct ProgressSender {
    fd: OwnedFd,
    last: Option<Instant>,
}
impl ProgressSender {
    /// Called per copied chunk; sends at most every `PROGRESS_INTERVAL`, plus
    /// the final sample of each file.
    pub fn report(&mut self, update: ProgressUpdate) {
        let now = Instant::now();
        if update.done != update.total
            && self
                .last
                .is_some_and(|l| now.duration_since(l) < PROGRESS_INTERVAL)
        {
            return;
        }
        self.last = Some(now);
        // A full or closed channel drops this update; the copy never waits.
        let _ = net::send(
            &self.fd,
            &update.encode(),
            SendFlags::DONTWAIT | SendFlags::NOSIGNAL,
        );
    }
}

/// Coordinator: every update waiting on the (nonblocking) coordinator end.
/// Malformed messages are ignored; the channel is advisory.
pub fn drain_progress(fd: &OwnedFd) -> Vec<ProgressUpdate> {
    let mut updates = Vec::new();
    let mut buffer = [0; 64];
    // Bounded: a child sends about one update a second.
    for _ in 0..256 {
        match net::recv(fd, &mut buffer, RecvFlags::DONTWAIT) {
            Ok((n, _)) if n > 0 => {
                if let Some(u) = ProgressUpdate::decode(&buffer[..n.min(buffer.len())]) {
                    updates.push(u);
                }
            }
            Ok(_) | Err(Errno::AGAIN) | Err(_) => break,
        }
    }
    updates
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn updates_round_trip_and_malformed_messages_are_ignored() {
        let u = ProgressUpdate {
            file_index: 3,
            phase: ProgressPhase::Verifying,
            done: 5,
            total: 9,
        };
        assert_eq!(ProgressUpdate::decode(&u.encode()), Some(u));
        let mut bad = u.encode();
        bad[0] = 7;
        assert_eq!(ProgressUpdate::decode(&bad), None);
        let mut over = u;
        over.done = 10;
        assert_eq!(ProgressUpdate::decode(&over.encode()), None);
        assert_eq!(ProgressUpdate::decode(&u.encode()[..23]), None);
    }
    #[test]
    fn sender_is_rate_limited_and_never_blocks_on_a_full_channel() {
        let (coordinator, child) = progress_pair().unwrap();
        let (a, b) = UnixStream::pair().unwrap();
        send_progress_channel(&a, &child).unwrap();
        drop(child);
        let mut sender = receive_progress_channel(&b).unwrap();
        let mut u = ProgressUpdate {
            file_index: 0,
            phase: ProgressPhase::Copying,
            done: 1,
            total: 100,
        };
        sender.report(u);
        u.done = 2;
        sender.report(u); // within the interval: not sent
        u.done = 100;
        sender.report(u); // final sample of the file: always sent
        let got = drain_progress(&coordinator);
        assert_eq!(got.iter().map(|g| g.done).collect::<Vec<_>>(), vec![1, 100]);
        // Nobody reading: reports keep returning immediately and are dropped.
        let started = Instant::now();
        for _ in 0..100_000 {
            u.done = u.total;
            sender.report(u);
        }
        assert!(started.elapsed() < Duration::from_secs(5));
        assert!(!drain_progress(&coordinator).is_empty());
        // The coordinator gone: still no error or wait.
        drop(coordinator);
        sender.report(u);
    }
}
