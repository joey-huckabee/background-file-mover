# Rust increment 72: buffered file publication and manifest interruption/recovery

## Scope

Extend retained NMP-41B qualification to selected file publication and manifest
commitment interruptions on same-share and separate-share layouts. Production
NFS and source deletion remain disabled. No Rust source, locked dependencies,
shipping executable, schema, retry/review behavior or shutdown deadline changes.

The mount-profile runner gains `--buffered-publication`, mutually exclusive with
its other worker matrices. A dedicated helper reuses audited qualification
artifacts and existing relocation hooks. The isolated root observer uses the
same SYS_PTRACE/DAC_READ_SEARCH facility as the buffered-read lab; ordinary
service/workers/controllers/HTTP remain UID/GID 1000 with zero active capabilities
and NoNewPrivs. All mounts, signals and effects belong to the owned fixture.

## Acceptance

Sixteen cases: two layouts, debug/release, and four points—`file_link_sync`,
`file_unlink`, `manifest_link_sync`, `manifest_unlink`. First capture actual
owned publication/manifest aliases and content, durable job phase and original
state/enrollment/source identities. Require claimed job 1/202 before producer
path reuse. Both layouts use buffered NFSv4.1/TCP/sec=sys, hard mounts, local state
and disjoint private role roots; two exports still share one server/outage domain.

During the joint NFSD outage, unlink cases must prove D-state `unlinkat` on the
correct staging-parent descriptor. Returned-LINK cases stay before their following
sync call and are SIGSTOPped; they are explicitly process-crash controls. Keep
health/job/control bounded with no replacement worker. Same-ID replay is checked
before outage and after recovery. After coordinator
SIGKILL, observe old-worker exclusion and refuse alternate-listener service,
initialization and direct-transfer contenders. Then kill the old worker, restore
storage and confirm actual exit before original-state recovery.

Recover on attempt 1 without overwriting/reallocating the original publication;
manifest cases must preserve their original manifest inode and digest. All owned
staging aliases disappear, source stays retained, and new producer bytes survive.
Another clean stop/restart/replay must preserve the same committed job and objects.
No review bypass, state reset, enrollment refresh or deletion is an acceptance aid.

## Results

Final run `mount-profile-20261019T044147Z-f2a623d7` **passes**: sixteen actual worker cases,
43 independent model/inventory controls, 9 exact driver snapshots and
cleanup_errors=[]. [Raw evidence](RUST-NFS-BUFFERED-PUBLICATION-EVIDENCE.json)
retains actual configuration/mount/device observations, namespace inode/link/hash
snapshots, syscall/descriptor records, worker security, original local state and
enrollment, control/contender/exit results, commitment and replay evidence/logs.
The client reports `glibc 2.22` on the shared kernel `6.18.33.2-microsoft-standard-WSL2`;
this is exact SLES userspace evidence, not an old SLES kernel qualification.

| Point | Same-share debug | Same-share release | Separate-share debug | Separate-share release |
|---|---|---|---|---|
| file_link_sync | Passed | Passed | Passed | Passed |
| file_unlink | Passed | Passed | Passed | Passed |
| manifest_link_sync | Passed | Passed | Passed | Passed |
| manifest_unlink | Passed | Passed | Passed | Passed |

All eight pending-unlink cases identify x86_64 syscall 263, flags zero,
the correct staging-parent descriptor and D state with zero NFSD threads.
The eight returned-LINK cases remain before following sync, with their local
pause unreleased and worker stopped. All 48 competing service/initialization/
direct-transfer commands refuse before old-worker SIGKILL. After restoration,
every old coordinator/worker thread is exited before recovery begins.

Normal original-state recovery completes all sixteen cases on attempt 1,
preserving original payload allocations and, in manifest cases, the original
manifest allocation/content. Staging aliases disappear, final link counts become
one, source custody/content remain retained, and newer producer bytes plus a
second clean restart/replay survive unchanged. All eight pending-unlink cases
retain both owned aliases after old-worker exit; normal recovery then removes
the staging alias. This is not matched server-completion/reply-loss proof.

Raw flock is contended in 32/32 orphan samples; 0 cases observe early
raw-lock closure in those samples. This is measured orphan exclusion before
worker SIGKILL, not new terminating/free-raw-guard or NAS-settlement qualification.

