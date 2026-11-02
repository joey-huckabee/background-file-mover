"""Reference artifact checker only; no service, authentication, SQL or file effects.

Run with Python 3.11+: python docs/api/check_retry_context_candidate.py
The wire contract is a candidate. This does not qualify Rust/HTTP behavior.
"""

import base64
import binascii
import hashlib
import json
import re
import sys
import unicodedata
from pathlib import Path


class InvalidContext(ValueError):
    pass


def require(condition, code):
    if not condition:
        raise InvalidContext(code)


def exact_integer(value, low, high):
    return type(value) is int and low <= value <= high


def selection_ids(body):
    require(type(body) is dict and set(body) == {"job_ids"}, "invalid_selection")
    ids = body["job_ids"]
    require(type(ids) is list and 1 <= len(ids) <= 256, "invalid_selection")
    require(all(exact_integer(i, 1, 2**63 - 1) for i in ids), "invalid_selection")
    return ids


def selection_frame(body):
    ids = selection_ids(body)
    return (b"BFM-RETRY-SELECTION\x00v1\x00" + len(ids).to_bytes(2, "big")
            + b"".join(i.to_bytes(8, "big") for i in ids))


def selection_digest(body):
    return hashlib.sha256(selection_frame(body)).hexdigest()


def payload_fields(context):
    keys = ["version", "instance_id", "selection_sha256", "review_epochs", "reason"]
    require(type(context) is dict and set(context) == set(keys), "invalid_payload")
    require(type(context["version"]) is int and context["version"] == 1, "invalid_payload")
    for field, size in [("instance_id", 32), ("selection_sha256", 64)]:
        value = context[field]
        require(type(value) is str and re.fullmatch("[0-9a-f]{%d}" % size, value)
                is not None, "invalid_payload")
    epochs = context["review_epochs"]
    require(type(epochs) is list and 1 <= len(epochs) <= 256, "invalid_payload")
    require(all(e is None or exact_integer(e, 0, 2**32 - 1) for e in epochs),
            "invalid_payload")
    reason = context["reason"]
    require(type(reason) is str, "invalid_payload")
    try:
        size = len(reason.encode("utf-8"))
    except UnicodeError as error:
        raise InvalidContext("invalid_payload") from error
    require(1 <= size <= 512 and bool(reason.strip()), "invalid_payload")
    require(not any(unicodedata.category(c) == "Cc" for c in reason), "invalid_payload")
    return {key: context[key] for key in keys}


def canonical_payload(context):
    return json.dumps(payload_fields(context), ensure_ascii=False,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def encode_context(context):
    raw = canonical_payload(context)
    require(len(raw) <= 4096, "decoded_too_large")
    value = "v1." + base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")
    require(len(value) <= 6144, "value_too_large")
    return value


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "invalid_payload")
        result[key] = value
    return result


def reject_number(_):
    raise InvalidContext("invalid_payload")


def decode_context(body, values, expected_instance, head_bytes=None):
    # values are case-insensitive occurrences after HTTP framing/OWS removal.
    # Authentication/CSRF precede this reference codec in the proposed service.
    if head_bytes is not None:
        require(exact_integer(head_bytes, 0, 8192), "head_too_large")
    require(type(values) is list and len(values) == 1, "header_occurrence")
    value = values[0]
    require(type(value) is str and len(value) <= 6144, "value_too_large")
    require(value.startswith("v1."), "invalid_encoding")
    token = value[3:]
    require(re.fullmatch("[A-Za-z0-9_-]+", token) is not None, "invalid_encoding")
    try:
        raw = base64.urlsafe_b64decode(token + "=" * (-len(token) % 4))
    except (ValueError, binascii.Error) as error:
        raise InvalidContext("invalid_encoding") from error
    require(base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii") == token,
            "invalid_encoding")
    require(len(raw) <= 4096, "decoded_too_large")
    try:
        context = json.loads(raw.decode("utf-8"), object_pairs_hook=unique_object,
                             parse_float=reject_number, parse_constant=reject_number)
    except (UnicodeError, ValueError, RecursionError) as error:
        raise InvalidContext("invalid_payload") from error
    require(canonical_payload(context) == raw, "noncanonical_payload")
    ids = selection_ids(body)
    require(context["selection_sha256"] == selection_digest(body), "selection_mismatch")
    require(len(context["review_epochs"]) == len(ids), "selection_mismatch")
    seen = {}
    for job_id, epoch in zip(ids, context["review_epochs"]):
        require(job_id not in seen or seen[job_id] == epoch, "duplicate_epoch_mismatch")
        seen[job_id] = epoch
    require(context["instance_id"] == expected_instance, "instance_mismatch")
    return context


def check_vectors(path):
    document = json.loads(path.read_text(encoding="utf-8"))
    for vector in document["known_answers"]:
        body, context = vector["body"], vector["context"]
        require([str(i) for i in selection_ids(body)] == vector["job_id_decimal_strings"],
                vector["id"] + ": lossless IDs")
        require(selection_frame(body).hex() == vector["selection_frame_hex"], vector["id"])
        require(selection_digest(body) == context["selection_sha256"], vector["id"])
        require(encode_context(context) == vector["header_value"], vector["id"])
        require(decode_context(body, [vector["header_value"]], context["instance_id"])
                == context, vector["id"])
    for case in document["decoding_cases"]:
        try:
            context = decode_context(case["body"], case["header_values"],
                                     case["expected_instance"], case.get("head_bytes"))
        except InvalidContext as error:
            require(case["outcome"] == str(error), case["id"] + ": " + str(error))
        else:
            require(case["outcome"] == "valid", case["id"])
            require(context["review_epochs"] == case["expected_epochs"], case["id"])
    limit = document["bounds"]
    context = {"version": 1, "instance_id": "f" * 32,
               "selection_sha256": "f" * 64, "review_epochs": [2**32 - 1] * 256,
               "reason": "\\" * 512}
    require(len(canonical_payload(context)) == limit["maximum_canonical_payload_bytes"],
            "maximum payload")
    require(len(encode_context(context)) == limit["maximum_canonical_value_bytes"],
            "maximum value")
    print("PASS: %d known answers, %d decoding cases, maximum payload %d/value %d bytes"
          % (len(document["known_answers"]), len(document["decoding_cases"]),
             len(canonical_payload(context)), len(encode_context(context))))


if __name__ == "__main__":
    try:
        check_vectors(Path(__file__).with_name("retry-context.candidate.vectors.json"))
    except (InvalidContext, KeyError, OSError, ValueError) as error:
        print("FAIL:", error, file=sys.stderr)
        sys.exit(1)
