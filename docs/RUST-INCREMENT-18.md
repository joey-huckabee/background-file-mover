# Increment 18: Rust worker interruption on the controlled NFS fixture

This increment extends the retained qualification capability with deterministic
pause points and real REST/worker interruption cases. Production NFS and source
cleanup remain disabled. No dependency, schema, REST field or deployed executable
is added. Normal transfers still hash while copying and reread staging (3N).

The `nfs-qualification` filesystem feature enables fixture controls selected by
`FILE_MOVER_QUALIFICATION_PAUSE` and a protected local
`FILE_MOVER_QUALIFICATION_RENDEZVOUS` directory. The worker creates an exclusive
`ready` marker containing its PID and point, then waits up to 60 seconds for an
owned regular `go` marker. The directory must be private and on a local allowed
filesystem; symlink release markers are refused. These markers are test controls,
not durable effect receipts or custody authorization. Production compiles the
pause function to a no-op and ignores both environment variables.

`scripts/nfs_runtime.py` runs after the existing six normal-transfer cases, using
the same audited production and qualification binaries in pinned SLES userspace.
It checks actual mounted filesystem types and keeps SQLite and rendezvous local.
Each profile exercises production controls being ignored plus four runtime cases:

- **Claim application:** pause after the durable claim intent, stop NFS, release
  the worker into the outage, request graceful shutdown, restore, confirm exit,
  restart and replay the same producer ID. No interrupted request may release
  producer paths or return 202 before the claim completes.
- **Partial copy:** pause after the first 1 MiB destination write, stop NFS,
  release into the next write, terminate the worker/coordinator, restore and
  confirm exit. Recovery uses attempt 2 and retains the uncertain attempt 1 file.
- **Publication and coordinator death:** pause with PublishIntent persisted,
  stop NFS and release the child into the blocked operation. Kill the coordinator
  while its actual Rust child retains inherited source custody. Competing startup
  must fail before SQLite/readiness. Restore and allow the old child to finish;
  only after its exit is confirmed may the new coordinator reconcile attempt 1.
- **Manifest alias intermediate:** pause after synchronizing the new completion
  link while both recorded names have exactly two links. Stop NFS, interrupt the
  worker, restore and confirm exit. Restart reconciles the same manifest intent,
  removes only its staging alias and records commitment without copying again.

During each outage, health and persisted status must remain available and exactly
one assigned child must remain. The runner records signal/exit observations; it
does not treat signal delivery as proof of exit. An orphan zombie proves exit and
closed descriptors but is explicitly distinguished from a PID reaped by init.
Recovery checks stable observed root identities, retained source hashes, exact
destination hashes/manifest, original-path reuse and disabled source cleanup.

The fixture always restores NFS before cleanup, confirms worker completion and
then unmounts before removing only its own resources. Unsafe/uncertain cleanup
fails the run and preserves the owning runner's resources where necessary.

This is one client on the modern WSL2 kernel, not the SLES kernel, old hardware,
cross-client NFS fencing, stable export authorization or server reboot/power-loss
durability. Longer outages, source-read/verification interruption and export
changes remain separate qualification increments. Package experiments stay paused.

Production gate `20261014T131403Z-aba44f6e` passed 114 tests per profile;
qualification gate `20261014T131404Z-59ecf22c-nfs-qualification` passed 115.
Debug/release artifacts in both modes passed exact pinned SLES execution and
ELF/loader/library audits. Maximum required GLIBC remained 2.18, below the 2.22
limit, with 42 locked external Linux packages. Formatting, Clippy and six negative
audit controls per mode passed; both gates finished without cleanup errors. See
[production evidence](RUST-SLES-EVIDENCE.json) and
[qualification evidence](RUST-SLES-QUALIFICATION-EVIDENCE.json).

Final fixture run `nfs-20261014T135218Z-8b830af8` passed all eight selected runtime
cases and both production-control cases, plus the six normal NFS transfers and
existing OS/startup boundary checks. Cleanup reported no errors. See
[runtime evidence](RUST-NFS-RUNTIME-EVIDENCE.json). Every runtime case records the
audited binary hash, phase snapshots, worker identity/exit observations and logs.

Both copy-outage workers remained unconfirmed as exited after SIGKILL until NFS
restoration. Their old staging files grew from the 1 MiB pause boundary to 2 MiB;
recovery preserved them and completed using attempt 2. Signal delivery therefore
did not establish cancellation or rollback. Health/status remained responsive;
recorded host command round trips were approximately 1.6–1.8 seconds, including
Podman/file-copy overhead, not a service latency SLA.

In both coordinator-death cases, the actual Rust child retained source custody
and refused competing startup before SQLite/readiness. After restoration and
continuation, publication existed with the expected hash before restart; the
orphan exited as a zombie (closed descriptors, not init-reaped). The new
coordinator reconciled attempt 1. Manifest-interruption cases retained their exact
bytes through two-name reconciliation and removed only the owned staging alias.
All cases retained private source bytes and kept reused original paths intact.

An initial driver run `nfs-20261014T134428Z-8668ff8f` failed because the minimal
SLES image has no `awk`. Its resources were preserved when driver cleanup became
uncertain, then restored, stopped and unmounted before removing only its recorded
resources; `recovery.json` remains in the ignored validation directory. The final
driver parses `/proc` data on the host and needs no added SLES package. This was
a fixture defect, not passing service qualification. The existing trace-matrix
check and Python syntax checks also passed.
