# Buffered NFS copy and verification interruption lab

This controlled qualification extends the [mount-profile infrastructure](NFS-MOUNT-PROFILE-LAB.md)
and [same-share procedure](NFS-SAME-SHARE-LAB.md). Production NFS and source
deletion remain disabled. No host/NAS mounts, credentials or production data are
used. The rootful Podman fixture has an internal network, a privileged kernel-NFS
server and a pinned SLES 12 SP5 client with SYS_ADMIN for mount setup and
SYS_PTRACE plus DAC_READ_SEARCH for the root observer's local /proc syscall
inspection (ptrace access and owner-only file lookup/read), with
no-new-privileges. Both observer capabilities are enabled only for this matrix, inside the
client's PID namespace; no host ptrace policy or process is changed. Service,
workers, controllers and HTTP run as UID/GID 1000 with no effective/permitted/
inheritable capabilities. Actual blocked-worker capability/identity records are required.

## Commands and infrastructure

1. From the repository root, run both mandatory GNU/glibc 2.22 gates. Retain the
   result directories printed by each command:

   ```powershell
   python scripts/check-rust-sles.py
   python scripts/check-rust-sles.py --qualification
   ```

2. Run the buffered-read extension with passing, source-identical artifacts:

   ```powershell
   python scripts/check-nfs-mount-profile.py --production-gate rust/validation/<production-run> --qualification-gate rust/validation/<qualification-run> --buffered-reads
   ```

   --buffered-reads and --same-share are mutually exclusive. Both gate reports
   must pass without cleanup errors. Their archives must match current Rust
   inputs and the recorded platform configuration; each executable must match
   its own artifact hash. The runner checks current source bytes before
   loading debug/release qualification binaries, verifies received hashes, and
   retains exact SHA-256/Base64 driver sources in the report. A previously passing
   source-identical gate may supply live binaries while fresh gates run; record
   that distinction and verify equality of the actual artifacts afterwards.

3. The outer runner repeats its 43 independent model/inventory decisions, parser
   and VFS-flag controls. Those are separate from payload-read evidence. Two
   root-squashed, synchronous child exports have 64 MiB tmpfs capacity each,
   distinct fsids 68/69, NFSv4.1/TCP/sec=sys and buffered NMP-41B settings. Noac
   NMP-41N history is not relabeled. State/configuration/ownership/rendezvous files
   remain local beneath a UID-1000 mode-0700 parent.

4. Mount only /tmp/profile-source for same-share cases. Source/destination are
   disjoint private roots with separate role markers on that actual mount/export.
   Then normally unmount it after workers exit. For separate-share cases, mount
   source and destination exports at /tmp/profile-source and
   /tmp/profile-destination. Record selected mount records and devices: source
   and destination match only for same-share, and local state differs in both.
   These exports share one server/network endpoint and failure domain.

## Eight actual worker cases

For each layout, run source_copy and verify_read in debug and release. Provision
fresh protected markers once, explicitly initialize source enrollment, and keep
the original configuration/database/enrollment through all restarts.

1. Create the nested 2 MiB plus 17 byte recording. Capture its inode/size/hash
   **before** the service invalidates read cache. Start the qualification service
   with the selected local rendezvous, submit the JSON contract, require job 1/202
   with source paths released, and only then write the next recording at the
   producer path. The recorder has no new polling or resume responsibility.
2. Identify exactly one actual delivery worker at its pause. source_copy is after
   the first MiB copied and before the next source read; staging is 1 MiB, phase
   Intent. verify_read is before rereading fully copied staging, phase Copied.
   The existing qualification hook applies per-file Random/DontNeed advice before
   the rendezvous. Inspect metadata only; hashing that target now would warm its
   cache and invalidate the experiment. Require no completion manifest.
3. Stop only the owned server's NFSD threads with rpc.nfsd 0 and verify the
   server's /proc/fs/nfsd/threads is zero. Release the local pause; after three
   seconds require the worker to be D with no read-completed marker and no
   replacement child. Read local /proc/<pid>/syscall: require x86_64 read(2), a
   1 MiB request and the descriptor resolving to claimed source data for
   source_copy or the destination staging file for verify_read. Metadata blockage
   or cache-advice issuance alone fails the case. These observations identify the
   client syscall/file, not a specific NFS RPC or withheld success reply.
4. Capture UID/capabilities/no-new-privileges. Require bounded health 200, unchanged
   job state/files and local Running controller status while the worker blocks.
   Kill only the coordinator PID. Observe the old worker still D across local
   guard/controller samples; OwnerUnavailable/exit 2 must retain logical exclusion
   even if the kernel has already closed the raw flock descriptor.
5. Only after those exclusion observations, try a service start on an alternate
   listener, explicit source initialization, and direct transfer with the same
   state. All must refuse promptly with the surviving-worker ownership diagnostic;
   the occupied original listener cannot stand in for a guard test. Confirm the
   old worker remains D, its epoch is unchanged and its read has not completed.
   No replacement or effect redispatch is authorized by a raw free flock.
