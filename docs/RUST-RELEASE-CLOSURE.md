# First Rust release: closure review

Reviewed 2026-10-22 against commit `d9c2f2d` on
`feature/rust-transfer-coordinator`. This is a documentation review, not a new
qualification run. All eight release gates remain open. The next increment is
P01 below, not another automatically selected NFS experiment.

## Scope stays fixed

The [first-release checklist](RUST-FIRST-RELEASE.md) remains authoritative for
scope. A remote recorder submits identity, source directory and explicit relative
file names; destination routing belongs to startup configuration. Sizes are
optional assertions. Preserve folders, identical-ID/body retries and whole-set
202 only after durable custody. Before 202 the recorder keeps files and parents
unchanged; afterward it can reuse those paths and has no monitoring duty.

Keep 3N normal logical I/O, verified no-clobber publication and a validated
`COMMITTED.json` consumer boundary. Include same-share and separate-share NFS,
one mover restarting on the same host/account/configuration, private work areas,
local persistent state, bounded shutdown (default 60 seconds, configurable
1-3600), and configurable source-space admission off by default. Configurable
postcommit cleanup is a first-release deliverable, also off by default.

Registration, S3, cross-host takeover, populated-state re-enrollment, offline
repair and general dashboards remain deferred. The later user-requested admin
dashboard history-clear workflow must be explicitly scoped in P01/release
planning (group 18); it is not implemented or resolved by the earlier general UI
deferral. A new scheduler framework, new dependency
experiment or performance optimization is not a release prerequisite merely
because an older design mentions it. Existing requirements must be reconciled
explicitly in P01/P10; this review does not withdraw any of them.

Production NFS and source deletion remain disabled throughout this plan. Passing
individual rows does not authorize enabling them. A final reviewed configuration
change requires all dependent gates and an explicit release decision.

## What the repository actually contains

| Gate | Existing implementation/evidence credited | What still blocks closure |
|---|---|---|
| FR-01 | Loopback submission, per-job status, retention and audited resume/reset controls; persisted identity/body and configured routing. [Remote contract](REMOTE-API-ACCESS-CONTRACT.md) defines RA-01-16. | Config validation rejects remote binding. The Unix controller is operator stop/status, not producer ingress. Protected producer socket, authenticated proxy integration and versioned OpenAPI/manifest contract remain undelivered. Draft routes are not implemented promises. P01-03. |
| FR-02 | Admission implemented, configurable/default-off; [increment 38](RUST-INCREMENT-38.md) really fills/restores source space and preserves existing/partial replay. Payload ENOSPC diagnostics/retry/review already exist. | Combined destination shortage/new admission, bounded concurrent load, unavailable statistics/root changes, and declared inode/quota/external-writer limits need the fixed capacity suite. Do not repeat increment 38 as missing implementation. P06. |
| FR-03 | Supervised mount-profile checks, enrollment/root checks, inherited guard and actual-worker-exit exclusion; substantial real NFS interruption/reply-loss/recovery evidence. [Increment 104](RUST-INCREMENT-104.md) adds partial-handoff source-change refusal. | NMP-41B is a candidate, not verified user mount inventory. Actual delayed-effect safety and required synchronization/server recovery cells are not universally qualified. Same-options remount is not continuity proof. P05, D01/D04. |
| FR-04 | Receipts, retained sources and policy representation provide prerequisites. | Runtime acceptance hardcodes cleanup false; status reports disabled. There is no qualified postcommit cleanup implementation. Default-off does not make this gate complete. P08. |
| FR-05 | Bounded stop/status, default-60 wait, process-group lifetime evidence, original-state recovery and selected manual/systemd races. Early lock-release defect found in increment 46 was fixed in [47](RUST-INCREMENT-47.md). | Allocation can precede its durable owning record; ambiguous leftovers refuse recovery. Remaining allocation/crash, capacity and shipping-unit lifecycle cases need closure. A stopped process does not prove NFS effects settled. P04-07. |
| FR-06 | Locked Zigbuild/glibc-2.22 builds, exact-target SLES userspace tests; reproducible controlled equivalent-systemd-228 lab. | Lab unit is expressly not a production unit. Shipping installation/account/confinement, proxy/native dependencies, disconnected packaging, upgrade/cutover and usable rollback contract remain. P09, D02/D03/D05. |
| FR-07 | Both retained SLES gates pass; source/evidence packs and independent fixture verifiers exist. | Historical trace generator discovers Python/Catch2, not Rust. Reconcile current L1 scope and derive/discover Rust L2/L3 evidence. Audit final shipping artifacts and every matrix disposition. P10/P12. |
| FR-08 | Current operator guide and 138 stable situations describe substantial existing behavior; DOC-01-06 retain user-documentation needs. | Producer/consumer/deployment/recovery guides and complete cutover walkthrough remain. Publish limitations and demonstrate old/new custody exclusion. P11/P12. |

