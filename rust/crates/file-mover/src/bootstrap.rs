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

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct DestinationRequest {
    version: u32,
    destination_root: String,
    destination_binding: mover_fs::DestinationBinding,
    #[serde(default)]
    destination_observation: Option<String>,
}

/// Destination acquisition child (shared delivery custody): validates the
/// job's destination binding and pin, then sends the locked description.
pub fn destination_worker() -> Result<(), Box<dyn std::error::Error>> {
    let mut channel = UnixStream::from(std::io::stderr().as_fd().try_clone_to_owned()?);
    channel.set_read_timeout(Some(Duration::from_secs(3)))?;
    let _instance = mover_fs::InstanceGuard::receive(&mut channel)?;
    channel.set_write_timeout(Some(Duration::from_secs(3)))?;
    let mut bytes = Vec::new();
    (&mut channel).take(16385).read_to_end(&mut bytes)?;
    if bytes.len() > 16384 {
        return Err("destination request too large".into());
    }
    let request: DestinationRequest = serde_json::from_slice(&bytes)?;
    if request.version != 1 {
        return Err("invalid destination protocol version".into());
    }
    mover_fs::send_destination_bootstrap_lock(
        &mut channel,
        &request.destination_root,
        &request.destination_binding,
        request.destination_observation.as_deref(),
    )
    .map_err(Into::into)
}

/// Must run on the dedicated startup supervisor thread, never the executor.
pub fn acquire(
    path: &str,
    binding: &mover_fs::SourceBinding,
    stop: &AtomicBool,
    instance: &std::sync::Arc<mover_fs::InstanceGuard>,
) -> Result<LocalClaimLock, String> {
    let request = || -> Result<Vec<u8>, Box<dyn std::error::Error>> {
        binding.validate()?;
        Ok(serde_json::to_vec(
            &serde_json::json!({"version":1,"source_root":path,"source_binding":binding}),
        )?)
    };
    supervise(
        "--internal-bootstrap-worker",
        "Source bootstrap",
        request,
        path,
        Some(binding),
        stop,
        instance,
    )
}

/// Destination custody for shared delivery, acquired in a supervised child so
/// the coordinator never touches the (possibly hard-NFS) destination itself.
/// Runs on a delivery worker thread, never the executor. The returned lock is
/// the coordinator's: delivery children inherit it and validate their own
/// job's binding against it.
pub fn acquire_destination(
    path: &str,
    binding: &mover_fs::DestinationBinding,
    expected: Option<&str>,
    stop: &AtomicBool,
    instance: &std::sync::Arc<mover_fs::InstanceGuard>,
) -> Result<LocalClaimLock, String> {
    let request = || -> Result<Vec<u8>, Box<dyn std::error::Error>> {
        binding.validate()?;
        Ok(serde_json::to_vec(
            &serde_json::json!({"version":1,"destination_root":path,
            "destination_binding":binding,"destination_observation":expected}),
        )?)
    };
    supervise(
        "--internal-destination-worker",
        "Destination custody",
        request,
        path,
        None,
        stop,
        instance,
    )
}

fn supervise(
    mode: &str,
    label: &str,
    request: impl FnOnce() -> Result<Vec<u8>, Box<dyn std::error::Error>>,
    path: &str,
    binding: Option<&mover_fs::SourceBinding>,
    stop: &AtomicBool,
    instance: &std::sync::Arc<mover_fs::InstanceGuard>,
) -> Result<LocalClaimLock, String> {
    let operation = || -> Result<LocalClaimLock, Box<dyn std::error::Error>> {
        if stop.load(Ordering::Relaxed) {
            return Err("startup stopped".into());
        }
        let bytes = request()?;
        if bytes.len() > 16384 {
            return Err("bootstrap request too large".into());
        }
        let (mut channel, worker_channel) = UnixStream::pair()?;
        channel.set_write_timeout(Some(Duration::from_secs(3)))?;
        channel.set_read_timeout(Some(Duration::from_secs(3)))?;
        instance.prepare_workers()?;
        let mut child = Supervised(
            Command::new(std::env::current_exe()?)
                .arg(mode)
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
                crate::logging::diagnostic_line!(
                    Warn,
                    "worker_termination_wait",
                    None,
                    None,
                    eprintln!("{label} termination requested; waiting for confirmed child exit")
                );
                return Err(format!("{} stopped or timed out", label.to_lowercase()).into());
            }
            if lock.is_none() {
                lock = receiver.poll_bound(&channel, path, binding)?;
            }
            if let Some(status) = child.0.try_wait()? {
                if !status.success() {
                    return Err(format!("{} child failed", label.to_lowercase()).into());
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
