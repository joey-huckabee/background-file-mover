# Immutable request identity v1 - candidate

This encoding is proposed, not an approved or implemented producer requirement.
It supplies the missing request binding in proposed manifest v2. It is not a
new job ID, user credential, content hash or proof of filesystem custody.

## Exact encoding

Validate the producer request first: reject duplicate/unknown JSON keys,
invalid Unicode scalar strings, invalid paths, duplicate/prefix-conflicting
files and incomplete/extra size maps. Record the original valid assertions.
No trimming, Unicode normalization, path alias resolution or size-policy flag
is part of request identity. UUID text is lowercase hyphenated hexadecimal.

Build this byte sequence, without JSON whitespace or platform line endings:

1. Literal ASCII `BFM-REQUEST-IDENTITY`, byte 00, ASCII `v1`, byte 00.
2. generator_id, canonical recording_id, source_directory, in that order.
   Encode each string as unsigned 32-bit big-endian UTF-8 byte length followed
   by precisely those UTF-8 bytes, without a terminating zero.
3. Unsigned 32-bit big-endian file count. Sort file paths by unsigned UTF-8 byte
   sequence and emit each as a length-prefixed string using step 2.
4. One byte 00 if expected_sizes_bytes was absent, or 01 if present. If present,
   emit each expected byte count as unsigned 64-bit big-endian, in the same
   sorted path order. The validated map must have exactly these keys.

Compute SHA-256 over the entire sequence; use 64 lowercase hexadecimal digits.
The manifest request_identity object contains version:1, algorithm:"sha256"
and that sha256 value. The current size-check setting is deliberately absent;
changing configuration must not change immutable request identity.

Sorting here compares the submitted set; it never reassigns persisted file IDs,
claim indices or manifest ordering. Lowercase UUID spelling and file permutation
produce the same digest. Adding/removing a complete map or changing an assertion
produces different identity even with comparison disabled. Distinct Unicode
spellings stay distinct, including precomposed versus combining characters.

## Fixtures and limits

[Seven known-answer vectors](request-identity-v1.candidate.vectors.json) include
full inputs, frame hex and SHA-256. The fixture format is review evidence, not
an invitation to embed source-directory text in a consumer manifest. Only the
digest goes into the proposed public manifest; original request/state remain
protected service data. A digest does not hide predictable source paths from
someone who already knows the other inputs, so do not treat it as a secret.

Vectors cover the minimal request, file permutation, uppercase UUID, complete
map, changed assertion and two Unicode spellings. A separate checker reconstructed
the framing from lengths/to_bytes and checked both Python hashlib and OpenSSL
against every saved answer. This checks the proposed encoding only, not Rust
implementation, collision handling, consumer compatibility or storage durability.

Compatibility approval for manifest v2, legacy manifest recovery and integer
representation remains required before freeze. If byte counts become decimal
strings on the JSON wire, they must still parse to the same bounded integers
for this encoding; do not silently hash the spelling of a JSON number.
