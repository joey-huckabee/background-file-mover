# Restart and shutdown recovery runbook

Updated 2026-11-03. Use this guide for the Rust mover, with the same host,
service account, configuration and original local database. It consolidates the
known restart scenarios; it does not claim every failure combination is tested.
Production NFS, source deletion and automatic cleanup remain disabled. All eight
release gates remain open. No runtime behavior changes accompany this guide.

## What restart does

Restart requests shutdown and then a new start. It does **not** promise to finish
every active move before stopping. Shutdown stops admission/dispatch, requests
worker termination and waits for actual exit. An interrupted copy may require a
new attempt; byte-offset resume is not promised.

Workers perform assigned filesystem steps. The coordinator validates their
replies and writes SQLite transitions. An orphan worker cannot write completion
to the database or independently run all remaining copy/verify/publish steps.
It may finish an already issued step before discovering the broken channel and
exiting; blocked kernel I/O can delay exit. A new coordinator does not reconnect
to or adopt it. Original-state recovery reconciles effects whose replies were lost.

The mover's shutdown budget defaults to 60 seconds, configurable from 1 to 3600.
It bounds the local stop wait, not kernel I/O. Systemd's `TimeoutStopSec`, kill
policy and restart policy are separate. Inspect the installed unit; do not assume
the application budget controls systemd. The disposable Rust fixture uses
`KillMode=control-group` and `SendSIGKILL=no`. It is not a shipping unit.

## Before a planned restart

1. Record the original configuration path, configured `state_database`, service
   account and installed unit name. Keep state, SQLite recovery files, enrollment,
   lifetime records, claimed sources and staging together. A live file copy is
   not a qualified backup/restore procedure.
