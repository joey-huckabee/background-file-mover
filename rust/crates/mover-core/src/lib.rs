//! Pure protocol rules. No HTTP, SQL or filesystem effects.
//!
//! Confirmation methods trust their caller to validate effects and durable
//! receipts. This state model alone does not establish storage durability.

use std::collections::BTreeSet;

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum ProtocolError {
    EmptyIdentity,
    EmptyRecording,
    InvalidRelativePath,
    ReservedPath,
    PathConflict,
    UnknownFile,
    InvalidTransition,
    ExpectedSizeMismatch,
    ConflictingReplay,
    DifferentSubmission,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct FileSpec {
    path: String,
    expected_size: Option<u64>,
}

impl FileSpec {
    pub fn new(path: impl Into<String>, expected_size: Option<u64>) -> Result<Self, ProtocolError> {
        let path = path.into();
        if path.is_empty()
            || path.len() > 4095
            || path.contains('\\')
            || path.chars().any(char::is_control)
            || path
                .split('/')
                .any(|p| p.is_empty() || p == "." || p == "..")
        {
            return Err(ProtocolError::InvalidRelativePath);
        }
        if path.split('/').any(|p| {
            matches!(
                p,
                ".file-mover" | ".control" | ".staging" | "COMMITTED.json"
            )
        }) {
            return Err(ProtocolError::ReservedPath);
        }
        Ok(Self {
            path,
            expected_size,
        })
    }

    pub fn relative_path(&self) -> &str {
        &self.path
    }

    pub fn expected_size(&self) -> Option<u64> {
        self.expected_size
    }
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Submission {
    generator_id: String,
    submission_id: String,
    source_directory: String,
    files: Vec<FileSpec>,
}

impl Submission {
    /// Filesystem authorization/root resolution and bounded API allocation are
    /// separate boundaries; this checks the pure request structure only.
    pub fn new(
        generator_id: impl Into<String>,
        submission_id: impl Into<String>,
        source_directory: impl Into<String>,
        files: Vec<FileSpec>,
    ) -> Result<Self, ProtocolError> {
        let generator_id = generator_id.into();
        let submission_id = submission_id.into();
        let source_directory = source_directory.into();
        if [&generator_id, &submission_id, &source_directory]
            .iter()
            .any(|s| s.trim().is_empty())
        {
            return Err(ProtocolError::EmptyIdentity);
        }
        if files.is_empty() {
            return Err(ProtocolError::EmptyRecording);
        }
        let names: BTreeSet<&str> = files.iter().map(FileSpec::relative_path).collect();
        if names.len() != files.len()
            || names.iter().any(|path| {
                path.match_indices('/')
                    .any(|(offset, _)| names.contains(&path[..offset]))
            })
        {
            return Err(ProtocolError::PathConflict);
        }
        Ok(Self {
            generator_id,
            submission_id,
            source_directory,
            files,
        })
    }

    pub fn files(&self) -> &[FileSpec] {
        &self.files
    }

    pub fn generator_id(&self) -> &str {
        &self.generator_id
    }
    pub fn submission_id(&self) -> &str {
        &self.submission_id
    }
    pub fn source_directory(&self) -> &str {
        &self.source_directory
    }
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct DeliveryPolicy {
    pub destination_id: String,
    pub group_by_generator: bool,
    pub delete_source_after_commit: bool,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum FilePhase {
    Pending,
    Claimed,
    Verified,
    Published,
    SourceRemoved,
}

#[derive(Clone, Debug, PartialEq, Eq)]
struct FileState {
    phase: FilePhase,
    actual_size: Option<u64>,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Handoff {
    Pending,
    Ready202,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Recording {
    submission: Submission,
    policy: DeliveryPolicy,
    accepted: bool,
    files: Vec<FileState>,
    committed: bool,
}

impl Recording {
    pub fn new(submission: Submission, policy: DeliveryPolicy) -> Result<Self, ProtocolError> {
        if policy.destination_id.trim().is_empty() {
            return Err(ProtocolError::EmptyIdentity);
        }
        let files = vec![
            FileState {
                phase: FilePhase::Pending,
                actual_size: None
            };
            submission.files.len()
        ];
        Ok(Self {
            submission,
            policy,
            accepted: false,
            files,
            committed: false,
        })
    }

    /// Call only after acceptance is committed to durable storage.
    pub fn confirm_acceptance(&mut self) {
        self.accepted = true;
    }

    /// Call only after validated claim/size/durability evidence is committed.
    pub fn confirm_claim(&mut self, index: usize, actual_size: u64) -> Result<(), ProtocolError> {
        if !self.accepted {
            return Err(ProtocolError::InvalidTransition);
        }
        let spec = self
            .submission
            .files
            .get(index)
            .ok_or(ProtocolError::UnknownFile)?;
        let state = self
            .files
            .get_mut(index)
            .ok_or(ProtocolError::UnknownFile)?;
        if spec
            .expected_size
            .is_some_and(|expected| expected != actual_size)
        {
            return Err(ProtocolError::ExpectedSizeMismatch);
        }
        if state.phase != FilePhase::Pending {
            return if state.actual_size == Some(actual_size) {
                Ok(())
            } else {
                Err(ProtocolError::InvalidTransition)
            };
        }
        state.actual_size = Some(actual_size);
        state.phase = FilePhase::Claimed;
        Ok(())
    }

    pub fn handoff(&self) -> Handoff {
        if self.accepted && self.files.iter().all(|f| f.phase != FilePhase::Pending) {
            Handoff::Ready202
        } else {
            Handoff::Pending
        }
    }

    /// Order-sensitive until API request normalization is finalized. Replay
    /// cannot select a new destination or reopen producer paths.
    pub fn replay(&self, candidate: &Submission) -> Result<Handoff, ProtocolError> {
        if self.submission.generator_id != candidate.generator_id
            || self.submission.submission_id != candidate.submission_id
        {
            return Err(ProtocolError::DifferentSubmission);
        }
        if &self.submission != candidate {
            return Err(ProtocolError::ConflictingReplay);
        }
        Ok(self.handoff())
    }

    pub fn policy(&self) -> &DeliveryPolicy {
        &self.policy
    }

    /// None means unknown or unrepresentable, never a wrapped byte count.
    pub fn actual_bytes_total(&self) -> Option<u64> {
        self.files
            .iter()
            .try_fold(0_u64, |total, f| total.checked_add(f.actual_size?))
    }

    pub fn file_phase(&self, index: usize) -> Option<FilePhase> {
        self.files.get(index).map(|f| f.phase)
    }

    /// Call with complete-copy and independent verification evidence.
    pub fn confirm_verification(&mut self, index: usize) -> Result<(), ProtocolError> {
        if self.handoff() != Handoff::Ready202 {
            return Err(ProtocolError::InvalidTransition);
        }
        self.advance(index, FilePhase::Claimed, FilePhase::Verified)
    }

    /// Call with verified no-clobber publication and directory-sync evidence.
    pub fn confirm_publication(&mut self, index: usize) -> Result<(), ProtocolError> {
        self.advance(index, FilePhase::Verified, FilePhase::Published)
    }

    /// Call after durable publication of the exact required set manifest.
    pub fn confirm_commit(&mut self) -> Result<(), ProtocolError> {
        if !self
            .files
            .iter()
            .all(|f| matches!(f.phase, FilePhase::Published | FilePhase::SourceRemoved))
        {
            return Err(ProtocolError::InvalidTransition);
        }
        self.committed = true;
        Ok(())
    }

    pub fn cleanup_authorized(&self, index: usize, currently_enabled: bool) -> bool {
        self.committed
            && self.policy.delete_source_after_commit
            && currently_enabled
            && self.file_phase(index) == Some(FilePhase::Published)
    }

    /// Call only after authorized private-source deletion/sync reconciliation.
    pub fn confirm_source_removed(
        &mut self,
        index: usize,
        currently_enabled: bool,
    ) -> Result<(), ProtocolError> {
        if self.file_phase(index) == Some(FilePhase::SourceRemoved) {
            return Ok(());
        }
        if !self.cleanup_authorized(index, currently_enabled) {
            return Err(ProtocolError::InvalidTransition);
        }
        self.advance(index, FilePhase::Published, FilePhase::SourceRemoved)
    }

    fn advance(
        &mut self,
        index: usize,
        expected: FilePhase,
        next: FilePhase,
    ) -> Result<(), ProtocolError> {
        let state = self
            .files
            .get_mut(index)
            .ok_or(ProtocolError::UnknownFile)?;
        if state.phase == next {
            return Ok(());
        }
        if state.phase != expected {
            return Err(ProtocolError::InvalidTransition);
        }
        state.phase = next;
        Ok(())
    }
}
