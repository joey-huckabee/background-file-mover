# Rust increment 53: separate NFS exports during coordinator death

Recorded 2026-10-17 on `feature/rust-transfer-coordinator`.

## Finite scope and pass conditions

Extend the retained fixture with `--coordinator-death --death-scope
separate-exports`: debug/release × claim, copy, destination verification,
pre-publication, file-link and manifest-link × blocked/following local stop.
These 24 cases repeat increment 52's custody/recovery obligations across two
separately mounted exports backed by distinct bounded server tmpfs filesystems.
SQLite, guard, worker lifetime record and control/configuration remain local.

Require distinct server and client filesystem devices, distinct client mount IDs,
hard NFSv4.1 mounts, and an actual cross-export hard-link refusal with the source
unchanged and destination absent. Every case checks actual endpoint/state
filesystem placement. No Rust/runtime code, dependency, schema, retry/review,
shutdown deadline or production-gate change is intended.

Each case uses one nested 2 MiB + 17-byte file. Stop the shared fixture server,
release the worker rendezvous and require actual D state. Surviving orphans must
retain the original local epoch through three bracketed raw-lock/status samples
and refuse three competing effect commands. Following-stop cases use the existing
two-second budget and distinguish prompt confirmed exit from retained terminating
workers. Never inspect unavailable NFS from the local controller or infer remote
settlement from a timeout, signal, free lock or process exit.

Restore NFS and confirm old exit before normal original-state recovery. Require
Committed, the original database/source inode and enrollment evidence, preserved
producer-reused paths, source retention/cleanup false and unchanged root identities.
Interrupted copies retain their old allocation and valid bytes while using attempt
2; verification/publication retain attempt 1. Publication and existing manifest
identities/hashes survive owned alias reconciliation without a second payload
allocation. Validate final payload hashes and manifest semantics. Keep previous
selectors and increment 47's strict raw-lock-closure regression available.

Retain the six normal transfer baselines, twelve state-parent refusals, all state
file admission/OS startup-lock-interruption checks and clean teardown. Run fresh
production and qualification GNU/glibc-2.22 zigbuild/ELF/pinned-SLES gates and
verify exact sources, executable hashes and fixture-driver provenance.
The retained normal baselines use their original source-only, destination-only
and same-export both-NFS layouts; separate-export death cases use the single
nested payload described above, not a new multi-file/load qualification.

## Qualification limits

Two exports share one controlled server and fail/restore together. This does
not qualify independent NAS/server outages, NetApp/Isilon behavior, exact in-flight
RPCs, delayed remote settlement, persistent storage or server reboot/power loss.
The tmpfs backends bound resource use; they do not model production disk durability.
Containers share the modern WSL2 kernel. Old kernels/CPUs, actual systemd/account
policy, both-NFS bootstrap/source-read deaths, large payloads and concurrent load
remain outside this finite matrix. Production NFS and source deletion stay
disabled; all eight first-release gates remain open.

## Results

The [separate-export evidence](RUST-NFS-SEPARATE-EXPORT-DEATH-EVIDENCE.json)
records `nfs-20261018T005553Z-66d9a470`. All 24 cases passed: twelve blocked
and seven terminating orphans retained ownership; five following-stop cases
exited promptly. All 57 competing effect commands refused; no ownership loss
occurred.

Both server backends have distinct filesystem devices. Both NFS client mounts
have distinct devices and mount IDs, with hard/vers=4.1 options. The cross-export
hard link failed with Invalid cross-device link, leaving its source identity/hash
unchanged and no destination name. Every death case also proves source,
destination and local state have three distinct filesystem devices. Each server
backend is bounded to 128 MiB and 4096 inodes; neither is filled by this matrix.

