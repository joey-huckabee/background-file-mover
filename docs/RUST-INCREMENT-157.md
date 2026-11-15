# Increment 157: NFS lab cleanup

User request 2026-11-15: fix the two NFS lab gaps found in increment 153.
Harness and documentation only; no service change.

## 1. Isolated outage startup (fixed)

Since 109dc4e (2026-11-04) the service refuses unenrolled state before any
source access. The `--isolated-startup` outage check started a fresh,
unenrolled qualification service during an NFS outage and expected it to block
in the source bootstrap; it now refused locally first, so the check could not
pass.

- With `--isolated-startup`, the harness now enrolls the NFS source with the
  qualification build first (`--initialize-source`, NFS reachable), so the
  outage startup reaches the source bootstrap and blocks there, as the check
  intends (local `--status` reports `Starting` with one bootstrap worker).
- "No SQLite created" became an exact unchanged-state check: before the outage
  the SQLite files are fingerprinted (size and SHA-256); after SIGTERM and the
  bootstrap child's confirmed exit (before NFS restoration) the database must be
  byte-identical, a `-wal` file may exist only empty (startup opens the database
  to check state compatibility; nothing is written), and no rollback journal may
  exist. The worker lifetime records are runtime ownership state and are not
  fingerprinted. Assertions report both fingerprints.
- [NFS-QUALIFICATION](NFS-QUALIFICATION.md) describes the enrollment step and
  the unchanged-state check.

Evidence: fresh gates for current main, production
`20261115T174101Z-a5aa54ba` and qualification
`20261115T180915Z-fda03e47-nfs-qualification` (both PASSED);
`nfs-20261115T190906Z-44d84f3d` with `--isolated-startup` **PASSED** end to
end (baseline cases, production refusals, SQLite state layout, inherited-lock
and outage checks). Two earlier runs failed on the check itself: the first
without a diagnostic, the second showing that the only change was an empty
`jobs.sqlite-wal`, which led to the exact rule above.

## 2. Coordinator-death kernel-closed guard (deferred)

The user deferred this for resources; it is recorded under "Release and
operational obligations" in the [roadmap](ROADMAP.md). The coordinator-death
matrix requires observing, in both builds, a terminating worker still in `D`
after the kernel closed its guard (the increment 46 counterexample, fixed in
increment 47). On the lab host's kernel (6.18 WSL2) that state does not occur:
in runs `nfs-20261115T114721Z-492a3abf` (one worker) and
`nfs-20261115T121758Z-8e686fe0` (two workers), every terminating verification
worker exited promptly when stopped (eight repetitions per run), and the
terminating copy workers stayed in `D` holding their guard. All 18 cases pass
otherwise. Options when resumed: a qualification-only hook that makes a
blocked worker drop its inherited guard (proves the increment 47 fix on any
kernel, changes the pass rule), or a host whose kernel shows the behavior.
