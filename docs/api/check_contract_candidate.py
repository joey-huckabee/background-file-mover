#!/usr/bin/env python3
"""Read-only structural checks. Requires the existing jsonschema package.

This is not an OpenAPI conformance validator or a service acceptance test.
Run from any directory: python3 docs/api/check_contract_candidate.py
"""
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


def main():
    schema = read("contract.candidate.schema.json")
    fixtures = read("contract.candidate.fixtures.json")["cases"]
    api = read("openapi.candidate.json")
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

    expected = {
        ("post", "/api/v2/jobs"), ("get", "/healthz"),
        ("post", "/api/v2/admin/login"), ("post", "/api/v2/admin/logout"),
        ("get", "/api/v2/admin/session"), ("get", "/api/v2/admin/jobs"),
        ("get", "/api/v2/jobs/{job_id}"), ("get", "/api/v2/retention"),
        ("get", "/api/v2/jobs/{job_id}/retention"),
        *(('post', '/api/v2/admin/jobs/' + action)
          for action in ('cancel', 'retry', 'clear-history', 'delete-data')),
        ("post", "/api/v2/jobs/{job_id}/resume"),
        ("post", "/api/v2/jobs/{job_id}/reset-missing"),
    }
    actual = {(method, path) for path, item in api["paths"].items()
              for method in item if method in ("get", "post", "put", "delete", "patch")}
    require(actual == expected, "route inventory differs: " + str(actual ^ expected))
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
        for response in op["responses"].values():
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
    print("NOT RUN: semantic annotations, full OpenAPI conformance, HTTP/SQL/security/runtime qualification")


if __name__ == "__main__":
    main()
