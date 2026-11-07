# Moving development to another computer

Current P01 review artifact: [consolidated contract proposal](REST-CONTRACT-PROPOSAL.md), with four remaining decision packages. Groups 1-52 are the approved baseline; [group-52 compatibility](api/COMPATIBILITY.md) settles policy while exact migration/rollback support and qualification remain pending.

Recorded 2026-11-01. Branch: `feature/rust-transfer-coordinator`.
Baseline before this handoff: `686e15c` (groups 1-44). This document is a durable
entry point for a new developer/agent without the previous chat. It does not
approve implementation before the remaining contract is settled, or authorize
moving a running mover's operational state to another host.

The [candidate contract bundle](api/README.md) contains the next concrete P01
artifacts and validation limits. Its schemas/fixtures are reviewable proposals;
the original 128 API/179 SC IDs retain their status; group 49 adds the approved
retry context header (API-E129/SC-180), with implementation/qualification pending.

## What is in Git, and where to read it

The roadmap deliberately contains future work only. Decisions, historical
verification and limitations are kept in linked documents, not agent memory.
Use these sources together; the roadmap alone is not the whole specification.

| Subject | Durable source | How to use it |
|---|---|---|
| Immediate next contract question and accepted decisions | [REST contract handoff](REST-CONTRACT-HANDOFF.md) | Read first. Resume the discussion, not another NFS experiment. |
| Future work | [Roadmap](ROADMAP.md) | Remove completed tasks; keep history elsewhere. |
| First-release scope and eight open gates | [First release](RUST-FIRST-RELEASE.md) | No release/production approval yet. |
| Bounded verification and implementation order | [Release closure](RUST-RELEASE-CLOSURE.md) | RC-01-24, P01-12 and D01-05 are the scheduler. |
| Exact approved versus pending REST behavior | [Error/acceptance review](REST-ERROR-SCENARIOS.md), [API draft](REST-API-DRAFT.md) | Groups 1-50 approved; remaining details not frozen. Old draft examples are not automatically the new wire contract. |
| User situations and documentation backlog | [Scenario catalog](RUST-SCENARIOS.md) | 189 SC IDs, six DOC IDs; pending cases are not passing tests. |
| Architecture/provenance | [Rust direction](RUST-DIRECTION.md), [conversation input](../CONVERSATION.md), [transfer protocol](TRANSFER-PROTOCOL.md), [integrity](INTEGRITY-DESIGN.md) | Later explicit decisions supersede historical proposals. |
| Historical results and design increments | RUST-INCREMENT-01 through RUST-INCREMENT-106 under docs/, [changelog](../CHANGELOG.md) | Increment 105 bounds closure; 106 records the continuing contract review. |
| ABI/userspace qualification | [Mandatory SLES gate](RUST-SLES-GATE.md), [platform pins](../scripts/rust-platform.json) | Both production and qualification modes required. |
| NFS/systemd procedures and limits | [NFS qualification](NFS-QUALIFICATION.md), [systemd lab](SYSTEMD-LIFECYCLE-LAB.md), [testing limitations](TESTING-LIMITATIONS.md) | Follow each selected lab's exact prerequisites, scope and cleanup. |
| Ownership, runtime operations and capacity | [Ownership contract](NFS-OWNERSHIP-FENCING-CONTRACT.md), [operator guide](RUST-OPERATOR-GUIDE.md), [retry policy](DELIVERY-RETRY-POLICY.md), [source-space design](SOURCE-SPACE-ADMISSION-DESIGN.md) | Same-host local state/fencing, default-60-second configurable shutdown, existing review/retry and default-off admission rules. |
| Remote producer boundary and deferred repair | [Producer access contract](REMOTE-API-ACCESS-CONTRACT.md), [retention/repair design](RETENTION-REPAIR-DESIGN.md) | Producer certificate proposal is separate from the later username/password admin decision; enrollment/repair are deferred. |
| Source/evidence portability inventory | [Evidence inventory](WORKSTATION-EVIDENCE-INVENTORY.json) | Historical report hashes plus the two latest local gate source/artifact hashes. |

## Exact stopping point; no chat memory required

