# Resume here

Written 2026-08-08, immediately before a Windows sign-out to activate
Hyper-V Administrators membership. This file exists so the next session — mine
or a different one — can pick up without reconstructing anything from memory.

Delete it once the lab has run once.

## Where things stand

| | |
|---|---|
| Branch | `integration-lab` (off `c7-dashboard`, off `main`) |
| Pushed | yes, everything is on GitHub |
| C7 | delivered on `c7-dashboard`, CI green, **not merged to main** |
| Lab | Phase 1 written, **never executed** |

## Done, and verified

- WSL2 moved to `D:\WSL\Ubuntu`; podman machine to `D:\WSL\podman-machine-default`.
  C: went from 2.8 GB free to 142.4 GB.
- `DESKTOP-QREB78E\Joey` added to `Hyper-V Administrators`. **Not yet effective** —
  the token in the current session predates it, which is why the sign-out is needed.
- `D:\filemover-lab\{iso,vhd,vm}` exist. `keys\` does **not** — my earlier chat
  message omitted it from the `New-Item` list. `New-KickstartIso.ps1` creates it, so
  this is not a blocker, but it is why the directory is missing.
- `Rocky-9.8-x86_64-minimal.iso` downloaded to `D:\filemover-lab\iso` and SHA256
  verified against the published `CHECKSUM` (`d338032c…`). 9.8 is the current 9.x.
- `Lab.psd1` pins that exact file name.

## Not done, and why

| Item | Blocked on |
|---|---|
| Ansible + lint tooling in WSL | `sudo` prompts; cannot install unattended |
| **Kickstart validation** | needs `pykickstart`, which needs the above. **Highest-risk unvalidated file in the lab** — a syntax error leaves Anaconda at an interactive prompt on a VM with no console, presenting as "the install hung" |
| `ansible-lint`, `--syntax-check`, `shellcheck`, `yamllint` | same |
| GPG fingerprint pin | needs a human to confirm it against `rockylinux.org` |
| Creating any VM | Hyper-V access, i.e. the sign-out |
| `Set-VMHost` path redirect | ran, but cannot be confirmed until Hyper-V is readable |

## After signing back in — in this order

**1. Confirm Hyper-V is reachable and the paths took:**

```powershell
Get-VMHost | Select-Object VirtualHardDiskPath, VirtualMachinePath
```

Both should be under `D:\filemover-lab`. If they are not, re-run:

```powershell
Set-VMHost -VirtualHardDiskPath 'D:\filemover-lab\vhd' -VirtualMachinePath 'D:\filemover-lab\vm'
```

**2. Install the control node** (will ask for your password):

```sh
sh integration/prereqs/install-control-node.sh
```

**3. Validate what has never been validated.** Do this BEFORE building a VM — the
kickstart is the file whose failure is most expensive to diagnose:

```sh
sh integration/scripts/validate.sh          # now with ksvalidator, ansible-lint, shellcheck
sh integration/scripts/verify-iso-signature.sh
```

**4. Only then**, build the VM:

```powershell
cd integration\provision\hyperv
.\New-KickstartIso.ps1
.\New-TestLab.ps1
.\Get-TestLab.ps1        # once the install finishes, ~10-15 min
```

**5. Configure and test:**

```sh
cd integration/configure
cp inventory.ini.example inventory.ini    # put the VM's IP in it
ansible-playbook -i inventory.ini site.yml
sh ../tests/run-all.sh
```

## Expect these to go wrong on the first run

Not pessimism — none of it has executed, and these are the specific places I would
look first:

1. **The kickstart.** Never validated. Watch the install in
   `vmconnect.exe localhost fm-rocky9-01` rather than assuming it is progressing.
2. **Secure Boot.** `MicrosoftUEFICertificateAuthority` is the right template for
   Rocky's shim, but if the VM says "no bootable device" that is the first suspect,
   not a bad ISO.
3. **The external switch.** `New-TestLab.ps1` refuses to guess which physical adapter
   to bind. If it lists candidates, set `HostAdapterName` in `Lab.psd1`. Host
   networking drops for a few seconds when the switch is created.
4. **SELinux denials.** Expected. They are the finding — the service likely needs a
   policy module — not a broken test.
5. **The SSH key on a DrvFs mount.** Copy it into WSL and `chmod 600` first; ssh
   refuses a key whose permissions read as 0777, and the error does not say that.

## Open questions I still owe you

- Should the integration suite eventually gate merges? My recommendation: no, not
  until it has earned trust. A suite that is red for environmental reasons and blocks
  merges gets disabled within a fortnight.
- C7 is sitting unmerged on `c7-dashboard`. Merge it before or after the lab runs?
