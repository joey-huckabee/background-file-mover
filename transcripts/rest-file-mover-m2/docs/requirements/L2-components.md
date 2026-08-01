# L2 Component Requirements — rest-file-mover

Components: CORE (job model/state), JSON, CONFIG, JOURNAL, RENAME, TRANSFER,
MANAGER, HTTP, DASH. Each L2 traces up to one or more L1s.

## CORE (M1) — traces L1-030, L1-031, L1-024, L1-042

- **L2-CORE-001** The core SHALL define the job state set and the legal-transition relation as pure functions with no I/O.
- **L2-CORE-002** The core SHALL represent a job with identity, source path, destination path, state, creation/update/finish timestamps, byte counters, and an error field.
- **L2-CORE-003** The core SHALL apply state transitions atomically: an invalid request SHALL leave the job unmodified.
- **L2-CORE-004** The core SHALL accept timestamps from the caller and SHALL NOT read the system clock.

## JSON (M2) — traces L1-002, L1-010, L1-011

- **L2-JSON-001** The JSON layer SHALL wrap the vendored parser behind a project-owned interface.
- **L2-JSON-002** The JSON layer SHALL reject malformed input with a diagnosable error, never by terminating the process.
- **L2-JSON-003** Characterization tests SHALL pin every vendored-parser behavior the system relies on.

## CONFIG (M3) — traces L1-050, L1-051

- **L2-CONFIG-001** The config loader SHALL parse INI syntax: sections, key=value pairs, comments, blank lines.
- **L2-CONFIG-002** The config loader SHALL validate presence, type, and range of every parameter and report file:line on the first failure.
- **L2-CONFIG-003** The config loader SHALL supply documented defaults only for parameters designated optional.

## JOURNAL (M4) — traces L1-033, L1-034

- **L2-JRNL-001** The journal SHALL append one JSON record per line via a single write(2) per record with O_APPEND.
- **L2-JRNL-002** The journal SHALL replay a file containing a torn final line by processing all complete records and reporting the truncation.
- **L2-JRNL-003** Journal replay SHALL be deterministic and side-effect-free apart from its returned event sequence.

## RENAME (M6) — traces L1-020, L1-024

- **L2-REN-001** The rename engine SHALL expand a configured template (timestamp, sequence, original-name fields) into the target filename.
- **L2-REN-002** The rename engine SHALL apply a configured collision policy (fail | suffix) when the target exists.
- **L2-REN-003** The rename engine SHALL operate only within a single filesystem and reject cross-device renames.

## TRANSFER (M7) — traces L1-021, L1-022, L1-023, L1-024

- **L2-XFR-001** Transfer strategies SHALL implement a common interface accepting source, destination, and a progress callback.
- **L2-XFR-002** The copy strategy SHALL write to a temporary name, fsync, then rename to the final name.
- **L2-XFR-003** The exec strategy SHALL launch the configured external command, reap the child, and map exit codes to job errors.
- **L2-XFR-004** Every strategy failure SHALL produce a human-readable error string including errno text where applicable.

## MANAGER (M8) — traces L1-030, L1-032, L1-035, L1-042

- **L2-MGR-001** The manager SHALL dispatch queued jobs to N worker threads via a mutex/condition-variable protected queue.
- **L2-MGR-002** The manager SHALL drive all job state changes exclusively through the CORE transition function.
- **L2-MGR-003** The manager SHALL support clean shutdown: stop intake, drain or fail in-flight jobs, join all workers.

## HTTP (M9, M10) — traces L1-010..L1-015, L1-041

- **L2-HTTP-001** The HTTP layer SHALL expose POST /api/jobs, GET /api/jobs, GET /api/jobs/{id}, GET /api/status, GET /.
- **L2-HTTP-002** Route handlers SHALL be pure functions of (request, manager view) → response, unit-testable without sockets.
- **L2-HTTP-003** The HTTP layer SHALL return 404 for unknown paths, 405 for unsupported methods, 413 for oversized bodies, and 400 for malformed JSON.
- **L2-HTTP-004** Acceptance tests SHALL demonstrate the vendored server survives oversized headers, invalid methods, and non-HTTP bytes without crashing.

## DASH (M11) — traces L1-040

- **L2-DASH-001** The dashboard SHALL be a single embedded HTML/JS page polling GET /api/status at a fixed interval.
- **L2-DASH-002** The dashboard SHALL function without external network resources.
