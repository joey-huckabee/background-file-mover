//! `Mover-Retry-Context` v1 codec (docs/api/RETRY-HEADER.candidate.md).
//!
//! Mirrors the reference checker docs/api/check_retry_context_candidate.py and is
//! tested against its vectors. Validation order and error classes follow it:
//! header occurrence, value size, encoding, decoded size, payload, canonical form,
//! selection, digest, epoch count, duplicate epochs, then instance.
use serde::Deserialize;

pub(crate) const MAX_VALUE: usize = 6144;
pub(crate) const MAX_DECODED: usize = 4096;
pub(crate) const MAX_SELECTION: usize = 256;

/// Reference error classes; the HTTP layer maps them to statuses.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(crate) enum ContextError {
    HeadTooLarge,
    HeaderOccurrence,
    ValueTooLarge,
    InvalidEncoding,
    DecodedTooLarge,
    InvalidPayload,
    NoncanonicalPayload,
    InvalidSelection,
    SelectionMismatch,
    DuplicateEpochMismatch,
    InstanceMismatch,
}
impl ContextError {
    #[cfg(test)]
    fn code(self) -> &'static str {
        match self {
            Self::HeadTooLarge => "head_too_large",
            Self::HeaderOccurrence => "header_occurrence",
            Self::ValueTooLarge => "value_too_large",
            Self::InvalidEncoding => "invalid_encoding",
            Self::DecodedTooLarge => "decoded_too_large",
            Self::InvalidPayload => "invalid_payload",
            Self::NoncanonicalPayload => "noncanonical_payload",
            Self::InvalidSelection => "invalid_selection",
            Self::SelectionMismatch => "selection_mismatch",
            Self::DuplicateEpochMismatch => "duplicate_epoch_mismatch",
            Self::InstanceMismatch => "instance_mismatch",
        }
    }
}

