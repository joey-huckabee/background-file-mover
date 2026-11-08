//! New producer structure only. No admission, authority, policy, hashing or I/O.
use crate::FileSpec;
use std::{
    collections::{BTreeMap, BTreeSet},
    fmt,
};

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum RequestValidationError {
    InvalidRecordingId,
    InvalidSize,
    InvalidGenerator,
    InvalidSourceDirectory,
    InvalidFilePaths,
    InvalidSizeMap,
    InvalidFileCount,
}
impl fmt::Display for RequestValidationError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{self:?}")
    }
}
impl std::error::Error for RequestValidationError {}

#[derive(Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub struct RecordingId([u8; 16]);
impl RecordingId {
    /// Textual hex order, never platform/GUID mixed endian. No version restriction.
    pub fn parse(text: &str) -> Result<Self, RequestValidationError> {
        if text.len() != 36 {
            return Err(RequestValidationError::InvalidRecordingId);
        }
        let mut result = [0; 16];
        let mut digit = 0;
        for (i, c) in text.bytes().enumerate() {
            if matches!(i, 8 | 13 | 18 | 23) {
                if c != b'-' {
                    return Err(RequestValidationError::InvalidRecordingId);
                }
                continue;
            }
            let n = match c {
                b'0'..=b'9' => c - b'0',
                b'a'..=b'f' => c - b'a' + 10,
                b'A'..=b'F' => c - b'A' + 10,
                _ => return Err(RequestValidationError::InvalidRecordingId),
            };
            if digit & 1 == 0 {
                result[digit / 2] = n << 4;
            } else {
                result[digit / 2] |= n;
            }
            digit += 1;
        }
        Ok(Self(result))
    }
    pub fn from_bytes(bytes: [u8; 16]) -> Self {
        Self(bytes)
    }
    pub fn as_bytes(&self) -> &[u8; 16] {
        &self.0
    }
}
impl fmt::Display for RecordingId {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        for (i, b) in self.0.iter().enumerate() {
            if matches!(i, 4 | 6 | 8 | 10) {
                write!(f, "-")?;
            }
            write!(f, "{b:02x}")?;
        }
        Ok(())
    }
}

pub fn parse_decimal_u64(text: &str) -> Result<u64, RequestValidationError> {
    if text.is_empty() || text.len() > 20 || (text.len() > 1 && text.starts_with('0')) {
        return Err(RequestValidationError::InvalidSize);
    }
    text.bytes().try_fold(0_u64, |value, b| {
        if !b.is_ascii_digit() {
            return Err(RequestValidationError::InvalidSize);
        }
        value
            .checked_mul(10)
            .and_then(|n| n.checked_add(u64::from(b - b'0')))
            .ok_or(RequestValidationError::InvalidSize)
    })
}