6. Restore the owned server with rpc.nfsd -G 10 -L 10 -V 4 -p 2049 2, wait eleven
   seconds and verify two threads. Confirm actual old-worker exit before starting
   anything new; an orphan zombie proves exited/closed files, not PID-1 reaping.
   Require NoActiveOwner and the original database inode/configuration/enrollment.
   Observe the old staging allocation and validate its original inode and prefix
   bytes. A source-copy partial may include a final authorized append before exit;
   its measured size must remain between the original MiB and full file size.
   Verification staging stays the full expected file. Require no manifest.
7. Restart with original state and retry the identical request: job 1/202 and
   eventual Committed. Interrupted copying preserves the old partial and uses
   attempt 2; verification keeps attempt 1 and the original publication allocation.
   Verify source custody/original inode/hash, full destination hash/size, nested
   manifest and source_cleanup_enabled=false. The destination is an independent
   inode from retained source even on the same share. No retry/review override,
   policy reset, enrollment refresh or shutdown-deadline change is introduced.
8. Stop via the bounded controller, wait for actual exit, restart and replay the
   same request again. Require the same committed job, manifest hash/publication
   inode, original state/enrollment, retained source and untouched newer producer
   bytes. Stop cleanly; retain service logs and actual per-case observations.

## Cleanup and evidence interpretation

The helper restores NFSD before terminating/waiting for known processes, including
on failure. Normally unmount after all known users exit, stop/unexport the owned
server, remove only the run's containers/volume/network, and retain reports/logs.
A cleanup error makes the run FAILED and preserves named recovery resources.
Do not force/lazy-unmount to obtain a passing cleanup result. If an unexpected
contender survives, preserve the fixture for scoped process/storage recovery.

Require overall PASSED, rust_executed=true, authorization.passed=true, eight
passing cases, exact profile/layout/point coverage and cleanup_errors=[]. Keep
failed capability/read assertions as failed records; do not substitute a later
metadata stall or another profile. See [increment 71](RUST-INCREMENT-71.md) for
actual run IDs, fresh compatibility results and retained evidence.

This is a finite joint-outage and process-death matrix with one client/server on
a shared modern Podman/WSL2 kernel and volatile tmpfs. It does not test independent
NAS failures, other-client cache visibility, read/write packet reply withholding, NAS/server reboot or failover, explicit grace/reclaim,
delayed mutating RPC settlement, persistent media/power loss, old SLES kernels,
all I/O sizes/cache states, long outages, concurrent load or every worker phase.
The pinned SLES userspace/glibc 2.22 checks are required but do not remove these
limits. FR-03/05 and all eight release gates remain open. Keep production NFS and
source deletion disabled; see [testing limitations](TESTING-LIMITATIONS.md).

## Observer permission preflight and retained failures

The first attempt lacks the observer capabilities and the next attempt has
SYS_PTRACE without DAC_READ_SEARCH. Both fail opening the UID-1000 owner-only
/proc syscall file; neither establishes passing read-descriptor qualification.
Both restore storage and clean up. Increment 71 retains their exact failed
reports/sources separately. SYS_PTRACE permits inspecting the other process;
DAC_READ_SEARCH permits root's read/traversal of its owner-only proc file when
DAC override is deliberately absent. These capabilities belong only to the
isolated observer. No host ptrace_scope change is needed.

Before repeating the full matrix, use a no-network pinned-SLES container with
the exact three-capability client profile (SYS_ADMIN plus the two observer
capabilities). Start an ordinary UID/GID-1000 sleep process, read its syscall
file as the observer, and record both status/capability files and glibc version.
Require zero active ordinary-process capabilities and no-new-privileges. Remove
that container. This is an OS permission check, not Rust or NFS read proof.
[The preflight record](RUST-NFS-BUFFERED-READS-OBSERVER-EVIDENCE.json) includes the
exact executable Python driver as SHA-256/Base64; restore those bytes under
rust/validation and run with Python from the repository to reproduce it.
The live matrix must still prove each blocked read/descriptor separately.

To restore and run that checksum-verified preflight driver:

```powershell
@'
from pathlib import Path
import base64, hashlib, json
r = json.loads(Path('docs/RUST-NFS-BUFFERED-READS-OBSERVER-EVIDENCE.json').read_text(encoding='utf-8'))
data = base64.b64decode(r['source']['base64'])
assert hashlib.sha256(data).hexdigest() == r['source']['sha256']
Path('rust/validation').mkdir(parents=True, exist_ok=True)
Path('rust/validation/probe-observer-71.py').write_bytes(data)
'@ | python -
python rust/validation/probe-observer-71.py
```

A new preflight replaces its evidence file with that run's actual measurements.
It creates/removes only its uniquely named no-network container; the three
capabilities are never granted to an ordinary service process.

The final increment-71 run observes the raw local flock still contended in all
sixteen orphan samples. It proves exclusion with that guard held; it does not add
buffered qualification of the physically closed-guard branch. Keep the earlier
[lifetime-ownership regression](RUST-INCREMENT-47.md) separate and read actual
raw-lock/controller observations before making broader ownership claims.
