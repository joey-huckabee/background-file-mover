# Retained NFS qualification capability

The user explicitly requested keeping this capability. Preserve its Cargo
feature, build identification, compatibility gates and fixture runner for future
qualification/regression work. Do not remove it when production NFS support is
eventually approved; changing that decision requires a new user direction.

## Build distinction

`file-mover/nfs-qualification` forwards to `mover-fs/nfs-qualification`. Both
features are disabled by default. The qualification build adds NFS filesystem
magic `0x6969` to the source/destination root allowlist. Ownership, permissions,
singleton locks, durable receipts, copying, verification, publication and source
retention use the same implementation as the production build. There is no
alternate transfer engine and no runtime option or environment variable that
enables NFS in a production binary.

Both builds identify themselves with `--check-platform`:

```text
file-mover 0.1.0 local-claim prototype build=production
file-mover 0.1.0 local-claim prototype build=nfs-qualification
```

Qualification service/transfer startup also prints a conspicuous warning.
Internal workers do not print that warning into their private IPC channels.
The label is derived from the filesystem crate's actual compiled capability,
including builds that enabled the leaf feature directly.

Qualification artifacts are for the controlled fixture and must remain outside
deployment packaging. They are retained under a separate validation run and have
`-nfs-qualification` filenames. This repository currently has no Rust deployment
packaging; future packaging must select production artifacts explicitly and
verify their build label. The feature adds no dependencies or package versions.
Production NFS support and source deletion remain disabled.

## Equivalent compatibility gates

Run both from the Windows checkout using native WSL Podman:

```powershell
wsl -d Ubuntu -- bash /mnt/c/Users/Joey/Documents/GIT-GitHub/joey-huckabee/background-file-mover/scripts/test-rust-wsl.sh
wsl -d Ubuntu -- bash /mnt/c/Users/Joey/Documents/GIT-GitHub/joey-huckabee/background-file-mover/scripts/test-rust-wsl.sh --qualification
```

On a Linux runner, the entry points are `python3 scripts/check-rust-sles.py` and
the same command with `--qualification`. Each gate runs formatting/Clippy,
cargo-zigbuild debug/release builds for x86_64 GNU/glibc 2.22, audits every ELF
artifact and executes exact artifacts in pinned SLES 12 SP5 userspace. Reports
record build mode and actual workspace features. Build labels are checked in
both smoke execution and an executable/API test. CI has a matrix for both modes.
No host-only test pass replaces either gate.

## Controlled normal-operation baseline

After both gates pass, reuse their exact artifacts:

```powershell
python scripts/check-nfs-boundaries.py rust/validation/<production-run> --qualification-gate rust/validation/<qualification-run> --isolated-startup
```

The runner verifies both source snapshots, artifact hashes and labels. It first
proves both production profiles reject a reachable NFS source without creating
SQLite. `scripts/nfs_baseline.py` then drives the actual qualification service
through REST in pinned SLES userspace, using the saved private hard-mounted
NFSv4.1 fixture. SQLite stays local. It tests NFS as source, as destination and
as both, in debug and release, asserting actual filesystem types.

Each case submits three files: a top-level text file, a nested file larger than
the copy buffer, and an empty file. Successful cases check stable-ID replay,
immediate reuse of original paths after 202, retained private source contents,
destination bytes, independently computed hashes and the exact V1 completion
manifest. Test hashing is outside the service; normal service I/O remains 3N.

Blocked cases retain their response, status, service log and available integrity
evidence. The runner reports a failed baseline rather than claiming unsupported
operations work. It does not silently introduce overwrite or deletion fallbacks.
All cases are attempted, then normal-operation failure prevents advancing to the
outage phase. The owning runner restores NFS and confirms process completion and
unmount before removing only its own resources. See [NFS-TEST-FIXTURE.md](NFS-TEST-FIXTURE.md).

## Qualification boundary

Allowing NFS in a test build is not production authorization. A normal-operation
baseline does not establish cross-client fencing, stable export/mount ownership,
coordinator death recovery, outage safety, server reboot or power-loss durability.
Those remain separate short increments before production enablement. Containers
use SLES/glibc userspace on the runner kernel; no actual SLES host testing is
required by this plan.
