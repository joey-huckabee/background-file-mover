# Rust service scenarios and user documentation backlog

This is the maintained scenario catalog for the Rust transfer coordinator. It
backfills the behavior addressed in increments 01–18 and grows with subsequent
increments. Read it before designing a new effect or writing user instructions.
It describes the current Rust prototype; the historical Python/C++ user guides
are reference material, not instructions for this service.

## Scope and reading rules

The current service is a trusted **loopback, protected local-filesystem prototype**,
with one configured generator/source and a destination selected at startup.
NFS works only in the retained opt-in qualification build and controlled fixture.
Remote REST, registration, S3 and source deletion are not enabled.

Three different facts matter to users:

- **Accepted:** the request is durable, but some files can still be at producer
  names. The producer must keep all submitted files and parents unchanged.
- **Claimed / submission HTTP 202:** all files have durable private-custody
  receipts. The producer can reuse original paths and need not monitor delivery.
  This does not mean the destination recording is ready.
- **Committed:** the recording has a validated immutable `COMMITTED.json`.
  Consumers wait for and validate that manifest. Sources remain retained in this
  prototype; completion does not authorize users to delete private custody data.

Every row gives an initial user explanation and the current response/action.
**Local** means implemented and covered by protected-local Rust tests through
the pinned SLES userspace gate. **Fixture** means exercised in the specified
controlled NFS setup, not production NFS approval. **Pending** means no passing
qualification is claimed. **Future** means not implemented or not qualified.
Evidence links explain the tests and their limits; they are not substitutes for
deployment instructions. Scenario IDs are documentation keys, not requirement IDs.

## Producer submissions and handoff

| ID | Situation | Behavior and user action | Scope / evidence |
|---|---|---|---|
| SC-001 | Submit one completed recording | Send generator ID, stable submission ID, mover-visible source directory and explicit file names. The configured destination is pinned when accepted. Close writers and leave files/parents unchanged until submission 202. | Local; [04](RUST-INCREMENT-04.md), [06](RUST-INCREMENT-06.md). |
| SC-002 | Several files in one recording | Every required file must be claimed before 202; delivery then proceeds automatically. A partial handoff does not release any producer paths. | Local; [03](RUST-INCREMENT-03.md), [06](RUST-INCREMENT-06.md). |
| SC-003 | File sizes unknown, empty or asserted | Omit `size_bytes` to let the service measure during claim. Zero is a valid size. If supplied, the unsigned expected size must match; mismatch blocks handoff. Size measurement does not read the payload. | Local; [03](RUST-INCREMENT-03.md), [04](RUST-INCREMENT-04.md). |
| SC-004 | Files in subfolders | List relative names such as `video/camera.bin`. Destination folders preserve these paths beneath the job directory. Empty/unlisted directories and unlisted files are not copied; there is no recursive directory submission. | Local; [03](RUST-INCREMENT-03.md), [06](RUST-INCREMENT-06.md). |
| SC-005 | Response lost, request timed out or recorder restarted | Retry the identical body with the same generator/submission IDs. The durable job is replayed; an uncertain response does not prove acceptance failed. Keep paths unchanged until a submission 202 is received. | Local; [02](RUST-INCREMENT-02.md), [04](RUST-INCREMENT-04.md). |
| SC-006 | Same ID used with changed request | Conflicting content returns 409; file-list order currently matters to exact replay. Preserve the original request for retry. Do not use a new ID to bypass an already accepted partial handoff. | Local; [02](RUST-INCREMENT-02.md), [04](RUST-INCREMENT-04.md). |
| SC-007 | Reuse original names immediately after 202 | The recorder can write its next recording at those names. Same-ID replay uses private claim receipts and never claims the new recording at a reused leaf. | Local and normal NFS fixture; [03](RUST-INCREMENT-03.md), [17](RUST-INCREMENT-17.md), [18](RUST-INCREMENT-18.md). |
| SC-008 | One file is missing while others have been claimed | Existing claims stay in custody. Before the pinned missing deadline expires, return retryable 503 `handoff_pending`; recorder retries drive reconciliation. No 202 is issued until all claims finish. Do not recreate or modify already handed-off files. | Local; [04](RUST-INCREMENT-04.md). |
| SC-009 | Missing-file deadline expires | Submission/retry persists a review block and returns 409 `recording_blocked`. Restart/replay does not extend it. Operator status can show an elapsed deadline before a retry persists the block. Keep pending paths unchanged and obtain review. | Local; [04](RUST-INCREMENT-04.md), [07](RUST-INCREMENT-07.md), [09](RUST-INCREMENT-09.md). |
| SC-010 | Unsafe source object, changed file or lost custody | Symlinks, special files, extra hard links, writable/unowned parents, mount escape and changed identities are refused. Ownership and closed immutable files are prerequisites; changing names does not stop an existing writer. Correct setup through review without deleting private data. | Local; [03](RUST-INCREMENT-03.md), [12](RUST-INCREMENT-12.md). |
| SC-011 | Wrong generator, source scope, JSON or HTTP framing | Unknown generator/out-of-scope source returns 403; invalid JSON/paths/framing returns 400; unsupported media returns 415. Supply the configured identity and strict supported contract. A generator ID is currently a configured label, not authentication. | Local; [04](RUST-INCREMENT-04.md). |
| SC-012 | Service busy or retention admission full | Transient queue/storage waits return 503; capacity refusal uses `retention_capacity`. No error releases paths. Back off with the same ID/body. Replays remain possible at retention capacity; reservations are conservative accounting, not measured free disk space. | Local; [04](RUST-INCREMENT-04.md), [06](RUST-INCREMENT-06.md), [10](RUST-INCREMENT-10.md). |

