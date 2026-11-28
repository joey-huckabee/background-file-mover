// Compiled only by test targets. Never weaken production epoch/guard checks.
use std::{fs, io::{Read, Seek, SeekFrom}, ops::{Deref, DerefMut}, os::unix::{fs::{OpenOptionsExt, MetadataExt}, process::CommandExt}, process::{Child, Command, Stdio}, sync::atomic::{AtomicU64, Ordering}};
static NEXT: AtomicU64 = AtomicU64::new(0);
const MARKER: &str = "FILE_MOVER_ISOLATED_TEST";

/// Kill/reap only the exact Child owned by this guard, including on unwind.
pub struct OwnedChild(Child);
impl OwnedChild { pub fn new(child: Child) -> Self { Self(child) } }
impl Deref for OwnedChild { type Target = Child; fn deref(&self) -> &Child { &self.0 } }
impl DerefMut for OwnedChild { fn deref_mut(&mut self) -> &mut Child { &mut self.0 } }
impl Drop for OwnedChild {
    fn drop(&mut self) {
        if !matches!(self.0.try_wait(), Ok(Some(_))) {
            let _ = self.0.kill();
            let _ = self.0.wait();
        }
    }
}
struct Log { path: std::path::PathBuf, device: u64, inode: u64 }
impl Drop for Log {
    fn drop(&mut self) {
        if fs::symlink_metadata(&self.path).is_ok_and(|m| m.is_file() && m.dev() == self.device && m.ino() == self.inode) {
            let _ = fs::remove_file(&self.path);
        }
    }
}

/// Parent returns true after the same exact test succeeds in its private group.
/// Child returns false and executes the unchanged scenario/assertions.
pub fn run(test: &str) -> bool {
    match std::env::var(MARKER) {
        Ok(selected) => {
            assert_eq!(selected, test, "isolated child ran the wrong test");
            let stat = fs::read_to_string("/proc/self/stat").unwrap();
            let group: u32 = stat.rsplit_once(") ").unwrap().1.split_whitespace().nth(2).unwrap().parse().unwrap();
            assert_eq!(group, std::process::id(), "test must own its process group");
            false
        }
        Err(std::env::VarError::NotPresent) => {
            let path = std::env::temp_dir().join(format!("mover-isolated-{}-{}.log", std::process::id(), NEXT.fetch_add(1, Ordering::Relaxed)));
            let mut log = fs::OpenOptions::new().read(true).write(true).create_new(true).mode(0o600).open(&path).unwrap();
            let metadata = log.metadata().unwrap();
            let _log = Log { path, device: metadata.dev(), inode: metadata.ino() };
            let mut child = OwnedChild::new(Command::new(std::env::current_exe().unwrap())
                .args(["--exact", test, "--test-threads=1", "--nocapture"])
                .env(MARKER, test).process_group(0)
                .stdin(Stdio::null()).stdout(Stdio::from(log.try_clone().unwrap()))
                .stderr(Stdio::from(log.try_clone().unwrap())).spawn().unwrap());
            let status = child.wait().unwrap();
            let length = log.metadata().unwrap().len();
            log.seek(SeekFrom::Start(length.saturating_sub(131072))).unwrap();
            let mut tail = Vec::new();
            log.take(131072).read_to_end(&mut tail).unwrap();
            let text = String::from_utf8_lossy(&tail);
            let summaries: Vec<_> = text.lines().filter(|line| line.starts_with("test result:")).collect();
            let executed = summaries.len() == 1
                && summaries[0].starts_with("test result: ok. 1 passed; 0 failed; 0 ignored;");
            // Do not expose nested libtest result lines on success: the SLES
            // report must count this scenario only once. Zero matched tests is
            // a failure even when libtest's process exit was successful.
            if !status.success() || !executed {
                eprintln!("ISOLATED_TEST_FAILURE test={test} child={} status={status}\n{text}", child.id());
            }
            assert!(status.success() && executed, "isolated test did not pass exactly once: {test} ({status})");
            true
        }
        Err(_) => panic!("isolated test marker must be UTF-8"),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn owned_child_is_reaped_when_a_scenario_panics() {
        let child = OwnedChild::new(Command::new("/bin/sleep").arg("30").process_group(0).spawn().unwrap());
        let pid = child.id();
        let stat = fs::read_to_string(format!("/proc/{pid}/stat")).unwrap();
        assert!(std::panic::catch_unwind(std::panic::AssertUnwindSafe(move || {
            let _child = child;
            panic!("test-only cleanup unwind");
        })).is_err());
        // A zombie would still have the same /proc start identity. Tolerate a
        // genuinely reused numeric PID; never signal it.
        let start = |s: &str| s.rsplit_once(") ").unwrap().1.split_whitespace().nth(19).unwrap().to_owned();
        if let Ok(after) = fs::read_to_string(format!("/proc/{pid}/stat")) {
            assert_ne!(start(&after), start(&stat), "owned child was not reaped");
        }
    }
}
