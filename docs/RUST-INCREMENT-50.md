# Rust increment 50: file publication and manifest coordinator death

Recorded 2026-10-17 on `feature/rust-transfer-coordinator`.

## Finite scope and pass conditions

Extend the retained fixture with `--coordinator-death --death-scope
publication-manifest`: twelve cases, debug/release × pre-file publication,
durable file-link, durable manifest-link × blocked/following local stop. Use a
local source and NFS destination to isolate destination effects; retain six
normal baselines including both-NFS layouts. No Rust runtime, dependency,
retry/review or production-gate change is intended.

Before outage, require durable Claim/202 and preserve a producer-reused path.
The job is Claimed, attempt 1. The pre-publication and file-link rows have
PublishIntent, with no completion manifest. The file-link row has exactly two
owned aliases of the verified staging inode. The manifest-link row has Published
and manifest phase 3, with COMMITTED.part and COMMITTED.json naming the same
owned inode, size and SHA-256. Snapshot object identities and hashes while NFS
is healthy; never inspect unavailable NFS from the local controller.

Stop the NFS server, release the local rendezvous and require the actual worker
to remain D before coordinator death. These cases differ from a crash held at
the local two-name pause: the worker is released into real hard-NFS blockage.
The checkpoint does not identify the exact subsequent in-flight RPC.

Kill only the coordinator for blocked cases. Following-stop cases use a
two-second configured wait: distinguish prompt confirmed exit from incomplete
stop with a surviving D child before killing the coordinator. Every surviving
orphan must remain D across three bracketed raw-flock/logical-status samples,
report OwnerUnavailable/exit 2 and refuse service, initialization and transfer
competitors using the same original state. Preserve the epoch until actual exit.
Raw flock closure is observational in this phase matrix; increment 47's stricter
claim/copy/verification regression remains available unchanged.

Restore NFS and confirm old worker exit before inspecting destination effects or
starting recovery. Any present old/final payload names must match the original
verified staging inode, bytes and hash, with link counts matching observed
aliases. File publication alone cannot create a completion manifest. An existing
manifest must retain its exact original inode/content. Normal same-state
recovery must reach Committed on attempt 1, with the same payload inode, one
final name, no second allocation and no remaining manifest staging alias.
Validate the final manifest and SHA-256, private source retention, producer reuse,
source cleanup false, root identities and replacement epoch. No forced adoption,
review reset, re-enrollment, guard deletion or allocation removal is used.

Retain six normal NFS transfers, twelve NFS-state-parent refusals, 184 state-file
refusals and OS inherited-lock/startup/interruption checks, with clean teardown.
Run fresh production and qualification GNU/glibc-2.22 zigbuild/ELF/pinned-SLES
userspace gates and audit exact source/archive/artifact provenance. Production
NFS and source deletion remain disabled.

## Results

The twelve selected coordinator-death cases in
`nfs-20261017T214723Z-07ac9666` passed. See the
[complete publication evidence](RUST-NFS-PUBLICATION-DEATH-EVIDENCE.json).

| Boundary | Debug blocked | Debug following stop | Release blocked | Release following stop |
|---|---|---|---|---|
| Before file publication | D orphan retains ownership | Terminating D orphan retains ownership | D orphan retains ownership | Terminating D orphan retains ownership |
| Durable file-link aliases | D orphan retains ownership | Terminating D orphan retains ownership | D orphan retains ownership | Terminating D orphan retains ownership |
| Durable manifest-link aliases | D orphan retains ownership | Terminating D orphan retains ownership | D orphan retains ownership | Terminating D orphan retains ownership |

Six blocked and six terminating orphans retained logical ownership. Each stayed
D across three bracketed raw-flock/status samples, reported OwnerUnavailable/
exit 2 and refused three same-state service/initialize/transfer competitors:
36 refusals in total, with no ownership loss. All six following-stop cases
returned ShutdownIncomplete/exit 2 at their configured two-second wait with zero
remaining time and a live child. None was classified as prompt exit. This does
not newly qualify a default-60 uninterruptible deadline for every operation.

Every case restored NFS and confirmed old exit before restart, retained its old
epoch until exit and published a new coordinator epoch during normal recovery.
All twelve recovered job 1 to Committed on attempt 1 without second allocation,
review reset, re-enrollment or replacement state. The final payload kept the
original verified staging inode, size and SHA-256, with one final name and no
payload staging alias. File-only publication cases had no completion manifest
before recovery; no orphan file effect started a subsequent manifest operation.
All four manifest cases kept the exact original manifest inode/hash and finished
with one final name and no staging alias through owned publication/reconciliation.
The pre-outage snapshot was still Claimed/Published/manifest phase 3 despite
the visible manifest.

All cases verified final manifest semantics, private source retention, producer-
reused paths, source cleanup false and unchanged root identities. All twelve old
workers were observed as terminal zombies after restoration; this is actual
process exit, not a claim that init reaped them. Local status then reported
NoActiveOwner and the physical guard was free before normal restart.

Six terminating workers, covering all three points in both profiles, remained D
after their raw flock had closed. Their independent epoch retained logical
ownership and all competitors refused. This is additional observed coverage;
this scope does not make raw closure mandatory or replace increment 47's strict
regression. No ownership loss occurred. Maximum measured orphan status was
0.985 seconds, competitor refusal 1.063 seconds and two-second stop 2.906 seconds,
including the fixture's Podman wait overhead.

