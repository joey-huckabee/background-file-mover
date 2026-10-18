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
