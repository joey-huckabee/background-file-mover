# Rust increment 68: first-release NFS mount profile

## Scope

Define a bounded first-release mount contract and validate its read-only
inventory decisions in controlled containers. Keep production NFS and source
deletion disabled. No Rust code, dependency, retry, acknowledgement, shutdown
deadline or transfer behavior changes. New profile enforcement in the service
is explicitly pending; the Python model is qualification infrastructure only.

The [contract](NFS-MOUNT-PROFILE.md), MP-01-12, selects **NMP-41B** as the buffered
hard/TCP NFSv4.1/sec=sys qualification candidate. **NMP-41N** preserves the earlier
noac/synchronous-write diagnostic profile separately. This does not assert that
either matches the user's still-unknown NAS settings or authorizes changing host
mounts. The [step-by-step lab](NFS-MOUNT-PROFILE-LAB.md) documents prerequisites,
privileges, exact commands, source snapshots, interpretation and cleanup.

## Results

`mount-profile-20261019T005139Z-e8c53b13` **passes**, cleanup errors `[]`.
[Raw passing evidence](RUST-NFS-MOUNT-PROFILE-EVIDENCE.json) contains all actual
inventories, declarations, results, source bytes/SHA-256, client/kernel/image,
server packages/exports and UID/GID/hash controls.

| Evidence | Result |
|---|---|
| Live-inventory decisions | 27 cases: N/N, B/B and both mixed combinations, stable pins, buffered baseline, same-share disjoint directories, refusal cases, remount and NFSD-zero observations |
| Synthetic inventory mutations | 10 refused: v3/v4.2, UDP, different security, local locks, cached failure fallback, unknown/duplicate options, multiple connections and lookup override |
| Declaration negative controls | 6 refused: address/export/profile mismatch, undeclared profile, noncanonical path and overlapping roots |
| Total model results | 43 cases: 13 PROFILE_MATCH_ONLY, 30 REFUSED; every match explicitly denies production/deletion authorization |
| Parser controls | 5 malformed/oversized cases refused; kernel escaping, optional fields, component containment and prefix collision checked |
| Ordinary account I/O | Four profile combinations preserve source/destination hash, UID/GID 1000, mode 0600 and 13 bytes on root-squashed child exports |
| Server unavailable | Verified NFSD threads=0; matching local inventory read/evaluation completes in 0.969 seconds, without accessing an NFS path |
| Restoration/cleanup | Original probe hashes verified after NFSD restart/grace; normal reverse-order unmount, then owned containers/export volume/network removed |

Actual live refusal cases cover soft, ro and nocto on each endpoint; missing both
mounts/missing destination; source/destination nested mounts, subtree bind alias,
NFS state and nested state; and a changed effective retry option against the old
pin. These are **model decisions**, not newly implemented mover startup/HTTP
responses. Same-share/mixed matches do not qualify actual mover transfers.

The client is the pinned SLES 12 SP5/glibc 2.22 image, sharing kernel
`6.18.33.2-microsoft-standard-WSL2`. Server packages are nfs-common and
nfs-kernel-server `1:2.6.2-4+deb12u1`, rpcbind `1.2.6-6+b1`. Two child exports use
separate 16 MiB tmpfs devices, sync/root_squash and fsids 68/69. The existing
pseudo-root export remains permissive inside the private fixture. No new packages,
VM bootstrap or host mount modifications were needed.

## Retained finding: mount IDs do not establish continuity

The first run, `mount-profile-20261019T004903Z-4d74cf97`, **failed** an assertion
that unmount/remount would change the entire observed pin. The kernel reused the
mount IDs and all selected records matched. Eighteen earlier model cases had
passed; cleanup completed without error. Preserve its
[raw evidence and original driver/model snapshots](RUST-NFS-MOUNT-PROFILE-INITIAL-EVIDENCE.json)
as a failed assumption, not passing qualification.

The corrected runner permits a matching same-options remount observation and
proves refusal after an actual effective timeo change (10 to 20). The passing run
again observes pin reuse. The contract now states that **matching snapshots do
not prove mount continuity**. Protected descriptor/root/enrollment checks and
safe effect authorization remain required. Matching local inventory while NFSD
is down separately demonstrates that it cannot prove availability or settlement.

## Compatibility and checks

Both required GNU/glibc 2.22 gates **pass** with no cleanup errors:

| Configuration | Run ID | Debug / release tests | Audited ELF |
|---|---|---:|---:|
| Production | `20261019T004550Z-7fabb2df` | 204 / 204 | 20 |
| Retained NFS qualification | `20261019T004602Z-f678ae07-nfs-qualification` | 205 / 205 | 20 |

See [production evidence](RUST-SLES-EVIDENCE.json) and
[qualification evidence](RUST-SLES-QUALIFICATION-EVIDENCE.json). Both use the
pinned Rust 1.99/cargo-zigbuild GNU target, debug/release exact target execution
in SLES 12 SP5/glibc 2.22 userspace, formatting/Clippy, 42 locked dependencies
and six negative ELF controls per configuration. All 40 audited artifact hashes
and both archives' 61 current Rust inputs were independently verified. No
host-only Rust test is substituted. The mount lab executes no Rust; the gates
audit and execute the existing unchanged shipping/qualification artifacts.

The raw model cases were replayed against their captured inventories/declarations;
all 43 expected decisions and exact source snapshots were verified, including the
old-pin comparison. Initial source snapshots and their hashes are preserved.

## User documentation and remaining work

SC-103/104/105 explain changed/missing mounts, same/separate shares and matching
inventories that cannot prove continuity or server availability. DOC-03/04/05 link
the contract/procedure and retain the remaining startup/deployment/recovery work.
The roadmap stays forward-looking: integrate the contract into supervised Rust
startup/effect checks, then qualify real B/B workers and remaining observed RPC
reply-loss/recovery boundaries. Earlier noac worker evidence and buffered OS-only
WRITE controls retain their original scope.

FR-03/05 and all eight release gates remain open. No old-kernel/NetApp/Isilon,
authenticated NAS identity, snapshot-to-use race exclusion, persistent local
state, physical storage/power durability or production enablement is established.
Registration, cross-host takeover and repair remain deferred.

Final checks also pass: Python syntax, all 43 captured model decisions replayed,
1,376 local documentation links, 105 unique scenario rows, trace-matrix parity,
and staged whitespace/LF/final-newline/conflict/file-size checks. Both lab attempts
cleaned up normally; no profile fixture containers, export volumes or networks
remain. No forced/lazy unmount or manual recovery was used.
