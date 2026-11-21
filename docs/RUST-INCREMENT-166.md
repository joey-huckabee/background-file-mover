# Increment 166: producer quickstart (DOC-01)

2026-11-21. The user was unavailable for the remaining dashboard trimming and
asked for other work. Release gate P10-11 (user guides) needs no product
decision, so this increment writes DOC-01. Documentation only; no behavior
change.

## Change

- New [producer quickstart and retry decision table](PRODUCER-QUICKSTART.md):
  - what a 202 means;
  - what the server administrator provides;
  - the request fields and rules;
  - how to send a request and read the reply;
  - retry timing;
  - a decision table for every producer error code: retry the same request,
    stop because the request is wrong, stop because it is not allowed, or stop
    because the operator is needed.
- Links from the [user guide index](USER-GUIDE.md), the DOC-01 row in
  [scenarios](RUST-SCENARIOS.md) and the roadmap's P10-11 item.

## How it was checked

Every statement was checked against the current source, not only the contract:
- **Codes and `retryable` flags:** every `error(status, code, retryable)` call
  in `file-mover/src`, plus the codec, framing and ingress mappings. All
  registered producer codes in `openapi.candidate.json` are covered.
- **`retry_after_seconds`:** only 429 sets it (1 s), with `Retry-After: 1`
  (`write_response`).
- **Missing-file window:** `missing_file_retry_window_seconds`, default 300.
  Automatic claiming of late files follows increment 163.
- **Limits:**
  - the body is at most 64 KiB;
  - a request line and headers over 8 KiB give 431;
  - more than 64 headers give 400 `invalid_http` (`http.rs`).
- **Size policy:** with `check_expected_sizes` on, a request without a size map
  is 400 `invalid_submission` (`process`).
- **Reservations:** `source_reserved` means another unfinished job holds the
  source path (`reservations` check in `accept`).

## Not covered

- DOC-02 (consumers), DOC-04 (restart and custody troubleshooting) and DOC-05
  (supported deployment matrix) remain open, as does L1/L2/L3 traceability.
- The guide is not release qualification; all eight release gates remain open.
