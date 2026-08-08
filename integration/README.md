# Integration lab

Automation for standing up a real Rocky 9 host and running the service on it.

**Why this exists:** every other tier in this project runs in a container or in WSL2.
That is enough to prove the code correct in the ways a compiler, a sanitiser and a unit
test can check. It cannot check `systemctl start`, `ExecStartPre` failing a unit, an
SELinux denial, a service account that cannot write its own state directory, or any
NFS behaviour the `L2-NFS-*` requirements describe. The rationale and the phasing are in
`docs/INTEGRATION-ENVIRONMENT.md`; what each setting does and which script applies it is
in `docs/INTEGRATION-INVENTORY.md`.

## The two layers, and the line between them

```
  layer 1   provision/hyperv/   "make me a host"      PowerShell + Hyper-V, on Windows
  ---------------------------------------------------------------------------------
  layer 2   configure/, tests/  "install and verify"  Ansible + POSIX sh, over SSH
```

**Layer 2 must never mention Hyper-V.** It targets any reachable RHEL 9 host given an
SSH address, and knows nothing about how that host came to exist. That line is the only
thing that keeps a different provider — a cloud instance, a colleague's spare box, bare
metal — a matter of writing a new layer 1 rather than a rewrite. If it erodes, the
hypervisor choice becomes permanent, and that is a bigger risk than the choice itself.

Concretely: no file under `configure/` or `tests/` may contain the strings `Hyper-V`,
`vhdx`, `New-VM`, or a `D:\` path. `scripts/assert-layer-separation.sh` enforces it.

## Prerequisites

**On Windows**, once:

```powershell
# Elevated, once. Sign out and back in afterwards -- group membership is
# granted at logon, so the change does not take effect in the current session.
Add-LocalGroupMember -Group "Hyper-V Administrators" -Member "$env:COMPUTERNAME\$env:USERNAME"

# Then, as your own account, point Hyper-V at the data drive.
New-Item -ItemType Directory -Force -Path 'D:\filemover-lab\vhd','D:\filemover-lab\vm','D:\filemover-lab\iso','D:\filemover-lab\keys'
Set-VMHost -VirtualHardDiskPath 'D:\filemover-lab\vhd' -VirtualMachinePath 'D:\filemover-lab\vm'
```

**In WSL2**, once: `sh integration/prereqs/install-control-node.sh`

> Do not run that before moving the WSL2 disk to D:. Installing Ansible grows
> `ext4.vhdx`, and that file lives on C: until it is moved. See the note at the top of
> the script.

It installs Ansible and the linters from apt, and `pykickstart` from PyPI into
`~/.local` — Ubuntu has no package for it. If it finishes by reporting
`ksvalidator MISSING`, that is the expected one-time outcome: `~/.local/bin` is
added to `PATH` by `~/.profile` only when it already exists at login, so the shell
that created it cannot see it. **Open a new shell and re-run.** The script exits
non-zero rather than passing, deliberately — a bootstrap that reports success
without the validators is worse than one that fails.

**Media**:

```powershell
cd integration\provision\hyperv
.\Get-RockyIso.ps1            # latest 9.x minimal, SHA256-verified
```

then, once, on the Linux side:

```sh
sh integration/scripts/verify-iso-signature.sh
```

The two checks answer different questions. `Get-RockyIso.ps1` verifies the ISO's SHA256
against the `CHECKSUM` published beside it, which proves the bytes match what that file
describes — it does **not** prove the file came from Rocky, since anyone able to serve
you both can make them agree. `verify-iso-signature.sh` checks the GPG signature over
`CHECKSUM`, and tells you to pin the key fingerprint after confirming it against
`rockylinux.org` once. Until it is pinned, that step is trust-on-first-use and the
script says so rather than implying more.

The exact ISO name is pinned in `provision/hyperv/Lab.psd1` — never the
`Rocky-9-latest-` alias, whose meaning changes underneath a lab that is supposed to be
reproducible.

## Running it

Layer 1 runs from a **Windows** PowerShell window — the Hyper-V cmdlets exist only
there — and the repo is reached over the WSL share:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
cd '\\wsl.localhost\Ubuntu\home\joey\GIT\background-file-mover\integration\provision\hyperv'
.\New-KickstartIso.ps1        # builds the OEMDRV ISO Anaconda auto-detects
.\New-TestLab.ps1             # creates the switch (if absent) and the VM, starts install
.\Get-TestLab.ps1             # state, IP address, and what to do next
```

The `Set-ExecutionPolicy` line is needed because an `Unrestricted` policy still
*prompts* for scripts on a UNC path. `Unblock-File` will not silence it — the zone
comes from the path being a share, not from a `Zone.Identifier` stream. Process scope
keeps the relaxation inside that one window.

```sh
cd integration/configure
cp inventory.ini.example inventory.ini   # put the VM's IP in it
ansible-playbook -i inventory.ini site.yml
sh ../tests/run-all.sh
```

## Getting in

| | |
|---|---|
| User | `labadmin` (never root — `rootpw --lock`) |
| Over SSH | the key at `D:\filemover-lab\keys\fm-lab-ed25519`. **Key only** — sshd has `PasswordAuthentication no` |
| At the console | the generated password in `D:\filemover-lab\keys\console-password.txt` |
| Escalation | passwordless `sudo` |

Copy the key into WSL and `chmod 600` it before use. ssh refuses a key read from
`/mnt/d`, because DrvFs reports every file as `0777` and the error message does not
say that.

The console password exists so that a VM whose sshd did not start can still be
diagnosed rather than rebuilt — rebuilding to diagnose destroys the evidence. It is
generated per machine, lives beside the private key, and is never in git.

## Recreating it

```powershell
.\Remove-TestLab.ps1          # stops the VM, deletes it, its VHDX and its VM directory
.\New-KickstartIso.ps1        # only needed if the kickstart or the key changed
.\New-TestLab.ps1
.\Get-TestLab.ps1
```

`Remove-TestLab.ps1` is idempotent and deletes the disk as well as the VM — a lab that
leaves 40 GB behind on every run is a lab nobody runs twice. It leaves the virtual
switch alone unless you pass `-RemoveSwitch`, because tearing down an external switch
drops the host's own networking for several seconds.

Three things that bite on a rebuild:

1. **The new VM has a new SSH host key.** If DHCP hands it the same address, ssh
   refuses to connect with `REMOTE HOST IDENTIFICATION HAS CHANGED`. Clear the old
   entry first: `ssh-keygen -R <ip>`.
2. **The address will probably change.** `inventory.ini` is gitignored and holds the
   old one; update it from `Get-TestLab.ps1`.
3. **`New-KickstartIso.ps1` cannot replace an ISO that is still attached to a VM.**
   Hyper-V holds the file open. The script detects this and names the VM and the
   command to detach it, rather than reporting a bare "used by another process".

The SSH key and the console password are **reused, not regenerated**, if they already
exist. Replacing either would lock you out of any VM still running from an earlier
build.

## Status

**Phase 1. Built and verified once, on 2026-08-08.** A Rocky 9.8 guest installs
unattended, boots, takes a DHCP lease, and accepts SSH key authentication as
`labadmin` with SELinux `Enforcing` and passwordless sudo. What has **not** run yet is
layer 2: the Ansible playbook and `tests/run-all.sh`.
