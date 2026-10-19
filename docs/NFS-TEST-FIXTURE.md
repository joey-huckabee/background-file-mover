# Disposable NFS fixture

E2 successfully tested kernel NFSv4.1 with the pinned SLES 12 SP5 client. Keep
this setup available for later file-operation and recovery experiments. No
fixture containers, export volumes, or networks remain running; the server
image remains cached. See [E2 results](E2-RUSTIX-RESULTS.md) and
[machine evidence](E2-RUSTIX-EVIDENCE.json).

The reproducible fixture is in
[the E2 runner](../experiments/e2-rustix/run.py),
[Containerfile](../experiments/e2-rustix/Nfs.Containerfile), and
[server entrypoint](../experiments/e2-rustix/nfs-server.sh). Run
`python experiments/e2-rustix/run.py` to repeat the complete qualification,
including fixture creation, mount checks, and cleanup. Windows needs Podman
on PATH. Before running the NFS phases, load `nfs` and `nfsd` in the Podman
WSL2 VM using `wsl -d podman-machine-default -u root -- modprobe nfs` and the
same command with `nfsd`. Unload only modules this run introduced after cleanup.

The rootful connection is `podman-machine-default-root`. The server uses a
private internal network, a native named volume at `/exports`, and a privileged
container; it publishes no ports. The client drops all capabilities except
`SYS_ADMIN` for the mount. Program checks run as UID/GID 1000. SQLite state
stays on local storage. The export is deliberately permissive within this
isolated fixture (`rw,sync,no_subtree_check,no_root_squash,fsid=0`).

The cached server image is `localhost/background-file-mover-e2-nfs`, ID
`90884509240d53671958810ac7ae1971b7cdfffda3d4135ce42cc39bf0bc3e69`.
Its Debian base digest is
`a4672c0cb26fbdde88e38fa2dfb6c681942306680e41e4378b28770b6e79ee91`.
Observed packages were nfs-common/nfs-kernel-server `1:2.6.2-4+deb12u1` and
rpcbind `1.2.6-6+b1`. Rebuilding can resolve newer packages: record the image
ID and installed package inventory again. The SLES client image and loader
are pinned in [images.json](../experiments/e2-rustix/images.json); the client
requires no new packages.

Mount with the client's existing mount implementation:
`mount -i -t nfs4 -o addr=<IP>,vers=4.1,proto=tcp,port=2049,soft,timeo=10,retrans=1 <IP>:/ /tmp/nfs`.
The soft/bounded retry options prevent fixture hangs; production durability
and outage tests require independently selected mount options. Assert NFS
filesystem magic `0x6969` and retain `/proc/mounts` rather than assuming a
directory is an NFS mount.

The server needs the nfsd pseudo-filesystem, rpcbind, exportfs, rpc.mountd,
and `rpc.idmapd -S`. Start nfsd with `-G 10 -L 10 -V 4 -p 2049 2` and wait
11 seconds before declaring readiness; otherwise grace recovery can stall
the first open. Disabling NFSv2 with `-N 2` fails on this kernel. Stop the
server with `rpc.nfsd 0` and `exportfs -au` after unmounting the client;
remove the exact containers, volume, and network created by this run.

This fixture uses WSL2 kernel `6.18.33.2-microsoft-standard-WSL2`, not the
SLES kernel. It exercised collision retention and link/unlink recovery paths,
including injected ENOSYS and EOPNOTSUPP. It does not establish compatibility
with every server/export or qualify reboot, outage, and power-loss durability.

## Hard-mount boundary qualification

Later Rust qualifications and their exact supported scope are maintained in
[NFS-QUALIFICATION.md](NFS-QUALIFICATION.md). The retained `--ownership` mode adds
a second private SLES client and diagnoses startup exclusion/absent-mount behavior;
see [increment 22](RUST-INCREMENT-22.md). It shares the runner kernel and does not
establish physical-host fencing or safe takeover.

[Increment 14](RUST-INCREMENT-14.md) reuses this server with the unchanged audited
Rust service and a hard NFSv4.1 mount. Its dedicated runner is
`scripts/check-nfs-boundaries.py`; it does not rerun E2 or enable NFS. It measures
startup rejection/blocking, inherited lock lifetime, signal observations and
metadata recovery after restoring nfsd. See
[RUST-NFS-EVIDENCE.json](RUST-NFS-EVIDENCE.json) for the cleanup-checked result.
Rust claim/copy/publication effects on NFS and distributed fencing remain
unqualified. Restore the server before attempting unmount or fixture removal.