## Delivery, integrity and consumers

| ID | Situation | Behavior and user action | Scope / evidence |
|---|---|---|---|
| SC-013 | Destination temporarily absent after handoff | The claimed recording remains retained and delivery is deferred five seconds without consuming the ordinary failure count. The recorder can continue after 202. Restore the pinned destination; restarting with a new route does not reroute the accepted job. | Local; [06](RUST-INCREMENT-06.md), [07](RUST-INCREMENT-07.md). |
| SC-014 | Large file crosses filesystems | Hash the source while copying to owned destination staging, independently reread staging, compare hash/size, then publish. Normal logical payload I/O is 3N; a 100 GB payload is copied once. Do not interpret logical I/O as network-byte or physical-disk guarantees. | Local and normal NFS fixture; [05](RUST-INCREMENT-05.md), [INTEGRITY-DESIGN](INTEGRITY-DESIGN.md), [17](RUST-INCREMENT-17.md). |
| SC-015 | Source changes or staging fails verification | Changed source identity/size or destination digest mismatch prevents verified publication/commitment. Source and uncertain staging are retained. Investigate through operator status/review; a retry is not permission to weaken integrity checks. | Local; [05](RUST-INCREMENT-05.md), [11](RUST-INCREMENT-11.md). |
| SC-016 | Final file or manifest name already exists | Never overwrite or adopt a foreign object because its bytes match. Recovery requires this operation's durable intent, owned identity and integrity evidence. A collision blocks/requires review. | Local; [05](RUST-INCREMENT-05.md), [06](RUST-INCREMENT-06.md), [17](RUST-INCREMENT-17.md). |
| SC-017 | Some destination files are visible before the recording completes | Individual file publication does not commit the set. Consumers wait for a valid immutable `COMMITTED.json` with the expected recording and complete ordered file mapping. Directory existence or 202 alone is insufficient. | Local and normal NFS fixture; [06](RUST-INCREMENT-06.md), [17](RUST-INCREMENT-17.md). |
| SC-018 | Restart after an incomplete copy | Keep the old uncertain partial file and allocate a new attempt. Completed copied/verified phases can resume their next step; uncertain publication is reconciled and may require an additional digest reread. Allow enough retention capacity for old and new attempts. | Local and copy-outage fixture; [05](RUST-INCREMENT-05.md), [13](RUST-INCREMENT-13.md), [18](RUST-INCREMENT-18.md). |
| SC-019 | Filesystem effect completed but its database receipt/reply was lost | Reconcile the recorded intent and exact owned object before saving completion; do not infer rollback from an error. This applies to claims, file publication and manifest publication. The recorder retries its original request; operators preserve custody objects. | Local; [03](RUST-INCREMENT-03.md), [06](RUST-INCREMENT-06.md), [12](RUST-INCREMENT-12.md). |
| SC-020 | No-clobber rename is unsupported and a link/unlink effect is interrupted | The supported fallback uses an exclusive link, synchronizes it, and unlinks only the old owned binding. Exactly two matching aliases may be reconciled; a foreign object or third link blocks. Do not manually remove either alias to make recovery look complete. | Local substep fault tests; NFS durable two-name claim/file/manifest cases. In-flight RPCs and other synchronization boundaries remain unqualified; [17](RUST-INCREMENT-17.md), [18](RUST-INCREMENT-18.md), [20](RUST-INCREMENT-20.md). |
| SC-021 | Recording is committed but sources/staging still consume space | Source cleanup is disabled and old attempts remain retained. Commitment never implies automatic space reclamation. Capacity planning must account for retained committed jobs. Inspection/repair and configurable deletion remain future effects. | Local; [06](RUST-INCREMENT-06.md), [10](RUST-INCREMENT-10.md). |
| SC-022 | Consumer runs as another user | Current recording directories are private to the service UID; production consumer permissions/metadata policy are unfinished. The manifest contract is implemented, but a deployment must not promise shared-reader access yet. | Current limitation; [06](RUST-INCREMENT-06.md). |

