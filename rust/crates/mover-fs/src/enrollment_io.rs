//! Narrow enrollment qualification controls. Production uses ordinary file I/O.
use super::*;
use std::io::Write;

#[cfg(not(feature = "nfs-qualification"))]
pub(super) fn write(file: &mut std::fs::File, bytes: &[u8]) -> std::io::Result<()> {
    file.write_all(bytes)
}

#[cfg(feature = "nfs-qualification")]
fn fault() -> Option<String> {
    std::env::var("FILE_MOVER_QUALIFICATION_ENROLLMENT_FAULT").ok()
}

#[cfg(feature = "nfs-qualification")]
pub(super) fn write(file: &mut std::fs::File, bytes: &[u8]) -> std::io::Result<()> {
    struct Writer<'a> {
        file: &'a mut std::fs::File,
        fault: Option<String>,
        calls: usize,
    }
    impl Write for Writer<'_> {
        fn write(&mut self, bytes: &[u8]) -> std::io::Result<usize> {
            self.calls += 1;
            match self.fault.as_deref() {
                Some("interrupted_write") if self.calls == 1 => {
                    Err(std::io::ErrorKind::Interrupted.into())
                }
                Some("write_zero") if self.calls > 1 => Ok(0),
                Some("write_enospc") if self.calls > 1 => {
                    Err(std::io::Error::from_raw_os_error(28))
                }
                Some("write_eio") if self.calls > 1 => Err(std::io::Error::from_raw_os_error(5)),
                Some("short_write" | "write_zero" | "write_enospc" | "write_eio") => {
                    self.file.write(&bytes[..bytes.len().min(7)])
                }
                _ => self.file.write(bytes),
            }
        }
        fn flush(&mut self) -> std::io::Result<()> {
            self.file.flush()
        }
    }
    Writer {
        file,
        fault: fault(),
        calls: 0,
    }
    .write_all(bytes)
}

pub(super) fn sync_file(file: &std::fs::File) -> Result<()> {
    #[cfg(feature = "nfs-qualification")]
    if fault().as_deref() == Some("file_sync") {
        return Err(ClaimError::Operation("enrollment_file_sync", Errno::IO));
    }
    fs::fsync(file).map_err(|e| ClaimError::Operation("enrollment_file_sync", e))
}

pub(super) fn sync_directory(area: &OwnedFd) -> Result<()> {
    #[cfg(feature = "nfs-qualification")]
    if fault().as_deref() == Some("directory_sync") {
        return Err(ClaimError::Operation(
            "enrollment_directory_sync",
            Errno::IO,
        ));
    }
    fs::fsync(area).map_err(|e| ClaimError::Operation("enrollment_directory_sync", e))
}
