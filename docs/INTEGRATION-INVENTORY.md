# Integration lab — configuration inventory

Every setting the lab applies, why it is that value, which script applies it, and
how to check it by hand. If a setting is not in this table, it is not
deliberate — that is the point of the table.

Companion documents: `docs/INTEGRATION-ENVIRONMENT.md` (why this environment
exists at all and how it is phased) and `integration/README.md` (how to run it).

**Status: Phase 1, written but never executed.** Syntax is validated; behaviour
is not. See § 7.

---

## 1. Host prerequisites (Windows)

| # | Item | Value | Why | Applied by | Verify |
|---|---|---|---|---|---|
| 1.1 | Hyper-V access | account in `Hyper-V Administrators` | Without it every `Get-VM`/`New-VM` fails on permissions. Group membership rather than running elevated each time, so provisioning is one command. | **Manual, once** — command in `integration/README.md` | `Get-VMHost` returns without error |
| 1.2 | VHD default path | `D:\filemover-lab\vhd` | Hyper-V defaults to `C:\ProgramData`. C: had **2.8 GB free**; a 40 GB VM would fail or fill the system drive. | **Manual, once** — `Set-VMHost` | `(Get-VMHost).VirtualHardDiskPath` |
| 1.3 | VM default path | `D:\filemover-lab\vm` | Same reason as 1.2. | **Manual, once** — `Set-VMHost` | `(Get-VMHost).VirtualMachinePath` |
| 1.4 | WSL2 disk location | `D:\WSL\Ubuntu` | `ext4.vhdx` is 58.9 GB and was on C:. Installing Ansible grows it; on a drive with 2.8 GB free that risks filling the system disk. | **Manual, once** — `wsl --manage Ubuntu --move` | `wsl -l -v`, then check the `Lxss` registry `BasePath` |
| 1.5 | Install media | `Rocky-9.8-x86_64-minimal.iso` in `D:\filemover-lab\iso` (2.57 GB) | Minimal, so the install itself does not depend on a mirror being reachable at that moment. 9.8 was the current 9.x when the lab was built. | `Get-RockyIso.ps1` | `New-TestLab.ps1` fails with a clear message if absent |
| 1.6 | ISO integrity | SHA256 matches the published `CHECKSUM` | Catches a truncated download, a corrupted mirror, and a mirror serving the wrong release. A file that fails is **deleted**, because a bad image left on disk is how a later run picks it up and produces a VM nobody can explain. | `Get-RockyIso.ps1` | re-run it; it verifies without re-downloading |
| | | | **Do not trust the byte counts in `CHECKSUM`.** For 9.8 it lists 1,480,048,640 bytes for *both* `boot.iso` and `minimal.iso` despite their hashes differing, and the real minimal ISO is 2.57 GB. The size lines are comments; only the SHA256 is checked, and only the SHA256 should be. | | |
| 1.7 | ISO authenticity | GPG signature over `CHECKSUM` | SHA256 alone proves only that the bytes match what the CHECKSUM file says — anyone able to serve you both can make them agree. This is a different question and needs a different check. | `integration/scripts/verify-iso-signature.sh` | run it; it reports OK or fails |
| 1.8 | Signing key pin | `provision/hyperv/rocky-gpg-fingerprint.txt` | Until the fingerprint is confirmed against a source outside the download channel, 1.7 is trust-on-first-use rather than verification. The script says so rather than implying more, and refuses to invent a fingerprint — a wrong pin looks like verification and is not. | **Manual, once** | file present and matching |

## 2. Lab configuration data

All of layer 1 reads one file: `integration/provision/hyperv/Lab.psd1`.

