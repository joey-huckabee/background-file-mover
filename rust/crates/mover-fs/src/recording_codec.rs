//! Inactive producer/v2 data codecs. No Store, worker, filesystem or HTTP calls.
//! Validation here proves shape/assertions only, never authority or custody.
use mover_core::{ProducerRequest, RecordingId, RequestValidationError, parse_decimal_u64};
use serde::{
    Deserialize, Deserializer, Serialize,
    de::{self, DeserializeOwned, MapAccess, SeqAccess, Visitor},
};
use serde_json::{Map, Number, Value};
use sha2::{Digest, Sha256};
use std::{collections::BTreeMap, fmt};

pub const MAX_PRODUCER_BYTES: usize = 65536;
pub const MAX_MANIFEST_BYTES: usize = 131072;
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum CodecError {
    TooLarge,
    InvalidJson,
    InvalidSubmission,
    InvalidFilePaths,
    IdempotencyKeyConflict,
    InvalidManifest,
}
impl fmt::Display for CodecError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{self:?}")
    }
}
impl std::error::Error for CodecError {}
type Result<T> = std::result::Result<T, CodecError>;

// serde_json::Value alone silently overwrites repeated map keys. Decode every
// object through this visitor first; escaped-equivalent keys are duplicates too.
struct UniqueValue(Value);
impl<'de> Deserialize<'de> for UniqueValue {
    fn deserialize<D: Deserializer<'de>>(d: D) -> std::result::Result<Self, D::Error> {
        struct UniqueVisitor;
        impl<'de> Visitor<'de> for UniqueVisitor {
            type Value = UniqueValue;
            fn expecting(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
                f.write_str("JSON without duplicate keys")
            }
            fn visit_bool<E: de::Error>(self, v: bool) -> std::result::Result<Self::Value, E> {
                Ok(UniqueValue(Value::Bool(v)))
            }
            fn visit_i64<E: de::Error>(self, v: i64) -> std::result::Result<Self::Value, E> {
                Ok(UniqueValue(Value::Number(v.into())))
            }
            fn visit_u64<E: de::Error>(self, v: u64) -> std::result::Result<Self::Value, E> {
                Ok(UniqueValue(Value::Number(v.into())))
            }
            fn visit_f64<E: de::Error>(self, v: f64) -> std::result::Result<Self::Value, E> {
                Number::from_f64(v)
                    .map(|n| UniqueValue(Value::Number(n)))
                    .ok_or_else(|| E::custom("nonfinite number"))
            }
            fn visit_str<E: de::Error>(self, v: &str) -> std::result::Result<Self::Value, E> {
                Ok(UniqueValue(Value::String(v.into())))
            }
            fn visit_string<E: de::Error>(self, v: String) -> std::result::Result<Self::Value, E> {
                Ok(UniqueValue(Value::String(v)))
            }
            fn visit_unit<E: de::Error>(self) -> std::result::Result<Self::Value, E> {
                Ok(UniqueValue(Value::Null))
            }
            fn visit_seq<A: SeqAccess<'de>>(
                self,
                mut a: A,
            ) -> std::result::Result<Self::Value, A::Error> {
                let mut v = Vec::new();
                while let Some(UniqueValue(item)) = a.next_element()? {
                    v.push(item);
                }
                Ok(UniqueValue(Value::Array(v)))
            }
            fn visit_map<A: MapAccess<'de>>(
                self,
                mut a: A,
            ) -> std::result::Result<Self::Value, A::Error> {
                let mut v = Map::new();
                while let Some((key, UniqueValue(item))) = a.next_entry::<String, UniqueValue>()? {
                    if v.insert(key, item).is_some() {
                        return Err(de::Error::custom("duplicate JSON key"));
                    }
                }
                Ok(UniqueValue(Value::Object(v)))
            }
        }
        d.deserialize_any(UniqueVisitor)
    }
}
fn json<T: DeserializeOwned>(raw: &[u8], limit: usize, shape_error: CodecError) -> Result<T> {
    if raw.len() > limit {
        return Err(CodecError::TooLarge);
    }
    if raw.starts_with(&[0xef, 0xbb, 0xbf]) {
        return Err(CodecError::InvalidJson);
    }
    let mut decoder = serde_json::Deserializer::from_slice(raw);
    let UniqueValue(value) =
        UniqueValue::deserialize(&mut decoder).map_err(|_| CodecError::InvalidJson)?;
    decoder.end().map_err(|_| CodecError::InvalidJson)?;
    serde_json::from_value(value).map_err(|_| shape_error)
}
fn supplied_map<'de, D: Deserializer<'de>>(
    d: D,
) -> std::result::Result<Option<BTreeMap<String, String>>, D::Error> {
    BTreeMap::<String, String>::deserialize(d).map(Some)
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct ProducerWire {
    generator_id: String,
    recording_id: String,
    source_directory: String,
    files: Vec<String>,
    #[serde(default, deserialize_with = "supplied_map")]
    expected_sizes_bytes: Option<BTreeMap<String, String>>,
}
pub fn decode_producer(raw: &[u8]) -> Result<ProducerRequest> {
    let wire: ProducerWire = json(raw, MAX_PRODUCER_BYTES, CodecError::InvalidSubmission)?;
    let id = RecordingId::parse(&wire.recording_id).map_err(|_| CodecError::InvalidSubmission)?;
    let sizes = wire
        .expected_sizes_bytes
        .map(|values| {
            values
                .into_iter()
                .map(|(p, n)| parse_decimal_u64(&n).map(|n| (p, n)))
                .collect::<std::result::Result<BTreeMap<_, _>, _>>()
        })
        .transpose()
        .map_err(|_| CodecError::InvalidSubmission)?;
    ProducerRequest::new(
        wire.generator_id,
        id,
        wire.source_directory,
        wire.files,
        sizes,
    )
    .map_err(|e| {
        if e == RequestValidationError::InvalidFilePaths {
            CodecError::InvalidFilePaths
        } else {
            CodecError::InvalidSubmission
        }
    })
}
/// Caller handles HTTP field OWS and duplicate occurrence rules before this.
pub fn validate_idempotency_key(id: RecordingId, value: &str) -> Result<()> {
    if RecordingId::parse(value).ok() == Some(id) {
        Ok(())
    } else {
        Err(CodecError::IdempotencyKeyConflict)
    }
}
pub fn identity_frame(request: &ProducerRequest) -> Vec<u8> {
    fn string(bytes: &mut Vec<u8>, text: &str) {
        // Constructor bounds each string to at most 4095 UTF-8 bytes.
        bytes.extend_from_slice(&(text.len() as u32).to_be_bytes());
        bytes.extend_from_slice(text.as_bytes());
    }
    let mut bytes = b"BFM-REQUEST-IDENTITY\0v1\0".to_vec();
    string(&mut bytes, request.generator_id());
    string(&mut bytes, &request.recording_id().to_string());
    string(&mut bytes, request.source_directory());
    let mut files: Vec<_> = request.files().iter().collect();
    files.sort_by(|a, b| {
        a.relative_path()
            .as_bytes()
            .cmp(b.relative_path().as_bytes())
    });
    bytes.extend_from_slice(&(files.len() as u32).to_be_bytes());
    for f in &files {
        string(&mut bytes, f.relative_path());
    }
    bytes.push(u8::from(request.expected_sizes_supplied()));
    if request.expected_sizes_supplied() {
        for f in &files {
            if let Some(n) = f.expected_size() {
                bytes.extend_from_slice(&n.to_be_bytes());
            }
        }
    }
    bytes
}
pub fn identity_sha256(request: &ProducerRequest) -> [u8; 32] {
    Sha256::digest(identity_frame(request)).into()
}
fn hex(bytes: &[u8]) -> String {
    bytes.iter().map(|b| format!("{b:02x}")).collect()
}
fn unhex<const N: usize>(text: &str) -> Result<[u8; N]> {
    if text.len() != N * 2
        || !text
            .bytes()
            .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
    {
        return Err(CodecError::InvalidManifest);
    }
    let mut out = [0; N];
    for (i, pair) in text.as_bytes().chunks_exact(2).enumerate() {
        let digit = |b| if b <= b'9' { b - b'0' } else { b - b'a' + 10 };
        out[i] = (digit(pair[0]) << 4) | digit(pair[1]);
    }
    Ok(out)
}

/// Caller-supplied measurements, NOT proof that any file exists or was verified.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct MeasuredFile {
    pub file_id: u16,
    pub path: String,
    pub size_bytes: u64,
    pub sha256: [u8; 32],
}
#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct RequestIdentityWire {
    version: u8,
    algorithm: String,
    sha256: String,
}
#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct FileWire {
    file_id: String,
    path: String,
    size_bytes: String,
    algorithm: String,
    sha256: String,
}
#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct ManifestWire {
    version: u8,
    instance_id: String,
    job_id: String,
    generator_id: String,
    recording_id: String,
    request_identity: RequestIdentityWire,
    files: Vec<FileWire>,
}
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ManifestV2 {
    instance_id: String,
    job_id: i64,
    generator_id: String,
    recording_id: RecordingId,
    request_sha256: [u8; 32],
    files: Vec<MeasuredFile>,
    bytes: Vec<u8>,
}
impl ManifestV2 {
    /// Use the ORIGINAL durable first-acceptance request/mapping, never a
    /// permuted transport replay. This checks supplied data, not its custody.
    pub fn build(
        instance_id: &str,
        job_id: i64,
        original: &ProducerRequest,
        mut files: Vec<MeasuredFile>,
    ) -> Result<Self> {
        if job_id <= 0 {
            return Err(CodecError::InvalidManifest);
        }
        unhex::<16>(instance_id)?;
        files.sort_by_key(|f| f.file_id);
        if files.len() != original.files().len()
            || files
                .iter()
                .zip(original.files())
                .enumerate()
                .any(|(i, (a, b))| usize::from(a.file_id) != i || a.path != b.relative_path())
        {
            return Err(CodecError::InvalidManifest);
        }
        let wire = ManifestWire {
            version: 2,
            instance_id: instance_id.into(),
            job_id: job_id.to_string(),
            generator_id: original.generator_id().into(),
            recording_id: original.recording_id().to_string(),
            request_identity: RequestIdentityWire {
                version: 1,
                algorithm: "sha256".into(),
                sha256: hex(&identity_sha256(original)),
            },
            files: files
                .into_iter()
                .map(|f| FileWire {
                    file_id: f.file_id.to_string(),
                    path: f.path,
                    size_bytes: f.size_bytes.to_string(),
                    algorithm: "sha256".into(),
                    sha256: hex(&f.sha256),
                })
                .collect(),
        };
        let bytes = serde_json::to_vec(&wire).map_err(|_| CodecError::InvalidManifest)?;
        Self::decode(&bytes)
    }
    /// Retain the exact input bytes (including legal whitespace/key ordering).
    /// A recovery caller MUST compare saved bytes/hash/object evidence, not
    /// reserialize this value to conceal a changed file. No re-encode API exists.
    pub fn decode(raw: &[u8]) -> Result<Self> {
        let wire: ManifestWire = json(raw, MAX_MANIFEST_BYTES, CodecError::InvalidManifest)?;
        if wire.version != 2
            || wire.request_identity.version != 1
            || wire.request_identity.algorithm != "sha256"
        {
            return Err(CodecError::InvalidManifest);
        }
        unhex::<16>(&wire.instance_id)?;
        let job_id = parse_decimal_u64(&wire.job_id)
            .ok()
            .and_then(|n| i64::try_from(n).ok())
            .filter(|n| *n > 0)
            .ok_or(CodecError::InvalidManifest)?;
        let id = RecordingId::parse(&wire.recording_id).map_err(|_| CodecError::InvalidManifest)?;
        if wire.recording_id != id.to_string() {
            return Err(CodecError::InvalidManifest);
        }
        let request_sha256 = unhex(&wire.request_identity.sha256)?;
        let mut files = Vec::new();
        for (i, f) in wire.files.into_iter().enumerate() {
            let n = parse_decimal_u64(&f.file_id).map_err(|_| CodecError::InvalidManifest)?;
            if n != i as u64 || n > 255 || f.algorithm != "sha256" {
                return Err(CodecError::InvalidManifest);
            }
            files.push(MeasuredFile {
                file_id: n as u16,
                path: f.path,
                size_bytes: parse_decimal_u64(&f.size_bytes)
                    .map_err(|_| CodecError::InvalidManifest)?,
                sha256: unhex(&f.sha256)?,
            });
        }
        // Reuse the pure new-request path/set/generator checks. '/' here is a
        // lexical placeholder only; no source is inferred from a manifest.
        ProducerRequest::new(
            wire.generator_id.clone(),
            id,
            "/".into(),
            files.iter().map(|f| f.path.clone()).collect(),
            None,
        )
        .map_err(|_| CodecError::InvalidManifest)?;
        Ok(Self {
            instance_id: wire.instance_id,
            job_id,
            generator_id: wire.generator_id,
            recording_id: id,
            request_sha256,
            files,
            bytes: raw.to_vec(),
        })
    }
    pub fn bytes(&self) -> &[u8] {
        &self.bytes
    }
    pub fn sha256(&self) -> [u8; 32] {
        Sha256::digest(&self.bytes).into()
    }
    pub fn files(&self) -> &[MeasuredFile] {
        &self.files
    }
    pub fn recording_id(&self) -> RecordingId {
        self.recording_id
    }
    pub fn job_id(&self) -> i64 {
        self.job_id
    }
    pub fn instance_id(&self) -> &str {
        &self.instance_id
    }
    pub fn request_sha256(&self) -> &[u8; 32] {
        &self.request_sha256
    }
    /// Service-side shape/binding check against ORIGINAL durable context. It
    /// still does not validate physical content, object identity or commitment.
    pub fn validate_context(
        &self,
        instance_id: &str,
        job_id: i64,
        original: &ProducerRequest,
    ) -> Result<()> {
        self.validate_request(original)?;
        if self.instance_id != instance_id
            || self.job_id != job_id
            || self
                .files
                .iter()
                .zip(original.files())
                .any(|(a, b)| a.path != b.relative_path())
        {
            return Err(CodecError::InvalidManifest);
        }
        Ok(())
    }
    /// For consumers with an original request: membership/digest, not unknown
    /// first-arrival ordering, physical content or authority.
    pub fn validate_request(&self, request: &ProducerRequest) -> Result<()> {
        let mut a: Vec<_> = self.files.iter().map(|f| f.path.as_str()).collect();
        a.sort_unstable();
        let mut b: Vec<_> = request.files().iter().map(|f| f.relative_path()).collect();
        b.sort_unstable();
        if self.generator_id != request.generator_id()
            || self.recording_id != request.recording_id()
            || self.request_sha256 != identity_sha256(request)
            || a != b
        {
            return Err(CodecError::InvalidManifest);
        }
        Ok(())
    }
}
#[cfg(test)]
mod tests;
