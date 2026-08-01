# L3-CPP Implementation Requirements — M1 (CORE)

Traces: L2-CORE-001..004. Verified by `tests/test_job.cpp`; requirement IDs
appear in Catch2 tags and in source comments.

- **L3-CPP-001** The job state enumeration SHALL contain exactly the states Queued, Renaming, Transferring, Done, and Failed.
- **L3-CPP-002** `to_string(JobState)` SHALL return a stable, unique, uppercase token for each state.
- **L3-CPP-003** `is_legal_transition(from, to)` SHALL permit exactly: Queued→Renaming, Renaming→Transferring, Transferring→Done, Queued→Failed, Renaming→Failed, Transferring→Failed; all other pairs, including self-transitions, SHALL be rejected.
- **L3-CPP-004** `is_terminal(JobState)` SHALL return true for Done and Failed and false otherwise.
- **L3-CPP-005** A newly constructed `Job` SHALL be in Queued with `created_at_ms == updated_at_ms == now_ms`, `finished_at_ms == 0`, both byte counters zero, and an empty error string.
- **L3-CPP-006** `Job::transition` SHALL return false and leave the object bitwise-unmodified when the requested transition is illegal.
- **L3-CPP-007** `Job::transition` to Failed SHALL be rejected when the supplied error message is empty.
- **L3-CPP-008** `Job::transition` to any non-Failed state SHALL be rejected when a non-empty error message is supplied.
- **L3-CPP-009** On success, `Job::transition` SHALL set the state to the requested value and `updated_at_ms` to the supplied timestamp.
- **L3-CPP-010** On a successful transition into a terminal state, `Job::transition` SHALL set `finished_at_ms` to the supplied timestamp.
- **L3-CPP-011** On a successful transition into Failed, `Job::transition` SHALL store the supplied error message in the job's error field.
- **L3-CPP-012** Core headers SHALL include no I/O, threading, or clock headers (`<iostream>`, `<fstream>`, `<thread>`, `<mutex>`, `<chrono>` are prohibited in `include/filemover/job.hpp`).
- **L3-CPP-013** All core code SHALL compile warning-free under `-std=c++11 -Wall -Wextra -Werror` on GCC 4.8.5.
- **L3-CPP-014** Test assertions SHALL use natural order (`actual == expected`).
- **L3-CPP-015** The test suite SHALL exhaustively enumerate all 25 (from, to) state pairs against the legal-transition table.
