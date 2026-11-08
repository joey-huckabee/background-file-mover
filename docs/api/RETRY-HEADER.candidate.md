# Retry context header v1 - wire candidate

Current engineering authority: [increment-120 closeout](API-CONTRACT-CLOSEOUT.md).
It supersedes conflicting proposal details below, especially per-job receipt
identity/storage, bounds and replay scope. Four visible defaults remain pending;
this is not full P01 freeze or runtime implementation.

2026-11-02. Group 49 approves header transport of existing review/audit context,
with job_ids-only body and preserved exact replay. The precise format here is a
reviewable technical proposal, not another approval group, API freeze or Rust
implementation. [Admin replay design](ADMIN-REPLAY.candidate.md) defines the
transactional requirements and still-open outcome/receipt policies.

## Request shape

Use exactly one case-insensitive `Mover-Retry-Context` header on the proposed
POST /api/v2/admin/jobs/retry route. Its value is `v1.` followed by canonical
unpadded base64url of the UTF-8 JSON object below. This encoding makes the
header ASCII even when the existing audit reason contains Unicode. The JSON
body remains {"job_ids":[42,43,42]}; no new public operation/job ID is created.

Decoded payload fields, in this exact order:

```json
{
  "version": 1,
  "instance_id": "0123456789abcdef0123456789abcdef",
  "selection_sha256": "76f612ec802d9462e213569df66f872fcccf33a61eeadc354ce5a7033bce150a",
  "review_epochs": [0, null, 0],
  "reason": "Inspected protected staging and corrected destination permissions"
}
```

The shown digest matches the duplicate-selection known answer. The [vector file](retry-context.candidate.vectors.json)
is authoritative for literal bytes and digests; the displayed indentation is
for reading only and is not a valid canonical wire payload.

- version is the integer token 1, matching the v1 prefix.
- instance_id is the mover's **existing** persisted 128-bit instance identity,
  as 32 lowercase hex digits. This additional precondition is proposed to reject
  the same job number/epoch at a different installation. It is not a new target
  identifier. Expose it in the authenticated RetryReviewSnapshot projection;
  final embedding into bounded job/list reads remains F01 work. Server receipt
  keys alone cannot provide this cross-instance rejection.
- selection_sha256 binds the exact ordered job_ids, including duplicates,
  using the framing below. It is not a replacement identifier or authorization.
- review_epochs has one entry per selection occurrence: null or an exact
  unsigned 32-bit integer. Repeated occurrences of one job must have identical
  frozen epoch values, including null. This validates consistency without
  deduplicating the list or predicting a per-job action result.
- reason preserves the existing required audit explanation: nonblank,
  control-free, 1-512 UTF-8 bytes. Preserve exact text; do not trim or normalize.
  One explanation applies to the selected jobs and must be appropriate for each;
  work needing different explanations uses separate selections. It is not an
  extra confirmation dialog or a server-invented generic reason.

The dashboard freezes selection, instance, epochs and explanation at the
operator's deliberate Retry action. An epoch is a concurrency precondition,
not proof of human inspection, corrected storage or safe custody. Keep the
existing review/ownership checks. Null means no authorizing reviewed epoch;
never replace it with whatever epoch becomes current later. Polling and session
renewal must not refresh a frozen request. A later deliberate retry uses later
review context. Authentication and CSRF protection remain independently required.

## Exact encoding and bounds

Encode compact JSON with the five keys in the stated order, no whitespace or
final newline, no BOM, shortest unsigned decimal integer tokens, and literal
UTF-8 Unicode scalars. Only quote and backslash escaping is needed in accepted
reason text; encode them as backslash-quote and backslash-backslash. Reject
controls (Unicode category Cc), unpaired surrogates, escaped alternative Unicode
spellings, escaped solidus and other noncanonical spellings. Null is `null`.
No unknown/duplicate fields, booleans-as-numbers, fractions or exponent tokens.
This is a fixed application profile, not a claim of general JSON canonicalization.

