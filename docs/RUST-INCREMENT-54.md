# Rust increment 54: independently unavailable NFS endpoints

Recorded 2026-10-17 on `feature/rust-transfer-coordinator`.

## Finite scope and pass conditions

Add `--coordinator-death --death-scope independent-endpoints`: 28 cases,
debug/release × seven operation boundaries × blocked/following local stop.
Source-only failures cover claim application and the first source payload read.
Destination-only failures cover copying after the first chunk, destination
verification, pre-publication, durable file-link and durable manifest-link.
This deliberately selects the endpoint used at each boundary; it is not an
all-boundaries × both-failure-directions qualification.

Use two owned server containers with distinct IPs/network namespaces, separate
128 MiB/4096-inode tmpfs exports, NFSv4.1 hard mounts, distinct endpoint policy
IDs and local database/ownership/control state. Reuse the exact audited service
binaries; no Rust/runtime/dependency, retry/review, shutdown deadline or
production-enable change is intended.

Stop only the selected server's NFSD threads. Require zero threads there and
two on the healthy server, then bounded fresh-file write/read/metadata probes
on the healthy mount. Release the worker rendezvous and require actual D state
while the healthy endpoint remains usable. Repeat healthy-endpoint probing
while any orphan remains D after coordinator death/competitor refusal. Never
probe unavailable NFS from the local controller or issue global sync during an
outage. No health probe claims persistent-storage durability.

For source-read cases, hash the source at healthy fixture setup before worker
cache invalidation. At the pre-read pause observe identity only: hashing there
would repopulate the cache and undermine the read-outage test. Require the local
read-completed marker to remain absent during source/verification read outages.
The payload is one nested 2 MiB + 17-byte file; this is not a large-load test.

Every surviving orphan must keep the original local epoch, remain D across
three bracketed raw-flock/status samples, report OwnerUnavailable/exit 2 and
refuse service/initialize/transfer competitors. Following-stop cases keep the
existing two-second budget and distinguish prompt exit. Restore both endpoints
and confirm old exit before normal original-state recovery; do not infer NAS
settlement from lock release, a signal, timeout or process exit.

Require Committed with the original database/source inodes and enrollment
evidence, producer reuse preserved, private source retained/cleanup false and
stable roots. Interrupted source reads/copies retain their old allocation and
valid prefix bytes and use attempt 2; verification/publication use attempt 1.
Publication and existing manifests retain their original verified inode/hash
through owned alias reconciliation. Validate final hashes and manifest semantics.
Keep all previous selectors and increment 47's strict raw-closure regression.

Run the retained six normal transfer baselines (their original one-server
layouts), twelve state-parent and all state-file/OS refusals, isolated startup
and clean teardown. Run fresh production and qualification GNU/glibc-2.22
zigbuild/ELF/pinned-SLES gates; verify exact source, executable and driver hashes.

## Limits

Two server network namespaces still share one modern WSL2 kernel and one
physical host. Stopping NFSD threads is not a real NAS reboot, power loss,
network partition/reclaim, authenticated export identity or delayed-RPC settlement
test. Tmpfs models no persistent disk durability. Actual NetApp/Isilon profiles,
old kernels/CPUs, systemd/account policy, both-NFS bootstrap, source failure
mid-copy, every opposite-endpoint boundary, concurrent load and indefinite outages
remain outside this matrix. Production NFS/source deletion stay disabled and
all first-release gates stay open.

## Results

The [independent-endpoint evidence](RUST-NFS-INDEPENDENT-ENDPOINT-DEATH-EVIDENCE.json) records `nfs-20261018T021606Z-942892cd`.
All 28 cases passed: 14 blocked and 4 terminating orphans retained ownership;
10 following-stop cases exited promptly. All 54 competing effect commands
refused; no ownership loss occurred.

Both endpoints have distinct container IDs, network namespaces, addresses,
server tmpfs devices, client devices and mount IDs. Their NFSv4.1 mounts are hard.
Each stopped endpoint reports zero NFSD threads while its healthy peer reports
two. Every case confirms actual D-state worker blockage while fresh healthy-peer
write/read/metadata probes complete. Surviving orphans are bracketed D before and
after an additional healthy-peer probe following coordinator death/refusals.
All 74 recorded healthy-peer probes passed, maximum 1.046
seconds; this is reachability evidence, not persistent-storage settlement.