The post-exit observations matched in both profiles:

| Boundary | Blocked orphan after restoration/exit | Terminating orphan after restoration/exit |
|---|---|---|
| Before file publication | Final file newly published; staging absent | Original staging remains; final absent |
| Durable file-link | Final remains; staging removed | Both exact owned aliases remain |
| Durable manifest-link | Final manifest remains; staging alias removed | Both exact owned manifest aliases remain |

The two blocked pre-publication workers therefore completed their authorized
publication after coordinator death. The four blocked link workers removed their
owned staging aliases after death. Terminating workers retained the original
stage/aliases for normal reconciliation. These observations explain why old
worker exit matters; none establishes settlement of all delayed NAS operations.

The complete fixture passed six normal NFS transfers, twelve NFS-state-parent
refusals and 184 state-file owner/mount/control refusals across fourteen preserved
fixtures (maximum 1.125 seconds). OS inherited-lock/interruption and isolated
startup checks passed; local Starting status took 0.906 seconds, and SIGTERM
confirmed bootstrap exit before server restoration without SQLite/readiness.
Global source/namespace identities remained stable. All captured driver hashes
match their executed working-copy bytes; Git LF-normalized script blobs are
checked separately against those same bytes. Cleanup errors are empty. Independent
Podman inspection found no containers or fixture volumes/networks, only the two
existing toolchain/cache volumes and default network.

Exact fixture command:

```powershell
python scripts/check-nfs-boundaries.py rust/validation/20261017T205538Z-a820f9e4 --qualification-gate rust/validation/20261017T205538Z-83e00d79-nfs-qualification --isolated-startup --coordinator-death --death-scope publication-manifest
```

Future runs can use fresh passing gate directories; retain full source/archive
and exact executable hash checks. The existing three scope selectors and the
strict increment 47 raw-lock-closure regression remain available unchanged.


## Compatibility and exact artifacts

Fresh production `20261017T214602Z-869cf81f` passed 204 tests per profile;
qualification rerun `20261017T215827Z-3df72cb2-nfs-qualification` passed 205 per
profile. Each passed twenty ELF audits and six negative controls using GNU/
glibc-2.22 cargo-zigbuild and exact target execution in pinned SLES 12 SP5
userspace. The graph remains 42 external packages, maximum imported GLIBC_2.18
and standard `/lib64/ld-linux-x86-64.so.2`. No Rust source, Cargo dependency/
feature, schema, private protocol or runtime policy changed.

Both fresh and reused gates have complete 61-file inventories matching current
Rust bytes, with verified source-archive digests. All twenty artifacts in each
fresh gate match their recorded hashes. See [production evidence](RUST-SLES-EVIDENCE.json)
and [qualification evidence](RUST-SLES-QUALIFICATION-EVIDENCE.json). Both gates
completed cleanup. The NFS fixture used the passing increment 49 gate directories
shown in its command while the fresh gates ran. All four production/qualification
× debug/release service binaries are byte-for-byte identical to the corresponding
fresh passing binaries; preserve actual fixture gate IDs in the raw report.
The failed initial qualification service and API test executables are also
byte-identical to the passing rerun. The shared runner kernel was
`6.18.33.2-microsoft-standard-WSL2`; containers do not qualify an old SLES kernel.

## Initial compatibility qualification finding

Initial qualification gate `20261017T214615Z-2f632f73-nfs-qualification` failed
in the existing debug API test
`configured_stop_deadline_survives_repeated_requests_signals_and_config_edits`.
Its API harness passed 82 tests and failed one. Both stop commands had already
returned ShutdownIncomplete with the configured two-second wait and zero
remaining time; the immediate subsequent status assertion at api.rs:3903 saw
Draining instead of ShutdownIncomplete. Preserve the [failed gate report](RUST-SLES-PUBLICATION-INITIAL-QUALIFICATION-EVIDENCE.json)
and [full target log](RUST-SLES-PUBLICATION-INITIAL-QUALIFICATION-FAILURE.txt).

Inspection of control.rs shows that the stop client conservatively subtracts the
first exchange from the daemon's remaining duration and uses truncated
milliseconds. Its own bounded wait can therefore finish slightly before the
daemon's monotonic deadline, making an immediate status assertion timing
sensitive. The failed run did not capture exact exchange timestamps. This is an
existing assertion race consistent with the observed phases, not proof that the
daemon reset or extended its first deadline. The full qualification rerun passed
both profiles with unchanged Rust inputs; no test was skipped or weakened. Stabilizing this
assertion while preserving the original deadline is retained in the future-only
roadmap. A passing rerun does not constitute fixing that race.

## Remaining scope

Both-NFS crash layouts, exact in-flight namespace/synchronization RPCs, longer or
indefinite outages, actual systemd/account/mount policy, NAS reboot/reclaim/power
loss and delayed remote-operation settlement remain unqualified. The SLES
containers share the modern runner kernel/CPU. Preserve all earlier failed
reports and the strict increment 47 regression. FR-03/05 remain open; no NAS-admin
fencer, takeover, registration or offline repair is introduced. Production NFS
and source deletion remain disabled. Maintain SC-034/036/039/040/050/092/093/095
and DOC-02/03/04/05 with stable identifiers.
