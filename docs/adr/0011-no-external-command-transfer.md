---
status: accepted
date: 2026-08-02
decision-makers: Joey
precedent: ADR-0010 (SQLite durable state), docs/CYBERSECURITY.md
---

# No external-command transfer strategy

## Context and Problem Statement

An inherited milestone delivered three transfer strategies: a same-filesystem
move, a cross-filesystem copy, and `ExecTransfer` — an arbitrary external
command (`rsync -a --remove-source-files {source} {dest}`) configured as a
free-text string and run via `fork`/`execvp`.

`L1-SYS-015` required all three. That requirement exists only because it was
derived from the inherited design's `L1-023`; nothing in the actual problem
asks for it.

## Decision Drivers

* The product's value is atomic moves with a single commit point and provable
  crash recovery (`L1-SEC-001`, `L1-SEC-002`)
* Configuration is validated data, not a program
* The deployment target is a STIG'd host with mandatory access control and
  application allowlisting
* The destination in the actual use case is a filesystem path

## Considered Options

* **Full delegation** — the command owns the move including source removal
* **Constrained delegation** — the command writes to a temp path we choose; we
  verify, place atomically, and remove the source
* **No external-command strategy**

## Decision Outcome

Chosen option: **no external-command transfer strategy.**

Three reasons, in increasing order of how hard they are to work around.

**It makes the configuration file executable.** Every other configuration
value is strictly validated so it cannot express anything but data — bounded
integers, an enum, a path with no embedded NUL. A free-text field that becomes
`execvp` gives anyone who can write the config arbitrary code execution as the
service account. On a host running application allowlisting, a daemon that is
also a generic command executor is precisely the pattern the control exists to
prevent.

**It voids the guarantees that justify the daemon.** An external command has
no commit point we control. Killed mid-command, recovery cannot distinguish
"the command finished and removed the source" from "the command never ran and
something else removed it" — the exact ambiguity `L1-SEC-001` and `L1-SEC-002`
exist to eliminate. Every guarantee would become conditional on which strategy
was configured, which is a materially weaker product than an unconditional one.

**It cannot honour the surrounding controls.** `L1-SEC-006` (never silently
overwrite) is unenforceable when `rsync` does the writing. `L2-SEC-005`
(trusted-UID and sticky-bit preconditions) is meaningless when an arbitrary
binary does the work. `L2-SEC-013` (SELinux labelling before the commit
rename) has no commit rename to precede.

Constrained delegation was considered seriously and rejected as not worth its
cost: it preserves the guarantees, but only serves commands producing a local
file — which is the case the daemon already handles natively. It buys an
extension point for transformations (compression, encryption) at the price of
the config-as-code hazard, and no such transformation is required.

### Consequences

* Good: every guarantee is unconditional. There is no configuration that
  silently disables the crash-recovery story.
* Good: the configuration file stays data. No validated-parameter file becomes
  an execution vector.
* Bad: no escape hatch for unanticipated destinations. A need the daemon does
  not natively support requires a code change rather than a config change.
* Bad: remote destinations — another host over SSH, an object store — are not
  supported at all. Should that become a genuine requirement, it is a design
  conversation with its own threat analysis, not a config key.

### Note on what was kept

The inherited implementation's **subprocess discipline was correct** and is
retained as a rule for any future subprocess this project ever spawns: split
the command into an argv array once, substitute into elements rather than into
a string, `fork`/`execvp`/`waitpid`, and never `system(3)` or any shell. That
is already `L2-SEC-008`. Rejecting the strategy is not a judgement on how it
was built.
