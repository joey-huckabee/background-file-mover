# Rust increment 80: live-coordinator payload reply loss

## Finite acceptance

Qualify exactly eight mover cases: COMMIT and UNSTABLE WRITE reply drop, each
on buffered NMP-41B same-share/separate-share layouts and debug/release builds.
Each operation/layout first requires native discovery, successful-reply release
and successful-reply drop controls (twelve native probes altogether). Withhold
matched server success before forwarding, prove the actual target fchmod/FD/D
state and complete server-local object, then discard replies and interrupt their
connection. Capture both active relays and retain unknown traffic.

The same coordinator must stay alive; check responsiveness at the held boundary
and sample after dropping replies;
sample health, status, same-ID 202 replay, coordinator PID, worker children and
original-worker state. This finite short-loss case must commit attempt 1 on the
original assignment without a replacement worker, review, manual repair or
restart. Require actual COMMIT replay or every original WRITE range/hash replay
with appropriate stability and later matching successful COMMIT when necessary.
Preserve original source/state/enrollment, newer producer bytes, verified final
manifest and job 1 identity. Keep production NFS/source deletion off, and all
Rust behavior, retry/review and assignment/shutdown deadlines unchanged.

Require fresh production and qualification SLES/glibc 2.22 gates, exact source
and forty-artifact comparison, independent raw-evidence audit, meaningful
negative controls, complete failed-run retention and clean final inventories.
Maintain SC-114 and DOC-01–05; DOC-06 remains deferred. This does not qualify
longer losses, replacement scheduling, server reboot/verifier changes, all NFS
phases or physical durability. The results below record the actual qualification.

## Actual results and provenance

The final two matrices **pass**: twelve native probes and eight service cases.
Both matrices repeat all 43 mount/inventory controls and capture 26 exact
acquisition/helper/test sources. They overlap only through distinct owned
fixture resources; both share the modern VM/kernel/CPU. The final independent
audits require all captured source bytes to match the final checkout.

- COMMIT: `mount-profile-20261020T001044Z-b3e25a22`, exact raw report 10,238,487 bytes.
- UNSTABLE: `mount-profile-20261020T001129Z-f98e856d`, exact raw report 401,112,414 bytes.

| Operation | Layout | Profile | Observed relay | Attempt | Payload recovery | API samples | Max health s | Max status s |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| COMMIT | same-share | debug | source | 1 | cached_exact_replay | 1 | 1.906 | 1.781 |
| COMMIT | same-share | release | source | 1 | cached_exact_replay | 1 | 1.860 | 1.844 |
| COMMIT | separate-shares | debug | source | 1 | cached_exact_replay | 1 | 1.735 | 1.750 |
| COMMIT | separate-shares | release | source | 1 | cached_exact_replay | 1 | 1.859 | 1.766 |
| UNSTABLE | same-share | debug | source | 1 | unstable_ranges_recovered (3 ranges) | 1 | 1.828 | 1.922 |
| UNSTABLE | same-share | release | source | 1 | unstable_ranges_recovered (3 ranges) | 1 | 1.703 | 1.703 |
| UNSTABLE | separate-shares | debug | source | 1 | unstable_ranges_recovered (3 ranges) | 1 | 1.860 | 1.797 |
| UNSTABLE | separate-shares | release | source | 1 | unstable_ranges_recovered (3 ranges) | 1 | 1.687 | 1.797 |

API times include the fixture's Podman/request transport overhead and sampling;
they are bounded responsiveness observations, not throughput/latency benchmarks.
Every case proves the same live coordinator, no replacement child, original
assignment/attempt 1, no ReviewRequired, same-ID 202 and no job 2. No service or
worker termination/restart is used for recovery. Normal bounded stop follows
validated final payload/manifest and source/database/enrollment checks.

All eight cases have one post-drop sample, whose status is already Committed.
Health/status also succeed while successful replies are held and the worker is
actually blocked. These discrete observations do not measure uninterrupted API
availability across the entire reconnect interval or an outage-duration bound.

Native drop recovery observed:

- COMMIT, same-share: `cached_exact_replay`.
- COMMIT, separate-shares: `cached_exact_replay`.
- UNSTABLE, same-share: `unstable_ranges_recovered`.
- UNSTABLE, separate-shares: `unstable_ranges_recovered`.

Actual matched server successes are held before forwarding. Actual pending
fchmod syscall 91/mode 0400/target FD and D state, matching controlled server
inode, complete 2 MiB+17 payload hash and live NFSD corroborate the boundary.
The COMMIT audit requires complete preceding UNSTABLE range coverage; WRITE
requires all three original full-count stable=0/committed=0 ranges. The raw
reports distinguish exact/session replay, changed slot hints, uncached errors,
new requests, requested/returned stability and later successful COMMIT as actually
observed. Original-handle selection accounts explicitly for every other-handle
forwarded receive ID, leaving all traffic in the raw report; it never filters
same-handle ranges, bytes, stability or retry identity to manufacture a pass.