2026-11-03 approval: group 51 closes the specific retry/deletion defaults in
[the short admin table](api/ADMIN-REPLAY.candidate.md#short-closeout-table), recorded
as API-E133-138/SC-184-189. Do not reopen those defaults or infer broader wire,
security/compatibility approval, P01 freeze or runtime implementation authority.
The current inventory is 138 API and 189 SC IDs, with six DOC IDs unchanged.

The user's later direct instruction authorizes bounded group-50 implementation.
[Increment 107](RUST-INCREMENT-107.md) describes the guarded offline completed-job
clear and its current actual validation. It preserves source/destination files,
refuses a live daemon/surviving epoch and opens only existing schema-11 state.
No HTTP admin/authentication or cancellation lifecycle is implemented by it.
The broad earlier implementation hold remains for other unsettled contract work.

We are in P01/API-I01, agreeing the REST contract before versioned OpenAPI and
related implementation. All eight release gates remain open. The saved
contract decisions now include groups 49-50 as recorded above and in the REST
handoff. The earlier group-48 checkpoint (2026-11-01), API-E125-128/SC-176-179:

- Successful login: 200 OK with session cookie.
- Incorrect credentials: 401 Unauthorized, "Invalid username or password."
- Missing/expired session: 401 Unauthorized, require sign-in.
- Successful manual sign-out: 204 No Content after all-session invalidation.

Exact routes, login request fields, response body schemas, cookie attributes
and remaining replay/concurrency details are still pending.

The preceding group 45 retry response is also approved:

```json
{
  "accepted_count": 1,
  "failed_count": 1,
  "skipped_count": 0
}
```

Both cancellation (group 44) and failed-work retry (group 45) use HTTP 202
with these three count fields. Retry counts describe attempts, not successful
transfers. **The user approved the retry response shape on 2026-11-01.**
Browser session-cookie login is approved in group 46; global manual sign-out
is approved in group 47. Group 48 resolves the four response statuses above.
Next consolidate exact routes, request/response schemas and replay decisions.
No runtime implementation is authorized yet.

Accepted admin behavior to preserve:

- One account, username/password; setup and password changes on the mover host.
  Remote dashboard access required. SSO, advanced account management and
  registration are deferred. Ordinary HTTPS/password/session implementation
  details remain; browser session cookies are approved in group 46. Group 48
  approves login 200/cookie, incorrect-credentials 401/shared message and
  missing/expired-session 401 requiring sign-in.
- Manual sign-out, password changes and restart invalidate every admin session.
  Successful manual sign-out returns 204 No Content after global invalidation.
  Configurable inactivity timeout defaults to 30 minutes. The mover service owns
  transfers independently of dashboard credentials/sessions; dashboard
  authentication events do not pause/cancel/restart transfers. Jobs recover normally after a
  mover restart.
- All four actions have separate endpoints with `{"job_ids":[42,43]}` bodies.
  Existing job_id and stored state govern eligibility; no extra identifier
  scheme. Credentials are separate from action JSON. Exact endpoint paths and
  methods are not approved yet.
- Cancel: simple confirmation showing selected jobs, no explanation; request
  cancellation only for unfinished work. Skip completed/already-cancelled jobs
  without reasons. Accepted request returns 202; show Cancellation pending until
  actual safe stop/effect settlement, then Cancelled. Cancellation is final for
  this release. Preserve files; no automatic restore/delete/history clear.
- Retry: eligible failed work only, no confirmation; 202 means accepted, not
  success. Show actual progress. Preserve original custody and existing audited
  review/reset prerequisites. Cancelled jobs cannot be revived.
- History clear: confirm selected jobs and explain UUID forgetting/file
  preservation. Only completed/safely-cancelled jobs; never auto-cancel. Skip
  ineligible jobs without reasons. Finished clear returns 200 and actual count.
  Group 50 removes every source/destination linkage, ownership/accounting and
  action result along with history/UUID recognition. Leave files in place and
  outside mover management; finish any desired mover deletion before clear. A cleared UUID later submitted is new work.
- Manual deletion: separate explicit confirmation, only mover-owned retained
  source/unfinished destination after safe stop. Protect unclaimed originals
  and completed recordings/manifests. Works with automatic cleanup off. Return
  202, show deleted/failed file counts, best effort. No automatic retries or
  special recovery workflow. Runtime production deletion remains disabled.
- Missing IDs are silently skipped for selected actions, including cleared jobs;
  no post-clear file ownership/inventory or reconstruction remains. This does not change separate
  single-resource/local-operator 404 mappings or hide storage errors.
- Process duplicate entries again. Do not deduplicate or predict cancellation
  state in the batch layer. Per-job operation decides; duplicate cancel counts
  as a failed cancel attempt, not failed transfer state. Group 44 adds skipped
  count but does not require per-entry reasons.

Accepted producer behavior is fully recorded in the contract handoff/review:
generator identity, mover-visible full source directory, explicit relative file
names, required global UUID recording_id, order-independent same-body replay,
optional all-or-nothing expected-size map, destination from startup config and
whole-set durable 202. Source paths may be reused only after confirmed handoff.
Default-disabled expected-size checking ignores a complete supplied map; current
startup setting applies to unfinished work, with no per-job policy snapshot.
Actual size/custody/hash verification always remains. Safely cancelled before
durable handoff returns 409 recording_cancelled/false; completed handoff preserves
202 replay even after cancellation/lost response, without reviving delivery.

Remaining work includes exact schema/config bounds and UUID canonicalization,
state/global-ID migration or safe refusal, validation precedence, action replay/
concurrency/transaction handling, login/logout/session wire, final manifest and
supported route inventory. Do not turn these into an unbounded series of new
requirements. Use API-I01-06 and P01-12 to finish the finite release contract.
No one uses the Rust prototype producer API, so replace it directly without an
old-wire adapter; preserve persisted custody and separate C++ cutover obligations.

## What is implemented versus merely agreed

Rust lives in rust/: mover-core, mover-store, mover-fs and file-mover. It is a
durable coordinator, not a C++-shaped port. Existing work includes SQLite state,
protected claiming, copy/hash/verify/publication/manifest delivery, supervision,
local ownership/lifetime guards, stop/status, retry/review and default-off source
space admission. Normal copy hashes source while copying and rereads destination
staging for verification: 3N logical data I/O. One service executable has internal
worker modes; test harness executables are not separately deployed services.

The runtime remains a trusted loopback/local prototype with production NFS and
source deletion disabled. New producer/admin/dashboard/login contracts are not
implemented by the documentation review. Current missing-file response is still
503, despite approved 409 behavior. Current producer wire/ID/order behavior also
predates the approved replacement. Do not report the design as shipped support.
Retain the opt-in NFS qualification capability permanently. Dependency experiments
stopped after E1-E5; do not start E6. Registration, S3, cross-host takeover and
offline repair remain deferred. Default-off safe cleanup is still a first-release
deliverable. The specific admin workflows are user requirements, despite earlier
general dashboard deferral; release scope must explicitly account for them.

## Git-preserved evidence and local-only artifacts

The audited baseline has 205 tracked docs/*EVIDENCE*.json reports (about 186 MB
combined), including failed, retained-failed, blocked and input/provenance reports.
They are not 205 passing suites. Their filenames, byte hashes, sizes and recorded
top-level statuses are in the inventory. Preserve failed acquisitions and their
limits, not just the latest passing report. Increment and lab docs link actual
cases, mechanisms, sources and limitations; do not infer universal coverage.

The raw rust/validation/ tree is ignored by rust/.gitignore and has no tracked
files. There are 436 local run directories at this checkpoint. They contain
source archives, exact ELF/test artifacts, logs/captures and fixture evidence.
They do **not** arrive in a Git clone; neither do Podman images/volumes, Rust/
Cargo caches, WSL distributions or GitHub credentials. The inventory lists run
directory names for locating/copying evidence, not proof that every directory is
a complete passed run. This handoff does not upload raw packs or caches.

The two retained latest SLES reports are:

| Mode | Run ID | Tests passed in each of debug/release | Audited binaries total |
|---|---|---|---|
| Production | 20261022T182946Z-dfe48216 | 211 | 20 |
| Qualification | 20261022T182945Z-5f06a0b5-nfs-qualification | 213 | 20 |

Both source archives have SHA-256
`0302461ffa27e63c1c4aeb490f238ee51f4eabfa8b1f6c9171aa6a6a5e846f52`.
On 2026-11-01 both archive hashes and all 62 archived rust/ files matched current
bytes; all 40 local binaries matched recorded artifact hashes. The inventory
records per-file/per-artifact hashes. These are source/artifact integrity checks,
not a new build/test, a cloud-host pass or a production qualification.

Before discarding this workstation, preserve rust/validation/ separately if you
need the historical raw proof. Copy/archive it with relative paths and verify
checksums at the destination; use private storage, not an unreviewed public dump.
No transfer destination or artifact-storage service has been selected here.
GitHub contains the tracked reports and procedures, not the ignored raw tree.
For development on a fresh machine, rerun gates to produce fresh usable artifact
packs. Reruns cannot recreate historical failure captures; keep the old packs
when historical auditability is needed. Do not manufacture old run directories
from a new build or edit a report to pretend the old binary was transferred.

## Resume on the cloud computer

1. Clone the repository with your own GitHub access and select the feature branch:

   ```sh
   git clone --branch feature/rust-transfer-coordinator https://github.com/joey-huckabee/background-file-mover.git
   cd background-file-mover
   git status --short
   git log -1 --oneline
   ```

   If already cloned, preserve local changes, fetch origin and select the branch;
   do not hard-reset a checkout with work. The handoff commit follows 686e15c.
2. Read this document, REST-CONTRACT-HANDOFF.md and AGENTS.md, followed by the
   roadmap/release matrix and the contract/scenario sections you are changing.
   You can resume the contract discussion without Docker/Podman or Rust builds.
3. For future verification, provision Python 3.11+, Git and a working Linux
   Podman engine. The cloud target should provide x86_64 Linux/container capability;
   Windows+WSL2 is the historical setup, not a required cloud OS. Check:

   ```sh
   python3 --version
   podman --version
   podman info
   podman system connection list
   ```

   Review available privileges/kernel features and disk capacity. Do not assume
   an unprivileged cloud/container sandbox can run NFS or nested systemd labs.
   A missing capability is a blocked fixture prerequisite, not reason to bypass
   the test or enable production support. Configure connections deliberately;
   podman-machine-default-root is the old workstation's fixture default, not a
   portable identity. The drivers expose --connection where documented.
4. Pinned builder/runtime images and Rust/Zig/cargo-zigbuild versions live in
   scripts/rust-platform.json. Cargo.lock and the controlled dependency manifests
   are tracked. Provision the pinned images/toolchain/locked sources with the
   gate; do not substitute current latest versions. Network may be needed for
   provisioning, while application builds remain locked/offline. No MUSL.
5. Every Rust build/test uses the mandatory gate, from the repo root:

   ```sh
   python3 scripts/check-rust-sles.py
   python3 scripts/check-rust-sles.py --qualification
   ```

   Windows can use python instead; scripts/test-rust-wsl.sh invokes the same gate
   from WSL. These run debug/release Cargo-libc builds, ELF audit and exact-target tests
   under pinned SLES 12 SP5 userspace with glibc 2.22. Host-only cargo tests are
   insufficient. Rust 1.99.0 and cargo-libc 0.2.4 are the current pins; see
   [the builder migration](CARGO-LIBC-MIGRATION.md). Historical reports/inventory
   retain their original ZigBuild inputs. Get actual new run directories from
   gate output, not old IDs.
6. For NFS/systemd work, choose a named finite RC/P package first. Follow its
   step-by-step lab with the exact passing gate artifacts, both modes as required,
   source/fixture input checks and owned-resource cleanup. Do not launch the
   entire historical matrix automatically. scripts/check-nfs-boundaries.py and
   scripts/check-systemd-boundaries.py plus specialist runners are retained.
   Their help/selected lab documents give actual selectors; ABI tests do not
   substitute for fault/lifecycle qualification.
7. The systemd-228 host-cgroup bootstrap approval was specifically for the old
   disposable Podman VM. The lab explicitly says not to infer approval for other
   machines/hierarchies. Do unaffected planning and private preflight first;
   obtain any required new-host authorization before broader host mutations.
   Never attach unknown hierarchies or move unrelated processes. Restore NFS
   before normal unmount; retain owned fixtures if teardown is uncertain.
8. Keep the branch, update scenarios/user-doc backlog alongside each increment,
   preserve evidence provenance, run appropriate checks and push. Do not rely on
   this chat being available on the new machine. Required references and unknowns
   are written down; future findings must also go into version control.

## Verification boundaries and machine-state distinction

Container compatibility is x86_64 GNU/glibc 2.22 with the standard Linux loader,
not a real SLES kernel/old CPU/NAS qualification. No real SLES installation is
required. Shared-kernel, systemd-228-equivalent versus vendor-maintenance,
physical disk/power durability, actual mount/export/account and cloud privileges
remain explicit limitations in TESTING-LIMITATIONS.md and D01-05. Controlled NFSD
or quiesced-container restart is not abrupt NAS/power-loss proof. A syscall or
clean fsync with no observed eligible RPC is not reply-withholding capability.
Local guard/process exit does not prove remote RPC settlement.

The service's supported ownership contract is one mover restarting on the same
host/account/config/local state, with protected source/destination NFS areas.
Moving the *development checkout* to the cloud is not permission to move an
active service database/WAL, enrollment, worker epochs or custody there, restore
stale state, rebind roots or run a second mover. Those require their own qualified
cutover/fencing design. No operational state or credentials are copied by this
handoff. This audit has not inventoried live Podman/WSL/OS processes or mounted
fixtures; it cannot certify the old machine is safe to discard/shut down.

The GitHub workflow .github/workflows/rust-ci.yml is tracked; a local gate pass
is not evidence of a successful remote CI run. Its current Rust path filters do
not run the gate for a documentation-only handoff. Retain CI/evidence-retention
closure under P10; do not infer missing raw-pack upload from a green workflow.

## Migration audit performed

This handoff adds no runtime implementation or dependency. Checks cover the
tracked report inventory/hashes, retained SLES archive/source/binary identity,
links/JSON/examples, stable 121 API/172 SC/six DOC identifiers and staged whitespace.
No Rust build/test or NFS/systemd fixture was run for this migration audit.
At the migration audit, retry accepted/failed/skipped counts were still pending.
Group 45 subsequently approved them on 2026-11-01; group 46 then approved
browser session-cookie sign-in. Group 47 approves global manual sign-out and
clarifies transfer independence from dashboard credentials. Group 48 approves
the four login/session/logout response statuses. Other wire/schema decisions
remain unsettled and implementation/qualification is pending.
