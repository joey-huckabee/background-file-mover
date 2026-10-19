//! Startup supervisor orchestration; all source I/O stays in an inherited worker.
use mover_fs::{EnrollmentAuthorization, EnrollmentReceipt, LocalClaimLock, SourceAuthorization};
use mover_store::{Store, StoreError};
use serde::{Deserialize, Serialize};
use std::{
    io::{Read, Write},
    os::{fd::AsFd, unix::net::UnixStream},
    sync::atomic::AtomicBool,
    time::Duration,
};
const LIMIT: u64 = 24576;

#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Request {
    version: u32,
    path: String,
    source: SourceAuthorization,
    receipt: String,
    object: Option<String>,
    create: bool,
}

#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Reply {
    version: u32,
    authorization: Option<EnrollmentAuthorization>,
    diagnostic: Option<String>,
}

pub fn authorize(
    config: &crate::Config,
    store: &Store,
    guard: &mut LocalClaimLock,
    initialize: bool,
    stop: &AtomicBool,
) -> Result<(), Box<dyn std::error::Error>> {
    let source = guard
        .source_authorization()
        .ok_or("source authorization required")?
        .clone();
    let receipt = EnrollmentReceipt::new(store.instance_id()?, &source).encode();
    let prior = store.source_ownership()?;
    if initialize && prior.is_none() {
        mover_fs::qualification_pause("enrollment_intent")?;
        store.prepare_source_ownership(
            &config.source_root,
            &source.binding.encode(),
            &source.observation,
            &receipt,
        )?;
        mover_fs::qualification_pause("enrollment_prepared")?;
    } else if prior.is_none() {
        return Err(StoreError::SourceEnrollmentRequired.into());
    }
    store.enroll_source(
        &config.source_root,
        &source.binding.encode(),
        &source.observation,
    )?;
    let ownership = store
        .source_ownership()?
        .ok_or(StoreError::SourceEnrollmentRequired)?;
    if ownership.receipt != receipt {
        return Err(StoreError::SourceRootChanged.into());
    }
    if ownership.object.is_none() && !initialize {
        return Err(
            "source enrollment pending; explicit initialization retry or review required".into(),
        );
    }
    let request = Request {
        version: 1,
        path: config.source_root.clone(),
        source,
        receipt: receipt.clone(),
        create: ownership.object.is_none(),
        object: ownership.object,
    };
    let bytes = serde_json::to_vec(&request)?;
    if bytes.len() as u64 > LIMIT {
        return Err("enrollment assignment too large".into());
    }
    let bytes = crate::payload::exchange(
        &bytes,
        "--internal-enrollment-worker",
        guard,
        guard,
        stop,
        LIMIT,
    ).map_err(|_| "source enrollment worker stopped, failed or outcome uncertain; preserve original state and source for review")?;
    let reply: Reply = serde_json::from_slice(&bytes)?;
    if reply.version != 1 {
        return Err("invalid source enrollment reply version".into());
    }
    let authorization = match (reply.authorization, reply.diagnostic) {
        (Some(authorization), None) => authorization,
        (None, Some(detail)) if crate::diagnostic::valid(&detail) => {
            return Err(format!(
                "source enrollment {detail}; preserve original state and source for review"
            )
            .into());
        }
        _ => return Err("invalid source enrollment reply".into()),
    };
    if authorization.receipt != receipt
        || mover_core::ObjectIdentity::decode(&authorization.object).is_none()
        || request
            .object
            .as_ref()
            .is_some_and(|o| o != &authorization.object)
    {
        return Err("invalid enrollment worker receipt".into());
    }
    if request.create {
        store.activate_source_ownership(&receipt, &authorization.object)?;
        mover_fs::qualification_pause("enrollment_active")?;
    }
    guard.attach_enrollment(authorization)?;
    Ok(())
}

pub fn worker() -> Result<(), Box<dyn std::error::Error>> {
    let mut channel = UnixStream::from(std::io::stderr().as_fd().try_clone_to_owned()?);
    channel.set_read_timeout(Some(Duration::from_secs(3)))?;
    let _instance = mover_fs::InstanceGuard::receive(&mut channel)?;
    channel.set_write_timeout(Some(Duration::from_secs(3)))?;
    let mut bytes = Vec::new();
    (&mut channel).take(LIMIT + 1).read_to_end(&mut bytes)?;
    if bytes.len() as u64 > LIMIT {
        return Err("enrollment assignment too large".into());
    }
    let request: Request = serde_json::from_slice(&bytes)?;
    if request.version != 1
        || request.source.enrollment.is_some()
        || request.create != request.object.is_none()
    {
        return Err("invalid enrollment assignment".into());
    }
    let mut stage = "custody_before";
    let result = (|| -> Result<EnrollmentAuthorization, Box<dyn std::error::Error>> {
        request.source.validate(&request.path)?;
        mover_fs::validate_payload_locks(&request.path, &request.path)?;
        stage = if request.create {
            "create_receipt"
        } else {
            "verify_receipt"
        };
        let authorization = if request.create {
            mover_fs::create_source_enrollment(&request.path, &request.source, &request.receipt)?
        } else {
            let authorization = EnrollmentAuthorization {
                receipt: request.receipt,
                object: request.object.ok_or("missing enrollment identity")?,
            };
            authorization.validate(&request.path, &request.source)?;
            authorization
        };
        stage = "custody_after";
        request.source.validate(&request.path)?;
        mover_fs::validate_payload_locks(&request.path, &request.path)?;
        Ok(authorization)
    })();
    let reply = match result {
        Ok(authorization) => Reply {
            version: 1,
            authorization: Some(authorization),
            diagnostic: None,
        },
        Err(error) => Reply {
            version: 1,
            authorization: None,
            diagnostic: Some(
                format!("{stage}: {}", crate::diagnostic::describe(error.as_ref()))
                    .chars()
                    .take(240)
                    .collect(),
            ),
        },
    };
    channel.write_all(&serde_json::to_vec(&reply)?)?;
    channel.shutdown(std::net::Shutdown::Write)?;
    Ok(())
}