[Increment 15](RUST-INCREMENT-15.md) adds the runner's `--isolated-startup`
qualification mode for the new bootstrap child. After the full SLES gate passes,
run `python scripts/check-nfs-boundaries.py rust/validation/<passing-gate-run>
--isolated-startup`. This requires startup shutdown and confirmed bootstrap exit
before server restoration on the fixture kernel; it also verifies absence of
readiness and SQLite creation during the outage. Historical increment-14
artifacts use the original mode without this flag. Neither mode enables NFS.
The completed isolated-startup result is recorded in
[RUST-NFS-STARTUP-EVIDENCE.json](RUST-NFS-STARTUP-EVIDENCE.json).

The retained [qualification capability](NFS-QUALIFICATION.md) adds
`--qualification-gate <passing-run>` to drive real REST transfers before outage
checks. Baseline failure stops advancement and is recorded explicitly, including
source-retention and commitment evidence. See [increment 16](RUST-INCREMENT-16.md).

[Increment 60](RUST-INCREMENT-60.md) reuses this cached server for selected
combined hard-NFS/systemd cases. It adds no Rust NFS implementation; the VM
kernel still provides NFS. See [the step-by-step lab](SYSTEMD-LIFECYCLE-LAB.md)
section 12 for server-image preparation, distinct hard-mounted exports, local
state and restoration/unmount-before-removal. Earlier scope statements above
are historical; current supported evidence and limits are in
[NFS qualification](NFS-QUALIFICATION.md). Production NFS/deletion remain off.

[Increment 61](RUST-INCREMENT-61.md) reuses the same cached server/approved manager
for selected incomplete-stop/repeated-start/restoration cases. No package
experiment, NFS implementation, new image or VM boot/module change is required.
See [the lab guide](SYSTEMD-LIFECYCLE-LAB.md) section 13 and actual results/limits;
normal-unmount-first teardown and production NFS/deletion restrictions remain.

[Increment 62](RUST-INCREMENT-62.md) reuses the cached server and pinned SLES
client for destination-only outage before startup/early delivery on independent
controlled endpoints. [The dedicated lab](NFS-DESTINATION-STARTUP-LAB.md) explains
image/module preflight, both gates, exact command, healthy-source checks,
empty/populated preparation, death/stop, original-state recovery and restore/
normal-unmount-first teardown. No package experiment, VM boot/module or systemd
bootstrap change is needed. Production NFS/deletion remain disabled.

[Increment 63](RUST-INCREMENT-63.md) adds twelve selected file/manifest
publication interruption records: four observed blocked client unlinkat syscalls
and eight crashes after namespace effects before sync. Original-state recovery
preserves inode/content and attempt one. Follow [the lab](NFS-PUBLICATION-SYNC-LAB.md)
for infrastructure, exact gates, interruptions and cleanup. Client syscall entry
does not prove RPC delivery/settlement, and pre-sync process crashes do not prove
power-loss durability. In-flight link/sync RPCs and full SH-11/12 remain open;
production NFS and source deletion stay disabled.

[Increment 64](RUST-INCREMENT-64.md) first proves server REMOVE completion
with its successful reply withheld and an actual pending client, then qualifies
four file/manifest worker cases. Loss includes explicit connection closure and
observed NFSv4.1 replay; the initial healthy-stream discard timeout stays failed.
The [lab](NFS-LOST-REPLY-LAB.md) records independent capability, exact SLES artifacts,
recovery and normal-unmount cleanup. No Rust inputs/dependencies changed. Remaining
claim/LINK/sync RPC, server-recovery/durability and full SH gates stay open;
production NFS and source deletion remain disabled.

[Increment 65](RUST-INCREMENT-65.md) qualifies four selected debug/release file/manifest LINK success-reply-loss cases after independent and repeated server-completion/withheld-success/pending-client controls. Recovery preserves original inode/content and attempt one. The loss model explicitly includes connection interruption; it does not qualify source-claim LINK, COMMIT/fsync reply loss, persistent-media/power/server recovery or old kernels. Production NFS and source deletion remain disabled.

[Increment 66](RUST-INCREMENT-66.md) qualifies four selected debug/release source-claim LINK/REMOVE success-reply-loss cases after independent and repeated source-server completion/withheld-success/pending-client controls. Initial/same-ID submissions remain retryable 503 with paths unreleased until original-state custody recovery confirms 202; only then does the producer reuse paths. Original claim inode/content, job ID, database/enrollment and attempt one survive delivery. Loss explicitly includes connection interruption; COMMIT/fsync, remaining claim/mount/security boundaries, server/media/power durability and old kernels remain unqualified. Production NFS and source deletion remain disabled.

