# Rust increment 55: source outage midway through copying

Recorded 2026-10-17 on `feature/rust-transfer-coordinator`.

## Finite scope and pass conditions

Add `--coordinator-death --death-scope source-mid-copy`: four cases,
debug/release, each blocked/following a two-second local stop. Both private roots
are on independent controlled NFSv4.1 hard-mounted endpoints; SQLite, ownership
and control state remain local. Stop only the source server NFSD threads.

Add a qualification-only `source_copy` rendezvous after the first copied chunk:
advise random access/cache eviction on the source descriptor before the next
read, then pause. Advice alone is not eviction evidence. Require a 1 MiB
staging prefix at the pause, actual D-state after release into source outage,
a blocked x86_64 read syscall on the claimed-source descriptor, no local
read-completed marker and an unchanged destination partial while
healthy-peer fresh write/read/metadata probes pass. Never hash/re-warm source
after the selected cache advice. Hash at healthy setup and check identity only
at the pause. This controls read-loop interruption, not an in-flight RPC boundary.

Kill the coordinator while blocked or after bounded stop. Surviving orphans
retain their original logical epoch through three bracketed local guard/status
samples and refuse service/initialize/transfer competitors. Distinguish prompt
stop from surviving-orphan coverage; do not require or infer physical guard
closure. Restore endpoints, confirm old worker exit, then recover using the
original state. Preserve source/database identities, enrollment evidence, old
partial allocation/valid prefix, producer-reused paths and stable roots. Require
Committed on attempt 2 with verified payload/manifest, retained private source
and cleanup false. No retry/review, shutdown deadline or production-enable change.

Retain six normal transfer baselines, twelve NFS-state-parent refusals, all
state-file/OS checks, isolated startup and clean teardown. Run fresh production
and qualification GNU/glibc-2.22 zigbuild/ELF/pinned-SLES gates and use their exact
artifacts. Record source/artifact/driver hashes and actual outcomes before
updating scenario support.

## Limits

Two container server namespaces share one modern WSL2 kernel and physical host;
tmpfs and NFSD thread outages do not qualify physical NAS failures, partition/
reclaim, delayed RPC settlement, disk/power durability or old kernels. The
payload is one nested 2 MiB + 17-byte file, not a production-size/load test.
Following-stop cases use two seconds, not default-60 deadline qualification.
Other endpoint directions/phases, bootstrap, actual mount/security discovery,
systemd/account policy and release gates remain open. Production NFS and source
deletion remain disabled.

## Initial instrumentation refusal

The [initial failed run](RUST-NFS-SOURCE-MID-COPY-INSTRUMENTATION-FAILURE-EVIDENCE.json),
`nfs-20261018T040358Z-fe4dc59b`, passes six normal baselines but stops the first
new case when its root observer cannot read `/proc/<worker>/syscall` in the
capability-restricted client. It is failed instrumentation, not passing
coordinator-death or source-copy recovery evidence. Cleanup errors are empty.

A network-disabled disposable SLES shell probe confirms the root observer needs
SYS_PTRACE plus DAC_READ_SEARCH to inspect a different UID's syscall file. Add
those capabilities only to the source-mid-copy fixture client, alongside its
existing mount capability; the service still runs as UID 1000 with zero
inheritable/permitted/effective capabilities and NoNewPrivs=1. The new case
asserts those worker properties. Descriptor resolution uses the same UID.
Production deployment capabilities and Rust artifacts are unchanged by this
instrumentation correction. Retain the failed report separately from the rerun.

## Results

The [raw evidence](RUST-NFS-SOURCE-MID-COPY-DEATH-EVIDENCE.json) records `nfs-20261018T041151Z-347d27e7`.
All four cases passed: two blocked orphans retained ownership and two
following-stop cases exited promptly. All six competing effect commands
refused; no ownership loss occurred. No terminating orphan survived a stop.

| Profile | Death phase | Outcome | Retained old partial bytes after recovery |
|---|---|---|---|
| debug | blocked | Blocked orphan retained | 2097169 |
| debug | terminating | Prompt confirmed exit | 1048576 |
| release | blocked | Blocked orphan retained | 2097169 |
| release | terminating | Prompt confirmed exit | 1048576 |

All four workers are observed in x86_64 read(2) with a 1 MiB request and a
descriptor naming their claimed source. Actual D state brackets observations;
the local read-completed marker stays absent before restoration. The original
1 MiB destination prefix, inode and hash remain unchanged while source NFSD=0,
destination NFSD=2 and healthy-destination probes pass. Source identity only is
observed at the pause; the setup hash predates source cache advice. All
10 healthy-peer probes pass, maximum 0.953 seconds.

Surviving orphans preserve their original epoch through three bracketed local
guard/status samples and competitor refusals. Physical raw-lock closure is
observational (0 cases), not a required branch here;
the earlier strict increment 47 regression remains available. Maximum observed
orphan status is 0.938 seconds; two-second stop response is
1.078 seconds, including Podman overhead. Prompt stop before
coordinator kill is not surviving-orphan or coordinator-SIGKILL coverage.

All cases restore endpoints and confirm old exit before normal original-state
recovery to Committed on attempt 2. Database/source inodes, enrollment evidence,
old partial allocation/valid bytes, producer-reused paths and stable roots are
preserved. Final source/destination SHA-256 and completion manifest semantics
pass. Private sources remain retained and cleanup false. The old worker may
finish an authorized read/write after restoration before exit; the retained
partial sizes above record the actual result, not cancellation by timeout.

Six normal transfer baselines, twelve NFS-state-parent refusals, 184 state-file
refusals across fourteen preserved fixtures and retained OS/startup checks pass.
Cleanup errors are empty. The report preserves detailed snapshots and logs.
A post-run Podman inventory confirms no containers, fixture volumes or fixture
networks remain; only the two Rust cache volumes and default network remain.

Exact fixture command:

```powershell
python scripts/check-nfs-boundaries.py rust/validation/20261018T034035Z-f07bc86c --qualification-gate rust/validation/20261018T034048Z-9fd95a19-nfs-qualification --isolated-startup --coordinator-death --death-scope source-mid-copy
```

## Compatibility and provenance

Fresh production `20261018T034035Z-f07bc86c` passes 204 tests per profile; qualification
`20261018T034048Z-9fd95a19-nfs-qualification` passes 205 per profile. Both complete GNU/glibc-2.22 cargo-zigbuild,
twenty ELF audits, six negative controls and exact debug/release execution in
pinned SLES 12 SP5 userspace. Formatting, Clippy and locked package/feature checks
pass. The graph remains 42 external packages; maximum imported GLIBC_2.18 and
standard `/lib64/ld-linux-x86-64.so.2` remain within the target boundary.

The fixture uses these fresh exact service binaries. All 61 archived Rust files,
source archive digests and executable hashes are checked against their reports
and current bytes. The only Rust input change adds the selected source-copy
cache-control call and tracks its read-completed observation. Production
before_read is a no-op; no package, runtime retry/review, shutdown deadline or
production-enable change is introduced. Executed driver hashes match working
bytes and staged blobs after LF normalization. See [production evidence](RUST-SLES-EVIDENCE.json)
and [qualification evidence](RUST-SLES-QUALIFICATION-EVIDENCE.json).

The scenario catalog retains 95 SC and six DOC IDs. DOC-02/03/04/05 gain this
selected source-copy interruption evidence, with limits kept explicit. All eight
release gates remain open. Production NFS and source deletion remain disabled.
