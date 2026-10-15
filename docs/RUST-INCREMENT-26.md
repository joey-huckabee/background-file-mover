# Rust increment 26: define fenced enrollment before implementation

Documentation increment on `feature/rust-transfer-coordinator`, 2026-10-15.
The [enrollment contract](FENCED-ENROLLMENT-DESIGN.md) separates first setup,
matching restart and positively fenced recovery. No Rust implementation, schema,
configuration, dependency, executable or qualification behavior changes here.

## Findings and decisions

Code review of `Store::enroll_source` confirms that the schema-9 enrollment is
local to one SQLite instance. The source marker authorizes a coordinator label;
it does not persistently bind the source to the original database. A fresh empty
database can enroll once custody is available. Increment 25's empty-scope peer
release control is consistent with this, but is not a populated-root takeover
test. Do not describe the proposed persistent source receipt as implemented.

The first implementation will pair explicit unused-scope enrollment with a
protected persistent source receipt and the original local state instance.
Ordinary startup must never invent missing ownership. A prepared/active enrollment
state machine must tolerate the lack of an atomic transaction between SQLite and
the source filesystem; partial or foreign states stay unready. Object allocation
ownership needs its own tested strategy before implementation is complete.

Restrict the first implementation to unused-scope enrollment and matching restart.
Existing-job re-enrollment, database-loss recovery, cloned/stale state and takeover
need separate fencing/reconciliation evidence. A copied instance ID cannot detect
a clone or stale backup. A new lock, a process exit, an operator assertion or a
generation number cannot independently stop outstanding filesystem effects.
No mutating rebind command or `--force` shortcut is introduced.

The contract defines required refusal, interrupted enrollment and delayed-effect
acceptance cases. It also specifies what a future independently qualified fence
must exclude, and that re-enrollment must preserve original job/route/integrity
evidence. No host/storage fence is chosen or qualified here. Lost-lock and
partition/reclaim behavior remain unqualified; repeated `flock` calls are not
proof of uninterrupted custody. Production NFS and source deletion remain off.

## Validation and limits

Reviewed the design against current source enrollment, regular-file custody,
schema-9 destination pins, the root ownership design and the protocol's uncertain
effect/recovery rules. Checked changed Markdown links, stable scenario IDs and
Git whitespace. Corrected the stale validation-in-progress sentence in increment
25 without changing its recorded gate/fixture results.

No Rust builds/tests or NFS fixture were run for this documentation-only change.
The passing increment-25 SLES/NFS reports remain historical evidence for their
exact source archives, not evidence that the new enrollment contract is enforced.
SC-064–067 explicitly label the new situations as gaps/future work; DOC-03–05
include their user explanations. Registration and offline repair stay deferred.

Next implement explicit first enrollment and matching restart with paired source
ownership, then qualify interrupted enrollment and fresh-state refusal. Keep
populated-state rebind and takeover blocked until a qualified fence and recovery
procedure exist. Partition/reclaim diagnostics can inform that work but must not
be presented as a production fence.
