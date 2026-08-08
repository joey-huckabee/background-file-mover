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

**Media**: download the Rocky 9 **minimal** ISO to `D:\filemover-lab\iso\`. The exact
file name goes in `provision/hyperv/Lab.psd1`. It is deliberately not downloaded
automatically — it is 2.5 GB, mirror URLs rot, and a script that silently fetches an
unverified OS image is not something this project should own.

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
