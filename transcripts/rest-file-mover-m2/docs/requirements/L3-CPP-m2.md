# L3-CPP Implementation Requirements — M2 (JSON codec)

Traces: L2-JSON-001..003. Verified by `tests/test_api_codec.cpp`.

- **L3-CPP-016** `decode_submit_request` SHALL accept only a JSON object whose members are exactly `source` and `dest`, both non-empty strings.
- **L3-CPP-017** `decode_submit_request` SHALL reject unknown members, missing members, wrong member types, and non-object top-level values.
- **L3-CPP-018** `decode_submit_request` SHALL reject string members containing an embedded NUL character.
- **L3-CPP-019** On rejection, `decode_submit_request` SHALL return false, populate a non-empty human-readable error, and leave the output parameter unmodified.
- **L3-CPP-020** The codec SHALL never terminate the process on malformed input, regardless of input size or nesting depth.
- **L3-CPP-021** `picojson.h` SHALL be included only by `src/api_codec.cpp` and `tests/test_api_codec.cpp`; all other translation units SHALL use the codec interface exclusively.
- **L3-CPP-022** `encode_job` SHALL emit members `id`, `source`, `dest`, `state`, `created_at_ms`, `updated_at_ms`, `finished_at_ms`, `bytes_total`, `bytes_moved`, `error`, with the state rendered via `to_string`.
- **L3-CPP-023** All emitted strings SHALL be JSON-escaped such that parsing the output reproduces the original values exactly, including quotes, backslashes, and control characters.
- **L3-CPP-024** `decode_submit_request` SHALL reject bodies containing non-whitespace bytes after the JSON value. (Compensates a pinned vendored-parser behavior: picojson's string-overload `parse()` ignores trailing content — see ADR-0006 and the characterization suite.)
- **L3-CPP-025** Characterization tests SHALL pin: non-empty error reporting on malformed input, int64 round-trip fidelity under `PICOJSON_USE_INT64`, rejection of invalid escapes and bare control characters, escaping behavior of `serialize()`, and the trailing-content behavior compensated by L3-CPP-024.