2. Check local status and the affected jobs using the
   [operator guide](RUST-OPERATOR-GUIDE.md#inspect-a-job). If interruption is
   undesirable, wait for committed jobs before requesting restart. A health
   response alone does not establish delivery completion.
3. Stop/start through the owner that launched the service: systemd for a managed
   unit, the local controller and original launch procedure for a manual daemon.
   Do not launch a manual competitor beside a systemd-managed instance.
4. After startup, verify mover readiness and original-job recovery. A new PID,
   systemd `active`, `MainPID=0`, or a successful control-command exit alone does
   not establish the required worker-exit or transfer-completion facts.

For a systemd-managed installation, an authorized administrator uses the actual
installed unit name, for example:

```sh
systemctl restart file-mover.service
```

Then perform the status, journal and job checks below even if the command
returns zero. If it times out or work remains blocked, use **Blocked stop or
restart**. For a manual daemon, request `file-mover --stop CONFIG.json`, confirm
old exit, then use the original manual launch command with the same configuration.
Do not use `--clear-history` as part of routine restart.

## Select the scenario

Evidence means the linked implementation or historical test scope, not a new
qualification of today's binary. Pending cases have handling limits rather than
an invented repair command. Transfer phases are covered in the next table.

| Situation and what you see | How to handle it | Evidence or limit |
|---|---|---|
| Planned restart while idle or after jobs commit | Request restart normally. Verify readiness and existing job IDs afterward. Restart does not clear history or remove retained files. | Local lifecycle: [43](RUST-INCREMENT-43.md); committed-state recovery: [06](RUST-INCREMENT-06.md). |
| Planned restart while transfers are active and storage responds | Allow shutdown to interrupt work and wait for worker exit. Start with original state; monitor the same jobs. Preserve old partials and capacity for another attempt. | SC-018/030; [13](RUST-INCREMENT-13.md), [43](RUST-INCREMENT-43.md). |
| `Draining` during stop/restart | Let the original shutdown proceed. Observe with `--status`; repeated stop/signal requests do not reset the loaded deadline. A stop request is not job cancellation. | SC-093; [43](RUST-INCREMENT-43.md), [51](RUST-INCREMENT-51.md). |
| `ShutdownIncomplete`, or systemd stop times out | Treat shutdown as incomplete even if a systemd command returned zero. Follow **Blocked stop or restart** below. Do not clear history or start a competing mover. | Selected real blocked workers: [45](RUST-INCREMENT-45.md), [60](RUST-INCREMENT-60.md), [61](RUST-INCREMENT-61.md). |
| Coordinator crashes/exits, but a worker survives; `OwnerUnavailable` or ownership refusal | Inspect the recorded process group using **Find the old workers**. Restore storage if needed and wait for old processes/threads to exit. No reconnect/adopt/force-unlock exists. | SC-031/062/092; lifetime fix [47](RUST-INCREMENT-47.md). |
| Repeated systemd starts fail, listener is occupied, or the unit reaches a start limit | Stop repeating starts. Check local ownership, listener/service identity and journal. After old exit and correction, use authorized `reset-failed`/`start` only if needed. A bind failure may occur before the ownership check. | [59](RUST-INCREMENT-59.md), [61](RUST-INCREMENT-61.md). Rate-limit saturation was not established by the selected NFS restart cases. |
| Source unavailable during bootstrap; `Starting` and no readiness | Restore the original approved source/mount. Bootstrap may remain blocked; use local status/stop rather than HTTP. If the coordinator exits, confirm bootstrap-worker exit before starting again. | SC-029; [15](RUST-INCREMENT-15.md), [48](RUST-INCREMENT-48.md), [49](RUST-INCREMENT-49.md), [56](RUST-INCREMENT-56.md). |
| Destination unavailable at startup, but source/bootstrap is healthy | Control-plane readiness can succeed while delivery waits. Restore the approved destination and inspect the same jobs; a restart alone does not fix storage. Do not equate HTTP 202 or Running with completed delivery. | SC-013/096; controlled [62](RUST-INCREMENT-62.md). |
| Source, destination or both fail during a transfer | Preserve custody and staging. Restore the original storage scope; if shutdown was requested, wait for old exit before replacement. Do not substitute a different mount/export with similar paths. | Selected independent/both-root cases [52](RUST-INCREMENT-52.md), [54](RUST-INCREMENT-54.md), [55](RUST-INCREMENT-55.md); remaining directions/settlement are not universally qualified. |
| Existing retry/backoff or `ReviewRequired` persists after restart | Read the recorded failure, count and deadline. Correct the cause and use the matching audited resume or missing-file reset procedure when eligible. Restart does not reset review, deadlines or attempt limits. | SC-009/024/026; [operator actions](RUST-OPERATOR-GUIDE.md#resume-reviewed-delivery), [retry policy](DELIVERY-RETRY-POLICY.md). |
| Invalid config, wrong account, unsafe database/sidecar/lifetime file, or unreadable local control | Keep the original state and capture the exact diagnostic. Correct the known configuration/provisioning problem under the approved account. Do not delete WAL, locks, epochs or create replacement state. An IPC error alone does not prove an orphan exists. | SC-095; [44](RUST-INCREMENT-44.md), [47](RUST-INCREMENT-47.md). |
| Root marker, enrollment, destination policy or filesystem identity no longer matches | Leave refused work stopped/reviewed. Investigate the original mount/binding and restore only its authorized scope. Do not reinitialize, edit receipts or rebind populated state. | SC-058-065; [23](RUST-INCREMENT-23.md), [24](RUST-INCREMENT-24.md), [27](RUST-INCREMENT-27.md). |
| Crash leaves valid SQLite WAL/recovery files | After confirmed old exit, use normal startup with the original database and sidecars; SQLite performs its normal recovery. Corrupt/foreign state stays refused; no general database repair is supplied. | SC-033/095; retained-WAL [44](RUST-INCREMENT-44.md). |
| Upgrade or attempted downgrade | Stop old binaries and all workers first. The schema-12 foundation binary accepts legacy jobs in its supported target layout; existing schema 11 returns MigrationRequired and UUID-bearing target state returns UnsupportedIdentity before payload bootstrap. The usable upgrader is not available yet; keep the original compatible binary/state. Old executables do not gain this check retroactively. Do not mix worker protocols or restore a stale database to force rollback. Deployment/cutover and reverse migration remain unqualified; see [increment 111](RUST-INCREMENT-111.md). | SC-033/063; [33](RUST-INCREMENT-33.md), [47](RUST-INCREMENT-47.md), [release gaps](RUST-RELEASE-CLOSURE.md). |
| First initialization was interrupted | Preserve any created receipt/database and inspect the exact stage. Matching activated enrollment restarts normally; created-but-unactivated or inconsistent state is not permission to repair/reinitialize. Use the documented enrollment diagnosis; stop on uncertainty. | SC-065; [27](RUST-INCREMENT-27.md), [28](RUST-INCREMENT-28.md), [29](RUST-INCREMENT-29.md). |
| Host reboot, power loss, or NAS restart | Preserve persistent original state, mount identity and receipts. Inspect storage and service diagnostics before recovery; host reboot removes local workers but does not prove remote RPC settlement or disk durability. Do not clear epochs or initialize fresh state to make startup pass. If continuity/effects cannot be established, keep the scope stopped and seek review. | Physical power-loss, arbitrary NAS restart and full deployment persistence are **not qualified**; [testing limits](TESTING-LIMITATIONS.md), SC-094. |
| Old local workers are gone, but remote effects/ownership remain uncertain | Do not infer safety from `NoActiveOwner` alone. Retain evidence and keep uncertain work stopped/reviewed; no general delayed-RPC settlement or cross-host takeover procedure is supplied. | SC-094 and SH-10-12 remain pending; [ownership contract](NFS-OWNERSHIP-FENCING-CONTRACT.md). |
| Offline clear/initialization/single-file command holds the instance | Wait for that command and its associated threads/workers to finish. It may have no daemon controller, so `OwnerUnavailable` is possible. Do not use systemd restart as a force-unlock. | Shared guard [42](RUST-INCREMENT-42.md), offline clear [107](RUST-INCREMENT-107.md). |
| A committed job was explicitly cleared before restart | Its files remain unmanaged and its old job/replay records stay forgotten. Restart does not scan/adopt them. A repeated submission is new work under current identity/no-clobber rules. | Group 50, SC-181-183; bounded offline implementation [107](RUST-INCREMENT-107.md). |

## Identify the interrupted transfer phase

Use durable job status; file visibility alone is insufficient. If a worker is
still alive, handle its lifetime first. These actions do not authorize manual
filesystem edits or repair.

| Interrupted phase | What restart can encounter | User action and recovery boundary |
|---|---|---|
| Claiming, before the recorder received whole-set HTTP 202 | Some files may already be private while other claims remain pending. A lost reply does not mean nothing happened. | Recorder retries the identical ID/body and keeps unreleased paths/parents unchanged until confirmed 202. Preserve existing claims; do not recreate already claimed files. See [103](RUST-INCREMENT-103.md), [104](RUST-INCREMENT-104.md). |
| Partial or unreceipted copy | An uncertain partial can remain; recovery may allocate a new attempt rather than resume at its byte offset. | Retain old partial/source evidence and provide capacity for a fresh attempt. Inspect status; do not delete staging to free space blindly. SC-018. |
| Copied or verifying | All bytes being present does not establish a verified destination. | Let normal recovery revalidate the stored phase and complete required digest checks. Do not publish/consume staging. [19](RUST-INCREMENT-19.md), [89](RUST-INCREMENT-89.md). |
| Payload publication/link/unlink/synchronization | A final name, a staging alias or both can exist without a saved completion receipt. | Let original-state recovery reconcile only the owned identities and integrity evidence. Do not overwrite a collision or remove aliases yourself. [50](RUST-INCREMENT-50.md), [63](RUST-INCREMENT-63.md), [65](RUST-INCREMENT-65.md). |
| Manifest publication or local commitment update | `COMMITTED.json` can exist before the coordinator records commitment. | Consumers use the validated manifest contract. Operators let normal recovery reconcile the exact owned manifest; do not edit the database to declare success. [06](RUST-INCREMENT-06.md), [96](RUST-INCREMENT-96.md). |
| Fully committed | Completion and retained files survive restart; old failure rows do not schedule another committed delivery. | No producer resubmission or cleanup is needed to restart. Retention remains until a separately supported action; restart does not delete or forget it. [06](RUST-INCREMENT-06.md), [107](RUST-INCREMENT-107.md). |
| Allocation happened but no durable owning receipt exists | Recovery cannot safely attribute a leftover directory/file. | Preserve it and keep the refusal; names, matching bytes and emptiness do not authorize adoption/deletion. Repair remains deferred. SC-032; [repair prerequisites](RETENTION-REPAIR-DESIGN.md). |

After confirmed producer HTTP 202, restarting the mover adds no monitoring duty
for the recorder and does not revoke path reuse. Submission 202 is custody,
not delivery. Consumers still require a validated completion manifest.

## Blocked stop or restart

Use the configured paths and actual installed unit name. In the examples,
`file-mover.service` is a placeholder for that unit. Run mover controls under the
service account; systemd/journal access requires the host's authorized privileges.

```sh
file-mover --status /path/to/config.json
systemctl status file-mover.service --no-pager
journalctl -u file-mover.service -n 100 --no-pager
systemctl cat file-mover.service
systemctl show file-mover.service -p MainPID -p ActiveState -p SubState -p Result
```

1. Record the results. `ShutdownIncomplete` or `OwnerUnavailable` preserves
   ownership. A manager timeout, MainPID zero, or a transient Started message
   does not prove old threads exited. Check the journal for listener binding,
   guard, configuration, storage or rate-limit failures.
2. **Find the old workers:** use the read-only process-group procedure in
   [the operator guide](RUST-OPERATOR-GUIDE.md#finding-surviving-workers-and-restarting).
   A `D` thread may be stuck in kernel storage I/O. Do not kill unrelated
   processes, clear lifetime files, force-unmount, or change state paths.
3. Resolve the actual underlying storage/configuration problem. Preserve the
   original scope and evidence. Observe old-process/thread exit and check local
   status again; do not create a restart loop while the old owner remains.
4. If the original daemon is still running or draining, let that shutdown finish.
   If a replacement already started, verify it instead of issuing another start.
   If no daemon remains and no old owner survives, original-scope checks must
   still pass; uncertain remote effects are not cleared by process exit.
5. If the unit is failed/rate-limited and no replacement is running, an authorized
   administrator can use the following **after** the preceding checks:

   ```sh
   systemctl reset-failed file-mover.service
   systemctl start file-mover.service
   ```

   `reset-failed` clears manager bookkeeping; it does not stop workers, fix files,
   release ownership or reset mover job review. Do not assume `Restart=on-failure`
   will recover an incomplete group stop automatically. For a manual daemon,
   use the original manual launch procedure instead of these systemd commands.
6. Verify local readiness and inspect the original affected job IDs. Follow the
   existing retry/review action if required. If admission or recovery still
   refuses, preserve diagnostics and stop attempting replacement; no general
   force-recovery tool is provided.

The selected [managed restart tests](RUST-INCREMENT-61.md) required explicit
reset-failed/start after storage restoration and confirmed old exit. Some
contenders failed at listener binding before reaching the ownership guard.
Their shortened fixture times and observed lack of automatic replacement are
not universal timing/retry promises. Consult the installed manager/unit and its
[systemctl](https://www.freedesktop.org/software/systemd/man/latest/systemctl.html)
and [kill-policy](https://www.freedesktop.org/software/systemd/man/latest/systemd.kill.html)
documentation; newer-manager manuals do not qualify SLES vendor patches.

## Confirm recovery before walking away

- Local status reports the new coordinator `Running`, and the readiness check
  succeeds. If it remains `Starting`, use the source/bootstrap case rather than
  declaring restart complete.
- The original job IDs are still present unless explicitly cleared earlier.
  `Retrying` means work remains subject to its saved deadline; `ReviewRequired`
  needs the matching operator action. Neither means the restart lost the job.
- Delivery success requires the committed job/validated manifest evidence, not
  just a running service or visible payload. Inspect the
  [job-status fields](RUST-OPERATOR-GUIDE.md#inspect-a-job).
- If the same failure repeats, retain the exact diagnostic, unit journal,
  affected job IDs and local status. Keep original state/custody intact and
  obtain review instead of repeatedly restarting or changing identifiers.

## Approved future behavior that is not implemented

- Dashboard sessions must be invalidated on mover restart (SC-157); dashboard
  authentication/session implementation is still pending.
- Restart must not revive a safely cancelled job (SC-162/165). Cancellation is
  not implemented by the offline completed-job clear. Stop/restart is not cancel.
- Current expected-size policy must apply to unfinished jobs after restart
  (SC-140); this approved producer-policy change is not implemented yet.
- General cross-host takeover, stale/cloned-state recovery, repair, production
  deployment/rollback and physical deletion are not supplied by this runbook.

## Coverage and evidence

This is a documentation-only consolidation of SC-005/009/013/018-021/024/026,
SC-028-033/037-042/058-065/092-099/103-138 and the explicitly pending contract
cases above. Keep the [scenario catalog](RUST-SCENARIOS.md),
[operator guide](RUST-OPERATOR-GUIDE.md), [testing limits](TESTING-LIMITATIONS.md)
and linked increment reports as the evidence record. Historical reports retain
their actual source versions and finite scope; no new Rust, systemd, NFS, reboot
or power-loss tests were run for this documentation change. DOC-04 now has this
consolidated runbook; remaining release/deployment qualification is still open.