## Operators, startup and supervision

| ID | Situation | Behavior and user action | Scope / evidence |
|---|---|---|---|
| SC-023 | Inspect one job while filesystem work stalls | `GET /api/v2/jobs/{job_id}` reads local durable state without source/destination filesystem calls. `Accepted`, `Claimed`, `Committed` and retry/review details describe persisted facts, not live storage readiness or proof of current custody. | Local and selected NFS outages; [07](RUST-INCREMENT-07.md), [18](RUST-INCREMENT-18.md). |
| SC-024 | Delivery reaches its three-failure review threshold | Ordinary failed/uncertain delivery is retried five seconds apart up to the persistent review threshold. Inspect/correct the cause, then submit audited `/resume` with the current review epoch, stable command ID and reason. HTTP 200 schedules reconciliation, not completed delivery or collision bypass. | Local; [06](RUST-INCREMENT-06.md), [08](RUST-INCREMENT-08.md). |
| SC-025 | Operator response lost or stale resume repeated | Retry the exact command ID/parameters to get its original receipt. Changed parameters conflict; a new command must use the current epoch. An old replay does not reset a later review or schedule another resume. | Local; [08](RUST-INCREMENT-08.md). |
| SC-026 | Extend the deadline for a reviewed missing file | Inspect the pending file and missing-review epoch, confirm recorder paths remain untouched, then use `/reset-missing` with a reason, stable command ID and explicit bounded retry window. This changes only the deadline; the recorder still retries and waits for its submission 202. | Local; [09](RUST-INCREMENT-09.md). |
| SC-027 | Inspect retention/headroom before admitting more work | Global/per-job retention endpoints report conservative database reservations and unmeasured counts, with exact decimal byte totals. They explicitly do not inspect disk, account for every orphan or authorize reclamation. A per-job report cannot establish global headroom. | Local; [10](RUST-INCREMENT-10.md). |
| SC-028 | A second service competes for the same source namespace | Exclusive source custody refuses the competing startup before SQLite/readiness. The local inherited lock remains while an actual child holds it. This is not distributed fencing across NFS clients. | Local and selected coordinator-death fixture; [15](RUST-INCREMENT-15.md), [18](RUST-INCREMENT-18.md). |
| SC-029 | Source mount unavailable during startup | Source bootstrap runs in a supervised child. No HTTP readiness is granted until custody and confirmed successful child exit. A listening socket is not readiness; the bootstrap deadline or a signal cannot guarantee a hard-mounted syscall will exit promptly. | Controlled NFS startup fixture; [14](RUST-INCREMENT-14.md), [15](RUST-INCREMENT-15.md). |
| SC-030 | Graceful shutdown during an active effect | Stop admission, request worker termination, and wait for confirmed exit before releasing the assignment. Effects may already have applied; retain evidence and replay after restart. Shutdown can wait for NFS restoration. | Local and selected NFS outages; [11](RUST-INCREMENT-11.md), [13](RUST-INCREMENT-13.md), [18](RUST-INCREMENT-18.md). |
| SC-031 | Worker killed or coordinator crashes during publication | A signal/deadline is not proof of exit. Do not launch a replacement until the old worker has exited; its inherited custody may outlive the coordinator. Reconcile any effect it finishes after connectivity returns. | Local and actual Rust-child NFS fixture; [13](RUST-INCREMENT-13.md), [18](RUST-INCREMENT-18.md). |
| SC-032 | Allocation exists without a durable allocation receipt | Preserve the unattributable directory/staging object and block adoption. Offline inventory/repair is deferred; names, emptiness or equal bytes do not authorize reuse/deletion. Durable creation intents and fencing are prerequisites for future repair. | Local; [03](RUST-INCREMENT-03.md), [06](RUST-INCREMENT-06.md), [RETENTION-REPAIR-DESIGN](RETENTION-REPAIR-DESIGN.md). |
| SC-033 | Existing local database opened after an upgrade | Tested migrations through schema 7 preserve jobs, instance identity, claims, retry state and audits. Foreign/future or inconsistent state is rejected and retained. This is not a promise about arbitrary future upgrades or backup/restore procedures. | Local; [02](RUST-INCREMENT-02.md), [08](RUST-INCREMENT-08.md), [09](RUST-INCREMENT-09.md). |