/// A validated request: exact ordered selection and its frozen context.
#[derive(Debug, PartialEq, Eq)]
pub(crate) struct RetryContext {
    pub(crate) job_ids: Vec<i64>,
    pub(crate) review_epochs: Vec<Option<u32>>,
    pub(crate) reason: String,
    pub(crate) instance_id: String,
    /// Exact canonical decoded payload bytes (basis of the receipt key).
    pub(crate) canonical: Vec<u8>,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Payload {
    version: u8,
    instance_id: String,
    selection_sha256: String,
    review_epochs: Vec<Option<u32>>,
    reason: String,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Selection {
    job_ids: Vec<i64>,
}

fn lower_hex(s: &str, len: usize) -> bool {
    s.len() == len
        && s.bytes()
            .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
}

/// Strict job selection body: exactly `{"job_ids":[...]}`, 1-256 exact positive i64.
pub(crate) fn selection(body: &[u8]) -> Result<Vec<i64>, ContextError> {
    let s: Selection = serde_json::from_slice(body).map_err(|_| ContextError::InvalidSelection)?;
    if s.job_ids.is_empty() || s.job_ids.len() > MAX_SELECTION || s.job_ids.iter().any(|i| *i < 1) {
        return Err(ContextError::InvalidSelection);
    }
    Ok(s.job_ids)
}

/// `BFM-RETRY-SELECTION\0v1\0` + u16 count + each ID as 8-byte big-endian.
pub(crate) fn selection_frame(ids: &[i64]) -> Vec<u8> {
    let mut frame = b"BFM-RETRY-SELECTION\0v1\0".to_vec();
    frame.extend_from_slice(&(ids.len() as u16).to_be_bytes());
    for id in ids {
        frame.extend_from_slice(&id.to_be_bytes());
    }
    frame
}

pub(crate) fn selection_digest(ids: &[i64]) -> String {
    mover_fs::sha256_hex(&selection_frame(ids))
}

fn canonical(p: &Payload) -> Vec<u8> {
    let epochs: Vec<String> = p
        .review_epochs
        .iter()
        .map(|e| e.map_or_else(|| "null".to_owned(), |v| v.to_string()))
        .collect();
    let mut reason = String::with_capacity(p.reason.len());
    for c in p.reason.chars() {
        match c {
            '"' => reason.push_str("\\\""),
            '\\' => reason.push_str("\\\\"),
            c => reason.push(c),
        }
    }
    format!(
        "{{\"version\":{},\"instance_id\":\"{}\",\"selection_sha256\":\"{}\",\"review_epochs\":[{}],\"reason\":\"{}\"}}",
        p.version,
        p.instance_id,
        p.selection_sha256,
        epochs.join(","),
        reason
    )
    .into_bytes()
}

fn valid_fields(p: &Payload) -> bool {
    p.version == 1
        && lower_hex(&p.instance_id, 32)
        && lower_hex(&p.selection_sha256, 64)
        && (1..=MAX_SELECTION).contains(&p.review_epochs.len())
        && (1..=512).contains(&p.reason.len())
        && !p.reason.trim().is_empty()
        && !p.reason.chars().any(char::is_control)
}

const ALPHABET: &[u8; 64] = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_";

pub(crate) fn base64url(bytes: &[u8]) -> String {
    let mut out = String::with_capacity(bytes.len().div_ceil(3) * 4);
    for chunk in bytes.chunks(3) {
        let n = (u32::from(chunk[0]) << 16)
            | (u32::from(*chunk.get(1).unwrap_or(&0)) << 8)
            | u32::from(*chunk.get(2).unwrap_or(&0));
        for i in 0..=chunk.len() {
            out.push(ALPHABET[((n >> (18 - 6 * i)) & 63) as usize] as char);
        }
    }
    out
}

fn unbase64url(text: &str) -> Option<Vec<u8>> {
    let value = |c: u8| ALPHABET.iter().position(|a| *a == c).map(|p| p as u32);
    if text.len() % 4 == 1 {
        return None;
    }
    let mut out = Vec::with_capacity(text.len() * 3 / 4);
    for chunk in text.as_bytes().chunks(4) {
        let mut n = 0_u32;
        for (i, c) in chunk.iter().enumerate() {
            n |= value(*c)? << (18 - 6 * i);
        }
        let bytes = [(n >> 16) as u8, (n >> 8) as u8, n as u8];
        out.extend_from_slice(&bytes[..chunk.len() - 1]);
    }
    // Canonical only: re-encoding must reproduce the input (no stray bits).
    (base64url(&out) == text).then_some(out)
}

/// Decode and validate one request. `values` are the header occurrences after
/// HTTP framing; `head_bytes`, when known, is the raw request head size.
pub(crate) fn decode(
    body: &[u8],
    values: &[&[u8]],
    expected_instance: &str,
    head_bytes: Option<usize>,
) -> Result<RetryContext, ContextError> {
    if head_bytes.is_some_and(|n| n > 8192) {
        return Err(ContextError::HeadTooLarge);
    }
    let [value] = values else {
        return Err(ContextError::HeaderOccurrence);
    };
    if value.len() > MAX_VALUE {
        return Err(ContextError::ValueTooLarge);
    }
    let value = std::str::from_utf8(value).map_err(|_| ContextError::InvalidEncoding)?;
    let token = value
        .strip_prefix("v1.")
        .ok_or(ContextError::InvalidEncoding)?;
    if token.is_empty()
        || !token
            .bytes()
            .all(|b| b.is_ascii_alphanumeric() || b == b'-' || b == b'_')
    {
        return Err(ContextError::InvalidEncoding);
    }
    let raw = unbase64url(token).ok_or(ContextError::InvalidEncoding)?;
    if raw.len() > MAX_DECODED {
        return Err(ContextError::DecodedTooLarge);
    }
    let payload: Payload =
        serde_json::from_slice(&raw).map_err(|_| ContextError::InvalidPayload)?;
    if !valid_fields(&payload) {
        return Err(ContextError::InvalidPayload);
    }
    if canonical(&payload) != raw {
        return Err(ContextError::NoncanonicalPayload);
    }
    let ids = selection(body)?;
    if payload.selection_sha256 != selection_digest(&ids)
        || payload.review_epochs.len() != ids.len()
    {
        return Err(ContextError::SelectionMismatch);
    }
    let mut seen = std::collections::BTreeMap::new();
    for (id, epoch) in ids.iter().zip(&payload.review_epochs) {
        if *seen.entry(*id).or_insert(*epoch) != *epoch {
            return Err(ContextError::DuplicateEpochMismatch);
        }
    }
    if payload.instance_id != expected_instance {
        return Err(ContextError::InstanceMismatch);
    }
    Ok(RetryContext {
        job_ids: ids,
        review_epochs: payload.review_epochs.clone(),
        reason: payload.reason.clone(),
        instance_id: payload.instance_id.clone(),
        canonical: raw,
    })
}

/// Opaque per-job receipt key: one canonical request context for one account.
/// Occurrence positions are stored separately with each outcome.
pub(crate) fn receipt_key(principal: &str, context: &RetryContext) -> String {
    let mut frame = b"BFM-RETRY-RECEIPT\0v1\0".to_vec();
    frame.extend_from_slice(principal.as_bytes());
    frame.push(0);
    frame.extend_from_slice(&context.canonical);
    mover_fs::sha256_hex(&frame)
}

#[cfg(test)]
mod tests {
    use super::*;

    const VECTORS: &str = include_str!("retry_context.vectors.json");

    fn body_bytes(body: &serde_json::Value) -> Vec<u8> {
        serde_json::to_vec(body).unwrap()
    }

    #[test]
    fn known_answers_match_frames_digests_and_headers() {
        let v: serde_json::Value = serde_json::from_str(VECTORS).unwrap();
        for k in v["known_answers"].as_array().unwrap() {
            let ids = selection(&body_bytes(&k["body"])).unwrap();
            let frame: String = selection_frame(&ids)
                .iter()
                .map(|b| format!("{b:02x}"))
                .collect();
            assert_eq!(frame, k["selection_frame_hex"], "{}", k["id"]);
            assert_eq!(
                selection_digest(&ids),
                k["context"]["selection_sha256"],
                "{}",
                k["id"]
            );
            let header = k["header_value"].as_str().unwrap();
            let ctx = decode(
                &body_bytes(&k["body"]),
                &[header.as_bytes()],
                k["context"]["instance_id"].as_str().unwrap(),
                None,
            )
            .unwrap();
            assert_eq!(
                format!("v1.{}", base64url(&ctx.canonical)),
                header,
                "{}",
                k["id"]
            );
            assert_eq!(ctx.reason, k["context"]["reason"], "{}", k["id"]);
        }
    }

    #[test]
    fn every_decoding_case_matches_the_reference_outcome() {
        let v: serde_json::Value = serde_json::from_str(VECTORS).unwrap();
        let cases = v["decoding_cases"].as_array().unwrap();
        assert!(cases.len() >= 52);
        for case in cases {
            let values: Vec<Vec<u8>> = case["header_values"]
                .as_array()
                .unwrap()
                .iter()
                .map(|h| h.as_str().unwrap().as_bytes().to_vec())
                .collect();
            let refs: Vec<&[u8]> = values.iter().map(Vec::as_slice).collect();
            let body = body_bytes(&case["body"]);
            let result = decode(
                &body,
                &refs,
                case["expected_instance"].as_str().unwrap(),
                case["head_bytes"].as_u64().map(|n| n as usize),
            );
            let expected = case["outcome"].as_str().unwrap();
            match result {
                Ok(ctx) => {
                    assert_eq!(expected, "valid", "{}", case["id"]);
                    let epochs: Vec<serde_json::Value> = ctx
                        .review_epochs
                        .iter()
                        .map(|e| e.map_or(serde_json::Value::Null, serde_json::Value::from))
                        .collect();
                    assert_eq!(
                        serde_json::Value::from(epochs),
                        case["expected_epochs"],
                        "{}",
                        case["id"]
                    );
                }
                Err(e) => assert_eq!(e.code(), expected, "{}", case["id"]),
            }
        }
    }

    #[test]
    fn maximum_width_payload_fits_the_bounds() {
        let v: serde_json::Value = serde_json::from_str(VECTORS).unwrap();
        let p = Payload {
            version: 1,
            instance_id: "f".repeat(32),
            selection_sha256: "f".repeat(64),
            review_epochs: vec![Some(u32::MAX); 256],
            reason: "\\".repeat(512),
        };
        let raw = canonical(&p);
        assert_eq!(
            raw.len() as u64,
            v["bounds"]["maximum_canonical_payload_bytes"]
                .as_u64()
                .unwrap()
        );
        assert_eq!(
            (3 + base64url(&raw).len()) as u64,
            v["bounds"]["maximum_canonical_value_bytes"]
                .as_u64()
                .unwrap()
        );
    }

    #[test]
    fn receipt_key_depends_on_principal_and_exact_context() {
        let ctx = |reason: &str| RetryContext {
            job_ids: vec![1],
            review_epochs: vec![Some(0)],
            reason: reason.into(),
            instance_id: "0".repeat(32),
            canonical: reason.as_bytes().to_vec(),
        };
        let a = receipt_key("p1", &ctx("x"));
        assert_eq!(a.len(), 64);
        assert_eq!(a, receipt_key("p1", &ctx("x")));
        assert_ne!(a, receipt_key("p2", &ctx("x")));
        assert_ne!(a, receipt_key("p1", &ctx("y")));
    }
}
