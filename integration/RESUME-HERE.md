# Resume here

Rewritten 2026-08-08, at the end of the session in which the lab ran end to end for
the first time. The previous version of this file said to delete it once that
happened. Keeping it instead, because the run produced a finding that matters more
than anything it replaced — see **The one thing that is not yet true**.

Delete it when the SELinux policy module lands and the lab is answering the question
it was built to answer.

## Where things stand

| | |
|---|---|
| Branch | `integration-lab` (off `c7-dashboard`, off `main`) |
| Pushed | yes, everything is on GitHub |
| C7 | delivered on `c7-dashboard`, CI green, **still not merged to main** |
| Lab | **built, provisioned, and green** — layers 1 and 2 both run |
| VM | `fm-rocky9-01` at `192.168.1.114`, left **running** |

## Done, and verified

Everything in the previous version of this note still holds (ISO fetched and
signature-verified against the pinned Rocky Release key, control node installed,
`validate.sh` passing with nothing skipped, `D:\filemover-lab\` laid out). Added
this session:

- **The VM exists and installs unattended.** Rocky 9.8, `Enforcing`, DHCP lease,
  SSH key auth as `labadmin`.
- **`site.yml` is green** — 34 ok, 0 failed. The source tree synchronises, the daemon
  **builds on the RHEL 9 toolchain** (g++ 11.5.0 20240719, Red Hat 11.5.0-14), the
  unit suite passes on the target, and the service installs and starts.
- **`tests/run-all.sh` is green** — `01-service-lifecycle.sh` passes every check:
  `Type=notify` with readiness observed by systemd, `/healthz` and the dashboard
  answering, running as `file-mover`, `NoNewPrivileges` / `ProtectSystem=strict` /
  `PrivateTmp` / `ProtectHome` / empty `CapabilityBoundingSet` all confirmed,
  `ExecStartPre` refusing a deliberately broken config, and a 0s drained stop.
- **Four broken assertions fixed** — see the CHANGELOG. All four failed on a *healthy*
  host, and each blamed something other than itself. That pattern is the reason the
  next section exists.

## The one thing that is not yet true

**The lab does not yet test SELinux, and its green result must not be read as if it
does.**

```
$ ps -eZ | grep file-mover
system_u:system_r:unconfined_service_t:s0  file-mover
$ ls -Z /usr/bin/file-mover
system_u:object_r:bin_t:s0  /usr/bin/file-mover
```

The host is `Enforcing` and `ausearch -m AVC -ts today` returns `<no matches>`. Both
are true and neither means what it looks like: the binary carries generic `bin_t`,
there is no policy module and therefore no domain transition, so systemd starts the
daemon **unconfined**. An unconfined process cannot generate a denial no matter what
it touches. Zero denials is what you would see if the service were perfectly
SELinux-clean *and* what you see here, where it is simply not being confined.

The previous note predicted denials on the first run and said they would be the
finding. Their absence is the finding.

**Next real work:** a policy module giving the service its own domain — `filemover_t`,
entered by transition from a `filemover_exec_t`-labelled binary — plus file contexts
for `/etc/file-mover`, `/var/lib/file-mover` (currently plain `var_lib_t`) and whatever
the mover reads and writes. Only once that is loaded do denials, or their absence,
mean anything. Expect the first confined run to be noisy; that is the point.

## Next — in this order

1. **The SELinux policy module.** Above. This is the lab's whole purpose.
2. **Decide on C7.** It is still sitting unmerged on `c7-dashboard`.
3. **`02-*` tests** — the lifecycle test is the only one. Actual file movement under a
   confined domain is untested.

Rebuilding from scratch, if ever needed — layer 1 from a **Windows** PowerShell window
(the Hyper-V cmdlets exist only there), layer 2 from WSL:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass   # see inventory 3.9
cd '\\wsl.localhost\Ubuntu\home\joey\GIT\background-file-mover\integration\provision\hyperv'
.\New-TestLab.ps1
.\Get-TestLab.ps1        # ~10-15 min
```

```sh
cd integration/configure
# inventory.ini is gitignored and holds the VM's address; it exists already
ansible-playbook -i inventory.ini site.yml
sh ../tests/run-all.sh
```

## Gotchas already paid for — do not rediscover these

The five from the previous version still stand and are not repeated in full:
`pykickstart` is PyPI-only, `~/.local/bin` is not on `PATH` in the shell that creates
it, the install script exits 1 on a missing tool, PowerShell cannot cast a COM object
to `IStream` (hence `Add-Type` for IMAPI2FS), Layer 1 prompts when run off the WSL
share (`-Scope Process Bypass`), and never use a fixed `/tmp/<name>` for scratch in
these scripts. Added:

- **Ansible facts can be confidently wrong about the host.** Both `os_family` and
  `selinux` misreported a correct Rocky 9 guest — the first because the value is
  generated from a table inside the control node's own Ansible, the second because the
  fact silently degrades to an error *string* when `python3-libselinux` is absent. When
  an assertion about the platform fails, verify the claim on the host with `raw` or
  `getenforce` before believing the playbook over the machine.
- **`ansible.posix.synchronize` needs `rsync` on both ends** and hides the reason
  inside an rsync protocol error.
- **`community.general.make` only returns `rc` when the command fails.** Any
  `failed_when: x.rc != 0` on it inverts into a failure on success.

## Environment — the WSL2 lockup, 2026-08-08

The session before this one died mid-playbook, and it was not Claude Code. WSL's
`mini_init` reclaim helper wrote to `/proc/sys/vm/compact_memory`; the page migration
that followed stalled roughly six minutes spinning in `hyperv_flush_tlb_multi`
(`rcu_sched self-detected stall`, NMI watchdog on `__pv_queued_spin_lock_slowpath`).
All WSL2 distros share one utility VM, so everything froze at once, and afterwards
`wsl -d Ubuntu` returned `HCS_E_CONNECTION_TIMEOUT` while the already-warm
`podman-machine-default` still answered.

Fixed by `C:\Users\Joey\.wslconfig`: `memory=12GB`, `processors=8`, `swap=8GB`, and
`[experimental] autoMemoryReclaim=disabled`, then `wsl --shutdown`. Recovery, if it
recurs, is `wsl --shutdown` and restart the distro; `wsl --update` off 2.3.26.0 /
kernel 5.15.167.4 is the durable fix and has not been done. Note `pageReporting` is
**not** a valid `[wsl2]` key in 2.3.26 and logs `Unknown key` on every start.

Diagnostic worth keeping: the kernel log is shared, so
`wsl -d podman-machine-default -- dmesg -T` shows stalls caused by a *different*
distro that is itself too wedged to enter.

### `validate.sh` can FAIL for a reason that is not in the repository

Seen at the end of this session and worth recognising rather than re-debugging:

```
integration/scripts/validate.sh: 101: cannot create /tmp/tmp.XXXX/as.out: Directory nonexistent
  FAIL  ansible syntax-check
```

Nothing is wrong with the syntax check or with `$TMP`. Ubuntu's
`/usr/lib/tmpfiles.d/tmp.conf` carries `D /tmp 1777 root root -`, and the `D`
directive **empties** `/tmp` when `systemd-tmpfiles-setup` runs at distro init.
A distro that has gone idle re-initialises on the next `wsl.exe` invocation, so
if that init lands in the middle of a running script, `mktemp -d` scratch is
deleted out from under it. The check that happens to be next reports FAIL.

Confirmed by control: a `mktemp -d` directory with **nothing at all running**
disappeared 8 seconds after creation, and `journalctl` showed
`systemd-tmpfiles` at that moment. An earlier hypothesis blamed `ansible-lint`
for deleting the directory containing its own stdout; that was wrong, and the
control is what disproved it.

It does not reproduce in an interactive shell, where the distro stays up.
Re-run `validate.sh` a second time in the same session and it passes clean, all
checks, nothing skipped. Only worth a code change if it starts biting during
ordinary interactive work — the scripts are not at fault.

## Open questions I still owe you

- Should the integration suite eventually gate merges? My recommendation is unchanged:
  not until it has earned trust — and this session is the argument for that, since a
  suite that was green while testing nothing about SELinux would have gated merges on
  a result that meant nothing.
- C7 is unmerged on `c7-dashboard`. Merge it before or after the policy module?