| # | Key | Value | Why |
|---|---|---|---|
| 2.1 | `LabRoot` … `KeyDir` | under `D:\filemover-lab` | C: has no room (§ 1.2). |
| 2.2 | `InstallIso` | exact file name | Named, not globbed: a glob matching two ISOs picks one silently, and 9.4 vs 9.5 is exactly what makes a result unreproducible. |
| 2.3 | `KickstartIso` | `filemover-ks.iso` | Built by `New-KickstartIso.ps1`, volume label `OEMDRV`. |
| 2.4 | `VmName` | `fm-rocky9-01` | Numbered so a second VM (the NFS server, Phase 3) is an obvious extension. |
| 2.5 | `CpuCount` / `MemoryMB` / `DiskGB` | 2 / 4096 / 40 | Host is 8c/16t with 32 GB; leaves room for the Phase 3 second VM without contention. |
| 2.6 | `DynamicMemory` | `$false` | Dynamic memory makes a page-cache-sensitive I/O test depend on what the host was doing. This lab exists to make results reproducible. |
| 2.7 | `SwitchName` / `SwitchType` | `fm-lab-external` / External | VM gets LAN DHCP, reaches a mirror for `dnf`, and is reachable from WSL2 by IP with no port forwarding. Accepted trade-off: the VM is visible on the LAN. |
| 2.8 | `HostAdapterName` | `$null` | Means "work it out, and refuse if ambiguous". Binding the wrong adapter drops the host's own network for several seconds. |
| 2.9 | `AdminUser` | `labadmin` | Not root. The lab should not normalise logging in as root. |
| 2.10 | `SshKeyName` | `fm-lab-ed25519` | Private half stays in `KeyDir` and is gitignored. |

## 3. Virtual machine (layer 1)

Applied by `integration/provision/hyperv/New-TestLab.ps1`.

| # | Item | Value | Why | Verify |
|---|---|---|---|---|
| 3.1 | Generation | 2 (UEFI) | Matches how a modern RHEL 9 server actually boots. | `(Get-VM fm-rocky9-01).Generation` |
| 3.2 | Secure Boot | On, template `MicrosoftUEFICertificateAuthority` | Rocky's shim is signed by the **Microsoft UEFI CA**, not the Windows CA. The default template refuses to boot it, presenting as "no bootable device" — which looks like a bad ISO rather than a policy mismatch. | `Get-VMFirmware fm-rocky9-01` |
| 3.3 | DVD drives | install ISO + kickstart ISO | Anaconda scans removable media for the `OEMDRV` label and auto-loads `ks.cfg`. This is what makes the install unattended **without** editing kernel boot parameters through a console. | `Get-VMDvdDrive fm-rocky9-01` |
| 3.4 | First boot device | the install DVD | Otherwise the VM boots an empty disk. | `(Get-VMFirmware fm-rocky9-01).BootOrder` |
| 3.5 | Auto start / stop | `Nothing` / `ShutDown` | A half-installed VM that silently reboots into a fresh install loop after a host reboot is hard to diagnose. | `Get-VM fm-rocky9-01 \| fl Automatic*` |
| 3.6 | Checkpoints | Disabled | An automatic production checkpoint during install creates a differencing disk nobody asked for. Revert-between-tests comes later, deliberately. | `(Get-VM fm-rocky9-01).CheckpointType` |
| 3.7 | Existing VM | refuse, unless `-Force` | A test result that depends on what a previous run left on disk is not a test result. | run it twice |

## 4. Guest install (kickstart)

Applied by `integration/provision/hyperv/kickstart/rocky9-lab.ks`.

The rule that keeps this file small: **if a setting could be applied over SSH
after first boot, it belongs in Ansible, not here.** What is left is only what
must exist before SSH works at all.

| # | Item | Value | Why | Verify on the guest |
|---|---|---|---|---|
| 4.1 | SELinux | `--enforcing` | **The single most important line in the lab.** The whole reason for a real RHEL host is to find out whether the service survives SELinux. A permissive lab answers that question wrongly and confidently. | `getenforce` |
| 4.2 | Firewall | enabled, `ssh` only | A lab with the firewall off cannot tell "not listening" from "blocked" — a distinction an operator faces on a real deployment. | `firewall-cmd --list-all` |
| 4.3 | Root account | `--lock` | A password-less root on a LAN-visible VM is unacceptable even in a lab. | `passwd -S root` |
| 4.4 | Lab account | `labadmin`, wheel, key-only, locked password | Key auth only; no password to leak or guess. | `ssh labadmin@<ip>` |
| 4.5 | Passwordless sudo | `/etc/sudoers.d/90-labadmin` | Ansible must escalate without an interactive prompt. Storing a sudo password in the inventory would be worse. **Lab-only affordance.** | `sudo -n true` |
| 4.6 | Timezone | UTC | Every timestamp the service emits is UTC (`format_event`). A guest in local time turns log correlation into arithmetic. | `timedatectl` |
| 4.7 | Partitioning | plain, no LVM | LVM is what production would use; here it adds a layer between the test and the filesystem it asserts about. | `lsblk` |
| 4.8 | Packages | `@^minimal-environment`, `openssh-server`, `python3` | `python3` here rather than bootstrapped later, to avoid the chicken-and-egg where the first playbook cannot run because its interpreter is missing. | `rpm -q python3` |
| 4.9 | Graphical target | `skipx` | Headless service host. The GUI stack is a large attack surface and hundreds of megabytes whose updates slow every rebuild. | `systemctl get-default` |