Code anchors for this review are `file-mover/src/lib.rs` (loopback validation,
cleanup policy/status), `file-mover/src/claim_worker.rs` (Allocate before
`begin_claim`), `mover-fs/src/lib.rs` (allocation/orphan limitation), and
`mover-store/src/lib.rs` (schema 11/migrations), all under `rust/crates/`.
See [repair prerequisites](RETENTION-REPAIR-DESIGN.md); fixing durable allocation
ordering is separate from adding the deferred offline repair tool.

The current [production evidence](RUST-SLES-EVIDENCE.json) and
[qualification evidence](RUST-SLES-QUALIFICATION-EVIDENCE.json) retain exact
artifacts and inputs. They establish their recorded ABI/test results, not a
complete release. Existing NFS results stay scoped to their actual layouts,
operations and fault mechanisms. See the
[previous checklist evidence](RUST-RELEASE-EVIDENCE-HISTORY.md) and individual
increment reports; this review supersedes their scheduling suggestions.

## Decisions that must not be hidden in implementation

| Decision | Required input/disposition | Blocks |
|---|---|---|
| D01: mount profile | Obtain read-only source/destination version/options/export/account observations when available. Compare with NMP-41B: buffered hard NFSv4.1/TCP/sec=sys, normal attribute cache and declared locking/coherence settings. Unknown NetApp/Isilon mounts cannot be assumed to match. No NAS administrator API or unapproved mount change is required by this review. | Final profile and NFS authorization. |
| D02: remote deployment | Select proxy/TLS package and supported version, certificate provisioning/allowlist, dedicated proxy account and protected backend socket permissions. Review native dependencies/licenses and qualify them on the target profile. Preserve RA-01-16; registration stays deferred. | P03 and shipping package. |
| D03: supported lifecycle | Declare shipping unit/restart policy, account, persistent local paths, kernel/cgroup/container assumptions and supported manager package. Equivalent 228 evidence is not exact SLES maintenance-RPM/kernel qualification. Container-only testing remains the agreed approach; do not add a real SLES installation prerequisite. | P07/P09 and truthful support claims. |
| D04: unproven storage faults | Decide how to satisfy required durability/server-recovery obligations where the fixture lacks the fault. NFSD-quiesced container restart is not abrupt live NAS/power failure. Clean local fsync with no RPC is not a withheld service-sync reply. Require an adequate reproducible mechanism or explicitly reviewed alternative evidence/scope decision. Until then the affected matrix cells and gates remain blocked. | Storage/durability closure; no implicit waiver. |
| D05: cutover/rollback | Identify supported predecessor and state format. Schema 11 refusal by an older binary is safe refusal, not working rollback. Define compatible-binary rollback and interrupted-upgrade recovery; never restore a stale database over active custody. Demonstrate legacy/new service exclusion using the supported installation workflow. | P09/P12 and functional upgrade/rollback claim. |

These decisions do not block the independent P01 contract work. Bring each to
the user as a simple question when its package approaches; do not select a less
demanding release scope on the user's behalf.

## Finite acceptance matrix

The 24 rows below are acceptance families, not 24 passing tests. Each has a
closed list of required variants. Existing evidence may satisfy an exact cell;
record its run/profile/artifact and remaining cells before running a package.
Do not multiply every row by every other row. Runtime qualification uses both
debug/release target artifacts; production and opt-in qualification builds retain
their separate SLES gates. NFS layout variants mean same-share disjoint roots and
separate-share roots; use separate server endpoints only where explicitly listed.