Use the URL-safe alphabet and reject padding, internal whitespace, comma joining,
invalid alphabet and nonzero unused encoding bits. Re-encode and compare both
base64url and canonical decoded JSON. HTTP framing removes permitted surrounding
OWS before passing the value to the codec; raw OWS still counts toward head size.
Canonical encoding rules follow [RFC 4648 sections 3.3/3.5/5](https://www.rfc-editor.org/rfc/rfc4648.html#section-3.5).

| Bound | Candidate limit |
|---|---|
| job_ids / review_epochs | 1-256 occurrences, equal lengths |
| job ID | Exact positive i64, at most 9223372036854775807 |
| epoch | Exact u32 or null; the existing 64-successful-command audit cap still applies separately |
| reason | 1-512 UTF-8 bytes; nonblank and control-free |
| decoded payload | 4096 bytes maximum |
| trimmed ASCII header value, including v1. | 6144 bytes maximum |
| complete raw HTTP request head | Existing 8192 bytes maximum, unchanged |

The widest structurally valid canonical payload is 4018 bytes: 256 maximum-u32
epochs and a 512-byte quote/backslash reason. Its encoded value is 5361 bytes,
within both context limits. Aggregate head space for request line, Host, cookie,
CSRF and all other fields remains bounded; reject oversize rather than silently
increase the limit. This arithmetic is not a test of the production HTTP parser.

Do not use binary64 conversion to parse/hash job IDs: 9007199254740993 must
remain distinct from 9007199254740992. Job status already returns decimal-string
IDs. The browser can preserve those strings, validate them and use exact integer
encoding for JSON selection and digest construction. JSON Schema alone checks
mathematical integers, not raw integer token spelling; raw decoding must retain
this evidence and reject floats/exponents even when mathematically integral.

## Exact selection binding

Concatenate:

1. ASCII `BFM-RETRY-SELECTION`, byte 00, ASCII `v1`, byte 00.
2. Unsigned 16-bit big-endian occurrence count, 1-256.
3. Each existing positive job ID as 8-byte big-endian integer, in submitted
   order, with repeated entries emitted again. No sorting or text delimiters.

Hash the full frame using SHA-256; encode 64 lowercase hex digits. This digest
is a fixed-size selection binding to fit the existing header limit; it is not
an independently generated operation ID. Validate the exact ordered selection and canonical context on each request.
Persist only the owning job's exact command projection alongside an internal
hashed receipt key, as defined by the increment-120 closeout. Do not retain
other selected job identities in that receipt. A digest match alone is not
authority to schedule work or resolve jobs through UUID reuse.

Bind internal receipts to the server-authenticated account, retry action,
original instance, exact selection/context and occurrence position. A client
cannot supply the trusted actor. Session renewal does not create a fresh retry
intent; revoked sessions still fail authorization before receipt disclosure.
Instance IDs are scope checks, not fencing against stale/cloned SQLite state.
Preserve the no-stale-state/no-rebind rules and AUTOINCREMENT job non-reuse.

## Validation and response proposal

1. Enforce raw framing, request/head/body limits and duplicate-header refusal.
2. Authenticate and apply CSRF/route protections before state/receipt disclosure.
3. Enforce context occurrence/value/decoded limits; validate encoding, canonical
   JSON and fields; losslessly validate the job_ids-only body.
4. Verify selection digest, epoch count, repeated-ID epoch consistency, then
   expected instance. Reject a malformed whole context before dispatch.
5. Recognize existing exact receipts before checking new-command eligibility,
   the current epoch or the 64-command audit cap.
6. For each new occurrence, validate its frozen context and persisted state,
   then atomically record audit/outcome and schedule only eligible original work.
   Preserve failed/skipped outcomes too; do not reconsider them on transport replay.

Proposed mapping: raw/encoded/decoded size refusal uses 431; other malformed
context/selection uses 400; wrong instance uses 409 review_conflict. Raw duplicate
HTTP headers retain framing 400 invalid_http rather than a fabricated application
reply. Missing/expired/revoked session is approved 401. Exact admin error-body
schema, stale/duplicate and failure semantics are fixed by the increment-120 closeout;
completed/null defaults still await approval. Group 51 already fixes zero-accepted 202. Group 50 removes every cleared-job
receipt and file linkage; preserve exact replay only for uncleared jobs.
A 503 or lost response never proves that no scheduling transaction committed.
The candidate OpenAPI documents these remaining boundaries, not fictional success.

## Reproducible artifact checks

Run `python docs/api/check_retry_context_candidate.py` with Python 3.11+.
The standard-library checker reads the [known answers and decoding cases](retry-context.candidate.vectors.json):
four exact frames/headers, 52 positive/rejection cases, and the maximum-width
bound. It touches no service, database or transfer files. The case file lists
future runtime obligations as NOT_RUN, including lost reply/later review,
authenticated replay, crash atomicity, partial batches, duplicates and history clear under group 50.

The checker demonstrates the proposed codec and refusal rules only. It does not
validate real HTTP framing, CSRF, audit storage, durable scheduling or worker
safety. Required SLES gates and finite affected qualification remain mandatory
for the later Rust implementation; production NFS/source deletion stay disabled.
