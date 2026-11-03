# Local coordinator and bounded cloud fan-out

Established 2026-11-01 in Cloudroom project `proj_yhjr5wn4cn`.
Updated 2026-11-03 with the user's approved small-team workflow. Fan-out means
delegating independent tasks in parallel, then integrating their results. It
does not promise a fixed quality percentage or replace executable validation.

- Local coordinator: thread `thr_grm8wj2gt7`, Codex, with canonical checkout
  `D:\GIT\GIT-GitHub\joey-huckabee\background-file-mover`.
- Existing cloud reviewer: thread `thr_xnjapdndei`, Codex `gpt-6.1-sol`, linked
  to the coordinator. Default to independent read-only review. Any implementation
  assignment must be explicit, already authorized and have exclusive file ownership.
- Development branch: `feature/rust-transfer-coordinator`.
- Linux test clone: Ubuntu WSL2 at
  `/home/joey/GIT/background-file-mover-testing`. The older
  `/home/joey/GIT/background-file-mover` checkout is preserved separately.

The coordinator owns integration and local validation. Cloud work starts from
pushed GitHub commits; uncommitted Windows changes do not arrive there. Commit
and push delegated inputs first, using `git pull --rebase` before every push.
Cloud work returns on its own branch; review and integrate explicitly without
overwriting concurrent local work. Resume the existing child with `room-cli
thread tell thr_xnjapdndei` and a concrete task. When the bundled PowerShell
launcher returns no output, invoke its adjacent `room-cli` script through Node.

## Team size and responsibility

Use a coordinator and independent reviewer for substantial work. Add one
temporary specialist only when a useful task can proceed independently. The
normal maximum is three active agents including the coordinator, with one
delegation level. Do not create a permanent specialist or duplicate every task.
Small fixes and straightforward documentation edits can stay with the coordinator.

| Role | Location | Ownership |
|---|---|---|
| Coordinator / implementer | Canonical Windows checkout and WSL2 test clone | Break down approved work, implement/integrate, resolve findings, own validation and delivery. Only the coordinator integrates into the development branch and reports release readiness. |
| Independent reviewer | Existing cloud child | Check approved requirements, actual diff and failure paths. Prioritize custody, integrity, recovery, deletion, schema and authentication changes. Report concrete defects, test gaps or unsupported claims; no requirement to find an issue. |
| Specialist, when useful | Separate cloud thread/branch | Audit documentation, investigate a bounded test gap or implement an independent approved component with assigned files. Return findings or commits to the coordinator. |

Use Cloudroom's `room-cli` for child management; do not launch agent CLIs or
untracked harness subagents. Start additional children only for the assigned
bounded work, from pushed inputs at an explicit base branch/commit. Leave
unrelated threads alone. Do not start agents merely to occupy available slots.

## Delegation and integration

Every assignment must include:

- Exact base commit, task objective and relevant approved requirements/decisions.
- Read-only versus implementation authority and the permitted files. Assign
  exclusive write ownership; agents must not concurrently edit the same files.
- Expected deliverable: findings or a branch/commit, with path/line references,
  actual checks/results, tests not run, assumptions and blockers.
- Bounded effort and a stopping condition. Return a useful result after one
  review pass; further review needs a changed diff, unresolved finding or new evidence.

Reviewers should assess the requirements and evidence independently, rather
than receive instructions to endorse the implementation. Findings should include
severity and a concrete failure example or reproduction where possible.
"No actionable findings" is valid; repeated approval-only rounds are not useful.

Cloud implementations use their own branches/checkouts. The coordinator reviews
and integrates them explicitly, preserving other work. Resolve integration
conflicts against the approved behavior; do not let an agent silently change
product scope or substitute its own approval for the user's decision. Routine
engineering choices remain autonomous within the already authorized task.

For example, an offline-bundle increment can split into coordinator-owned
packaging implementation, a reviewer checking state/overwrite safety, and an
optional specialist auditing disconnected-use instructions and prerequisites.
These are distinct assignments, not three agents independently rewriting packaging.

## Review and validation order

1. Identify independent work and assign only the useful pieces. Keep tightly
   dependent steps with their owner rather than splitting them artificially.
2. Run appropriate focused checks and request independent review for substantial
   changes, especially custody/integrity/deletion/authentication/schema/recovery.
   Review before long validation where practical so defects are caught early.
3. Address findings and review material changes to the affected diff. Freeze the
   integrated code and test inputs before the required full gate runs.
4. Use one coordinator-managed WSL build queue: one heavy build/test suite at a
   time, with production and qualification gates sequential. Cloud ARM64 review
   or portable tests cannot replace x86_64 GNU/glibc-2.22 ELF audits and SLES tests.
