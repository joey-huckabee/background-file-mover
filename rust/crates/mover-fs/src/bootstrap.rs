//! Private child bootstrap channel. Parent receipt handling performs no source I/O.
use super::{LocalClaimLock, SourceAuthorization, SourceBinding};
use mover_core::ObjectIdentity;
use rustix::{
    fd::{AsFd, OwnedFd},
    io::Errno,
    net::{
        self, RecvAncillaryBuffer, RecvAncillaryMessage, RecvFlags, ReturnFlags,
        SendAncillaryBuffer, SendAncillaryMessage, SendFlags,
    },
};
use serde::{Deserialize, Serialize};
use std::{
    io::{IoSlice, IoSliceMut, Write},
    mem::MaybeUninit,
    os::unix::net::UnixStream,
};
const LIMIT: usize = 16384;

#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Receipt {
    version: u32,
    path: String,
    root: Option<String>,
    namespace: Option<String>,
    lock: Option<String>,
    authorization: Option<SourceAuthorization>,
    error: Option<String>,
}

#[cfg(test)]
mod tests {
    use super::*;
    fn rejected(mut receiver: BootstrapReceiver, channel: &UnixStream) -> String {
        for _ in 0..32 {
            match receiver.poll(channel, "/source") {
                Err(e) => return e,
                Ok(None) => {}
                Ok(Some(_)) => panic!("malformed bootstrap accepted custody"),
            }
        }
        panic!("bootstrap did not finish");
    }
    #[test]
    fn missing_descriptor_and_oversized_receipts_fail_closed() {
        let object = ObjectIdentity {
            device: 1,
            inode: 1,
            uid: 1000,
            size: 0,
            modified_seconds: 0,
            modified_nanos: 0,
            links: 1,
        }
        .encode();
        let body = serde_json::to_vec(&Receipt {
            version: 2,
            path: "/source".into(),
            root: Some(object.clone()),
            namespace: Some(object.clone()),
            lock: Some(object),
            authorization: None,
            error: None,
        })
        .unwrap();
        for (bytes, expected) in [
            (body, "missing bootstrap descriptor"),
            (vec![b'x'; LIMIT + 1], "bootstrap receipt too large"),
        ] {
            let (channel, mut writer) = UnixStream::pair().unwrap();
            writer.write_all(&bytes).unwrap();
            writer.shutdown(std::net::Shutdown::Write).unwrap();
            assert_eq!(rejected(BootstrapReceiver::default(), &channel), expected);
        }
    }
    #[test]
    fn extra_descriptors_fail_closed() {
        let (channel, writer) = UnixStream::pair().unwrap();
        let file = std::fs::File::open("/dev/null").unwrap();
        let descriptors = [file.as_fd(), file.as_fd()];
        let mut space = [MaybeUninit::uninit(); rustix::cmsg_space!(ScmRights(2))];
        let mut control = SendAncillaryBuffer::new(&mut space);
        assert!(control.push(SendAncillaryMessage::ScmRights(&descriptors)));
        net::sendmsg(
            &writer,
            &[IoSlice::new(b"x")],
            &mut control,
            SendFlags::NOSIGNAL,
        )
        .unwrap();
        assert_eq!(
            rejected(BootstrapReceiver::default(), &channel),
            "extra bootstrap descriptor"
        );
    }
    #[test]
    fn legacy_or_inconsistent_lock_receipts_are_rejected() {
        let object = ObjectIdentity {
            device: 1,
            inode: 2,
            uid: 1000,
            size: 0,
            modified_seconds: 0,
            modified_nanos: 0,
            links: 1,
        };
        let mut invalid = object.clone();
        invalid.links = 2;
        for (version, lock, expected) in [
            (1, Some(object.encode()), "bootstrap scope/version mismatch"),
            (2, None, "missing bootstrap lock identity"),
            (
                2,
                Some(invalid.encode()),
                "inconsistent bootstrap lock custody",
            ),
        ] {
            let (channel, mut writer) = UnixStream::pair().unwrap();
            writer
                .write_all(
                    &serde_json::to_vec(&Receipt {
                        version,
                        path: "/source".into(),
                        root: Some(object.encode()),
                        namespace: Some(object.encode()),
                        lock,
                        authorization: None,
                        error: None,
                    })
                    .unwrap(),
                )
                .unwrap();
            writer.shutdown(std::net::Shutdown::Write).unwrap();
            assert_eq!(rejected(BootstrapReceiver::default(), &channel), expected);
        }
    }
}

