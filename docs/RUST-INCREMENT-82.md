# Rust increment 82: manifest WRITE reply-loss recovery

## Finite acceptance

Keep production NFS and source deletion disabled. Preserve Rust code, dependencies,
retry/review behavior and assignment/stop deadlines. Use cargo-zigbuild GNU/glibc
2.22 and both mandatory SLES compatibility gates.

Run sixteen actual-worker cases on buffered NMP-41B same-share/separate-share
layouts and debug/release profiles: four healthy discoveries, four successful-reply
hold/release controls, four live-coordinator drops and four coordinator-death drops.
Repeat discovery and release controls before fault cases on each layout. Retain
all raw RPCs, server bytes, descriptor identity, current syscall and process state.
Require complete manifest WRITE success withheld, requested/returned FILE_SYNC,
uncommitted API status, published payload, absent public manifest, health and
same-ID 202. Use only existing publish and manifest_link_rpc checkpoints.

For live loss, discard saved success and reset the connection. Require successful
same-handle/range/bytes FILE_SYNC replay, original coordinator/assignment, attempt-1
commitment, bounded health/status samples and same-ID replay without review.
For death, confirm coordinator exit, orphan D state and retained local guard;
snapshot DB/WAL only after coordinator exit and verify saved phase-1 immutable
manifest intent against server staging. Kill the old worker, drop the reply and
confirm actual exit before restarting original state. Retain distinct pre/post
restart wire windows. Pause before manifest publication, prove same inode/bytes
and phase-3 status, then commit. A post-restart write is application recovery from
original intent, not automatically native session replay. After normal stop,
confirm phase 4 and exact original manifest intent. Preserve source, database
inode, enrollment and producer-path reuse; prohibit duplicate job 2.

Require thirty exact acquisition/helper/test snapshots, evidence rejection tests,
independent raw-proof audit, all 62 Rust inputs and forty artifact comparisons to
fresh passing SLES gates, final owned-fixture cleanup and both engine inventories.
Maintain SC-116 and DOC-01–05; DOC-06 remains deferred. Local exit/free guard does
not prove remote settlement. FILE_SYNC and volatile exports do not prove power
survival, physical NAS interoperability, old SLES kernel/package patches or other
manifest sizes/cache/load/outage boundaries. Record actual results after the run.

## Initial failed acquisition

Retain the complete initial report and all thirty exact source snapshots in
[RUST-NFS-MANIFEST-LOSS-INITIAL-EVIDENCE.json](RUST-NFS-MANIFEST-LOSS-INITIAL-EVIDENCE.json):
mount-profile-20261020T012953Z-261a2261, 32,865,886 raw bytes, cleanup_errors=[].
Six same-share cases passed before the first death case stopped on a fixture
assertion. The selected manifest_link checkpoint follows link_durable, so the
restarted staging inode already had two names. Bytes, inode and saved phase-1
intent matched; the incorrect private-only/public-absent expectation caused the
failure. This acquisition does not qualify the remaining cases or death recovery.
The corrected finite matrix uses the existing manifest_link_rpc/link_enter pause
before publication LINK. No Rust code, retry/review or deadline change follows.
Reacquire the complete sixteen-case matrix after freezing the corrected sources.

## Second acquisition: observed restart compound

Retain the complete second report and all thirty exact source snapshots in
[RUST-NFS-MANIFEST-LOSS-REACQUISITION-EVIDENCE.json](RUST-NFS-MANIFEST-LOSS-REACQUISITION-EVIDENCE.json):
mount-profile-20261020T014416Z-9ffaf0f3, 34,839,410 raw bytes, cleanup_errors=[].
Six cases pass; the first death case reaches Committed with verified payload/
manifest, original private one-link bytes/inode at the corrected pre-LINK pause,
and phase-1 intent evidence. The checker then rejects an actual post-restart
compound [SEQUENCE, PUTFH, WRITE, GETATTR], because the shared payload selector
requires exactly [SEQUENCE, PUTFH, WRITE]. No final phase-4 state copy is acquired,
so this incomplete acquisition is not counted as a completed recovery case.