| Boundary | Debug blocked | Debug following stop | Release blocked | Release following stop |
|---|---|---|---|---|
| Source claiming | Blocked orphan retained | Prompt confirmed exit | Blocked orphan retained | Prompt confirmed exit |
| Payload copy | Blocked orphan retained | Terminating orphan retained | Blocked orphan retained | Terminating orphan retained |
| Destination verification | Blocked orphan retained | Terminating orphan retained | Blocked orphan retained | Terminating orphan retained |
| Before file publication | Blocked orphan retained | Prompt confirmed exit | Blocked orphan retained | Prompt confirmed exit |
| Durable file-link aliases | Blocked orphan retained | Terminating orphan retained | Blocked orphan retained | Prompt confirmed exit |
| Durable manifest-link aliases | Blocked orphan retained | Terminating orphan retained | Blocked orphan retained | Terminating orphan retained |

Every surviving orphan stayed D through three bracketed raw-flock/status samples
and reported OwnerUnavailable/exit 2 with its original epoch intact. Five workers
outlived raw-flock closure with logical ownership retained: verification and
manifest-link in both profiles, plus debug file-link. Raw closure is
observational here; the stricter increment 47 matrix
remains available separately. Prompt exit is distinct from surviving termination.

All cases restored NFS and confirmed old exit before original-state recovery.
Every case reached Committed with its original database/source inodes and enrollment
evidence, unchanged roots, retained private source, producer reuse preserved and
source cleanup false. Copy interruptions retained the old partial inode and valid
bytes, then used attempt 2; verification/publication used attempt 1. All twelve
publication cases preserved the verified payload inode without a second
allocation; all four manifest-link cases preserved the existing manifest
inode/hash and reconciled owned aliases. Final payload/manifest validation passed.

Six normal transfer baselines, twelve NFS-state-parent refusals and 184 state-file
owner/mount/control refusals across fourteen preserved fixtures passed (maximum
0.922 seconds). OS inherited-lock/isolated startup/interruption checks passed;
blocked-bootstrap local status took 0.890 seconds, and SIGTERM confirmed child
exit before restoration without SQLite or readiness. Maximum observed
orphan status was 1.032 seconds, competing-start refusal
0.984 seconds and two-second stop 2.890 seconds, including
Podman overhead. Cleanup errors are empty. Independent Podman inspection found
no containers or fixture volumes/networks; only the existing toolchain/registry
cache volumes and default network remain. Inspect the raw report for every
refusal and preserved identity snapshot.

Exact fixture command:

```powershell
python scripts/check-nfs-boundaries.py rust/validation/20261017T231054Z-44eb94d4 --qualification-gate rust/validation/20261017T231054Z-7f99fe60-nfs-qualification --isolated-startup --coordinator-death --death-scope separate-exports
```

## Compatibility and provenance

Fresh production `20261018T005552Z-19547ccf` passed 204 tests per profile; qualification
`20261018T005553Z-3e07ad26-nfs-qualification` passed 205 per profile. Both completed GNU/glibc-2.22 cargo-zigbuild,
twenty ELF audits, six negative controls and exact debug/release execution in
pinned SLES 12 SP5 userspace. Formatting, Clippy and locked package/feature checks
pass. The graph stays at 42 external packages, maximum imported GLIBC_2.18 and
standard `/lib64/ld-linux-x86-64.so.2`.

The fixture reused increment 52's passing gate directories in the command above.
Both 61-file inventories match current Rust bytes; archive digests match their
recorded reports, and all fresh executable hashes were verified. All four reused
service binaries are byte-identical to the fresh
gates. Captured driver hashes match executed working-copy bytes; staged Git
blobs are checked after LF normalization. No Rust build inputs changed. See
[production evidence](RUST-SLES-EVIDENCE.json) and
[qualification evidence](RUST-SLES-QUALIFICATION-EVIDENCE.json). The shared
fixture kernel was `6.18.33.2-microsoft-standard-WSL2`, not an old SLES kernel.

SC-034/036/039/040/050/092/093/095 and DOC-02/03/04/05 record the selected
layout. SC-089/094 remain pending for delayed server effects. The future-only
roadmap retains independent endpoint failures, remaining both-NFS bootstrap/read,
in-flight RPC, actual mount/security, durability and systemd/account work.
No release gate or production NFS/source-deletion setting is enabled.
