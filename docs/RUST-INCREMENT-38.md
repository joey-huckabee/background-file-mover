# Rust increment 38: native source-space depletion and recovery

Qualification increment on `feature/rust-transfer-coordinator`, 2026-10-16.
Implements the next selected FR-02 acceptance cases from the
[first-release checklist](RUST-FIRST-RELEASE.md). Runtime code, dependencies,
configuration defaults and persisted/wire formats are unchanged. Production
NFS and source deletion remain disabled.

## Finite acceptance matrix

The retained `scripts/check-nfs-boundaries.py --source-storage` option requires
passing production and qualification SLES gates with exact current Rust sources
and audited binary hashes. It retains normal-operation baseline and OS/startup
checks; it does not imply `--runtime`, `--ownership`, `--enrollment-storage` or
`--delivery-storage`. The new `scripts/nfs_source_storage.py` is permanent fixture
capability and its driver hashes are recorded in the report.

Both debug and release execute the same cases on a separate 32 MiB/512-inode
server tmpfs source export, hard NFSv4.1, with healthy local SQLite and destination.
The enabled policy stays at max(4 MiB, 5 percent), five-second sample age and
two-second probe timeout throughout. No synthetic fault/pause selectors are used.

| Case | Pass condition |
|---|---|
| Baseline jobs | Job 1 reaches 202 and commitment. Job 2 is durably accepted with one protected claim and a missing file; its response releases no paths. |
| Native shortage | Fill only the disposable server tmpfs until native ENOSPC, then leave 1 MiB available for ordinary claim metadata. After sufficient cache expiry, a new ID gets source_space_low, no job ID, no path release, no private claim and no job 3. Source identity/content and retained job count are preserved. |
| Existing claimed replay | Job 1 still returns 202 with the same job while low; producer-reused data is untouched. |
| Partial recovery while low | Retrying job 2 with its file absent stays handoff_pending. Add that file; identical replay confirms all claims and reaches 202/commitment despite the low-space new-key guard. A fresh new-key refusal confirms Low still applies. |
| Live restoration | Remove only the owned filler, wait out cache age and retry the previously refused identical ID/body. It becomes job 3 and commits, with the same coordinator PID and byte-identical policy/configuration. No restart, resume or database modification is used. |
| Retained evidence | Validate all three manifests, final and claimed-source sizes/hashes and original source identity. Preserve producer-reused paths and claimed source; cleanup stays disabled. |

## Results

Fixture run `nfs-20261017T021532Z-82d1b058` **passed**, exit 0, with no
cleanup errors. [Saved report](RUST-NFS-SOURCE-SPACE-EVIDENCE.json) includes both
new profile cases, six passing source/destination/both baseline transfers,
production startup refusal on NFS, inherited-lock and interrupted metadata/
isolated-startup checks. The separate runtime/ownership/enrollment/destination
storage suites were not selected and are not claimed rerun.

Both new cases measured exactly 1,048,576 available bytes against a 4,194,304-byte
required floor, returned no-job/no-release low-space refusal, recovered the
partial job while still low and accepted the previously refused submission as
job 3 after removing the filler. Restored server availability was 33,521,664 bytes
in debug and 33,488,896 in release. All three jobs committed, manifests and
payload hashes matched, original claimed-file identities and reused producer
paths survived. The policy/configuration and coordinator PID stayed unchanged.

The fixture reused the exact audited production/qualification artifacts from
increment 36 gates `20261017T000923Z-833766e7` and
`20261017T000924Z-2ecefab1-nfs-qualification`. Its driver checks complete Rust
source archive inventory/content before running, verifies binaries and their
hashes against passing gate reports, and records hashes of all three drivers.
Those driver hashes match the final files. Raw server capacity arrays record
blocks total/free/available, inodes total/free and fragment size, respectively.
The runner uses root Podman in WSL2,
pinned SLES 12 SP5/glibc 2.22 userspace and kernel
`6.18.33.2-microsoft-standard-WSL2`; no real SLES host is needed.

Fresh production gate `20261017T021546Z-70e2fc33` passed, exit 0: 177 tests
per profile, 20 audited artifacts and six ELF negative controls, formatting and
Clippy checks, 42 external packages and maximum required GLIBC_2.18. Its
58-file archived source inventory/content and all 20 local artifact hashes match
the final Rust tree/report; cleanup completed without errors. The
[production report](RUST-SLES-EVIDENCE.json) is updated. No host-only Rust tests
were used.

Fresh qualification gate `20261017T021558Z-a71f1387-nfs-qualification` also passed,
exit 0: 178 tests per profile, 20 audited artifacts, six negative controls,
formatting/Clippy checks, the same 42 external packages and maximum GLIBC_2.18.
Its complete 58-file source archive and all 20 artifact hashes match current
sources/report; cleanup completed without errors. Both freshly rebuilt service
binaries are byte-identical to those used by the source-storage fixture.
The [qualification report](RUST-SLES-QUALIFICATION-EVIDENCE.json) is updated.
Final engine inventory contains no containers or fixture networks/volumes; only
the existing toolchain/registry caches and default network remain.
These gates ran through root Podman using the documented WSL2 fallback, GNU/glibc
2.22 cargo-zigbuild and exact target test execution in pinned SLES userspace.

## Scope limits

This qualifies native tmpfs block consumption observed over the selected NFS
fixture, not a physical disk or quota. Leaving metadata headroom after ENOSPC
is deliberate: admission refusal and accepted-job recovery are the cases here,
not claiming that acceptance reserves physical bytes/inodes. External-writer
races, inode/quota exhaustion, in-flight hard-NFS statistics stalls, export
replacement, old kernels/CPUs, independent fencing and power-loss durability
remain separate obligations. SC-080 gains only live unchanged-policy behavior;
its broader restart/crash qualification does not follow from this experiment.

## Harness and documentation checks

Python syntax compilation and CLI help pass. The source-storage option refuses
before any engine setup when no qualification gate is supplied. Driver hashes
in the successful report match the final source files. Local Markdown targets,
all 81 stable scenarios, six DOC items, eight release gates, trace-matrix
consistency and Git whitespace are checked. No Rust source, Cargo manifest,
lockfile, feature, schema or runtime default changed. The scenario catalog and
DOC-03 guide explain the native fixture result and retain broader storage gaps;
future-only roadmap and handoffs move to access/authority design prerequisites.
