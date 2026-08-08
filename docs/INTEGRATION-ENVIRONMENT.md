# Integration environment — proposal

**Status:** proposed, not built. Awaiting a decision on the hosting choice in § 3.

## 1. The problem this solves

Every tier this project runs today executes in a container or in WSL2. That has been
enough to make the code correct in the ways a compiler, a sanitiser and a unit test can
check. It cannot check the things the requirements are actually about.

Unexercised on any real target host, as of C7:

| Area | Requirements | Why a container cannot answer it |
|---|---|---|
| Service lifecycle | `L2-CTL-019`, `L2-CTL-020`, `L2-SEC-014` | `systemctl start/stop`, `ExecStartPre` failing the unit, `Type=notify` readiness as seen *by systemd*, `TimeoutStopSec` draining. The unit is verified by `systemd-analyze` and by running the daemon with its own `ExecStartPre` arguments — neither is `systemctl start`. |
| Hardening | `L2-SEC-014` | `ProtectSystem=strict`, `ReadWritePaths=`, an empty `CapabilityBoundingSet=`, `UMask=0077`, a dedicated service account. These either work or silently deny the service its own state directory. |
| SELinux | `L2-ENV-001..003` | RHEL 9 enforces by default. A daemon that writes to `/var/lib` under a confined type without a policy is denied, and the failure appears as an unexplained I/O error. |
| NFS semantics | `L2-NFS-001..007`, `L2-SEC-007` | `renameat2(RENAME_NOREPLACE)` support is **detected by attempting it** (`L2-NFS-001`), silly-rename artifacts (`.nfsXXXX`) appear only on a real export with a file held open by another client, `ESTALE` is a live-export condition, and the `actimeo=0` mitigation in `docs/CYBERSECURITY.md` § 4.3 is a mount option. |
| CIFS/SMB | `L2-XFR-*` two-hop delivery | Different locking, different case semantics, no POSIX rename guarantees. |
| Interference | `L2-SEC-009..011` | The `FailedExternal` outcome models endpoint security quarantining a file mid-move. Reproducing it needs something that actually removes files. |

The risk is not that the code is wrong. It is that **the first time any of this runs on
a target host will be at a deployment**, and the failure modes above present as
"permission denied", "stale file handle" or "the unit timed out" — the kinds of error
that consume a day each when they arrive without a reproduction.

## 2. What the environment has to provide

1. A **RHEL 9-family host** running the real `systemd`, with SELinux enforcing.
2. A **second host exporting NFS**, so the client is a genuine client — same-host loopback
   NFS does not exercise the attribute cache, and the cache is where `L2-SEC-002`'s
   residual risk lives.
3. The ability to export **NFSv3 and NFSv4 separately**. This is not a nicety:
   `L2-NFS-002` records that NFSv3 has no `RENAME_NOREPLACE` equivalent, and the project
   therefore treats `LinkThenUnlink` as a **primary tested path, not a fallback**.
   Testing only v4 would leave the strategy production actually runs on untested.
4. A **CIFS/SMB export** for the same reason, later.
5. **Repeatable teardown.** A test that leaves an NFS mount behind poisons the next run.
6. Eventually: **SLES 12 SP5**, the other deployment target, and the one whose toolchain
   the GCC 4.8.5 tier already exists for.

## 3. The choice: local hypervisor vs cloud

### Recommendation: build it on Hyper-V first.

The deciding argument is item 3 above, and it is technical rather than a preference.

- **AWS EFS speaks NFSv4.1 only.** It cannot export NFSv3, so the `LinkThenUnlink`
  strategy — the one the recordings mount actually uses — could not be tested against a
  managed AWS filesystem at all. Reaching NFSv3 on AWS means running
  `nfs-kernel-server` on an EC2 instance, at which point the managed-service advantage
  is gone and what remains is a Linux VM that costs money by the hour.
- **CIFS on AWS** means FSx for Windows File Server, which is expensive for intermittent
  use and is a different implementation from the Samba an on-premises share is likely to
  be. A Samba container or VM is a closer match and free.
- **The workload is on-premises.** The service moves recordings between local and NFS
  storage on an isolated network. A test environment that can only exist with internet
  access is a poor model of a deployment that has none, and it cannot be used to
  reproduce a customer problem from a disconnected site.
- **Cost and latency.** Snapshot-and-revert on a local VM is seconds and free. The
  iteration loop for "boot, mount, run, inspect, revert" matters more than raw capacity
  here; these tests are I/O-shaped, not scale-shaped.
- Windows 11 Pro includes Hyper-V, and it coexists with WSL2 — both already use the same
  hypervisor, so enabling it costs nothing that is currently working.