5. Documentation audits or other independent work can continue while gates run.
   A later relevant source/tooling change requires the applicable fresh validation;
   a passing run of an older snapshot does not validate the changed source.
6. Record exact commits, artifacts, actual results and limits before delivery.
   No agent may waive gates, enable production NFS/deletion or move operational
   state/custody merely because another agent approved a diff.

Fan-out can overlap reviews and independent work; it does not shorten a single
SLES test's required runtime or justify duplicate heavy builds on the same host.

## Evaluate whether fan-out helps

For substantial increments, keep a short note with the task roles, concrete
defects caught before delivery, rework/validation reruns, elapsed delivery time
and token/cloud cost where observable. Unknown cost stays unknown. Compare
similar work over several increments; do not treat different task sizes or a
single anecdote as proof of a 15% improvement. Keep the specialist only when its
contribution justifies the coordination/cost. This is a workflow check, not a
new benchmark project or an approval step for routine work.

## Current implementation boundaries

Current planning artifact: [consolidated REST proposal](REST-CONTRACT-PROPOSAL.md).
The coordinator owns the draft and integration; the cloud child reviews contract
consistency. Groups 1-50 remain approved; unsettled API implementation awaits
remaining decisions. Separately authorized work includes bounded offline history
clear and the build/packaging increments [107](RUST-INCREMENT-107.md),
[108](RUST-INCREMENT-108.md) and [109](RUST-INCREMENT-109.md). This agent workflow
does not expand their scope or approve the remaining API/deployment contract.

For P01 schema work, see the [candidate bundle](api/README.md). Cloud review
is read-only; local artifact validation uses existing WSL Python/jsonschema and
OpenSSL without a Rust build or operational-state access. The Linux-native
checkout still advances only from committed coordinator work.

## Synchronizing Linux tests

The WSL test clone has `coordinator` pointing to the D: checkout via
`/mnt/d/GIT/GIT-GitHub/joey-huckabee/background-file-mover`, and `origin` pointing
to GitHub. It tests committed coordinator changes. Before each run, verify the
test clone has no local edits, then run inside Ubuntu:

```sh
cd /home/joey/GIT/background-file-mover-testing
git status --short
git fetch coordinator
git merge --ff-only coordinator/feature/rust-transfer-coordinator
git rev-parse HEAD
python3 scripts/check-rust-sles.py
python3 scripts/check-rust-sles.py --qualification
```

Stop and inspect if local edits exist or fast-forward fails. Do not reset the
clone or discard evidence to force synchronization. Keep compilation and test
artifacts on Linux-native storage. Gate results live under ignored
`rust/validation/` in the test clone; preserve raw packs separately as needed.

## Verified setup and remaining limits

Initial setup readiness: x86_64 Ubuntu 24.04 on WSL2, Python 3.12.3, native rootless
Podman 5.8.2 responding to `podman info`, and both digest-pinned builder/runtime
images present. The gate's help command runs. No Rust build/test or SLES gate
was run for this agent setup; cached images alone do not establish a gate pass.
For the subsequent Cargo-libc builder change and fresh gate results, see
[the migration record](CARGO-LIBC-MIGRATION.md).

Cloud readiness: Debian 12 on ARM64, Python 3.11.2, Git 2.56.0; Podman/Docker
absent and x86_64 execution unavailable/unverified. Required SLES gates are
blocked there. Local production and retained qualification gates remain required
for Rust changes. NFS/systemd labs require their separately documented selected
prerequisites; readiness does not qualify those labs.

Read `REST-CONTRACT-HANDOFF.md` and `WORKSTATION-HANDOFF.md` before development.
Group 50 replaces post-clear owner retention: clear forgets all source/destination
linkage, accounting/inventory and results while leaving files. Files then leave
mover management; all file effects must already be safely stopped/settled.
Group 49 adds reviewed-state retry context in a header (API-E129/SC-180),
with job_ids-only body and exact-command replay preserved. Concrete header encoding/bounds are in the
[wire candidate](api/RETRY-HEADER.candidate.md); outcome/transactional receipt
design remains pending, with no runtime implementation.
Groups 1-50 are approved, including retry attempt counts, browser session
cookies, global manual admin sign-out and login/session/logout response statuses. Transfers belong to the mover service
and run independently of dashboard credentials/sessions. Remaining wire/login
details and implementation/qualification are pending. All eight
release gates remain open. Agent setup authorizes no REST implementation,
production NFS/source deletion, or movement of operational state/custody.
