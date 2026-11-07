# Rust increment 52: both-NFS coordinator death and recovery

Recorded 2026-10-17 on `feature/rust-transfer-coordinator`.

## Finite scope and pass conditions

Add `--coordinator-death --death-scope both-nfs` to the retained fixture:
24 cases, debug/release × claim, payload copy, destination verification,
pre-file publication, durable file-link and durable manifest-link × blocked or
following local stop. Both private roots are on the same controlled NFS export;
the database, guard, lifetime record, configuration and control socket stay local.
Assert actual filesystem types rather than inferring placement from path names.
Each death case uses one recording with one nested 2 MiB + 17-byte payload;
the normal baselines also exercise multiple files and an empty file.
This increment changes qualification drivers only, with no Rust/runtime,
dependency, retry/review, deadline, schema or production-enable change.

Stop the controlled NFS server, release the local worker rendezvous, then require
an actual D-state child before coordinator death. Require three bracketed
raw-flock/logical-status observations and three refused competing effect commands
for each surviving orphan. A following-stop worker may exit promptly; record
that outcome separately instead of counting it as retained orphan coverage.
Keep the original epoch through actual old exit. Do not inspect unavailable NFS
from the local controller, start conflicting workers, or infer remote settlement
from local lock release, process exit or the configured two-second stop wait.

After restoring NFS, confirm old exit before normal original-state recovery.
Require the same database inode and unchanged enrollment evidence. The private
claimed source must retain its original inode, size and SHA-256; a producer's
reused original path must survive. Interrupted copying uses a new attempt while
preserving the old partial inode and valid prefix bytes; verification/publication
retain their original attempt. Publication/manifest cases additionally retain
the original verified payload inode and any existing manifest inode/hash, with
exact owned alias reconciliation and no second payload allocation. Validate final
manifest semantics, destination hash, root identities and source cleanup false.

Retain all previous death scope selectors, including increment 47's stricter
raw-lock-closure regression. Run the six normal NFS transfer baselines, state
parent/file admission refusals, OS inherited-lock/startup/interruption checks,
clean teardown and both mandatory SLES compatibility gates.

## Qualification limits

The fixture is one controlled Linux NFSv4.1 server and one client with two private
roots on one export, using a hard mount and a shared modern WSL2 kernel. It does
not qualify separate exports/NAS servers, independent endpoint failures, NetApp
or Isilon behavior, exact in-flight link/unlink or synchronization RPCs, server
reboot/power durability, delayed remote settlement, actual systemd/account policy,
old kernels/CPUs or takeover. Both-NFS bootstrap/source-read death cases remain
outside this finite matrix, as do production-size payloads and concurrent load.
Production NFS and source deletion remain disabled; FR-03/05 and the other
first-release gates stay open.

## Results

The [complete both-endpoint evidence](RUST-NFS-BOTH-ENDPOINT-DEATH-EVIDENCE.json)
records `nfs-20261017T231054Z-3ef61c70`. All 24 selected cases passed: twelve
blocked and seven terminating orphans retained ownership; five following-stop
cases exited promptly. All 57 competing effect commands refused; no ownership
loss occurred.

| Boundary | Debug blocked | Debug following stop | Release blocked | Release following stop |
|---|---|---|---|---|
| Source claiming | Blocked orphan retained | Prompt confirmed exit | Blocked orphan retained | Prompt confirmed exit |
| Payload copy | Blocked orphan retained | Terminating orphan retained | Blocked orphan retained | Terminating orphan retained |
| Destination verification | Blocked orphan retained | Terminating orphan retained | Blocked orphan retained | Terminating orphan retained |
| Before file publication | Blocked orphan retained | Prompt confirmed exit | Blocked orphan retained | Terminating orphan retained |
| Durable file-link aliases | Blocked orphan retained | Terminating orphan retained | Blocked orphan retained | Terminating orphan retained |
| Durable manifest-link aliases | Blocked orphan retained | Prompt confirmed exit | Blocked orphan retained | Prompt confirmed exit |

All surviving orphans stayed D across three bracketed raw-flock/logical-status
samples, with OwnerUnavailable/exit 2 and retained original epoch. Five workers
outlived raw-flock closure while logical exclusion remained intact: verification
and file-link in both profiles, plus release pre-publication. Raw closure is
observational for this matrix; increment 47's
strict two-profile regression is retained separately. Prompt exit is never
counted as a surviving terminating orphan.

All 24 cases restored NFS and confirmed old exit before recovery, then reached
Committed using the original database inode and unchanged enrollment receipt.
All preserved the source inode/size/SHA-256, producer-reused path, root identities,
private claimed source and source-cleanup-disabled policy. Copy interruptions
recovered on attempt 2 and retained the original partial inode with valid prefix
bytes. Verification and publication recovered on attempt 1. All twelve publication
cases kept the verified payload inode without a second allocation; all four
manifest-link cases also kept the existing manifest inode/hash and reconciled
the owned staging alias. Final manifests and destination hashes passed.

Six normal source-only/destination-only/both-NFS transfer baselines and twelve
NFS-state-parent refusals passed. All 184 state-file owner/mount/control refusals
passed across fourteen preserved fixtures (maximum 0.922 seconds). OS inherited-
lock and isolated startup/interruption checks passed; blocked-bootstrap local
status took 0.860 seconds, and SIGTERM confirmed child exit before restoration
without SQLite or readiness. Maximum orphan status was 1.125 seconds, competing
start refusal 1.203 seconds and two-second stop 2.875 seconds, including Podman
overhead. Cleanup errors are empty. Independent Podman inspection found no
containers or fixture volumes/networks; only the two toolchain/registry cache
volumes and default network remain.

Exact fixture command:

```powershell
python scripts/check-nfs-boundaries.py rust/validation/20261017T223628Z-210e8bd1 --qualification-gate rust/validation/20261017T223629Z-a96b200b-nfs-qualification --isolated-startup --coordinator-death --death-scope both-nfs
```

## Compatibility and exact artifacts

Fresh production `20261017T231054Z-44eb94d4` passed 204 tests per profile; qualification
`20261017T231054Z-7f99fe60-nfs-qualification` passed 205 per profile. Both use GNU/glibc-2.22 cargo-zigbuild,
twenty ELF audits and six negative controls, with exact target execution in
pinned SLES 12 SP5 userspace. Formatting, Clippy and the locked feature/package
checks pass. The graph remains 42 external packages, maximum imported GLIBC_2.18
and standard `/lib64/ld-linux-x86-64.so.2`.

The fixture used the passing increment 51 gate directories shown above. Complete
61-file source inventories, archive digests and all fresh executable hashes were
verified; the four service binaries are byte-identical between reused and fresh
gates. Captured NFS driver hashes match the executed working-copy bytes. No Rust
build inputs or application code changed. See [production evidence](RUST-SLES-EVIDENCE.json)
and [qualification evidence](RUST-SLES-QUALIFICATION-EVIDENCE.json). The fixture
kernel was `6.18.33.2-microsoft-standard-WSL2`; this is container userspace compatibility evidence.

SC-034/036/039/040/050/092/093/095 and DOC-02/03/04/05 carry the selected layout
evidence and remaining documentation scope. SC-089/094 delayed-server-effect
qualification stays pending. The future-only roadmap retains separate-export,
remaining both-NFS bootstrap/read, in-flight RPC, durability and lifecycle work;
no release gate or production NFS/source-deletion switch is closed by this run.
