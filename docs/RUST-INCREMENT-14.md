# Increment 14: Hard-mounted NFS boundary qualification

This increment adds a reproducible container qualification runner,
`scripts/check-nfs-boundaries.py`. It measures the current startup boundary and
kernel lock/interruption behavior before enabling NFS. It introduces no Rust
code, dependencies, database migrations or configuration changes.

## Measured scope

The runner reuses exact debug/release service binaries from a passing mandatory
SLES gate. It compares every archived Rust input and the complete current input
inventory, verifies artifact hashes before and after copying, and checks eager
relocation in the pinned SLES 12 SP5/glibc 2.22 client. The cached E2 server image
is reused; package experiments remain paused.

The disposable private network has no published ports. The client drops all
capabilities except SYS_ADMIN for mounting; checks and filesystem probes run as
UID/GID 1000. SQLite remains local. The actual kernel NFSv4.1 mount is asserted
using filesystem magic and `/proc/mounts`. It uses `hard,timeo=10,retrans=1,noac`:
the retry values do not establish a bounded hard-mount operation deadline.
Disabling attribute caching deliberately makes the metadata outage observable;
these are qualification settings, not prescribed production mount options.

The checks cover:

- Both unchanged service profiles reject a reachable NFS source and create no
  SQLite database. There is no production NFS override.
- An exclusive namespace-directory lock remains held by a child inheriting the
  open description after its simulated coordinator is killed. It becomes
  available after that child exits.
- Stopping the isolated server's nfsd threads leaves metadata operations and the
  actual service's source startup pending at three-second observations.
- SIGTERM during service startup and SIGKILL during an assigned metadata probe
  are observed separately. Signal delivery is never treated as proof of exit.
- Restoring nfsd allows pending metadata to finish and the service to reject NFS.
  Root/namespace device, inode, ownership and permissions remain identical;
  interrupted-worker exit and subsequent lock acquisition are checked.

The runner restores the server before killing/reaping probe processes or
unmounting. It removes only its own containers, volume and network. If restoration,
process exit or unmount cannot be confirmed, it reports failure and retains the
fixture identities for recovery instead of tearing down the server underneath
unresolved client I/O. Kernel modules are prerequisites managed outside the
runner; it does not unload shared modules.

## Result and next implementation

The final boundary run `nfs-20261014T022308Z-9df298c4` passed with no cleanup
errors. The actual startup process remained pending one second after SIGTERM;
the metadata probe's exit was observed one second after SIGKILL, before server
restoration. That successful kill observation on this kernel is not a general
guarantee of cancellation. The final run and renewed mandatory SLES
gate are recorded in [RUST-NFS-EVIDENCE.json](RUST-NFS-EVIDENCE.json) and
[RUST-SLES-EVIDENCE.json](RUST-SLES-EVIDENCE.json).

The renewed mandatory gate `20261014T021610Z-7cc8e5ee` passed all 98 tests per
profile, debug and release, with all 20 executable artifacts audited and run in
pinned SLES userspace. Maximum required GLIBC remains 2.18; the external Linux
dependency graph remains 42 packages. Formatting, Clippy, six negative audit
controls and the existing trace-matrix check passed, with no container cleanup
errors. The service hashes match the earlier passing gate used by the NFS run.
CI changes to the fixture runner also trigger the standard SLES gate; CI does
not execute the privileged NFS fixture itself.

The useful finding is that source singleton initialization still runs on the
coordinator's startup path. A mounted but unavailable NFS root can block there
before request handling, even though reachable NFS is correctly rejected. The
listener's `Listening` message is not proof that the service is ready. Next isolate
this bootstrap and define readiness/shutdown behavior while preserving inherited
custody locks and the dedicated local SQLite owner. Do not enable NFS as part of
that implementation.

This is boundary evidence, not qualification of Rust claiming, copy/verification,
publication or recovery on NFS. The lock/probe processes use OS tools. It does not
establish distributed fencing, server reboot recovery, replacement-export identity,
old SLES kernel/CPU behavior or power-loss durability. NFS and source deletion
remain disabled; full filesystem-session outage/recovery qualification remains
future work.

To reproduce on the saved Windows rootful Podman connection after loading the
fixture's nfs/nfsd modules:

```powershell
python scripts/check-nfs-boundaries.py rust/validation/<passing-gate-run>
```

An alternate rootful connection can be supplied with `--connection`. The server
image must already exist; see [NFS-TEST-FIXTURE.md](NFS-TEST-FIXTURE.md). Logs and
full reports remain under ignored `rust/validation/nfs-<run-id>/`.