## Compatibility and controlled NFS qualification

| ID | Situation | Behavior and user action | Scope / evidence |
|---|---|---|---|
| SC-034 | Modern host builds for SLES 12 SP5 userspace | Both production and qualification binaries use zigbuild GNU/glibc 2.22 and conservative x86_64 settings. Every build gate audits loader/libraries/symbols and executes exact debug/release artifacts in pinned SLES userspace. Containers share the runner kernel/CPU. | Compatibility gate; [RUST-SLES-GATE](RUST-SLES-GATE.md). |
| SC-035 | Production binary receives an NFS root or fixture pause variables | NFS roots are rejected; fixture controls cannot enable NFS or pause production effects. Check the compiled build label before testing/deployment. Qualification builds remain separate from deployment packaging. | Production controls and refusal fixture; [NFS-QUALIFICATION](NFS-QUALIFICATION.md), [18](RUST-INCREMENT-18.md). |
| SC-036 | Normal NFS source, destination, or both | The qualification service performs multi-file handoff/replay, path reuse, nested and empty file delivery and exact manifest/hash validation in both profiles. SQLite remains local. This is one controlled client/server, not approval of arbitrary mounted shares. | Fixture; [17](RUST-INCREMENT-17.md), [baseline evidence](RUST-NFS-BASELINE-EVIDENCE.json). |
| SC-037 | NFS fails while claim application is pending | The interrupted request cannot return 202 or release paths. Health/status remain available after initial startup; restore connectivity, confirm worker exit, restart/replay and complete the same claim. | Fixture; [18](RUST-INCREMENT-18.md). |
| SC-038 | NFS destination write stalls after partial copy | Health/status remain available and no replacement starts prematurely. SIGKILL did not establish immediate exit in the measured cases; old staging could grow before restoration. Recovery retained it and committed a new attempt. | Fixture; [18](RUST-INCREMENT-18.md). |
| SC-039 | NFS publication is pending when the coordinator dies | The actual child retains source custody and refuses competing startup. It can finish publication after restoration; only confirmed exit permits restart/reconciliation. The fixture distinguishes exited zombies from processes reaped by init. | Fixture; [18](RUST-INCREMENT-18.md). |
| SC-040 | NFS fails with both completion-manifest aliases present | Reconcile the exact durable manifest and two owned aliases, remove only the staging binding, preserve exact manifest bytes and record commitment without copying again. | Fixture; [18](RUST-INCREMENT-18.md). |
| SC-041 | NFS source payload read is interrupted | The fixture observed a kernel-blocked reader with an incomplete payload loop, kept the assignment until confirmed exit and recovered using attempt 2. The zero-byte attempt 1, private source and reused original path were retained. Read workers exited before restoration in this run; this is not a universal cancellation guarantee. | Fixture, debug/release; [19](RUST-INCREMENT-19.md), [runtime evidence](RUST-NFS-RUNTIME-EVIDENCE.json). |
| SC-042 | NFS destination verification read is interrupted | Already copied staging stayed Copied while its independent reread was incomplete and kernel-blocked. Confirmed exit preceded recovery, which reverified and committed the same attempt 1 with the expected manifest/hash. This does not establish prompt cancellation for other operations/outages. | Fixture, debug/release; [19](RUST-INCREMENT-19.md), [runtime evidence](RUST-NFS-RUNTIME-EVIDENCE.json). |
| SC-049 | NFS fails after a claim link is durable but before the original name is removed | Both profiles withheld 202 (503 handoff_pending, paths unreleased), preserved both exact aliases through interruption and recovered the same inode to one private name before 202. Reusing the original path and replaying the same ID then preserved the next recording. The aliases are one payload, not two copies. Keep paths untouched before 202 and preserve ambiguous names for recovery. | Fixture, debug/release; [20](RUST-INCREMENT-20.md), [runtime evidence](RUST-NFS-RUNTIME-EVIDENCE.json). Worker exit was not observed before restoration in the debug case; signals do not prove cancellation. |
| SC-050 | NFS fails after a final file link is durable but staging still exists | Both profiles retained staging/final aliases and no completion manifest through interruption, then recovered the same inode on attempt 1, removing only staging and validating the committed manifest/hash. A visible final filename still does not commit the recording. Preserve aliases and wait for a valid COMMITTED.json. | Fixture, debug/release; [20](RUST-INCREMENT-20.md), [runtime evidence](RUST-NFS-RUNTIME-EVIDENCE.json). The worker was held at the local durable-link checkpoint; an in-flight unlink RPC is not qualified. |
| SC-051 | NFS source claiming remains blocked for three minutes | Keep submitted paths untouched until 202. Both profiles kept Accepted/unreleased state and the same blocked worker, with responsive health/status. Same-ID retries returned retryable 503 handoff_pending then service_busy when the one-slot submission queue stayed occupied. After restoration the running coordinator committed attempt 1, retained sources and preserved subsequent original-path reuse/replay. An HTTP timeout does not cancel its queued command. | Fixture, debug/release; [21](RUST-INCREMENT-21.md), [long-outage evidence](RUST-NFS-LONG-OUTAGE-EVIDENCE.json). Selected 193-second observations; no concurrent flood or arbitrary-duration guarantee. |
| SC-052 | NFS destination verification remains blocked for three minutes | Already claimed paths may be reused; three same-ID retries returned 202 for the same job. Both profiles retained Copied state, an incomplete reread and the same blocked worker, with responsive health/status. After restoration they committed attempt 1 without restarting and validated manifest/hashes while retaining sources. Consumers still wait for a valid completion manifest. | Fixture, debug/release; [21](RUST-INCREMENT-21.md), [long-outage evidence](RUST-NFS-LONG-OUTAGE-EVIDENCE.json). Selected 195-second observations; no server reboot or power-loss guarantee. |