[Increment 67](RUST-INCREMENT-67.md) correlates four actual debug/release claim/delivery synchronization traces with raw NFS traffic. Selected noac sync intervals have no observed outgoing RPC; separate buffered OS controls prove stable WRITE reply withholding/recovery, not COMMIT or mover sync-loss support. See [the reproducible sync lab](NFS-SYNC-LAB.md). No Rust/service/dependency policy changes; production NFS and source deletion remain disabled, and FR-03/05 remain open.

## Read-only mount-profile qualification

Use [the mount-profile lab](NFS-MOUNT-PROFILE-LAB.md) and
`scripts/check-nfs-mount-profile.py` for increment 68. This reuses the cached
kernel-NFS server and pinned SLES client, with separate root-squashed child exports,
UID/GID 1000 controls and normal-unmount cleanup. It validates model decisions,
not Rust startup or transfer support. Keep B/B candidate and N/N legacy evidence
separate. A matching proc inventory is neither NAS availability nor mount continuity.

Increment 69 adds [supervised Rust authorization checks](NFS-MOUNT-PROFILE-LAB.md#supervised-rust-authorization-extension)
to the profile lab, using exact passing production/qualification artifacts and
fresh declared root-squashed B/B and N/N fixtures. The shared nfs_binding helper
adds declarations only when provisioning new disposable markers; it never updates
them automatically at service restart. Retained noac boundary checks remain scoped
separately. Production NFS and source deletion remain disabled.

[Increment 71](RUST-INCREMENT-71.md) adds the mount-profile runner's
--buffered-reads mode. Its isolated root observer has SYS_PTRACE and
DAC_READ_SEARCH in addition to the mount-setup SYS_ADMIN capability, matching
the earlier syscall-observer facility. Ordinary UID-1000 processes retain zero
active capabilities and no-new-privileges. Follow the [buffered-read lab](NFS-BUFFERED-READS-LAB.md)
for the independent permission preflight, cache ordering, actual blocked-read
proof, joint same/separate-export outage/death/recovery and cleanup. Production
NFS/deletion remain disabled; no host/NAS privilege or ptrace policy is changed.

[Increment 72](RUST-INCREMENT-72.md) adds `--buffered-publication` on the same
owned infrastructure and observer capabilities. The
[step-by-step lab](NFS-BUFFERED-PUBLICATION-LAB.md) documents sixteen
same/separate-share returned-LINK/pre-sync and blocked file/manifest unlinkat
death/recovery/replay cases, original-state preservation and normal teardown.
Separate exports share one server/outage domain. Production NFS and source
deletion stay off; syscall/process-crash evidence is distinct from lost replies
or physical durability.

[Increment 73](RUST-INCREMENT-73.md) reuses that fixture with
`--buffered-post-unlink`, eight after-staging-removal/before-directory-sync
process-crash cases. The root client needs only mount-setup SYS_ADMIN; no extra
syscall-observer capabilities are added, and ordinary processes remain UID/GID
1000 with zero active capabilities. The [lab](NFS-BUFFERED-POST-UNLINK-LAB.md)
documents exact commands, original one-link allocation recovery, normal cleanup
and the distinction from actual pending sync/RPC or persistent-media qualification.
Production NFS and source deletion remain disabled.

## Buffered source-claim matrix

[Increment 74](RUST-INCREMENT-74.md) reuses the fixture with --buffered-claims:
eight pre-202 custody LINK/producer-name REMOVE interruptions on both buffered
share layouts and profiles. Root observation needs SYS_PTRACE and DAC_READ_SEARCH
alongside mount-setup SYS_ADMIN; ordinary workers retain UID/GID 1000, zero
active capabilities and NoNewPrivs. See [the lab](NFS-BUFFERED-CLAIM-LAB.md) for
mounts, pending-syscall proof, original-state recovery, artifact audit and normal
cleanup. One server means joint outage; production NFS/deletion stay off.

## Buffered enrolled/populated bootstrap matrix

[Increment 75](RUST-INCREMENT-75.md) reuses the fixture with --buffered-bootstrap:
eight buffered enrolled-empty/populated startup death/recovery cases on both
layouts/profiles. Explicit ordinary 60-second attribute maxima and at least
65 seconds of fixture cache aging precede actual bootstrap launch into outage;
no host cache flushing, remounting or service deadline change is used. Isolated
root observation needs SYS_PTRACE and DAC_READ_SEARCH with mount-setup SYS_ADMIN;
ordinary movers remain unprivileged. Follow [the lab](NFS-BUFFERED-BOOTSTRAP-LAB.md)
for pending-worker/readiness, original state/WAL/partial/inode recovery and cleanup.
One server means joint outage; production NFS/deletion remain disabled.
