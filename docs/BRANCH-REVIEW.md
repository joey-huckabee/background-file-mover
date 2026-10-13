# Outstanding branch review

Reviewed 2026-10-13 after pushing the experiments/direction as `6df3003` on
`feature/rust-transfer-coordinator`. Remote references were refreshed first.
`main` remains `a6efb3d0964f4b5914f918a12876b4d0dc6d4717`. The machine record
[BRANCH-REVIEW-EVIDENCE.json](BRANCH-REVIEW-EVIDENCE.json) preserves full tips,
ancestry, all unique commit subjects/dates, changed paths and diff statistics.
GitHub's all-state PR lookup returned no PRs for this repository at review time.
No branches, tags, lab VMs or deployment resources were removed during the initial
review. C6 was subsequently retired at the user's explicit request; see below.

## Inventory and cleanup recommendation

| Branch | Tip | Ahead / behind main | Relationship | Recommendation |
|---|---|---|---|---|
| c6-daemon-entry-point | 53fabf0 | 0 / 3 | Entire tip is an ancestor of main | Deleted after revalidation; main retains the work |
| c7-dashboard | af7af20 | 2 / 0 | Unmerged; fully contained in integration-lab | Preserve reference/requirements, archive before deleting |
| integration-lab | 3e9226b | 9 / 0 | Contains both dashboard commits and seven additional lab commits | Preserve lab/test findings, archive before deleting |
| feature/rust-transfer-coordinator | Active feature | New work | Experiments and redesign handoff | Keep as the active branch |

Counts are commit ancestry relative to refreshed origin/main, not claims about
passing tests. Unmerged patches have no equivalents in main according to git cherry.
This was a source/history review; old branch suites, CI and lab health were not rerun.

## C6: already retained in main

Exact tip: `53fabf0e457dd8d31ea7364e1f8b3709f7941146`. Its final commit is
the operational event stream. Main includes it and then `c619cad` (close C6/open
C7), `39d07ad` (C6 merge), and `a6efb3d` (predicate wait/gate fix). There are
no unique branch commits or merge-base changes to preserve separately. Refer
to main's daemon lifecycle/event implementation and requirements during redesign.
Deleting this branch reference would remove no unique development work.

**Cleanup completed, 2026-10-13:** re-fetched origin, confirmed the tip still
matched the reviewed full SHA and was an ancestor of origin/main with zero unique
commits, then deleted the remote branch with an exact-tip lease. Pruned its local
remote-tracking reference and verified the remote branch was absent. No local C6
branch existed. Main and both unmerged branches remain intact.

## C7: operator dashboard and status API

Exact tip: `af7af20b51f54f98ce5f6270d1d779fecf0c28cb`.

| Commit | Work |
|---|---|
| 19588e24e6c67adfe57a88601497abf8149d6d12 | Operator dashboard, L2-DASH-001..003 |
| af7af20b51f54f98ce5f6270d1d779fecf0c28cb | Construct embedded page on first use instead of before main |

Seventeen paths changed: 1121 insertions and 43 deletions. Important retained work:

- Embedded offline HTML/CSS/JS served at GET/HEAD `/`, explicit UTF-8 type and no
  runtime asset/CDN dependency. Dynamic data uses textContent/createTextNode.
- `/api/status` adds running/runnable/active state, aggregate state counts and a
  newest-first job list with a router-chosen 50-row response cap.
- Manager status snapshots release the manager lock before store queries; the
  status encoder reports limit/truncation and existing job representations.
- Dashboard artifact and router tests cover escaping/HTML sinks, offline behavior,
  content type, status and method handling. Build/CI add a source safety gate and
  gate self-tests. Trace-matrix/changelog records and integration planning were added.

