# Rust increment 70: buffered same-share transfer and recovery

## Scope

Qualify real service workers with disjoint private source/destination roots on
one buffered NMP-41B mount/export, with original SQLite and ownership state on
local disk. Keep production NFS and source deletion disabled. No Rust behavior,
dependency, executable, retry/review classification or shutdown deadline changes.

The retained mount-profile runner gains --same-share and a dedicated helper.
It reuses checksum/source-verified gate artifacts, fresh binding provisioning,
the maintained runtime Case helpers and qualification-only durable-link pauses.
The runtime helper accepts an explicit fixture NFS root; its default path and
existing matrices remain unchanged. The same-share export has 64 MiB tmpfs
capacity to hold both independent copies for all six finite cases.

## Cases and assertions

Debug/release each exercise an uninterrupted baseline, coordinator/worker death
after durable source claim LINK, and death after durable destination file LINK.
These returned operations leave two owned names before old-name removal; they
are not pending/lost-RPC-reply experiments. Inventory, selected mount record,
device and explicit declarations prove the actual same-share layout. Separate
root IDs/role markers preserve private custody boundaries.

Claim interruption keeps paths unreleased, producer names untouched and manifest
absent. Publication interruption requires confirmed submission 202 before the
producer reuses its original path; staging/final aliases match and the manifest
remains absent. Each paused actual worker is stopped, the coordinator alone is
killed, and worker survival is observed before that worker is killed. Restart
waits for confirmed worker exit; no guard-release shortcut is used.

Original configuration/database/enrollment recovery must return the same job/202
and eventually Committed. Verify original claimed inode/hash, retained source,
destination hash/size and immutable nested-path manifest. The final destination
inode must differ from the retained source inode even though their device is
the same; file-link recovery preserves its original publication inode. A second
bounded stop/start and same-ID replay must preserve database inode, configuration
and enrollment hashes, manifest hash and newer producer bytes. Source cleanup is
false throughout.

## Results

Final same-share run `mount-profile-20261019T030103Z-1445a1a6` **passes**, with
six passing live cases, 43 passing independent model/inventory decisions and
cleanup_errors=[]. [Raw final evidence](RUST-NFS-SAME-SHARE-EVIDENCE.json) retains
actual mount inventory, explicit bindings/configurations, responses, stopped and
exited worker observations, one-link source/publication identities, manifests,
original-state recovery, replay and exact SHA-256/Base64 fixture sources. The four
paused workers run as UID/GID 1000 with no effective/permitted/inheritable
capabilities and no-new-privileges. Baselines use the same ordinary service account.

| Profile | Uninterrupted | Durable claim LINK crash/recovery | Durable file LINK crash/recovery |
|---|---|---|---|
| Debug | Passed | Passed | Passed |
| Release | Passed | Passed | Passed |

The preliminary run `mount-profile-20261019T024946Z-04cceeed` also passes all six
cases and 43 controls with clean cleanup. Preserve its
[separate raw record](RUST-NFS-SAME-SHARE-PRELIMINARY-EVIDENCE.json). The final run
makes the local parent UID-1000/mode-0700 and adds one-link/private-source and
unchanged source/publication inode assertions across committed replay. These
are six distinct cases repeated with stronger fixture checks, not twelve
independent failure scenarios.

Both fresh required compatibility gates pass with no cleanup errors:

| Configuration | Run ID | Debug / release tests | Audited ELF artifacts |
|---|---|---:|---:|
| Production | `20261019T024518Z-217cc08d` | 211 / 211 | 20 |
| NFS qualification | `20261019T024519Z-8839b997-nfs-qualification` | 212 / 212 | 20 |

[Production](RUST-SLES-EVIDENCE.json) and
[qualification](RUST-SLES-QUALIFICATION-EVIDENCE.json) evidence include GNU/glibc
2.22 cargo-zigbuild output, exact pinned SLES execution, formatting/Clippy,
42 locked dependencies and six negative ELF controls per configuration. There
is still one shipping executable; audited counts include test binaries and both
build profiles. No Rust source or Cargo.lock change is introduced.

To run the live fixture alongside fresh compatibility checks, it uses passing,
source-identical audited artifacts: production `20261019T024518Z-217cc08d` and
qualification `20261019T013345Z-9af2676b-nfs-qualification`. Independently verify
**all 40 artifact hashes** match the corresponding fresh gates, including the
exact debug/release service binaries exercised live. Both fresh source archives
match all 62 current Rust inputs. The
[input/equivalence evidence](RUST-NFS-SAME-SHARE-INPUT-EVIDENCE.json) preserves
those checksum-verified archives, input hashes and exact verifier source. All
six final driver snapshots also match the current working inputs byte for byte.
The preliminary run uses both earlier passing increment-69 gates; it is recorded
separately and does not replace fresh compatibility checks.

Final verification also covers Python syntax, trace-matrix parity, unique 105
scenario/six DOC rows, local documentation links, JSON, whitespace and file-size
checks. Both Podman engines have no remaining test containers; the owned fixture
network/volume are removed after normal unmount. Rootful storage retains only
the preexisting toolchain/registry caches and default network. Preserve existing
images/toolchain caches. Final live cleanup_errors is empty.

## Documentation and limits

[The step-by-step lab](NFS-SAME-SHARE-LAB.md) describes commands, fixture privileges,
mount/export layout, exact-artifact checks, pause/effect boundaries, original-state
recovery and normal cleanup. SC-104 and related handoff/replay/retention scenarios
are maintained with actual scope. DOC-03/04/05 keep full production walkthroughs
pending. No prior noac or inventory-only result becomes buffered service evidence.

These are one-client, one-file, single-host process-crash cases on volatile tmpfs
with a continuously running server/kernel. They do not prove delayed remote
settlement, withheld replies, server restart/grace, other-client caches, NAS
firmware, persistent-media/power durability, arbitrary mount changes or complete
bootstrap/copy/verify/manifest interruption coverage. Pinned SLES 12 SP5 userspace
uses the modern shared Podman/WSL2 kernel; no old SLES kernel, real installation
or production-size/endurance qualification is claimed. FR-03/05 and all eight
release gates stay open. Production NFS and source deletion stay disabled.