All six WRITE drop recoveries (two native plus four mover) show three
RETRY_UNCACHED_REP responses; two retry requests update only the permitted
highest-slot hint. Three new requests resend the original handle/ranges/bytes
with stable=0 and receive committed=0. One later successful same-handle/verifier
whole-file COMMIT covers all three ranges; three stored range relationships do
not mean three distinct COMMIT calls. Each mover case additionally accounts for
one later WRITE on another handle. No stronger-stability resend is observed.
All selected payload loss/replay traffic uses the source relay in both layouts.

Fresh required SLES gates both pass:

- Production `20261019T235321Z-4aa4b43e`: 211 exact target tests per profile.
- Qualification `20261019T235332Z-7199cd27-nfs-qualification`: 212 per profile.

Locked cargo-zigbuild GNU/glibc 2.22 debug/release builds, exact execution in
pinned SLES 12 SP5 userspace, ELF/relocation checks and six ELF-audit negative
controls pass. All 62 current Rust entries and forty ELF artifact bytes match
current/live/fresh archives, including the earlier qualification gate used by
the live runs. All 42 locked packages/features stay unchanged. One shipping
executable remains; the audited disposable native probe is fixture-only.

Both independent audits pass raw payload SHA/decoding/bounds, held-before-
forwarding proof, actual syscall/FD/server correlations, replay/range/stability/
COMMIT relationships, unchanged-source/state/replay/manifest invariants and
original/fresh source/artifact provenance. The COMMIT audit passes
17 proof mutations; the WRITE audit passes 19.
Each also captures four invalid-selector refusals before fixture creation and
successful seven decoder, eight I/O-analysis and ten resend regression methods.
Exact verifier, native-probe and audit-source bytes are retained with each input
report. Raw reports use streaming SHA-256 and lossless zlib/base64 retention.

- [COMMIT raw evidence](RUST-NFS-BUFFERED-COMMIT-LIVE-LOSS-EVIDENCE.json) and [audit inputs](RUST-NFS-BUFFERED-COMMIT-LIVE-LOSS-INPUT-EVIDENCE.json).
- [WRITE raw evidence](RUST-NFS-BUFFERED-UNSTABLE-LIVE-LOSS-EVIDENCE.json) and [audit inputs](RUST-NFS-BUFFERED-UNSTABLE-LIVE-LOSS-INPUT-EVIDENCE.json).

## Preliminary and cancelled acquisitions

`mount-profile-20261019T235348Z-9b4b5d20` passes six native and four COMMIT service
cases before the explicit payload/other-handle accounting refinement. Its exact
10,220,992-byte report and 26 source snapshots remain in
`RUST-NFS-BUFFERED-LIVE-LOSS-PRELIMINARY-EVIDENCE.json`. It is supplementary;
the final common-source matrices above establish this increment's acceptance.

A quoting error in the local edit utility prevented that refinement from being
applied before duplicate `mount-profile-20261020T000717Z-b8cc851a` started.
The duplicate was deliberately cancelled before Rust/service execution by an
owned client's private setup-directory conflict. Its normal runner error path
unmounted and cleaned up with cleanup_errors=[], zero service cases and
rust_executed=false. Its full 651,690-byte FAILED report and exact sources remain
in `RUST-NFS-BUFFERED-LIVE-LOSS-CANCELLED-EVIDENCE.json`, labelled cancelled
setup, not a service qualification failure or pass. The utility was corrected;
all ten regression methods passed before the final matrices started. The audits
checksum both supplementary reports and preserve their actual status/scope.

## Documentation, cleanup and remaining limits

The [complete procedure](NFS-BUFFERED-LIVE-LOSS-LAB.md) records setup, commands,
privileges, native proof before service injection, acceptance, independent audit,
lossless retention, cleanup and testing limitations. SC-114 feeds DOC-01–05;
all earlier IDs remain stable: 114 scenarios and six documentation backlog IDs.
The recorder gains no post-202 polling or intervention duty; consumers still
validate the completion manifest. DOC-06 and all other deferred work stay parked.

Final inventories are captured only after both gates and both NFS runners exit.
Both engines have zero containers. Rootful retains only the two original cache
volumes and default network; rootless retains its original caches and eleven
unrelated September anonymous volumes with creation metadata. No cleanup
uncertainty, forced/lazy unmount or unrelated resource deletion is waived.

Pinned SLES/glibc 2.22 userspace runs on modern WSL2 kernel 6.18.33.2. Volatile
tmpfs, one server per matrix and two logical exports are not physical-media
power-loss proof, independent NAS failure domains, original SLES kernel/packages
or NetApp/Isilon interoperability. A completed COMMIT, returned fsync or free
local guard is not universal remote-settlement authority. Longer losses, server
reboot/verifier changes, worker replacement, other sizes/cache/load/phases and
unobserved source sync/pre-checkpoint behavior remain unqualified. All eight
release gates stay open; production NFS and deletion stay disabled.

Next discover and prove actual manifest-side RPC/reply-withholding capability
before defining its finite fault matrix. Do not assume a small manifest produces
the same UNSTABLE/COMMIT pattern as this payload boundary.
