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

```powershell
cd integration\provision\hyperv
.\New-KickstartIso.ps1        # builds the OEMDRV ISO Anaconda auto-detects
.\New-TestLab.ps1             # creates the switch (if absent) and the VM, starts install
.\Get-TestLab.ps1             # state, IP address, and what to do next
```

```sh
cd integration/configure
cp inventory.ini.example inventory.ini   # put the VM's IP in it
ansible-playbook -i inventory.ini site.yml
sh ../tests/run-all.sh
```

Teardown is `.\Remove-TestLab.ps1`, which is idempotent and removes the disk as well as
the VM. A lab that leaves 40 GB behind on every run is a lab nobody runs twice.

## Status

**Phase 1 only, and nothing here has been executed yet.** Written against a machine
where Hyper-V was installed but not yet accessible to the account. Syntax is validated
(PowerShell AST parse, `sh -n`, YAML load); behaviour is not. Treat the first run as
part of writing it.
