//! One startup assignment, supervised off the async coordinator. No SQLite here.
use crate::payload::Supervised;
use mover_fs::{BootstrapReceiver, LocalClaimLock};
use serde::Deserialize;
use std::{
    io::{Read, Write},
    os::{fd::AsFd, unix::net::UnixStream},
    process::{Command, Stdio},
    sync::atomic::{AtomicBool, Ordering},
    time::{Duration, Instant},
};

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Request {
    version: u32,
    source_root: String,
    source_binding: mover_fs::SourceBinding,
}

pub fn worker() -> Result<(), Box<dyn std::error::Error>> {
    let mut channel = UnixStream::from(std::io::stderr().as_fd().try_clone_to_owned()?);
    channel.set_read_timeout(Some(Duration::from_secs(3)))?;
    let _instance = mover_fs::InstanceGuard::receive(&mut channel)?;
    channel.set_write_timeout(Some(Duration::from_secs(3)))?;
    let mut bytes = Vec::new();
    (&mut channel).take(16385).read_to_end(&mut bytes)?;
    if bytes.len() > 16384 {
        return Err("bootstrap request too large".into());
    }
    let request: Request = serde_json::from_slice(&bytes)?;
    if request.version != 1 {
        return Err("invalid bootstrap protocol version".into());
    }
    mover_fs::send_bound_bootstrap_lock(&mut channel, &request.source_root, &request.source_binding)
        .map_err(Into::into)
}

/// Must run on the dedicated startup supervisor thread, never the executor.
pub fn acquire(
    path: &str,
    binding: &mover_fs::SourceBinding,
    stop: &AtomicBool,
    instance: &std::sync::Arc<mover_fs::InstanceGuard>,
) -> Result<LocalClaimLock, String> {
    let operation = || -> Result<LocalClaimLock, Box<dyn std::error::Error>> {
        if stop.load(Ordering::Relaxed) {
            return Err("startup stopped".into());
        }
        binding.validate()?;
        let bytes = serde_json::to_vec(
            &serde_json::json!({"version":1,"source_root":path,"source_binding":binding}),
        )?;
        if bytes.len() > 16384 {
            return Err("bootstrap request too large".into());
        }
        let (mut channel, worker_channel) = UnixStream::pair()?;
        channel.set_write_timeout(Some(Duration::from_secs(3)))?;
        channel.set_read_timeout(Some(Duration::from_secs(3)))?;
        instance.prepare_workers()?;
        let mut child = Supervised(
            Command::new(std::env::current_exe()?)
                .arg("--internal-bootstrap-worker")
                .stdin(Stdio::null())
                .stdout(Stdio::null())
                .stderr(Stdio::from(std::os::fd::OwnedFd::from(worker_channel)))
                .spawn()?,
        );
        instance.send(&mut channel)?;
        channel.write_all(&bytes)?;
        channel.shutdown(std::net::Shutdown::Write)?;
        let mut receiver = BootstrapReceiver::default();
        let mut lock = None;
        let deadline = Instant::now() + Duration::from_secs(30);
        loop {
            if stop.load(Ordering::Relaxed) || Instant::now() >= deadline {
                eprintln!(
                    "Source bootstrap termination requested; waiting for confirmed child exit"
                );
                return Err("source bootstrap stopped or timed out".into());
            }
            if lock.is_none() {
                lock = receiver.poll_bound(&channel, path, Some(binding))?;
            }
            if let Some(status) = child.0.try_wait()? {
                if !status.success() {
                    return Err("source bootstrap child failed".into());
                }
                // Queued socket data/EOF may lag the first exit observation.
                if let Some(mut lock) = lock {
                    lock.attach_instance(instance.clone())?;
                    return Ok(lock);
                }
            }
            std::thread::sleep(Duration::from_millis(20));
        }
    };
    operation().map_err(|e| e.to_string())
}
