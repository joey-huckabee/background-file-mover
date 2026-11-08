use super::*;
use serde_json::json;
fn vectors() -> Value {
    serde_json::from_str(include_str!("identity-v1.json")).unwrap()
}
fn cases() -> Value {
    serde_json::from_str(include_str!("producer-manifest.json")).unwrap()
}
fn minimal() -> ProducerRequest {
    decode_producer(&serde_json::to_vec(&vectors()["vectors"][0]["request"]).unwrap()).unwrap()
}
fn golden() -> Value {
    cases()["cases"]
        .as_array()
        .unwrap()
        .iter()
        .find(|c| c["id"] == "manifest-v2")
        .unwrap()
        .clone()
}
fn measured() -> Vec<MeasuredFile> {
    ManifestV2::decode(&serde_json::to_vec(&golden()["value"]).unwrap())
        .unwrap()
        .files()
        .to_vec()
}
const INSTANCE: &str = "0123456789abcdef0123456789abcdef";
#[test]
fn original_seven_identity_vectors_and_assertion_equivalence() {
    let data = vectors();
    let mut requests = Vec::new();
    for vector in data["vectors"].as_array().unwrap() {
        let request = decode_producer(&serde_json::to_vec(&vector["request"]).unwrap()).unwrap();
        assert_eq!(
            hex(&identity_frame(&request)),
            vector["frame_hex"].as_str().unwrap(),
            "{}",
            vector["id"]
        );
        assert_eq!(
            hex(&identity_sha256(&request)),
            vector["sha256"].as_str().unwrap()
        );
        requests.push(request);
    }
    assert!(requests[0].same_assertions(&requests[1]));
    assert_eq!(requests[0], requests[1]);
    assert!(requests[0].same_assertions(&requests[2]));
    assert!(!requests[0].same_assertions(&requests[3]));
    assert!(!requests[3].same_assertions(&requests[4]));
    assert!(!requests[5].same_assertions(&requests[6]));
    assert_eq!(requests[1].files()[0].relative_path(), "metadata.json");
    assert_eq!(
        RecordingId::from_bytes(*requests[0].recording_id().as_bytes()),
        requests[0].recording_id()
    );
}
#[test]
fn existing_structural_and_semantic_fixture_expectations() {
    for case in cases()["cases"].as_array().unwrap() {
        let raw = serde_json::to_vec(&case["value"]).unwrap();
        let expected =
            case["valid"] == true && case.get("semantic_valid") != Some(&Value::Bool(false));
        let actual = if case["schema"] == "ProducerRequest" {
            decode_producer(&raw).is_ok()
        } else {
            ManifestV2::decode(&raw).is_ok()
        };
        assert_eq!(actual, expected, "{}", case["id"]);
    }
}
#[test]
fn strict_raw_json_and_original_map_rules_before_policy() {
    for raw in [
        b"".as_slice(),
        b"{} {}",
        b"\xef\xbb\xbf{}",
        b"{\"files\":[\"\\ud800\"]}",
        b"{\"x\":NaN}",
        b"{\"x\":1,\"x\":2}",
        b"{\"x\":{\"a\":1,\"\\u0061\":2}}",
        b"{\"x\":\"\xff\"}",
    ] {
        assert_eq!(
            decode_producer(raw).unwrap_err(),
            CodecError::InvalidJson,
            "{raw:?}"
        );
    }
    let deep = format!("{}null{}", "[".repeat(2000), "]".repeat(2000));
    assert_eq!(
        decode_producer(deep.as_bytes()).unwrap_err(),
        CodecError::InvalidJson
    );
    let mut request = vectors()["vectors"][0]["request"].clone();
    request["expected_sizes_bytes"] = Value::Null;
    assert_eq!(
        decode_producer(&serde_json::to_vec(&request).unwrap()).unwrap_err(),
        CodecError::InvalidSubmission
    );
    request["expected_sizes_bytes"] = json!({"camera1/video.bin":"0"});
    assert_eq!(
        decode_producer(&serde_json::to_vec(&request).unwrap()).unwrap_err(),
        CodecError::InvalidSubmission
    );
    request["expected_sizes_bytes"] = json!({"camera1/video.bin":"18446744073709551615","camera2/video.bin":"9007199254740993","metadata.json":"0"});
    let decoded = decode_producer(&serde_json::to_vec(&request).unwrap()).unwrap();
    assert_eq!(decoded.files()[0].expected_size(), Some(u64::MAX));
    for value in [
        json!(1),
        json!(true),
        json!("00"),
        json!("1e2"),
        json!("18446744073709551616"),
    ] {
        request["expected_sizes_bytes"]["metadata.json"] = value;
        assert_eq!(
            decode_producer(&serde_json::to_vec(&request).unwrap()).unwrap_err(),
            CodecError::InvalidSubmission
        );
    }
    let raw=br#"{"generator_id":"g","recording_id":"00000000-0000-0000-0000-000000000000","source_directory":"/","files":["a"],"expected_sizes_bytes":{"a":"0","a":"0"}}"#;
    assert_eq!(decode_producer(raw).unwrap_err(), CodecError::InvalidJson);
    let request = minimal();
    let id = request.recording_id();
    assert!(validate_idempotency_key(id, &id.to_string().to_ascii_uppercase()).is_ok());
    for key in [
        format!("{id} "),
        "00000000-0000-0000-0000-000000000000".into(),
        "not-a-uuid".into(),
    ] {
        assert_eq!(
            validate_idempotency_key(id, &key),
            Err(CodecError::IdempotencyKeyConflict)
        );
    }
}
#[test]
fn manifest_golden_saved_bytes_and_durable_file_mapping() {
    let request = minimal();
    let fixture = golden();
    let mut files = measured();
    files.reverse();
    let built = ManifestV2::build(INSTANCE, 42, &request, files).unwrap();
    assert_eq!(
        built.bytes().len(),
        fixture["serialized_utf8_length"].as_u64().unwrap() as usize
    );
    assert_eq!(
        hex(&built.sha256()),
        fixture["serialized_utf8_sha256"].as_str().unwrap()
    );
    assert_eq!(built.request_sha256(), &identity_sha256(&request));
    assert!(built.validate_context(INSTANCE, 42, &request).is_ok());
    assert!(built.validate_context(INSTANCE, 43, &request).is_err());
    assert!(
        built
            .validate_context("f123456789abcdef0123456789abcdef", 42, &request)
            .is_err()
    );
    let permutation =
        decode_producer(&serde_json::to_vec(&vectors()["vectors"][1]["request"]).unwrap()).unwrap();
    assert!(built.validate_request(&permutation).is_ok());
    assert!(built.validate_context(INSTANCE, 42, &permutation).is_err());
    assert!(ManifestV2::build(INSTANCE, 42, &permutation, measured()).is_err());
    let pretty = serde_json::to_vec_pretty(&fixture["value"]).unwrap();
    let parsed = ManifestV2::decode(&pretty).unwrap();
    assert_eq!(parsed.bytes(), pretty);
    assert_eq!(parsed.files(), built.files());
    assert_ne!(parsed.sha256(), built.sha256());
    assert!(parsed.validate_context(INSTANCE, 42, &request).is_ok());
    let mut changed = fixture["value"].clone();
    changed["request_identity"]["sha256"] = json!("0".repeat(64));
    let parsed = ManifestV2::decode(&serde_json::to_vec(&changed).unwrap()).unwrap();
    assert!(parsed.validate_request(&request).is_err());
}
#[test]
fn malformed_manifest_fields_and_duplicate_keys_are_refused() {
    let value = golden()["value"].clone();
    let mut mutations = Vec::new();
    for (field, bad) in [
        ("version", json!(1)),
        ("version", json!(2.0)),
        (
            "recording_id",
            json!(value["recording_id"].as_str().unwrap().to_ascii_uppercase()),
        ),
        ("job_id", json!("9223372036854775808")),
        ("job_id", json!("0")),
        ("job_id", json!("042")),
        ("instance_id", json!(INSTANCE.to_ascii_uppercase())),
        ("extra", json!(0)),
        ("files", json!([])),
    ] {
        let mut changed = value.clone();
        changed[field] = bad;
        mutations.push(changed);
    }
    for (field, bad) in [
        ("file_id", json!("256")),
        ("file_id", json!("00")),
        ("size_bytes", json!(0)),
        ("size_bytes", json!("01")),
        ("sha256", json!("A".repeat(64))),
        ("algorithm", json!("SHA256")),
        ("extra", json!(0)),
    ] {
        let mut changed = value.clone();
        changed["files"][0][field] = bad;
        mutations.push(changed);
    }
    let mut changed = value.clone();
    changed["files"].as_array_mut().unwrap().swap(0, 1);
    mutations.push(changed);
    let mut changed = value.clone();
    changed["files"][1]["path"] = changed["files"][0]["path"].clone();
    mutations.push(changed);
    for changed in mutations {
        assert!(
            ManifestV2::decode(&serde_json::to_vec(&changed).unwrap()).is_err(),
            "{changed}"
        );
    }
    let raw = serde_json::to_string(&value).unwrap();
    let duplicate = raw.replacen("\"version\":2", "\"version\":2,\"version\":2", 1);
    assert_eq!(
        ManifestV2::decode(duplicate.as_bytes()).unwrap_err(),
        CodecError::InvalidJson
    );
    let duplicate = raw.replacen(
        "\"algorithm\":\"sha256\"",
        "\"algorithm\":\"sha256\",\"algorithm\":\"sha256\"",
        1,
    );
    assert_eq!(
        ManifestV2::decode(duplicate.as_bytes()).unwrap_err(),
        CodecError::InvalidJson
    );
}
#[test]
fn byte_limits_and_maximum_integer_manifest_are_bounded() {
    let mut raw = serde_json::to_vec(&vectors()["vectors"][0]["request"]).unwrap();
    raw.resize(MAX_PRODUCER_BYTES, b' ');
    assert!(decode_producer(&raw).is_ok());
    raw.push(b' ');
    assert_eq!(decode_producer(&raw), Err(CodecError::TooLarge));
    assert_eq!(
        ManifestV2::decode(&vec![b' '; MAX_MANIFEST_BYTES + 1]).unwrap_err(),
        CodecError::TooLarge
    );
    let paths: Vec<_> = (0..256)
        .map(|i| format!("{}{i:03}\u{2028}\"", "q".repeat(230)))
        .collect();
    let value = json!({"generator_id":"A".repeat(128),"recording_id":"00000000-0000-0000-0000-000000000000","source_directory":"/","files":paths});
    let raw = serde_json::to_vec(&value).unwrap();
    assert!(raw.len() <= MAX_PRODUCER_BYTES);
    let request = decode_producer(&raw).unwrap();
    let files = request
        .files()
        .iter()
        .enumerate()
        .map(|(i, f)| MeasuredFile {
            file_id: i as u16,
            path: f.relative_path().into(),
            size_bytes: u64::MAX,
            sha256: [0xab; 32],
        })
        .collect();
    let manifest = ManifestV2::build(INSTANCE, i64::MAX, &request, files).unwrap();
    assert!(manifest.bytes().len() <= 106673);
    assert_eq!(manifest.job_id(), i64::MAX);
    assert!(manifest.bytes().windows(3).any(|s| s == [0xe2, 0x80, 0xa8]));
    assert!(!manifest.bytes().windows(6).any(|s| s == b"\\u2028"));
    assert!(manifest.files().iter().all(|f| f.size_bytes == u64::MAX));
    assert!(
        ManifestV2::decode(manifest.bytes())
            .unwrap()
            .validate_context(INSTANCE, i64::MAX, &request)
            .is_ok()
    );
}