/// Called only in the bootstrap child. SCM_RIGHTS preserves the locked open
/// description; reopening /proc or the source path would not preserve custody.
pub fn send_bootstrap_lock(channel: &mut UnixStream, path: &str) -> Result<(), String> {
    send_lock(channel, path, None)
}
pub fn send_bound_bootstrap_lock(
    channel: &mut UnixStream,
    path: &str,
    binding: &SourceBinding,
) -> Result<(), String> {
    send_lock(channel, path, Some(binding))
}
fn send_lock(
    channel: &mut UnixStream,
    path: &str,
    binding: Option<&SourceBinding>,
) -> Result<(), String> {
    let acquired = match binding {
        Some(binding) => LocalClaimLock::acquire_bound(path, binding),
        None => LocalClaimLock::acquire(path),
    };
    let receipt = match &acquired {
        Ok(lock) => Receipt {
            version: 2,
            path: path.into(),
            root: Some(lock.root.encode()),
            namespace: Some(lock.namespace.encode()),
            lock: Some(lock.lock.encode()),
            authorization: lock.authorization.clone(),
            error: None,
        },
        Err(e) => Receipt {
            version: 2,
            path: path.into(),
            root: None,
            namespace: None,
            lock: None,
            authorization: None,
            error: Some(e.to_string()),
        },
    };
    let bytes = serde_json::to_vec(&receipt).map_err(|e| e.to_string())?;
    if bytes.len() > LIMIT {
        return Err("bootstrap receipt too large".into());
    }
    if let Ok(lock) = acquired {
        let mut space = [MaybeUninit::uninit(); rustix::cmsg_space!(ScmRights(1))];
        let mut control = SendAncillaryBuffer::new(&mut space);
        let descriptors = [lock._held.as_fd()];
        if !control.push(SendAncillaryMessage::ScmRights(&descriptors)) {
            return Err("bootstrap descriptor buffer".into());
        }
        let sent = net::sendmsg(
            &*channel,
            &[IoSlice::new(&bytes)],
            &mut control,
            SendFlags::NOSIGNAL,
        )
        .map_err(|e| e.to_string())?;
        if sent == 0 {
            return Err("bootstrap channel closed".into());
        }
        channel
            .write_all(&bytes[sent..])
            .map_err(|e| e.to_string())?;
    } else {
        channel.write_all(&bytes).map_err(|e| e.to_string())?;
    }
    channel
        .shutdown(std::net::Shutdown::Write)
        .map_err(|e| e.to_string())
}

#[derive(Default)]
pub struct BootstrapReceiver {
    bytes: Vec<u8>,
    descriptor: Option<OwnedFd>,
    finished: bool,
}
impl BootstrapReceiver {
    /// Nonblocking socket-only polling. Returned custody remains provisional
    /// until the supervisor confirms successful child exit.
    pub fn poll(
        &mut self,
        channel: &UnixStream,
        path: &str,
    ) -> Result<Option<LocalClaimLock>, String> {
        self.poll_bound(channel, path, None)
    }
    pub fn poll_bound(
        &mut self,
        channel: &UnixStream,
        path: &str,
        binding: Option<&SourceBinding>,
    ) -> Result<Option<LocalClaimLock>, String> {
        if self.finished {
            return Err("bootstrap receipt already consumed".into());
        }
        let mut data = [0; 2048];
        let mut space = [MaybeUninit::uninit(); rustix::cmsg_space!(ScmRights(2))];
        let mut control = RecvAncillaryBuffer::new(&mut space);
        let received = match net::recvmsg(
            channel,
            &mut [IoSliceMut::new(&mut data)],
            &mut control,
            RecvFlags::DONTWAIT | RecvFlags::CMSG_CLOEXEC,
        ) {
            Ok(r) => r,
            Err(Errno::AGAIN | Errno::INTR) => return Ok(None),
            Err(e) => return Err(e.to_string()),
        };
        if received
            .flags
            .intersects(ReturnFlags::CTRUNC | ReturnFlags::TRUNC)
        {
            return Err("truncated bootstrap message".into());
        }
        for ancillary in control.drain() {
            match ancillary {
                RecvAncillaryMessage::ScmRights(fds) => {
                    for fd in fds {
                        if self.descriptor.is_some() {
                            return Err("extra bootstrap descriptor".into());
                        }
                        self.descriptor = Some(fd);
                    }
                }
                _ => return Err("unexpected bootstrap ancillary message".into()),
            }
        }
        if self.bytes.len() + received.bytes > LIMIT {
            return Err("bootstrap receipt too large".into());
        }
        self.bytes.extend_from_slice(&data[..received.bytes]);
        if received.bytes != 0 {
            return Ok(None);
        }
        self.finished = true;
        let receipt: Receipt = serde_json::from_slice(&self.bytes).map_err(|e| e.to_string())?;
        if receipt.version != 2 || receipt.path != path {
            return Err("bootstrap scope/version mismatch".into());
        }
        if let Some(error) = receipt.error {
            if self.descriptor.is_some()
                || receipt.root.is_some()
                || receipt.namespace.is_some()
                || receipt.lock.is_some()
                || receipt.authorization.is_some()
            {
                return Err("inconsistent bootstrap failure".into());
            }
            return Err(error);
        }
        let root = receipt
            .root
            .as_deref()
            .and_then(ObjectIdentity::decode)
            .ok_or("missing bootstrap root identity")?;
        let namespace = receipt
            .namespace
            .as_deref()
            .and_then(ObjectIdentity::decode)
            .ok_or("missing bootstrap namespace identity")?;
        let lock = receipt
            .lock
            .as_deref()
            .and_then(ObjectIdentity::decode)
            .ok_or("missing bootstrap lock identity")?;
        if lock.uid != root.uid || lock.device != root.device || lock.size != 0 || lock.links != 1 {
            return Err("inconsistent bootstrap lock custody".into());
        }
        if root.uid != namespace.uid || root.device != namespace.device {
            return Err("inconsistent bootstrap custody".into());
        }
        if receipt.authorization.as_ref().map(|a| &a.binding) != binding
            || receipt.authorization.as_ref().is_some_and(|a| {
                a.binding.validate().is_err()
                    || a.enrollment.is_some()
                    || a.observation.is_empty()
                    || a.observation.len() > 2048
            })
        {
            return Err("bootstrap authorization mismatch".into());
        }
        Ok(Some(LocalClaimLock {
            path: path.into(),
            root,
            namespace,
            lock,
            authorization: receipt.authorization,
            destination_authorization: None,
            _held: self
                .descriptor
                .take()
                .ok_or("missing bootstrap descriptor")?,
        }))
    }
}