Primary references at the pinned commit:
[dashboard](https://github.com/joey-huckabee/background-file-mover/blob/af7af20b51f54f98ce5f6270d1d779fecf0c28cb/cpp/src/dashboard.cpp),
[manager status](https://github.com/joey-huckabee/background-file-mover/blob/af7af20b51f54f98ce5f6270d1d779fecf0c28cb/cpp/src/manager.cpp),
[dashboard tests](https://github.com/joey-huckabee/background-file-mover/blob/af7af20b51f54f98ce5f6270d1d779fecf0c28cb/cpp/tests/test_dashboard.cpp),
[integration rationale](https://github.com/joey-huckabee/background-file-mover/blob/af7af20b51f54f98ce5f6270d1d779fecf0c28cb/docs/INTEGRATION-ENVIRONMENT.md).

Carry the offline/security requirements and test scenarios into the Rust API/UI
design, rather than merging C++ implementation solely to rescue its work. Review
before reuse: status loads every state batch and sorts all jobs before truncating,
so the response cap does not bound database/query memory. The truncated flag uses
size >= limit, which cannot distinguish exactly-full from omitted rows. The page
starts a new poll every two seconds without an in-flight guard or request timeout;
slow requests can overlap. Rust status queries and UI polling should be bounded
at their actual admission/allocation boundaries. Historical green CI is recorded
in branch notes and was not independently reverified in this review.

## Integration lab: provisioning, service checks and unfinished confinement

Exact tip: `3e9226b09e737522e8ea404108ee6cf0e5d64c91`. The first two commits
are C7 above. Seven additional commits develop the lab:

| Commit | Work |
|---|---|
| 11b5832 | Hyper-V provisioning and Ansible configuration, phase 1 |
| 0e8a464 | Fetch/verify Rocky ISO and initial resume note |
| c86a0d9 | Control-node installation fixes |
| 1f11db8 | ISO signature verification and false-check correction |
| f2824e1 | Working kickstart ISO generation |
| dcb359f | Rebuildable lab and first-build fixes |
| 3e9226b | Layer 2 end-to-end run and four assertion fixes |

Compared with main, 44 paths changed: 4067 insertions and 43 deletions, including
C7. The inventory includes `integration/` provisioning, Ansible roles/templates,
syntax/layer-separation/signature checks, lifecycle tests, environment/inventory
docs, resume notes, changelog and ignored local secrets/artifacts.

Layer 1 is Windows Hyper-V/PowerShell: pinned Rocky media, SHA256 plus separate
GPG verification, kickstart/OEMDRV ISO creation, VM creation/inspection/removal,
and locally generated credentials. Layer 2 is host-independent SSH/Ansible:
base/build tools, source sync, C++ target build/unit suite, service account,
configuration and systemd install. A separation gate keeps Hyper-V assumptions
out of configure/tests. Existing lifecycle checks cover readiness, health/dashboard,
service identity, hardening, invalid-config refusal and stop duration.

Historical branch notes report a successful Rocky 9.8 layer-2 run, while the
branch README still says layer 2 has not run. Preserve the newer
[resume note](https://github.com/joey-huckabee/background-file-mover/blob/3e9226b09e737522e8ea404108ee6cf0e5d64c91/integration/RESUME-HERE.md)
and [changelog](https://github.com/joey-huckabee/background-file-mover/blob/3e9226b09e737522e8ea404108ee6cf0e5d64c91/CHANGELOG.md)
as historical evidence, and correct the contradictory status when adapting it.
No assertion about a VM still running in that old note was checked this session.

**Important unfinished work:** the service ran as unconfined_service_t with a
generic bin_t binary. An enforcing host and empty AVC log did not demonstrate
service confinement. The lifecycle script can still call that condition a pass.
The branch calls for filemover_t/filemover_exec_t domain transition and file
contexts, a genuinely confined run, and `02-*` actual file movement tests; only
the lifecycle test exists. A short idle stop does not establish active-transfer
draining. Integration CI gating was explicitly still an open decision.

Keep the lessons from fixed platform checks: distribution facts can misidentify
Rocky; SELinux facts need their Python support or direct inspection; synchronize
needs rsync on both ends; successful Ansible make results need not have rc. Also
retain unique scratch directories, IMAPI2FS writing/validation fixes, guarded
credential reuse, stale-key/IP/attached-ISO rebuild diagnostics, and layered media
verification. WSL lockup/tmpfiles notes describe old local versions/settings;
they are troubleshooting history, not current environment facts.

Adapt useful systemd/permission/confinement assertions to Rust and the user's
container-first qualification policy. Hyper-V/Rocky infrastructure is optional
reference work, not a newly required actual-SLES-host test. Preserve deployment
failure scenarios while replacing C++ build/install assumptions. Credentials,
ISOs, VM disks and local inventories must remain outside Git.

## Safe retirement sequence

1. Keep the current feature branch. Preserve this review and the redesign handoff.
2. C6 can be retired once its reviewed tip is reconfirmed as merged into main.
3. Before deleting unmerged references, create and push clearly named archive
   tags at the full reviewed tips, or create a verified durable Git bundle. A SHA
   written in Markdown alone is not a retention guarantee after references vanish.
4. Integration-lab contains the entire dashboard history; its archive preserves
   both. Separate dashboard tagging still makes its milestone easy to locate.
5. Re-fetch and compare tips immediately before deletion, so newer work cannot
   disappear under a stale review. Retire references only after source retention
   and any PR state are reconfirmed. Branch deletion does not tear down lab resources.

No merge or branch deletion is needed to start the new architecture. The next
round begins with [RUST-DIRECTION.md](RUST-DIRECTION.md), and uses this inventory
to decide which requirements/tests to reuse before eventual cleanup.