## Planned situations without implementation/qualification promises

| ID | Situation | Remaining decision or prerequisite | Scope |
|---|---|---|---|
| SC-043 | Remote recorder submits to a mover with a shared NFS mount | Define remote listener/security and caller binding; later registration uses a one-time setup key. Current loopback generator label is not a token. Keep registration work deferred. | Future; [REST draft](REST-API-DRAFT.md). |
| SC-044 | Destination is S3/object storage | Qualify separate object ownership, checksums, multipart/retry and manifest semantics. An ETag is not universally SHA-256, and a provider checksum does not automatically replace the agreed filesystem verification path. | Future; [INTEGRITY-DESIGN](INTEGRITY-DESIGN.md). |
| SC-045 | Cleanup enabled after commitment | Implement explicit pinned job policy plus current startup authorization, verified publication receipts and separately retried conservative deletion. Current service always retains source data. | Future; [TRANSFER-PROTOCOL](TRANSFER-PROTOCOL.md). |
| SC-046 | Another client, changed export/root or old worker attempts an effect | Establish stable export/root authorization and cross-client fencing. Single-client flock/observed inode identity is insufficient. Do not enable production NFS before this qualification. | Future; [NFS-QUALIFICATION](NFS-QUALIFICATION.md). |
| SC-047 | Server reboot, power loss, indefinite outage or physical disk exhaustion | Qualify storage durability, server/export changes, physical free-space margins and retry behavior. Current process-kill/container tests do not prove hardware/kernel/power-loss outcomes. Selected three-minute outages are tracked separately in SC-051/052. | Future; [ROADMAP](ROADMAP.md). |
| SC-048 | Operator inventories/repairs orphaned data or lists every job | Design durable allocation ownership, fenced repair and bounded paginated inventory/queries. Existing read-only accounting/status are not an offline repair tool or collection API. | Deferred/future; [RETENTION-REPAIR-DESIGN](RETENTION-REPAIR-DESIGN.md). |

