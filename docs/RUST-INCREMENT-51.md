# Rust increment 51: bounded post-stop status observation

Recorded 2026-10-17 on `feature/rust-transfer-coordinator`.

## Problem and change

Increment 50 preserved an existing qualification API failure: both stop clients
returned ShutdownIncomplete/exit 2, but an immediate daemon status still reported
Draining. The client conservatively subtracts the first exchange time from the
remaining daemon budget. Its expiry can precede the daemon's expiry slightly;
the immediate status assertion incorrectly required them to coincide. Preserve
that [failed gate report](RUST-SLES-PUBLICATION-INITIAL-QUALIFICATION-EVIDENCE.json)
and [full target log](RUST-SLES-PUBLICATION-INITIAL-QUALIFICATION-FAILURE.txt).

Change only the existing repeated-stop integration test in
`rust/crates/file-mover/tests/api.rs`. After both stop replies, poll daemon status
within the original four-second bound per round, measured from its first stop.
This is a test observation bound, not a new runtime shutdown deadline. Never
start a fresh four-second interval per status query. Accept only Draining/exit 0
with positive,
nonincreasing remaining milliseconds, the same original instance identity and
the loaded two-second budget. Require eventual ShutdownIncomplete/exit 2 with
zero remaining time before the original bound. Unknown/unavailable/stopped or
replacement-instance observations fail; the daemon must remain alive behind its
qualification-only drain pause throughout these observations.

Keep the original repeated stop, SIGTERM and edit-to-3600-seconds checks. Both
stop replies must still report the original two-second budget and zero remaining
time. Initialization must still refuse while the paused daemon owns state.
Release the fixture pause only afterward, confirm exit and NoActiveOwner, verify
source bytes, and prove normal restart/stop. Run three independent rounds per
qualification profile; the test count stays unchanged. A passing test does not
assert that every round happened to observe intermediate Draining.

No production Rust module, controller/server timing, default 60-second wait,
configuration/schema, dependency, retry/review rule or publication protocol
changes. Production NFS and source deletion remain disabled. No NFS fixture is
rerun or newly qualified by this test-only increment; retain prior NFS evidence
with its original source/run IDs and limitations. These are local drain-pause
integration rounds in qualification builds, not real kernel-blocked NFS cases.

## Validation

Fresh production and qualification checks use `scripts/check-rust-sles.py`:
GNU/glibc-2.22 cargo-zigbuild, all emitted ELF audits and exact debug/release
target execution in pinned SLES 12 SP5 userspace. Require unchanged graph,
complete source/archive/artifact audits, the repeated-stop test passing three
rounds in each qualification profile, and service binaries identical to the
previous passing increment 50 builds. Containers share the modern runner
kernel/CPU; no old-kernel, systemd or NAS settlement qualification follows.

## Results

Both fresh gates passed on the first run:

| Build | Run | Target tests per profile | ELF audits / negative controls |
|---|---|---|---|
| Production | `20261017T223628Z-210e8bd1` | 204 debug, 204 release | 20 / 6 |
| Qualification | `20261017T223629Z-a96b200b-nfs-qualification` | 205 debug, 205 release | 20 / 6 |

Each API harness passed all 83 tests, including the updated repeated-stop test.
The two qualification profiles exercised six independent rounds in total,
checking twelve stop replies against the original two-second budget, same-instance
status/countdown and the unchanged four-second observation bound in every round.
Ownership refusal, retained source bytes and normal exit/restart checks passed.
The unchanged default-60 integration test also passed in both qualification
profiles. These local drain-pause results add no actual NFS deadline/cancellation
coverage. No intermediate-Draining observation count was instrumented or claimed.

Both complete 61-file source inventories match current Rust bytes, and the
source-archive digests and all twenty executable hashes per gate were verified.
Compared with the prior increment 50 archives, only api.rs differs; Git comparison
confirms all text outside the target function is unchanged. All four production/
qualification × debug/release service binaries are byte-for-byte identical to the
prior passing builds (`20261017T214602Z-869cf81f` and
`20261017T215827Z-3df72cb2-nfs-qualification`). Runtime deadlines, defaults,
production NFS/source deletion gates and deployed ABI are unchanged.

The graph remains 42 external packages; all ELF artifacts retain maximum imported
GLIBC_2.18 and standard `/lib64/ld-linux-x86-64.so.2`. Formatting, Clippy,
traceability, whitespace, documentation links and 95 SC/six DOC identifier checks
pass. See [production evidence](RUST-SLES-EVIDENCE.json) and
[qualification evidence](RUST-SLES-QUALIFICATION-EVIDENCE.json). Both gates
completed cleanup. Independent Podman inspection confirms no containers or
fixture resources remain; only the two existing toolchain/registry cache volumes
and default network are retained.

SC-034/093 and DOC-03/04/05 now record the bounded observation and actual test
scope. The future-only roadmap no longer lists this completed test task. Keep
increment 50's original failed report/log and prior NFS reports unchanged;
FR-03/05 and remaining deployment/storage qualifications stay open.