Both fresh required SLES gates pass without cleanup errors:

| Configuration | Run ID | Debug / release tests | Audited ELF artifacts |
|---|---|---:|---:|
| Production | `20261019T043611Z-20b3d700` | 211 / 211 | 20 |
| Qualification | `20261019T043611Z-3152e430-nfs-qualification` | 212 / 212 | 20 |

[Production](RUST-SLES-EVIDENCE.json) and
[qualification evidence](RUST-SLES-QUALIFICATION-EVIDENCE.json) retain the pinned
cargo-zigbuild GNU/glibc 2.22 build, ELF interpreter/library/symbol audit, six
negative controls per configuration, exact SLES-userspace test execution,
formatting/Clippy and 42 locked dependencies. There is one shipping executable;
artifact counts include tests and both profiles.

The live matrix uses passing source-identical increment-71 gates
`20261019T033428Z-dca3f6f6` and
`20261019T033430Z-125e507b-nfs-qualification` while fresh gates run. The
[independent input audit](RUST-NFS-BUFFERED-PUBLICATION-INPUT-EVIDENCE.json)
verifies all 62 Rust entries in both fresh archives and live gate archives,
all forty fresh artifact hashes and byte equality to the live input gates,
all nine final driver snapshots/current bytes, tuple coverage and acceptance
invariants. It preserves fresh source archives and the exact verifier source,
plus the failed initial report hash. Gzip metadata can differ; Rust entry bytes
and executable/test bytes must match. No Rust source or Cargo.lock changed.

Independent post-run inventory confirms both Podman engines have no containers.
The rootful engine retains only its pre-existing toolchain cache volumes
`file-mover-rustup-1-99`/`file-mover-cargo-registry` and default `podman` network;
owned export volumes/networks are removed. Cached images remain available.
Cleanup uses normal NFS unmounts, with no host/NAS data or configuration changed.

Initial run `mount-profile-20261019T043626Z-cbfb180d` remains **FAILED** in
[the original report](RUST-NFS-BUFFERED-PUBLICATION-INITIAL-EVIDENCE.json), with
cleanup_errors=[]. The harness incorrectly required same-ID POST replay to return
202 during joint source/destination outage. Replay invokes supervised custody
validation, so that expectation also required a separate source-validation path
to complete during outage. The assertion failed before coordinator-death acceptance; no native passing
case is claimed. The actual HTTP response was not captured by that draft harness,
so no specific response code/body is inferred from the failed assertion. The
corrected matrix records 202 replay before outage and after recovery, and retains
health/status/control-only observations during the joint outage. No Rust behavior
or timeout is changed to make the test pass.

## Reproduction and limitations

Follow the [step-by-step lab](NFS-BUFFERED-PUBLICATION-LAB.md). It documents exact
commands, infrastructure/privileges, checkpoint ordering, syscall and ownership
proof, original-state recovery, replay, normal unmount and bounded cleanup.

An already visible valid manifest can precede SQLite Committed; the tests require
its payload to be fully published and valid. A payload-only interruption must
leave no consumer manifest. These are owned-inode reconciliation tests, not a
new foreign-target conflict race; existing local no-clobber negative controls
remain separate. Raw guard observations are reported as measured and never
treated as NAS-side cancellation/settlement authority.
Contender refusal is sampled before the old worker receives SIGKILL; afterwards
the harness waits for actual old-thread exit before starting anything. This adds
no terminating/free-raw-guard contender branch; earlier lifetime-ownership
regression evidence remains separately applicable.

Pending client unlinkat is not matched server completion with a withheld reply.
Returned LINK before its following sync is not a pending fsync/COMMIT failure or
power-loss test. This one-client/live-tmpfs-server/shared-modern-kernel fixture
does not establish independent NAS/cache/failover/reclaim, delayed remote-effect
settlement, persistent media, old-kernel semantics, every boundary/direction,
production-sized load or endurance. Keep remaining buffered bootstrap/claim,
post-unlink sync and actual sync/RPC loss qualification open. FR-03/05 and all
eight release gates remain open; production NFS and source deletion stay off.

SC-107 and DOC-01/02/03/04/05 track the user-facing explanation and remaining
guide work. Earlier stable IDs remain intact. The roadmap retains future work
only, with evidence in this report and the scenario catalog.
