# L1 — System Requirements

Level 1 requirements state *what* the Background File Mover system must accomplish.
Each is a single SHALL statement with a declared verification method. L1 requirements
decompose into L2 architectural derivations (`docs/L2-REQ.md`), which decompose into L3
implementation obligations (`docs/L3-REQ.md`). Live verification status is tracked in
the auto-generated `docs/TRACE-MATRIX.md`, not here.

Verification method codes: **T** = Test, **I** = Inspection, **A** = Analysis,
**D** = Demonstration.

---

### L1-SYS-001

The system shall transfer completed scenario recording files independently of the
simulation orchestration process.

**Verification Method**: Test (T), Demonstration (D)

### L1-SYS-002

The system shall allow simulation preparation activities to resume after the recording
files have been claimed and the transfer job has been durably accepted.

**Verification Method**: Test (T), Demonstration (D)

### L1-SYS-003

The system shall prevent source recording data from being deleted until the
corresponding destination data has been successfully published and verified.

**Verification Method**: Test (T)

### L1-SYS-004

The system shall relocate submitted source files within the source filesystem to
prevent subsequent simulation runs from overwriting the submitted paths.

**Verification Method**: Test (T)

### L1-SYS-005

The system shall recover incomplete transfer jobs following service termination, host
restart, NFS interruption, or process failure.

**Verification Method**: Test (T)

### L1-SYS-006

The system shall provide configurable integrity verification for transferred files.

**Verification Method**: Test (T)

### L1-SYS-007

The system shall maintain a durable record of every submitted transfer job and every
file included in each job.

**Verification Method**: Test (T)

### L1-SYS-008

The system shall provide interfaces to submit, inspect, retry, and diagnose transfer
jobs.

**Verification Method**: Test (T)

### L1-SYS-009

The production application shall operate using only Python 3.10 standard-library
modules.

**Verification Method**: Test (T), Inspection (I)

### L1-SYS-010

The system shall retain source data and provide actionable error information when a
transfer cannot be safely completed.

**Verification Method**: Test (T)