## 5. Guest configuration (Ansible, layer 2)

Applied by `integration/configure/site.yml`. **Nothing under `configure/` may
mention Hyper-V** — enforced by `integration/scripts/assert-layer-separation.sh`.

### 5.1 `base` role — `configure/roles/base/tasks/main.yml`

| # | Item | Why | Verify |
|---|---|---|---|
| 5.1.1 | Assert RHEL 9 family | Running elsewhere gives a green result that says nothing about the target. | playbook fails on a non-RHEL host |
| 5.1.2 | Assert SELinux enforcing | Asserted **before** anything is installed. If something silently switched it to permissive, every SELinux result from this lab is worthless. | `getenforce` |
| 5.1.3 | `curl`, `policycoreutils*`, `setools-console`, `audit` | The tests need `curl`; diagnosing a denial needs `ausearch` and `sesearch`. | `rpm -q audit` |
| 5.1.4 | `auditd` running | Without it SELinux denials are not recorded at all, and 5.1.2 would pass while proving nothing. | `systemctl is-active auditd` |
| 5.1.5 | Open port 8080/tcp | Explicit, so a failure means "not listening" rather than "blocked". | `firewall-cmd --list-ports` |

### 5.2 `buildtools` role — `configure/roles/buildtools/tasks/main.yml`

| # | Item | Why | Verify |
|---|---|---|---|
| 5.2.1 | `gcc-c++`, `make`, `glibc-devel` | **Build on the target.** A binary built in WSL2 (glibc 2.35) will not run on Rocky 9 (glibc 2.34) — glibc is backward compatible, not forward. Building here also exercises the RHEL 9 toolchain, which no container tier covers. **Lab-only; C8's RPM replaces this and the compiler comes off the host.** | `g++ --version` |
| 5.2.2 | No `sqlite-devel` | SQLite is vendored as an amalgamation (ADR-0010). Installing the system headers risks building against a different SQLite than the one shipped. | `rpm -q sqlite-devel` → not installed |
| 5.2.3 | `synchronize` the source, not `git clone` | The point is to test the working tree in front of you, including uncommitted changes. A clone tests whatever is on the remote. | `ls /opt/file-mover-src` |
| 5.2.4 | Run `make check` on the target | The same unit suite, on RHEL 9 against its own libstdc++. Not a substitute for the integration tests, but a failure here means the platform differs in a way worth knowing first. | playbook output |

### 5.3 `filemover` role — `configure/roles/filemover/tasks/main.yml`

| # | Item | Value | Why | Verify |
|---|---|---|---|---|
| 5.3.1 | Service account | `file-mover`, system, `/sbin/nologin` | Matches `User=`/`Group=` in the shipped unit. | `id file-mover` |
| 5.3.2 | Binary | `/usr/bin/file-mover`, root:root `0755` | The service account must not be able to rewrite the binary it runs as. `NoNewPrivileges` is the other half. | `ls -l /usr/bin/file-mover` |
| 5.3.3 | `restorecon` on the binary | Makes the SELinux label explicit rather than depending on inheritance having happened. | `ls -Z /usr/bin/file-mover` |
| 5.3.4 | Config dir | `/etc/file-mover` `0750` root:file-mover | The service reads it; nothing else needs to. | `ls -ld /etc/file-mover` |
| 5.3.5 | State dir | `/var/lib/file-mover` `0750` file-mover:file-mover | Matches `UMask=0077` in the unit. Holds the paths of everything ever moved. | `ls -ld /var/lib/file-mover` |
| 5.3.6 | systemd unit | **copied from `deploy/systemd/file-mover.service` in the repo** | A lab that installs its own simplified unit tests the lab's unit — the one artifact nobody ships. | `systemctl cat file-mover` |
| 5.3.7 | `--check` before enabling | L2-CTL-019, run the way `ExecStartPre` runs it. | playbook output |