/// Validated semantic assertions, retaining first-submission order. This does
/// not prove a bounded wire body, source authority, custody or measured sizes.
#[derive(Clone, Debug)]
pub struct ProducerRequest {
    generator_id: String,
    recording_id: RecordingId,
    source_directory: String,
    files: Vec<FileSpec>,
}
// Equality means immutable request equivalence; original arrival order remains
// separately available through files() for the first durable path/index map.
impl PartialEq for ProducerRequest {
    fn eq(&self, other: &Self) -> bool {
        self.same_assertions(other)
    }
}
impl Eq for ProducerRequest {}
impl ProducerRequest {
    pub fn new(
        generator_id: String,
        recording_id: RecordingId,
        source_directory: String,
        paths: Vec<String>,
        sizes: Option<BTreeMap<String, u64>>,
    ) -> Result<Self, RequestValidationError> {
        if generator_id.is_empty()
            || generator_id.len() > 128
            || !generator_id.as_bytes()[0].is_ascii_alphanumeric()
            || !generator_id
                .bytes()
                .all(|b| b.is_ascii_alphanumeric() || b"._-".contains(&b))
        {
            return Err(RequestValidationError::InvalidGenerator);
        }
        if !source_directory.starts_with('/')
            || source_directory.len() > 4095
            || source_directory.contains('\\')
            || source_directory.chars().any(char::is_control)
            || (source_directory != "/"
                && source_directory[1..]
                    .split('/')
                    .any(|p| p.is_empty() || p == "." || p == ".."))
        {
            return Err(RequestValidationError::InvalidSourceDirectory);
        }
        if paths.is_empty() || paths.len() > 256 {
            return Err(RequestValidationError::InvalidFileCount);
        }
        if let Some(sizes) = &sizes
            && (sizes.len() != paths.len() || paths.iter().any(|p| !sizes.contains_key(p)))
        {
            return Err(RequestValidationError::InvalidSizeMap);
        }
        let names: BTreeSet<&str> = paths.iter().map(String::as_str).collect();
        if names.len() != paths.len()
            || names
                .iter()
                .any(|p| p.match_indices('/').any(|(i, _)| names.contains(&p[..i])))
        {
            return Err(RequestValidationError::InvalidFilePaths);
        }
        let files = paths
            .into_iter()
            .map(|p| {
                let size = sizes.as_ref().map(|m| m[&p]);
                FileSpec::new(p, size).map_err(|_| RequestValidationError::InvalidFilePaths)
            })
            .collect::<Result<Vec<_>, _>>()?;
        Ok(Self {
            generator_id,
            recording_id,
            source_directory,
            files,
        })
    }
    pub fn generator_id(&self) -> &str {
        &self.generator_id
    }
    pub fn recording_id(&self) -> RecordingId {
        self.recording_id
    }
    pub fn source_directory(&self) -> &str {
        &self.source_directory
    }
    pub fn files(&self) -> &[FileSpec] {
        &self.files
    }
    pub fn expected_sizes_supplied(&self) -> bool {
        self.files[0].expected_size().is_some()
    }
    /// Exact immutable assertions, independent of arrival order or size policy.
    /// A hash comparison alone is never used to establish this equivalence.
    pub fn same_assertions(&self, other: &Self) -> bool {
        let contents = |request: &Self| {
            request
                .files
                .iter()
                .map(|f| (f.relative_path().to_owned(), f.expected_size()))
                .collect::<BTreeMap<_, _>>()
        };
        self.generator_id == other.generator_id
            && self.recording_id == other.recording_id
            && self.source_directory == other.source_directory
            && contents(self) == contents(other)
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

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn exact_uuid_and_decimal_boundaries() {
        let text = "01234567-89AB-CDEF-0000-FFFFFFFFFFFF";
        let id = RecordingId::parse(text).unwrap();
        assert_eq!(id.to_string(), text.to_ascii_lowercase());
        assert_eq!(
            *id.as_bytes(),
            [
                1, 35, 69, 103, 137, 171, 205, 239, 0, 0, 255, 255, 255, 255, 255, 255
            ]
        );
        assert!(RecordingId::parse("00000000-0000-0000-0000-000000000000").is_ok());
        for bad in [
            "{01234567-89ab-cdef-0000-ffffffffffff}",
            "0123456789abcdef0000ffffffffffff",
            "01234567-89ab-cdef-0000-fffffffffffg",
            "01234567_89ab-cdef-0000-ffffffffffff",
            "01234567-89ab-cdef-0000-ffffffffffff ",
        ] {
            assert!(RecordingId::parse(bad).is_err(), "{bad}");
        }
        assert_eq!(parse_decimal_u64("18446744073709551615").unwrap(), u64::MAX);
        assert_eq!(
            parse_decimal_u64("9007199254740993").unwrap(),
            9007199254740993
        );
        assert_eq!(parse_decimal_u64("0").unwrap(), 0);
        for bad in [
            "",
            "00",
            "01",
            "+1",
            "-1",
            "1.0",
            "1e3",
            " 1",
            "1\n",
            "18446744073709551616",
        ] {
            assert!(parse_decimal_u64(bad).is_err(), "{bad}");
        }
    }
    #[test]
    fn request_order_map_presence_and_exact_unicode_assertions() {
        let id = RecordingId::parse("00000000-0000-0000-0000-000000000000").unwrap();
        let make = |files: Vec<String>, sizes| {
            ProducerRequest::new("g".into(), id, "/source".into(), files, sizes).unwrap()
        };
        let a = make(vec!["b".into(), "a".into()], None);
        let b = make(vec!["a".into(), "b".into()], None);
        assert!(a.same_assertions(&b));
        assert_eq!(a.files()[0].relative_path(), "b");
        let map = make(
            vec!["a".into(), "b".into()],
            Some(BTreeMap::from([("a".into(), 0), ("b".into(), u64::MAX)])),
        );
        assert!(!a.same_assertions(&map));
        assert!(map.expected_sizes_supplied());
        assert!(
            !make(vec!["\u{e9}".into()], None)
                .same_assertions(&make(vec!["e\u{301}".into()], None))
        );
    }
    #[test]
    fn new_request_validation_does_not_change_legacy_rules() {
        let id = RecordingId::parse("00000000-0000-0000-0000-000000000000").unwrap();
        let make = |generator: &str, source: &str, paths: Vec<String>, sizes| {
            ProducerRequest::new(generator.into(), id, source.into(), paths, sizes)
        };
        for source in [
            "relative", "/a/", "/a//b", "/a/../b", "/a/./b", "/a\\b", "/\u{80}",
        ] {
            assert!(make("g", source, vec!["a".into()], None).is_err());
        }
        for generator in ["", "_g", "g x", "\u{e9}"] {
            assert!(make(generator, "/", vec!["a".into()], None).is_err());
        }
        for paths in [
            vec!["a".into(), "a".into()],
            vec!["a".into(), "a/b".into()],
            vec!["x/COMMITTED.json".into()],
            vec!["\u{e9}".repeat(2048)],
        ] {
            assert!(make("g", "/", paths, None).is_err());
        }
        assert!(make("g", "/", vec!["a".into()], Some(BTreeMap::new())).is_err());
        assert!(make("g", "/", vec!["a".into(), "a/bb".into()], None).is_err());
        assert!(make("g", "/", vec!["a".into(), "ab".into()], None).is_ok());
        assert!(
            crate::Submission::new(
                "_legacy",
                "not-a-uuid",
                "/source",
                vec![FileSpec::new("a", None).unwrap()]
            )
            .is_ok()
        );
    }
}
