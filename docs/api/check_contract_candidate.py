#!/usr/bin/env python3
"""Read-only structural checks. Requires the existing jsonschema package.

This is not an OpenAPI conformance validator or a service acceptance test.
Run from any directory: python3 docs/api/check_contract_candidate.py
"""
import hashlib
import json
from pathlib import Path

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parent


def read(name):
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def walk(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)


def scalar_bytes(value):
    # Python accepts escaped lone surrogates during json.loads; the wire does not.
    return value.encode("utf-8", errors="strict")


def strict_wire_json(raw, limit):
    require(len(raw) <= limit, "wire byte limit")
    require(not raw.startswith(b"\xef\xbb\xbf"), "BOM is not allowed")

    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "duplicate JSON key")
            result[key] = value
        return result

    def constant(value):
        raise ValueError("non-JSON constant: " + value)

    value = json.loads(raw.decode("utf-8", errors="strict"),
                       object_pairs_hook=pairs, parse_constant=constant)

    def scalars(node):
        if isinstance(node, str):
            scalar_bytes(node)
        elif isinstance(node, dict):
            for key, item in node.items():
                scalar_bytes(key)
                scalars(item)
        elif isinstance(node, list):
            for item in node:
                scalars(item)
    scalars(value)
    return value


def manifest_bytes(value):
    # Deterministic writer, independent of the parsed object's key insertion order.
    fields = ("version", "instance_id", "job_id", "generator_id", "recording_id")
    result = {key: value[key] for key in fields}
    result["request_identity"] = {key: value["request_identity"][key]
                                  for key in ("version", "algorithm", "sha256")}
    result["files"] = [{key: entry[key] for key in
                        ("file_id", "path", "size_bytes", "algorithm", "sha256")}
                       for entry in value["files"]]
    return json.dumps(result, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def lexical_semantics(name, value):
    # Contract reference checks only: never source authority/custody/effect proof.
    try:
        if name == "JobId":
            return 0 < int(value) <= 9223372036854775807
        if name not in ("ProducerRequest", "ManifestV2"):
            raise ValueError("no semantic checker for " + name)
        paths = value["files"] if name == "ProducerRequest" else [e["path"] for e in value["files"]]
        if len(set(paths)) != len(paths):
            return False
        if any(len(scalar_bytes(path)) > 4095 for path in paths):
            return False
        if any(other.startswith(path + "/") for path in paths for other in paths if path != other):
            return False
        if name == "ProducerRequest":
            source = value["source_directory"]
            if len(scalar_bytes(source)) > 4095 or (source != "/" and source.endswith("/")):
                return False
            sizes = value.get("expected_sizes_bytes")
            return sizes is None or set(sizes) == set(paths)
        return (0 < int(value["job_id"]) <= 9223372036854775807
                and [e["file_id"] for e in value["files"]] == [str(i) for i in range(len(paths))]
                and len(manifest_bytes(value)) <= 131072)
    except (UnicodeError, ValueError, TypeError):
        return False


def check_producer_manifest(schema, fixtures, vectors):
    checked = 0
    for case in fixtures:
        if "semantic_valid" in case:
            require(lexical_semantics(case["schema"], case["value"]) == case["semantic_valid"],
                    "semantic expectation: " + case["id"])
            checked += 1
    for vector in vectors:
        require(lexical_semantics("ProducerRequest", vector["request"]), "vector semantic bounds")
    case = next(c for c in fixtures if c["id"] == "manifest-v2")
    value = case["value"]
    encoded = manifest_bytes(value)
    require(len(encoded) == case["serialized_utf8_length"], "manifest golden length")
    require(hashlib.sha256(encoded).hexdigest() == case["serialized_utf8_sha256"], "manifest golden bytes")
    require(strict_wire_json(encoded, 131072) == value, "strict manifest round trip")
    request = next(v for v in vectors if v["id"] == "minimal")["request"]
    require(set(request["files"]) == {e["path"] for e in value["files"]}, "golden membership")
    require(value["request_identity"]["sha256"] == vectors[0]["sha256"], "golden request binding")
    # These parser checks require no new stored fixture/vector collection.
    for bad in (b'{"x":1,"x":2}', b'{"x":"\\ud800"}', b'{"x":NaN}'):
        try:
            strict_wire_json(bad, 65536)
        except (AssertionError, ValueError, UnicodeError):
            pass
        else:
            raise AssertionError("invalid raw JSON accepted")
    require(strict_wire_json(json.dumps(request).encode("utf-8"), 65536) == request,
            "strict producer round trip")
    upper = dict(value, job_id="9223372036854775807", generator_id="A" * 128, files=[])
    overhead = len(manifest_bytes(upper))
    entry = dict(value["files"][0], file_id="255", path="", size_bytes="18446744073709551615")
    per_file = len(json.dumps(entry, ensure_ascii=False, separators=(",", ":")).encode("utf-8")) - 2
    maximum = overhead + 256 * per_file + 65536 + 255
    require(maximum <= 131072, "valid request can overflow manifest bound")
    producer = schema["$defs"]["ProducerError"]
    require(producer["properties"]["retry_after_seconds"]["anyOf"][0]["minimum"] == 1,
            "usable delays must be positive")
    print(f"PASS: {checked} existing semantic fixtures, existing manifest golden and {maximum}-byte conservative manifest bound")


def main():
    schema = read("contract.candidate.schema.json")
    fixtures = read("contract.candidate.fixtures.json")["cases"]
    api = read("openapi.candidate.json")
    approved = api["x-approved-closeout-defaults"]
    require(set(approved) == {"completed_retry", "null_retry", "cancel_transport_replay", "empty_deletion"},
            "closeout must retain all four explicit approved decisions")
    require(approved == schema["x-approved-closeout-defaults"]
            and all(value.startswith("approved:") for value in approved.values()),
            "schema/OpenAPI must preserve group53 approvals")
    require(api["x-status"] == schema["x-status"] == "engineering-contract-frozen",
            "engineering freeze status disagrees")
    require(api["x-retry-receipts"]["cross_job_selection_retained"] is False
            and api["x-retry-receipts"]["exact_own_projection_required"] is True
            and api["x-retry-receipts"]["automatic_expiry"] is False,
            "receipt metadata conflicts with clear/replay boundaries")
    require("rate_limited" in api["paths"]["/api/v2/admin/login"]["post"]["responses"]["429"]["x-error-codes"],
            "bounded login error registry missing")
    Draft202012Validator.check_schema(schema)
    seen = set()
    for case in fixtures:
        require(case["id"] not in seen, "duplicate fixture ID: " + case["id"])
        seen.add(case["id"])
        validator = Draft202012Validator({"$defs": schema["$defs"],
                                          "$ref": "#/$defs/" + case["schema"]})
        errors = list(validator.iter_errors(case["value"]))
        require((not errors) == case["valid"],
                case["id"] + ": " + "; ".join(e.message for e in errors))

    # Reuse the original seven vectors: the approved JSON size spelling changes,
    # while the integer framing and hashes must remain identical.
    vectors = read("request-identity-v1.candidate.vectors.json")["vectors"]
    producer = Draft202012Validator({"$defs": schema["$defs"],
                                    "$ref": "#/$defs/ProducerRequest"})
    for vector in vectors:
        request = vector["request"]
        producer.validate(request)
        frame = bytearray(b"BFM-REQUEST-IDENTITY\x00v1\x00")

        def string(value):
            encoded = value.encode("utf-8")
            frame.extend(len(encoded).to_bytes(4, "big"))
            frame.extend(encoded)

        string(request["generator_id"])
        string(request["recording_id"].lower())
        string(request["source_directory"])
        paths = sorted(request["files"], key=lambda path: path.encode("utf-8"))
        frame.extend(len(paths).to_bytes(4, "big"))
        for path in paths:
            string(path)
        sizes = request.get("expected_sizes_bytes")
        frame.append(0 if sizes is None else 1)
        if sizes is not None:
            require(set(sizes) == set(paths), "vector size-map membership mismatch")
            for path in paths:
                frame.extend(int(sizes[path]).to_bytes(8, "big"))
        require(frame.hex() == vector["frame_hex"], "identity frame changed: " + vector["id"])
        require(hashlib.sha256(frame).hexdigest() == vector["sha256"],
                "identity hash changed: " + vector["id"])

    check_producer_manifest(schema, fixtures, vectors)

    rust_fixtures = ROOT.parent.parent / "rust/crates/mover-fs/src/recording_codec"
    require(json.loads((rust_fixtures / "identity-v1.json").read_text(encoding="utf-8"))
            == read("request-identity-v1.candidate.vectors.json"), "Rust identity fixture copy differs")
    copied = json.loads((rust_fixtures / "producer-manifest.json").read_text(encoding="utf-8"))
    require(copied["cases"] == [c for c in fixtures if c["schema"] in ("ProducerRequest", "ManifestV2")],
            "Rust producer/manifest fixture subset differs")

    expected = {
        ("post", "/api/v2/jobs"), ("get", "/healthz"),
        ("post", "/api/v2/admin/login"), ("post", "/api/v2/admin/logout"),
        ("get", "/api/v2/admin/session"), ("get", "/api/v2/admin/jobs"),
        ("get", "/api/v2/jobs/{job_id}"), ("get", "/api/v2/retention"),
        ("get", "/api/v2/jobs/{job_id}/retention"),
        # Added with the dashboard settings view and live updates (increments 133/136).
        ("get", "/api/v2/admin/settings"), ("get", "/api/v2/admin/events"),
        *(('post', '/api/v2/admin/jobs/' + action)
          for action in ('cancel', 'retry', 'clear-history', 'delete-data')),
        ("post", "/api/v2/jobs/{job_id}/resume"),
        ("post", "/api/v2/jobs/{job_id}/reset-missing"),
    }
    actual = {(method, path) for path, item in api["paths"].items()
              for method in item if method in ("get", "post", "put", "delete", "patch")}
    require(actual == expected, "route inventory differs: " + str(actual ^ expected))
    producer_op = api["paths"]["/api/v2/jobs"]["post"]
    registry = {code for response in producer_op["responses"].values()
                for code in response.get("x-error-codes", [])}
    require(registry == set(schema["$defs"]["ProducerError"]["properties"]["error"]["enum"]),
            "producer error enum/registry differ")
    require(any(p["name"] == "Idempotency-Key" and not p["required"]
                for p in producer_op["parameters"]), "producer optional UUID header missing")
    ids = set()
    for method, path in sorted(actual):
        op = api["paths"][path][method]
        require(op["operationId"] not in ids, "duplicate operationId")
        ids.add(op["operationId"])
        params = {p["name"]: p for p in op.get("parameters", [])}
        if "{job_id}" in path:
            require(params.get("job_id", {}).get("required"), "missing job_id path parameter")
        if method == "post" and path.startswith("/api/v2/admin/"):
            require(params.get("Origin", {}).get("required"), "POST Origin missing: " + path)
            if not path.endswith("/login"):
                require(op["security"] == [{"adminCookie": [], "adminCsrfHeader": []}],
                        "cookie AND CSRF required: " + path)
        if method == "get":
            require(not params.get("Origin", {}).get("required", False),
                    "GET must accept browser omission of Origin: " + path)
        if path.endswith(("/resume", "/reset-missing")):
            require(op.get("x-access-boundary") == "trusted-local-only", "local audience missing")
            require("Idempotency-Key" in params and not params["Idempotency-Key"]["required"],
                    "existing optional operator header missing")
            require("idempotency_key_conflict" in op["responses"]["400"]["x-error-codes"],
                    "existing command/header conflict missing")
        if op.get("x-trusted-local-alternative") or op.get("x-access-boundary") == "trusted-local-only":
            require("recording_blocked" in op["responses"]["409"]["x-error-codes"],
                    "existing instance-validation error missing")
        for status, response in op["responses"].items():
            # The live-updates stream is the one documented non-JSON success body.
            streamed = path == "/api/v2/admin/events" and status == "200"                 and "text/event-stream" in response.get("content", {})
            require(status == "204" or streamed or "application/json" in response.get("content", {}),
                    "mover response schema missing: " + path + " " + status)
            for media in response.get("content", {}).values():
                require("schema" in media, "missing response schema")
            ref = response.get("content", {}).get("application/json", {}).get("schema", {}).get("$ref", "")
            if response.get("x-error-codes") and ref.endswith(("/AdminError", "/OperatorError")):
                allowed = schema["$defs"][ref.rsplit("/", 1)[1]]["properties"]["error"]["enum"]
                require(set(response["x-error-codes"]) <= set(allowed), "unknown error code: " + path)
    for node in walk(api):
        if "$ref" in node:
            prefix = "./contract.candidate.schema.json#/$defs/"
            require(node["$ref"].startswith(prefix), "unexpected reference: " + node["$ref"])
            require(node["$ref"][len(prefix):] in schema["$defs"], "dangling reference")
    print(f"PASS: {len(schema['$defs'])} definitions, {len(fixtures)} structural fixtures, "
          f"{len(actual)} route operations and reference/access checks")
    print(f"PASS: {len(vectors)} existing request-identity frames/hashes with decimal-string size inputs")
    print("PASS: Rust test fixture copies match existing contract vectors/cases")
    print("NOT RUN: other semantic annotations, full OpenAPI conformance, HTTP/SQL/security/runtime/consumer qualification")


if __name__ == "__main__":
    main()
