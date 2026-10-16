//! Diagnostics around the existing payload calls; never retry/phase authority.
use rustix::{fd::AsFd, fs};
use std::{
    fs::File,
    io::{self, Read, Write},
};

#[derive(Clone, Copy, Debug)]
pub(super) enum Operation {
    SourceRead,
    CopyWrite,
    CopyFileSync,
    CopyDirectorySync,
    VerificationRead,
    PublicationFileSync,
    PublicationStagingSync,
    PublicationDirectorySync,
}
impl Operation {
    fn tag(self) -> &'static str {
        match self {
            Self::SourceRead => "payload_source_read",
            Self::CopyWrite => "payload_copy_write",
            Self::CopyFileSync => "payload_copy_file_sync",
            Self::CopyDirectorySync => "payload_copy_directory_sync",
            Self::VerificationRead => "payload_verification_read",
            Self::PublicationFileSync => "payload_publication_file_sync",
            Self::PublicationStagingSync => "payload_publication_staging_sync",
            Self::PublicationDirectorySync => "payload_publication_directory_sync",
        }
    }
}

pub(super) struct Failure {
    operation: Operation,
    error: io::Error,
}
impl std::fmt::Display for Failure {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{} ", self.operation.tag())?;
        if let Some(errno) = self.error.raw_os_error() {
            write!(f, "errno={errno}; ")?;
        } else {
            let kind = match self.error.kind() {
                io::ErrorKind::Interrupted => "interrupted",
                io::ErrorKind::WriteZero => "write_zero",
                _ => "other",
            };
            write!(f, "kind={kind}; ")?;
        }
        match self.error.raw_os_error() {
            Some(28) => f.write_str("storage full; restore approved capacity; preserve source/state; resume only if review required"),
            Some(5) => f.write_str("storage I/O error; inspect storage; preserve source/state; existing review rules apply"),
            _ => f.write_str("inspect storage; preserve source/state; existing review rules apply"),
        }
    }
}
impl std::fmt::Debug for Failure {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        std::fmt::Display::fmt(self, f)
    }
}
impl std::error::Error for Failure {}

fn run<T>(operation: Operation, effect: impl FnOnce() -> io::Result<T>) -> Result<T, Failure> {
    #[cfg(feature = "nfs-qualification")]
    if std::env::var("FILE_MOVER_QUALIFICATION_PAYLOAD_FAULT")
        .ok()
        .as_deref()
        == Some(operation.tag())
    {
        return Err(Failure {
            operation,
            error: io::Error::from_raw_os_error(if matches!(operation, Operation::CopyWrite) {
                28
            } else {
                5
            }),
        });
    }
    effect().map_err(|error| Failure { operation, error })
}
pub(super) fn read(
    file: &mut File,
    buffer: &mut [u8],
    operation: Operation,
) -> Result<usize, Failure> {
    run(operation, || file.read(buffer))
}
pub(super) fn write(file: &mut File, bytes: &[u8]) -> Result<(), Failure> {
    run(Operation::CopyWrite, || file.write_all(bytes))
}
pub(super) fn sync_file(file: &File) -> Result<(), Failure> {
    run(Operation::CopyFileSync, || file.sync_all())
}
pub(super) fn sync_fd(fd: &impl AsFd, operation: Operation) -> Result<(), Failure> {
    run(operation, || {
        fs::fsync(fd).map_err(|e| io::Error::from_raw_os_error(e.raw_os_error()))
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn payload_diagnostics_keep_operation_errno_and_safe_actions_without_error_text() {
        for operation in [
            Operation::SourceRead,
            Operation::CopyWrite,
            Operation::CopyFileSync,
            Operation::CopyDirectorySync,
            Operation::VerificationRead,
            Operation::PublicationFileSync,
            Operation::PublicationStagingSync,
            Operation::PublicationDirectorySync,
        ] {
            for errno in [5, 28, 13] {
                let error = Failure {
                    operation,
                    error: io::Error::from_raw_os_error(errno),
                };
                let detail = crate::failure_diagnostic(&error);
                assert!(detail.starts_with(&format!("{} errno={errno};", operation.tag())));
                assert!(detail.contains("preserve source/state"));
                assert!(
                    detail.len() <= 240
                        && detail.bytes().all(|b| b.is_ascii_graphic() || b == b' ')
                );
            }
        }
        for (error, kind) in [
            (io::Error::other("secret/path\nforged payload"), "other"),
            (io::ErrorKind::Interrupted.into(), "interrupted"),
            (io::ErrorKind::WriteZero.into(), "write_zero"),
        ] {
            let error = Failure {
                operation: Operation::CopyWrite,
                error,
            };
            let detail = crate::failure_diagnostic(&error);
            assert!(detail.contains(&format!("kind={kind};")));
            assert!(
                !detail.contains("secret") && !detail.contains("forged") && !detail.contains('\n')
            );
            assert_eq!(format!("{error:?}"), detail);
        }
    }
}