### Where AWS wins, and when to revisit

- **Unattended CI.** A local hypervisor cannot be driven from a GitHub-hosted runner.
  If integration tests should gate every PR rather than run on demand, that needs either
  a self-hosted runner on the Hyper-V host or cloud instances.
- **Scale and parallel matrices** — several distributions at once, or a soak test.
- **SLES 12 SP5**, which is available as a Marketplace AMI and is otherwise a licensing
  conversation.

Revisit when integration tests are stable enough to be worth gating on. Running them
on demand from the workstation is the right first step, and the cheapest way to find
out what they should even assert.

### The design decision that keeps both open

Split the automation in two, with a hard interface between them:

```
  layer 1  provision   "make me a host"          Hyper-V PowerShell today,
                                                 Terraform later, no other change
  layer 2  configure   "install and verify"      plain POSIX shell over SSH,
           and test     against ANY RHEL 9 host   knows nothing about hypervisors
```

Layer 2 is the valuable part and it must not contain the word "Hyper-V" anywhere. If
that boundary holds, moving to AWS later is a new layer 1 and nothing else. If it does
not hold, the choice made now is permanent — which is the actual risk in this decision,
more than the choice itself.

## 4. Proposed shape

```
integration/
  provision/
    hyperv/
      New-TestLab.ps1          create switch, VMs, disks, attach ISO
      Remove-TestLab.ps1       full teardown, idempotent
      Checkpoint-TestLab.ps1   snapshot / revert
      kickstart/rocky9.ks      unattended install, SSH key, no interaction
    README.md                  what layer 1 guarantees layer 2
  configure/
    install-service.sh         build or copy the RPM, create the account, install unit
    setup-nfs-server.sh        exports for v3 and v4, separate paths
    setup-nfs-client.sh        mounts, including an actimeo=0 variant
    setup-samba.sh             later
  tests/
    01-service-lifecycle.sh    systemctl start/stop/restart, --check fails the unit
    02-selinux.sh              enforcing, no denials in the audit log
    03-hardening.sh            the unit's own claims, verified from inside the service
    04-nfs-v4.sh               RENAME_NOREPLACE path
    05-nfs-v3.sh               LinkThenUnlink path -- the one production uses
    06-interference.sh         delete the source mid-move; expect FailedExternal
    run-all.sh                 ordered, with per-test setup and teardown
  README.md
```

### Phasing — start small

**Phase 1 (the first useful thing).** One Rocky 9 VM. Install the daemon from the build,
`systemctl start`, confirm `Type=notify` readiness is what systemd sees, `curl` the
dashboard, `systemctl stop`, confirm the drain. Then `--check` against a bad config and
confirm the unit refuses to start. That alone retires the largest open risk in § 1, and
needs no NFS at all.

**Phase 2.** SELinux: run enforcing, submit a job, and assert `ausearch` reports no
denials for the service's domain. Expect to write a policy module; that is the finding,
not a failure.

**Phase 3.** A second VM exporting NFS. Mount v4, run the move suite. Then mount v3 and
run the same suite — the strategies differ and both are production paths.

**Phase 4.** Interference and hostile conditions: remove a source mid-move, drop the
export while a move is in flight (`ESTALE`), fill the destination filesystem.

**Phase 5.** CIFS, and SLES 12 SP5.

## 5. What this proposal does not settle

- **Whether the tests gate merges.** Recommendation: no, not at first. An integration
  suite that is red for environmental reasons and blocks merges gets disabled within a
  fortnight. Run it on demand and before a release until it earns trust.
- **How the daemon gets onto the host** — RPM, or a tarball and a script. C8 owns
  packaging; Phase 1 can copy the binary and the unit file by `scp` and stay honest
  about being a stopgap.
- **Where the VM images live.** Rocky 9 ISOs are large and must not enter git.
- **SLES 12 SP5 licensing**, which is a procurement question, not a technical one.

## 6. Cost sketch

| | Hyper-V (local) | AWS |
|---|---|---|
| Standing cost | none | ~$0.02–0.10/hr per instance, plus EFS/FSx |
| Setup effort | PowerShell + kickstart, moderate | Terraform + networking, moderate |
| NFSv3 | yes, self-managed export | only by self-managing on EC2 |
| CIFS | Samba, free | FSx, expensive |
| Runs in GitHub CI | only via a self-hosted runner | yes |
| Models an isolated site | yes | poorly |
| Teardown | revert a checkpoint, seconds | terraform destroy, minutes |

The recommendation is Hyper-V for Phases 1–4, with layer 2 written so that adding an
AWS layer 1 later is additive rather than a rewrite.