| Boundary | Failed endpoint | Debug blocked | Debug following stop | Release blocked | Release following stop |
|---|---|---|---|---|---|
| Source claiming | Source | Blocked orphan retained | Prompt confirmed exit | Blocked orphan retained | Prompt confirmed exit |
| First source payload read | Source | Blocked orphan retained | Prompt confirmed exit | Blocked orphan retained | Prompt confirmed exit |
| After first destination copy chunk | Destination | Blocked orphan retained | Terminating orphan retained | Blocked orphan retained | Terminating orphan retained |
| Destination verification | Destination | Blocked orphan retained | Prompt confirmed exit | Blocked orphan retained | Terminating orphan retained |
| Before file publication | Destination | Blocked orphan retained | Prompt confirmed exit | Blocked orphan retained | Prompt confirmed exit |
| Durable file-link aliases | Destination | Blocked orphan retained | Terminating orphan retained | Blocked orphan retained | Prompt confirmed exit |
| Durable manifest-link aliases | Destination | Blocked orphan retained | Prompt confirmed exit | Blocked orphan retained | Prompt confirmed exit |

All surviving orphans retain OwnerUnavailable/exit 2 and their original epoch
across three bracketed raw-flock/status samples. Two
workers outlive raw-flock closure while logical exclusion remains intact. Raw
closure is observational here; increment 47's strict regression stays available
separately. Prompt stops are not surviving-orphan or coordinator-SIGKILL coverage.

All 28 cases restore endpoints and confirm old exit before original-state
recovery to Committed. Original database/source inodes and enrollment evidence,
private source, producer reuse, stable roots and cleanup false are preserved.
The eight source-read/copy cases retain their original partial inode and valid
bytes, then use attempt 2. All four source-read cases keep read-completed absent
during outage, with the source hash captured before cache invalidation. Verification
and publication use attempt 1. All twelve publication cases preserve the verified
payload inode without second allocation; all four manifest-link cases preserve
the existing manifest inode/hash and reconcile aliases. Final hashes and manifest
semantics pass.

Six retained normal baselines, twelve state-parent refusals and 184 state-file
refusals across fourteen preserved fixtures pass. OS inherited-lock/isolated
startup/interruption checks pass. Maximum orphan status is 0.985
seconds, competitor refusal 1.063 seconds and two-second stop
2.844 seconds, including Podman overhead. Cleanup errors are empty;
the raw report retains individual observations and preservation snapshots.
An independent post-run Podman inventory confirms no containers, fixture volumes
or fixture networks remain; only the two Rust cache volumes and default network
remain.

Exact fixture command:

```powershell
python scripts/check-nfs-boundaries.py rust/validation/20261018T005552Z-19547ccf --qualification-gate rust/validation/20261018T005553Z-3e07ad26-nfs-qualification --isolated-startup --coordinator-death --death-scope independent-endpoints
```

## Compatibility and provenance

Fresh production `20261018T021600Z-b1b4dbae` passes 204 tests per profile; qualification
`20261018T021600Z-cb955ad5-nfs-qualification` passes 205 per profile. Both complete GNU/glibc-2.22 cargo-zigbuild,
twenty ELF audits, six negative controls and exact debug/release target execution
in pinned SLES 12 SP5 userspace. Formatting, Clippy and locked package/feature
checks pass. The graph stays at 42 external packages, maximum imported GLIBC_2.18
and standard `/lib64/ld-linux-x86-64.so.2`.

The fixture reuses increment 53's passing binaries in the command above. Both
61-file inventories match current Rust bytes, archive digests match their own
reports and every fresh executable hash is verified. All four reused service
binaries are byte-identical to the fresh gates. Captured driver hashes match
executed working-copy bytes; staged blobs are checked after LF normalization.
No Rust build input changed. See [production evidence](RUST-SLES-EVIDENCE.json)
and [qualification evidence](RUST-SLES-QUALIFICATION-EVIDENCE.json). The shared
kernel is `6.18.33.2-microsoft-standard-WSL2`; this does not qualify an old SLES kernel.

The scenario catalog and DOC-01–05 record selected independent endpoint behavior.
SC-089/094 delayed-effect settlement remains pending. The future-only roadmap
keeps untested opposite-direction/phase cases, bootstrap, mount/security, real
NAS/disk durability, in-flight RPCs and systemd/account work. Production NFS and
source deletion remain disabled; all eight release gates stay open.