`Partial` means selected evidence exists; `Missing` means a deliverable is absent;
`Blocked` means required capability/profile evidence is unresolved. None closes a
whole FR gate. Each row needs an executable case manifest with concrete inputs,
expected outcomes, timeout, cleanup and retained evidence before execution; this
is implementation of the fixed row, not permission to grow its scope indefinitely.

| Case | Gates / contract obligations | Fixed variants and acceptance condition | Review status / package |
|---|---|---|---|
| RC-01 | FR-01/07 | Versioned submission/status/control/error schemas and manifest validation; exact supported route inventory, retry classes, ID retention, encoding, optional size, nested paths, metadata and whole-set 202. Reconcile proposed-only routes against active requirements. | Missing; P01 |
| RC-02 | FR-01; RA-01-08 | Every existing RA-01-08 acceptance/refusal obligation on the selected protected producer socket/proxy boundary; certificate allowlist, configured identity binding and separation from operator access. No unauthenticated fallback. | Missing; P02-03 |
| RC-03 | FR-01/05; RA-09-16 | Every existing RA-09-16 obligation: frozen request/resource/time bounds, identical retry/lost response, backend/proxy failures and certificate operations as specified in that contract. Freeze concrete malicious framing/path inputs, not an unlimited fuzzing promise. | Missing; P02-03 |
| RC-04 | FR-03/05; SH-01/13; MP-06/09 | Original local state succeeds; wrong/stale/copied state, unsafe ownership, NFS state/sidecars, foreign private allocations and scope aliases refuse before effects. No automatic adoption/rebind. | Partial; P04-05 |
| RC-05 | FR-03/05; SH-03/04 | Six existing internal worker modes: bootstrap, enrollment, source-space, claim, payload and delivery. For each, audit inherited authority and coordinator death before actual exit; include source-read, file-publication and manifest assignment phases. Replacements remain excluded; recovery uses original state. | Partial; P05/07 |
| RC-06 | FR-05 | Claim-private, recording, payload-staging and manifest-staging allocations: crash before allocation, after creation/before receipt, and after receipt. Durable intent/owned reconciliation or explicit conservative legacy/foreign refusal; never name-based adoption/deletion. | Missing durable-intent coverage; P04 |
| RC-07 | FR-03; MP-01-05/07-10 | Each MP obligation's positive and refusal vectors, bound to real supervised startup/worker authorization, both roots. Include missing mount, incompatible options, overlap/nested aliases, changed pins and inaccessible/replaced root. Reuse the contract's existing finite vectors. | Partial; P05, D01 |
| RC-08 | FR-03/05; SH-10/11; MP-11/12 | Both NFS layouts, source claim LINK and REMOVE: pending effect, applied reply withheld, coordinator death, original-state recovery and identical-ID retry before 202. Include one-file and partial two-file custody. Retain existing 84/97/98/102-104 evidence where exact. | Partial; P05 |
| RC-09 | FR-03/05; SH-10/11; MP-11/12 | Both layouts, payload and manifest LINK and staging REMOVE: applied reply withheld, coordinator death and original-state recovery. Validate original inode/attempt, no-clobber and consumer commitment independently of reply visibility. | Partial; P05 |
| RC-10 | FR-03; SH-11/12 | Source-file/source-directory and payload-file/payload-directory/manifest-file/manifest-directory sync boundaries: record actual syscall and eligible RPC first. Withhold a reply only to a positively attributed operation. Local completion/no RPC gets an explicit capability disposition, never a fabricated blocked-sync pass. Native dirty-write controls remain separate. | Blocked for unobserved RPC cells; P05, D04 |
| RC-11 | FR-03/05; SH-10/12 | Both layouts: interrupted copy and verification reread, original-state continuation after endpoint restoration. Independent-endpoint cases interrupt source during copy and destination during verification, proving the peer stays healthy. Preserve full destination verification and 3N normal path. | Partial; P05 |
| RC-12 | FR-03; SH-11/12 | Source claim, copy, verification, payload LINK/REMOVE and manifest LINK/REMOVE: compare controlled NFSD restart, quiesced-container restart and required abrupt-server/durability fault disposition. No claim that these mechanisms are equivalent. Delayed writes/UNSTABLE settlement must be safe or block recovery. | Partial; abrupt/durability cells blocked; P05, D04 |
| RC-13 | FR-02 | Existing source-fill/restoration baseline; admission off/on, below/at/above threshold, same-ID new/partial/claimed replay, blocked statistics and changed root. Enabled refusal creates no new job or false path release; restore capacity without changing policy. | Partial; P06 |
| RC-14 | FR-02/05 | Destination ENOSPC and source admission off/on, finite six-request burst at the existing admission limit, exhausted payload retry budget and audited resume. Freeze inode/quota/external-writer vectors and classify actual versus injected errors. Preserve existing-job retries and bounded resources. | Partial; P06 |
| RC-15 | FR-03/05; SH-02/09 | Manual/manual, manual/systemd and systemd/systemd starts; exactly one effect owner. Selected shipping-account/unit restart policy cannot let a rejected contender stop the owner or start an unbounded restart loop. | Partial; P07/09, D03 |
| RC-16 | FR-05; SH-05-08 | Wait values 1/60/3600 and invalid config; clean drain, incomplete stop, repeat signal/stop and subsequent status. Test real blocked copy and bootstrap workers at short/default deadlines; controller returns bounded incomplete without releasing ownership or resetting the first deadline. | Partial; P07 |
| RC-17 | FR-05/06; SH-09/13 | Shipping account/local persistent state: manager failure or MainPID zero with surviving worker, restart after incomplete stop, host/container service restart with original state, wrong config/state refusal. Unit-scoped actions and bounded status remain safe. | Partial; P07/09 |
| RC-18 | FR-04 | Job cleanup policy off/on crossed with current startup authorization off/on. Only both on permits cleanup after whole-manifest/receipt validation; producer-reused paths and other jobs remain untouched. Retained accounting remains correct. | Missing; P08 |
| RC-19 | FR-04/05 | Owned claimed-source unlink: before effect, applied/unrecorded reply, crash/restart; destination changed, custody changed and foreign leftovers. Persist/reconcile progress independently, preserve review, no recopy or unsafe removal. Both NFS layouts after required storage gates. | Missing; P08 |
| RC-20 | FR-05/06 | Supported fresh state and each declared writable schema migration to 11 (update target if changed), interrupted upgrade, supported binary rollback and unsupported-version refusal. Preserve DB/WAL/custody; stale backup restoration is prohibited. | Partial; P09, D05 |
| RC-21 | FR-06 | Disconnected locked build, licenses/notices, exact native dependencies, install/uninstall preserving state, service-account permissions and actual confinement denials. Qualify the chosen proxy and shipping unit, not only their lab substitutes. | Missing shipping package; P09 |
| RC-22 | FR-07; SH-14 | Production and qualification SLES gates: target GNU/glibc 2.22, exact ELF/interpreter/library audit and target tests; retained sources/hashes. Update CI input coverage/artifact retention and explicit specialized fixture execution procedure. | Passing baseline, RC rerun required; P10/12 |
| RC-23 | FR-07/08 | Current L1 to Rust L2/L3 to discovered meaningful test/evidence mapping, all RC/RA/SH/MP dispositions reviewed; DOC-01-05 complete and DOC-06 deferred tools distinguished from required cleanup instructions. | Missing release trace/docs; P10-11 |
| RC-24 | FR-08 | Exact candidate walkthrough: remote lost-202 retry, partial multi-file handoff/path reuse, consumer validation, capacity recovery, original-state stop/restart, cleanup off/on and legacy cutover/declared rollback. No simultaneous old/new custody. | Missing; P12 |