### 5.4 Service configuration — `configure/roles/filemover/templates/file-mover.ini.j2`

| # | Setting | Lab value | Production | Why they differ |
|---|---|---|---|---|
| 5.4.1 | `http.bind` | `0.0.0.0` | `127.0.0.1` | **LAB DIVERGENCE.** The API has no authentication (ADR-0003); loopback is the entire access control at v1.0.0. The lab binds all interfaces so the control node can reach it, with firewalld limiting exposure to one port. |
| 5.4.2 | `logging.level` | `DEBUG` | `INFO` | The tests read the journal, and the event stream is the main evidence of what the service did. |
| 5.4.3 | everything else | same as `config/file-mover.ini` | — | Divergence is the exception and is listed here; anything not in this table matches the shipped reference config. |

## 6. Tests

`integration/tests/01-service-lifecycle.sh`, run over SSH by `run-all.sh`.

| # | Assertion | Requirement | Why it needs a real host |
|---|---|---|---|
| 6.1 | Unit is active | L2-CTL-020 | — |
| 6.2 | `Type=notify` and `SubState=running` | L2-CTL-011 | The **only** way to check readiness as *systemd* observes it. With `Type=simple` systemd reports active before the port is open. |
| 6.3 | `/healthz`, `/api/status`, `/` answer | L2-CTL-012, L2-DASH-001 | — |
| 6.4 | Runs as `file-mover`, not root | L2-SEC-014 | — |
| 6.5 | `NoNewPrivileges`, `ProtectSystem`, `PrivateTmp`, `ProtectHome`, `UMask`, empty `CapabilityBoundingSet` | L2-SEC-014 | systemd reports what it **applied**, which is not always what was asked: a directive it does not understand is ignored with a warning nobody reads. |
| 6.6 | No SELinux denials | L2-ENV-001..003 | Impossible in a container. A denial here is a **finding** — the service needs a policy module — not a broken test. |
| 6.7 | Invalid config fails the unit | L2-CTL-019 | Tested by actually breaking the config and asking systemd to start. `--check` passing in a shell proves less than the unit refusing to come up. |
| 6.8 | Stop drains, does not hit `TimeoutStopSec` | L2-CTL-020 | If stop took 120 s, systemd killed it — meaning a move could have been torn in half. |

## 7. What is verified, and what is not

Run `sh integration/scripts/validate.sh` (POSIX shell, YAML, layer separation)
and `integration/scripts/Test-Syntax.ps1` (PowerShell parse + `Lab.psd1` import).

| Checked | How |
|---|---|
| POSIX shell syntax | `sh -n`, no tooling needed |
| YAML syntax | `python3 -c yaml.safe_load` |
| PowerShell syntax | the parser built into PowerShell — **no PSScriptAnalyzer**, which is a module download on a machine with no room on C: |
| `Lab.psd1` imports and has every required key | `Import-PowerShellDataFile` |
| Layer 2 never mentions the hypervisor | `assert-layer-separation.sh`, negative-tested |
| Lab paths are on D: | grep in `validate.sh` |

| **Not checked** | Why |
|---|---|
| **The kickstart** | `ksvalidator` (pykickstart) is not installed. A syntax error here leaves Anaconda at an interactive prompt on a VM with no console attached, which presents as "the install hung". **This is the highest-risk unvalidated file in the lab.** |
| `ansible-lint`, `--syntax-check` | Ansible is not installed yet — it must wait for the WSL disk move (§ 1.4). |
| `shellcheck`, `yamllint` | Same. |
| **Whether any of it works** | Hyper-V was installed but not accessible to the account when this was written. Nothing here has created a VM. Treat the first run as part of writing it. |
