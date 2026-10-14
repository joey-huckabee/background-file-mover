//! Claim orchestration stays in parent; observation/allocation/rename in children.
use mover_core::{ClaimIntent, ObjectIdentity};
use mover_fs::{ClaimError, LocalClaimLock};
use mover_store::{Accepted, Store};
use serde::{Deserialize, Serialize};
use std::{
    io::{Read, Write},
    os::{fd::AsFd, unix::net::UnixStream},
    sync::atomic::AtomicBool,
    time::Duration,
};
const LIMIT: usize = 32768;
#[derive(Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct ClaimWire {
    job_id: i64,
    file_index: usize,
    root_path: String,
    source_name: String,
    private_name: String,
    objects: [String; 4],
}
impl ClaimWire {
    fn new(c: &ClaimIntent) -> Self {
        Self {
            job_id: c.job_id,
            file_index: c.file_index,
            root_path: c.root_path.clone(),
            source_name: c.source_name.clone(),
            private_name: c.private_name.clone(),
            objects: [&c.root, &c.parent, &c.area, &c.source].map(ObjectIdentity::encode),
        }
    }
    fn decode(self) -> Result<ClaimIntent, ClaimError> {
        if self.job_id <= 0
            || self.file_index >= 256
            || self.private_name != format!("{}-{}", self.job_id, self.file_index)
        {
            return Err(ClaimError::Blocked("invalid claim assignment"));
        }
        mover_core::FileSpec::new(&self.source_name, None)
            .map_err(|_| ClaimError::Blocked("invalid claim path"))?;
        let objects = self
            .objects
            .iter()
            .map(|s| ObjectIdentity::decode(s).ok_or(ClaimError::Blocked("invalid claim identity")))
            .collect::<Result<Vec<_>, _>>()?;
        Ok(ClaimIntent {
            job_id: self.job_id,
            file_index: self.file_index,
            root_path: self.root_path,
            source_name: self.source_name,
            private_name: self.private_name,
            root: objects[0].clone(),
            parent: objects[1].clone(),
            area: objects[2].clone(),
            source: objects[3].clone(),
        })
    }
}
#[derive(Serialize, Deserialize)]
#[serde(tag = "operation", rename_all = "snake_case", deny_unknown_fields)]
enum Assignment {
    Observe {
        version: u32,
        job_id: i64,
        file_index: usize,
        root_path: String,
        source_name: String,
        expected_size: Option<u64>,
    },
    Allocate {
        version: u32,
        claim: ClaimWire,
    },
    Apply {
        version: u32,
        claim: ClaimWire,
    },
    Validate {
        version: u32,
        claim: ClaimWire,
    },
}
#[derive(Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
enum Failure {
    MissingSource,
    ExpectedSizeMismatch,
    Blocked,
}
#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Receipt {
    version: u32,
    claim: Option<ClaimWire>,
    error: Option<Failure>,
}
fn request(
    assignment: &Assignment,
    guard: &LocalClaimLock,
    stop: &AtomicBool,
) -> Result<ClaimIntent, ClaimError> {
    let bytes = serde_json::to_vec(assignment)
        .map_err(|_| ClaimError::Blocked("claim assignment encoding"))?;
    if bytes.len() > LIMIT {
        return Err(ClaimError::Blocked("claim assignment too large"));
    }
    let bytes = super::payload::exchange(
        &bytes,
        "--internal-claim-worker",
        guard,
        guard,
        stop,
        LIMIT as u64,
    )
    .map_err(|_| ClaimError::Blocked("claim worker outcome uncertain"))?;
    let reply: Receipt =
        serde_json::from_slice(&bytes).map_err(|_| ClaimError::Blocked("invalid claim receipt"))?;
    if reply.version != 1 {
        return Err(ClaimError::Blocked("invalid claim receipt version"));
    }
    match (reply.claim, reply.error) {
        (Some(c), None) => c.decode(),
        (None, Some(Failure::MissingSource)) => Err(ClaimError::MissingSource),
        (None, Some(Failure::ExpectedSizeMismatch)) => Err(ClaimError::ExpectedSizeMismatch),
        _ => Err(ClaimError::Blocked("claim operation blocked")),
    }
}
pub(crate) fn claim(
    store: &Store,
    guard: &LocalClaimLock,
    stop: &AtomicBool,
    job_id: i64,
    index: usize,
) -> Result<Accepted, ClaimError> {
    let job = store
        .get(job_id)?
        .ok_or(ClaimError::Blocked("unknown job"))?;
    if !guard.matches_path(&job.context.source_root_path) {
        return Err(ClaimError::Blocked("source scope changed"));
    }
    let intent = match store.claim_intent(job_id, index)? {
        Some((_, true)) => return Ok(job), // Never reopen a producer's reused path.
        Some((intent, false)) => intent,
        None => {
            let file = job
                .recording
                .submission()
                .files()
                .get(index)
                .ok_or(ClaimError::Blocked("unknown file"))?;
            let name = if job.context.source_relative_directory.is_empty() {
                file.relative_path().to_owned()
            } else {
                format!(
                    "{}/{}",
                    job.context.source_relative_directory,
                    file.relative_path()
                )
            };
            let observed = request(
                &Assignment::Observe {
                    version: 1,
                    job_id,
                    file_index: index,
                    root_path: job.context.source_root_path.clone(),
                    source_name: name.clone(),
                    expected_size: file.expected_size(),
                },
                guard,
                stop,
            )?;
            if observed.job_id != job_id
                || observed.file_index != index
                || observed.root_path != job.context.source_root_path
                || observed.source_name != name
                || file
                    .expected_size()
                    .is_some_and(|n| n != observed.source.size)
            {
                return Err(ClaimError::Blocked("observation receipt mismatch"));
            }
            store.claim_capacity(observed.source.size)?;
            let allocated = request(
                &Assignment::Allocate {
                    version: 1,
                    claim: ClaimWire::new(&observed),
                },
                guard,
                stop,
            )?;
            let mut expected = observed.clone();
            expected.area = allocated.area.clone();
            if allocated != expected {
                return Err(ClaimError::Blocked("allocation receipt mismatch"));
            }
            store.begin_claim(&allocated)?;
            allocated
        }
    };
    if store.claim_intent(job_id, index)? != Some((intent.clone(), false)) {
        return Err(ClaimError::Blocked(
            "matching unfinished claim intent required",
        ));
    }
    let applied = request(
        &Assignment::Apply {
            version: 1,
            claim: ClaimWire::new(&intent),
        },
        guard,
        stop,
    )?;
    if applied != intent {
        return Err(ClaimError::Blocked("applied claim receipt mismatch"));
    }
    Ok(store.finish_claim(&intent)?)
}
pub fn worker() -> Result<(), Box<dyn std::error::Error>> {
    let mut channel = UnixStream::from(std::io::stderr().as_fd().try_clone_to_owned()?);
    channel.set_read_timeout(Some(Duration::from_secs(3)))?;
    channel.set_write_timeout(Some(Duration::from_secs(3)))?;
    let mut bytes = Vec::new();
    (&mut channel)
        .take(LIMIT as u64 + 1)
        .read_to_end(&mut bytes)?;
    if bytes.len() > LIMIT {
        return Err("claim assignment too large".into());
    }
    let assignment: Assignment = serde_json::from_slice(&bytes)?;
    let (version, path) = match &assignment {
        Assignment::Observe {
            version, root_path, ..
        } => (*version, root_path),
        Assignment::Allocate { version, claim }
        | Assignment::Apply { version, claim }
        | Assignment::Validate { version, claim } => (*version, &claim.root_path),
    };
    if version != 1 {
        return Err("invalid claim protocol version".into());
    }
    let path = path.clone();
    mover_fs::validate_payload_locks(&path, &path)?;
    let result = match assignment {
        Assignment::Observe {
            job_id,
            file_index,
            root_path,
            source_name,
            expected_size,
            ..
        } => mover_fs::observe_claim(job_id, file_index, &root_path, &source_name, expected_size),
        Assignment::Allocate { claim, .. } => {
            claim.decode().and_then(|c| mover_fs::allocate_claim(&c))
        }
        Assignment::Apply { claim, .. } => claim.decode().and_then(|c| {
            mover_fs::apply_claim_effect(&c)?;
            Ok(c)
        }),
        Assignment::Validate { claim, .. } => claim.decode().and_then(|c| {
            mover_fs::validate_claim_scope(&c)?;
            Ok(c)
        }),
    };
    mover_fs::validate_payload_locks(&path, &path)?;
    let reply = match result {
        Ok(c) => Receipt {
            version: 1,
            claim: Some(ClaimWire::new(&c)),
            error: None,
        },
        Err(e) => Receipt {
            version: 1,
            claim: None,
            error: Some(match e {
                ClaimError::MissingSource => Failure::MissingSource,
                ClaimError::ExpectedSizeMismatch => Failure::ExpectedSizeMismatch,
                _ => Failure::Blocked,
            }),
        },
    };
    let bytes = serde_json::to_vec(&reply)?;
    if bytes.len() > LIMIT {
        return Err("claim receipt too large".into());
    }
    channel.write_all(&bytes)?;
    Ok(())
}
pub(crate) fn validate_handoff(
    store: &Store,
    guard: &LocalClaimLock,
    stop: &AtomicBool,
    id: i64,
) -> Result<(), ClaimError> {
    let (intent, done) = store
        .claim_intent(id, 0)?
        .ok_or(ClaimError::Blocked("missing handoff claim"))?;
    if !done || !guard.matches_path(&intent.root_path) {
        return Err(ClaimError::Blocked("incomplete handoff"));
    }
    let reply = request(
        &Assignment::Validate {
            version: 1,
            claim: ClaimWire::new(&intent),
        },
        guard,
        stop,
    )?;
    if reply != intent {
        return Err(ClaimError::Blocked("handoff validation receipt mismatch"));
    }
    Ok(())
}