Contract coverage is explicit: RA-01-08 -> RC-02; RA-09-16 -> RC-03;
SH-01/13 -> RC-04/17, SH-02/09 -> RC-15/17, SH-03/04 -> RC-05,
SH-05-08 -> RC-16, SH-10-12 -> RC-08-12, SH-14 -> RC-22;
MP-01-05/07-10 -> RC-07 (MP-09 also RC-04), MP-06 -> RC-04,
MP-11/12 -> RC-08-11. Mapping does not replace the original obligation's text.

For unobserved sync RPCs, perform one bounded discovery package over the six
listed boundaries on the selected profile, with concrete workload/cache inputs
agreed before the run. If it cannot reproduce an eligible RPC, stop that branch
of experiments and report D04. Do not keep adding workloads automatically.
Likewise an unavailable abrupt-restart mechanism is a blocked disposition, not
an indefinite series of bootstrap attempts. No physical durability claim can be
derived merely from a successful process/container restart.

## Ordered work packages

P01 input: [the error review and API-I01-06](REST-ERROR-SCENARIOS.md) record
approved groups 1-41 (including retention, file-preserving controls and confirmed owned-data disposal scope). Resolve
remaining request/schema/compatibility decisions before freezing OpenAPI and
implementing identity changes. This refines RC-01-03 without adding a release
gate or claiming new runtime/qualification evidence.