The manifest-specific selector explicitly accepts these two observed shapes for
post-restart recovery, preserving every operation and raw byte. It still requires
exact original handle/offset/count/data, full FILE_SYNC result/verifier and a
post-restart receive-ID boundary. Live replay and the original withheld request
remain restricted to the proven three-operation shape. Unit controls reject
appended COMMIT, READ and another WRITE. Operation numbers follow
[RFC 8881 COMPOUND](https://www.rfc-editor.org/rfc/rfc8881.html#section-16.2).
The retained actual second-run RPCs
pass the corrected semantic validator before the full matrix is reacquired.
No production parser, Rust code, retry/review or deadline changes are introduced.

## Actual results

The complete corrected sixteen-case matrix **passes** with cleanup_errors=[]:
`mount-profile-20261020T020019Z-94c531c6`. All 43 inventory/model controls and all
thirty exact acquisition/helper/test snapshots pass the independent audit. Eight
healthy/hold-release controls precede eight new live/death WRITE-loss cases on
their respective layouts. Each recording has one 2 MiB+17-byte file and a small
version-1 manifest.
No new Rust checkpoint or native probe is introduced.
Both incomplete acquisitions above remain separate from this full rerun.

The final raw report is 104,963,420 bytes, retained
losslessly with SHA-256 in [raw evidence](RUST-NFS-MANIFEST-LOSS-EVIDENCE.json).
The [independent audit](RUST-NFS-MANIFEST-LOSS-INPUT-EVIDENCE.json) retains
source archives, all case analyses, rejection controls, exact verifier/shared
wire-auditor sources and final inventories.

| Layout | Profile | Loss case | Relay | Manifest bytes | Pending syscall | Requested/returned stability | Payload attempt |
| --- | --- | --- | --- | --- | --- | --- | --- |
| same-share | debug | live-drop | source | 348 | 91 | 2/2 | 1 |
| same-share | release | live-drop | source | 350 | 91 | 2/2 | 1 |
| same-share | debug | death-drop | source | 349 | 91 | 2/2 | 1 |
| same-share | release | death-drop | source | 351 | 91 | 2/2 | 1 |
| separate-shares | debug | live-drop | source | 353 | 91 | 2/2 | 1 |
| separate-shares | release | live-drop | source | 355 | 91 | 2/2 | 1 |
| separate-shares | debug | death-drop | source | 354 | 91 | 2/2 | 1 |
| separate-shares | release | death-drop | source | 356 | 91 | 2/2 | 1 |

Healthy discovery accounting (decoded manifest-handle scope only):

| Layout | Profile | Decoded COMMIT requests | Undecoded calls retained |
| --- | --- | --- | --- |
| same-share | debug | 0 | 56 |
| same-share | release | 0 | 55 |
| separate-shares | debug | 0 | 61 |
| separate-shares | release | 0 | 61 |

These counts cover decoded requests on the attributed manifest handle in the
captured window. Unknown traffic remains explicit; this does not establish
absence of every possible COMMIT/RPC, every synchronization boundary or all kernels.

Every fault first proves the actual successful server WRITE reply is withheld,
with complete private manifest bytes and a blocked real worker on the target FD.
The public manifest is absent, API manifest phase is 1 and payload phase Published;
health and same-ID 202 work. Requested/returned stability is 2/2 (FILE_SYNC), a
server protocol promise rather than physical power-durability evidence. See
[RFC 8881 WRITE](https://www.rfc-editor.org/rfc/rfc8881.html#section-18.32).
Dropping includes explicit interruption of the corresponding connection.

### Live coordinator

All four cases receive one matching uncached-retry reply followed by one
successful complete-range WRITE. Each first post-drop API sample is already
Committed.

The auditor recomputes exact original handle/offset/count/bytes, requested and
returned FILE_SYNC, full returned counts and unchanged verifier. Session identity
comparison permits only highest_slotid hint updates; session/sequence/slot/cache
and other request fields remain significant. Cached/session replay and a new
semantic write after NFS4ERR_RETRY_UNCACHED_REP are reported separately. All raw
forwarded records remain available, with other handles accounted separately.
The original coordinator/assignment remains; no review, manual resume, replacement
or second payload attempt occurs. Successful status is a discrete observation,
not a continuous API-availability or exact reconnect-latency measurement.

### Coordinator death and original-state recovery

All four cases confirm coordinator exit, the orphan worker's D state and unchanged
local guard with independent flock exit 73. Its inherited FDs include instance.lock
and no SQLite file. Only after confirmed coordinator exit are exact DB/WAL copies
acquired, hashed before/after and queried read-only in disposable host copies.
quick_check, metadata instance identity and phase-1 manifest bytes/hash/inode agree
with the held server object. Kill the worker, drop/reset and confirm actual old
worker exit before restart; retain distinct pre/post-restart wire windows and
forwarded receive-ID boundaries. The single-threaded orphaned workers exit in
Z state: their descriptors close while the fixture's minimal PID 1 leaves zombie
entries unreaped.

The same configuration/local state restarts with a new coordinator/worker. Existing
manifest_link_rpc pauses before publication LINK: API phase 3, public manifest
absent and original one-link staging inode/exact bytes. The recorded allocation
is rewritten using immutable saved intent, not replaced. Release commits normally;
after confirmed normal stop, copied state is phase 4 with identical original
manifest body/hash/instance ID and allocation inode. The already published payload
stays at attempt 1; repeated small manifest writes do not recopy the payload.

Post-restart successful original-handle/range/bytes FILE_SYNC writes are reported
as application recovery from original intent. A post-restart wire window alone
cannot uniquely attribute every kernel request to a process, prove native session
replay or establish remote settlement. Raw session/stateid evidence is retained;
none is relabelled as a cached replay merely because bytes match.

### Shared invariants and compatibility

Every final manifest and published payload validates. Original source private
inode/content, local database inode, enrollment and job ID survive; new producer
bytes at reused paths remain intact. Identical replay returns 202/job 1 and job 2
is absent. Source cleanup stays disabled. No Rust input, dependency, API,
retry/review, assignment or stop-deadline change is made.

| Gate | Fresh run | Exact target tests per profile | Audited artifacts |
| --- | --- | --- | --- |
| production | 20261020T012047Z-f928ee63 | 211 | 20 |
| qualification | 20261020T012058Z-32359582-nfs-qualification | 212 | 20 |

Both gate processes exit successfully after cleanup. Locked cargo-zigbuild uses
GNU/glibc 2.22 and pinned SLES 12 SP5 userspace; all 62 Rust inputs match live and
fresh archives, and all forty artifact bytes match the earlier passing gates
used by the fixture. The graph remains 42 packages; each gate runs six ELF-audit
negative controls. Host Cargo tests are not substituted.

The final audit passes 23 raw-proof/buffer/loss/intent rejection
controls and the selector refusal control, plus seven RPC-decoder, eight I/O-analysis,
four manifest-capability and seven manifest-recovery test methods. The new seven
methods include eighteen resend identity/semantic/shape and eight intent-copy counterexamples.

All owned fixture containers/networks are removed after restoration and normal
unmounts, with no cleanup errors or lazy-unmount waiver. Both final engine
inventories have no containers. Rootful storage contains only the two original
Rust caches and the default network. Original rootless caches and unrelated
September anonymous volumes remain untouched.

## Boundaries and remaining work

Maintain SC-116 and DOC-01–05, with 116 stable SC identifiers and six DOC IDs.
The [complete lab procedure](NFS-MANIFEST-LOSS-LAB.md) and
[testing limitations](TESTING-LIMITATIONS.md) cover setup, failure retention,
checkpoint correction, raw attribution, copied-state inspection and cleanup.
All eight first-release gates remain open. Production NFS/source deletion and
DOC-06, registration, S3 and offline repair remain deferred/disabled.

One modern shared WSL2 kernel, one server and volatile logical exports do not
qualify original SLES kernel/maintenance-package behavior, independent NASes,
NetApp/Isilon interoperability, persistent media/power or reboot/verifier changes.
Earlier source/pre-checkpoint I/O, remaining synchronization/claim/bootstrap
phases, all cache/manifest-size/load/outage durations, actual deployment/account
control and stronger authority/settlement evidence remain open. Local worker exit
and guard availability are not NAS remote-settlement proof. Continue the
future-only roadmap without promoting finite cases to production support.