## Documentation work fed by this catalog

The explanations above are the first retrospective user documentation. The
following deliverables still need complete runnable examples and operational
instructions. Update this table when a guide is delivered; do not silently treat
an increment result document as a finished user guide.

| Documentation item | Scenarios | Existing material to reuse | Remaining user-facing work |
|---|---|---|---|
| DOC-01 Producer quickstart and retry decision table | SC-001–012 | [04](RUST-INCREMENT-04.md), [local example](../rust/config/local.example.json) | Ready-to-run client example, 202/error handling and an explicit partial-handoff/lost-response walkthrough. |
| DOC-02 Consumer recording/manifest guide | SC-004, SC-014–022 | [06](RUST-INCREMENT-06.md), [integrity design](INTEGRITY-DESIGN.md) | Example manifest validator, incomplete-set/collision examples and final permissions policy when implemented. |
| DOC-03 Operator status and review runbook | SC-008–010, SC-023–027 | [07](RUST-INCREMENT-07.md), [08](RUST-INCREMENT-08.md), [09](RUST-INCREMENT-09.md), [10](RUST-INCREMENT-10.md) | Worked status snapshots, resume/reset commands, stale/uncertain command retry and retention capacity triage. |
| DOC-04 Restart/shutdown/custody troubleshooting | SC-018–020, SC-028–033, SC-037–042, SC-049–052 | [13](RUST-INCREMENT-13.md), [15](RUST-INCREMENT-15.md), [18](RUST-INCREMENT-18.md), [19](RUST-INCREMENT-19.md), [20](RUST-INCREMENT-20.md), [21](RUST-INCREMENT-21.md) | Explain partial versus completed effects, delayed worker exit, two-name recovery, live outage recovery, preserved artifacts and escalation without unsupported manual repair. |
| DOC-05 Supported deployment and qualification matrix | SC-022, SC-034–036, SC-043–047, SC-051–052 | [SLES gate](RUST-SLES-GATE.md), [NFS qualification](NFS-QUALIFICATION.md) | Production package/systemd instructions and approved endpoint/kernel/storage matrix only as qualification permits. |
| DOC-06 Future adapters, cleanup and repair guides | SC-043–048 | Protocol/design notes above | Keep parked until implementation and evidence establish supported behavior; publish limitations now through this catalog. |

## How to maintain this list

For every development increment:

1. Identify affected scenario IDs before implementation. Add a new stable ID for
   a distinct user situation; do not renumber or reuse IDs.
2. Update behavior, user action and scope when implementation changes. Include
   successful, retryable, review-required and uncertain outcomes as applicable.
3. Link actual passing evidence and record its environment/limits. A failed
   fixture remains a finding, not a supported scenario. Promote Pending only
   after the required gates and relevant fixture checks pass.
4. Update DOC items with missing examples/runbooks or delivered guide links.
   New capabilities should not become invisible documentation obligations.
5. Keep unfinished work in the future-only roadmap. Preserve completed evidence
   here and in increment result documents, without rewriting historical results.

This catalog does not replace requirements or formal Rust traceability. When
L2/L3 derivations and Rust trace discovery land, add their requirement/test links
alongside these user situations.