| Package | Concrete deliverable | Dependencies |
|---|---|---|
| P01 | Freeze versioned OpenAPI, manifest and supported release behavior/error/retention inventory. Identify unresolved active requirements explicitly. This is the next increment. | Review baseline |
| P02 | Implement protected producer Unix ingress and configured caller binding, preserving local operator separation and existing acceptance behavior. | P01 |
| P03 | Integrate selected authenticated remote proxy, certificate workflow and complete RA suite. Registration stays deferred. | P02, D02 |
| P04 | Persist allocation intent/receipt ordering and qualify its four object classes; conservative ambiguous legacy refusal, no offline repair tool. | P01 |
| P05 | Close the bounded NFS matrix RC-04/05/07-12 using existing evidence first; publish blocked capability/profile cells rather than expanding tests automatically. | P04, D01/D04 for final closure |
| P06 | Complete capacity suite RC-13/14 without redesigning existing retry/review policy. | P01; storage findings from P05 |
| P07 | Qualify remaining bounded shutdown and selected shipping-unit lifecycle cells. | D03, relevant P05 results |
| P08 | Implement default-off, independently recoverable source cleanup and its receipt/authorization tests. Keep production switch off. | P04-07 safety prerequisites |
| P09 | Deliver supported package/unit/account/confinement, disconnected build, provisioning and state-preserving upgrade/rollback/cutover. | P03/07/08, D02/D03/D05 |
| P10 | Finish Rust requirements/trace discovery, meaningful failure coverage, CI/evidence retention and candidate artifact inventory. Update mappings alongside earlier packages. | P01-09 for final closure |
| P11 | Finish producer/consumer/operator/deployment/recovery docs from the scenario catalog; maintain them alongside implementation. | P01-09 for final behavior |
| P12 | Execute exact release-candidate walkthrough and SLES gates, review every blocked/partial cell and all eight gates; only then propose production enablement/release. | P01-11 and D01-05 resolved |

These are deliverables, not a promise of twelve turns or a release date. Split
implementation into short tested increments. A newly found safety defect blocks
release and gets a named matrix row/requirement and reviewed scope change. Generic
requests for more cache combinations, NAS products, throughput tuning or longer
endurance are later hardening unless tied to an unmet existing obligation or the
declared shipping profile; do not silently drop required delayed-effect,
durability, bounded-resource or lifecycle evidence under that label.

## Validation and limitations of this review

No Rust source, dependency, runtime switch, fixture or generated evidence is
changed. No new build, NFS run, systemd run or release qualification is claimed.
The retained SLES gates are prior evidence; P12 must rerun them on the candidate.
Review checks cover local links, matrix/contract identifiers, retained baseline
status, unchanged runtime sources, scenario-ID stability and diff whitespace.
Shared-kernel containers do not reproduce a SLES kernel, exact vendor systemd
patches, physical NAS persistence or all NetApp/Isilon behavior. These remain
explicit support/evidence decisions, not a requirement to test on a real SLES host.
