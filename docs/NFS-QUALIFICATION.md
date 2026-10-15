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
From [increment 23](RUST-INCREMENT-23.md), compiled capability also requires an
explicit `source_binding` and preprovisioned source marker. The fixture provisions
them through `scripts/nfs_binding.py`; service startup never creates them. A
declared NFS source cannot fall back to an underlying local directory. Strict
observed identity pins do not authenticate a server/export or provide fencing.

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

For root/ownership diagnostics, run the same baseline runner with both gate
directories and `--isolated-startup --ownership` (omit `--runtime` unless also
repeating that separate matrix). It creates one additional pinned client,
records distinct network/mount namespaces and server-side NFS client identities,
compares actual coordinator exclusion between clients, and includes a regular-file
remote-lock positive control. It then removes only the peer's mount and tests
startup at the same pathname/configuration on the underlying local filesystem.
No jobs are submitted while coordinators overlap or the mount is absent. The
current missing-mount probe includes a copied matching NFS marker and requires
both builds to refuse the local stand-in without changing an existing database.

See [increment 22](RUST-INCREMENT-22.md) and
[the root/ownership design](ROOT-OWNERSHIP-DESIGN.md). Diagnostic completion is
separate from protection: inspect `ownership.probe_status`, each startup
exclusion/refusal field and `production_authorized`. PASSED is not production
approval if those probes expose a gap. The two clients intentionally declare the
same coordinator identity, so that probe still measures exclusion of a cloned
identity, not marker mismatch between different IDs. The retained full interruption and
long-outage reports remain separate evidence with different scopes.

For deterministic real-worker interruption, add `--runtime` to the fixture
command above. It requires both passing gate directories and first repeats the
normal baseline. [Increment 18](RUST-INCREMENT-18.md) explains its claim, partial
copy, coordinator-death and manifest-intermediate cases and evidence boundaries.
The qualification-only pause controls are permanent fixture capabilities, have a
60-second pause budget and require a private local rendezvous directory. Production
ignores them. Do not set them for ordinary service execution or deployment.

[Increment 19](RUST-INCREMENT-19.md) adds source-read and destination-verification
interruption. For those selected points only, the worker issues per-file Random
and DontNeed advice before the rendezvous, then enters the payload read loop.
Advice is not proof of cache eviction: a local `read-completed` observation is
created after the loop and before post-read metadata checks. The fixture fails
if that marker appears during the outage or the assigned reader is not observed
in kernel-blocked state `D`, avoiding a cached payload read being
mistaken for a pending read. These observations never authorize durable effects.
Production issues neither advice nor markers. Cache advice adds no normal
payload pass, dependency or production requirement.

See [the scenario catalog](RUST-SCENARIOS.md) for the user-visible situations and
documentation work fed by these qualification results.

[Increment 20](RUST-INCREMENT-20.md) adds explicit `claim_link` and `file_link`
points after the new exclusive link is synchronized and before old-name removal.
These cases hold the local rendezvous while NFS is unavailable, interrupt the
worker, restore connectivity and require both owned aliases before restart.
Recovery must preserve the recorded inode and remove only its old binding.
This is a deterministic process crash at a real NFS link intermediate, not an
in-flight unlink RPC test. The latter remains unqualified.

[Increment 21](RUST-INCREMENT-21.md) adds three-minute outage cases to the same
`--runtime` command for claim application and destination verification in both
profiles. The worker is released immediately into real NFS operations; the pause
budget is not extended. The runner samples health/status and kernel-blocked
assignment identity throughout the outage, makes three sequential same-ID retries,
then restores NFSD and requires live recovery on attempt 1 without restarting
the service. A retry left waiting in the single-slot submission queue can cause
later retries to return retryable 503 `service_busy`; `handoff_pending` is also
valid before custody is complete. No 503 releases source paths.
These checks do not simulate concurrent floods or server reboot.
See the increment results before treating SC-051/052 as qualified.

To rerun just those four runtime cases after an assertion change, append
`--long-outages-only` to `--runtime`. Normal baseline and OS/startup checks still
run; report `runtime_scope` identifies the restricted runtime scope. It is not
a replacement for the full runtime suite after changes to service effects.
Each runtime case also writes a result JSON after its cleanup, so an earlier
failure can be inspected before the entire fixture completes.

If Ubuntu's post-reboot user runtime prevents native rootless Podman startup,
the same gate can use the healthy Podman WSL2 engine from Windows:

```powershell
$env:CONTAINER_CONNECTION = 'podman-machine-default-root'
python scripts/check-rust-sles.py
python scripts/check-rust-sles.py --qualification
```

Use this environment selection for the gate process; no persistent connection
default needs changing. Sources still build under `/work` in the pinned Linux
builder, and every artifact still runs in pinned SLES userspace. Engine-local
toolchain/registry caches are retained. This changes neither the target nor the
compatibility checks. Record the chosen engine in the increment results.

[Increment 17](RUST-INCREMENT-17.md) records the no-clobber rename refusal measured
on the fixture and the owned link/unlink recovery implementation. Worker diagnostics
are observations, never authorization to commit an effect or delete retained data.

Allowing NFS in a test build is not production authorization. The normal baseline
and selected runtime cases provide one-client evidence for their measured
operations. Cross-client fencing, stable export/mount ownership, outages beyond
the selected three-minute cases, concurrent flooding and queue-memory limits,
in-flight link/unlink RPCs, other synchronization boundaries, server reboot and power-loss durability
remain separate qualification before production enablement. Containers
use SLES/glibc userspace on the runner kernel; no actual SLES host testing is
required by this plan.
