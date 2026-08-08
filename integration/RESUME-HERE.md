# Resume here

Written 2026-08-08 before a Windows sign-out to activate Hyper-V Administrators
membership; updated the same day, after the sign-out, once the control node was
installed. This file exists so the next session — mine or a different one — can
pick up without reconstructing anything from memory.

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
- `DESKTOP-QREB78E\Joey` added to `Hyper-V Administrators`. **Effective** after the
  sign-out: `Get-VMHost` answers, and `VirtualHardDiskPath` / `VirtualMachinePath`
  read back as `D:\filemover-lab\vhd` and `…\vm`, so the earlier `Set-VMHost` did take.
- `D:\filemover-lab\{iso,vhd,vm}` exist. `keys\` does **not** — my earlier chat
  message omitted it from the `New-Item` list. `New-KickstartIso.ps1` creates it, so
  this is not a blocker, but it is why the directory is missing.
- `Rocky-9.8-x86_64-minimal.iso` downloaded to `D:\filemover-lab\iso` and SHA256
  verified against the published `CHECKSUM` (`d338032c…`). 9.8 is the current 9.x.
- `Lab.psd1` pins that exact file name.
- **Control node installed** — ansible 2.10.8, ansible-lint 5.4.0, shellcheck 0.8.0,
  yamllint 1.26.3, pykickstart 3.77.
- **`validate.sh` passes with nothing skipped**, including `ksvalidator -v RHEL9` on
  the kickstart. That check was negative-tested on copies (a typo'd directive and an
  unterminated `%packages`) and fails on both, so the pass means something.

- **ISO authenticity verified.** `verify-iso-signature.sh` reports `SIGNATURE OK` and
  the fingerprint matches the pin, `21CB256AE16FC54C6E652949702D426D350D275D`
  (Rocky Release key 2022), confirmed by Joey against `rockylinux.org`. Negative-tested
  both ways: a tampered `CHECKSUM` gives `BAD signature`, a wrong pin gives
  `FINGERPRINT MISMATCH`.

## Not done, and why

| Item | Blocked on |
|---|---|
| Creating any VM | nothing — this is the next real step |
| **Kickstart *semantics*** | reviewed by hand, two defects fixed (§ 4.10–4.11); still unproven until an install runs |

## Gotchas already paid for — do not rediscover these

- **`pykickstart` is not an Ubuntu package.** Not under that name, not as
  `python3-pykickstart`; `apt-cache search kickstart` returns `youtube-dl`. It comes
  from PyPI via `pip3 install --user`. An earlier version of the install script had
  it in the apt list, and `set -eu` meant the whole install aborted there having
  installed nothing.
- **`~/.local/bin` is not on `PATH` in the shell that creates it.** Ubuntu's
  `~/.profile` adds it only if it exists at login, so `ksvalidator` installs fine and
  `command -v` still fails. Open a new shell. This is not a dotfile bug.
- **The install script exits 1 if any tool is missing.** It used to print `MISSING`
  and exit 0, which made "installed nothing" and "installed everything" look identical.
- **PowerShell cannot cast a COM object to `IStream`.** Its COM adapter carries no
  interface type information, so `[...ComTypes.IStream] $stream` throws *"Cannot
  convert the System.\_\_ComObject value …"*. The IMAPI2FS image write therefore goes
  through a small `Add-Type` C# helper, where the same object is a plain RCW. This is
  why every working IMAPI2FS recipe on the internet uses `Add-Type`.
- **Layer 1 prompts before running, off the WSL share.** `Unrestricted` still asks for
  scripts on a UNC path, and `Unblock-File` will not silence it — the zone comes from
  the path, not a `Zone.Identifier` stream. `Set-ExecutionPolicy -Scope Process Bypass`
  in the window you are working in.
- **Never use a fixed `/tmp/<name>` for scratch output in these scripts.** Run one of
  them under `sudo` once and the file is left root-owned; every later run as your own
  user fails its redirect, `set -e` calls that a failed check, and the diagnostics get
  read from the *earlier* run's file. `verify-iso-signature.sh` did exactly this and
  reported `SIGNATURE VERIFICATION FAILED` while printing `Good signature` as the
  reason. All three scripts now use `mktemp -d` with a cleanup trap.

## Next — in this order

Layer 1 runs from a **Windows** PowerShell window, over the WSL share, because the
Hyper-V cmdlets exist only on the Windows side:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass   # see inventory 3.9
cd '\\wsl.localhost\Ubuntu\home\joey\GIT\background-file-mover\integration\provision\hyperv'
```

**1.** Build the VM (`New-KickstartIso.ps1` is already done — the ISO exists and was
verified by mounting it):

```powershell
.\New-TestLab.ps1
.\Get-TestLab.ps1        # once the install finishes, ~10-15 min
```

**2. Configure and test:**

```sh
cd integration/configure
cp inventory.ini.example inventory.ini    # put the VM's IP in it
ansible-playbook -i inventory.ini site.yml
sh ../tests/run-all.sh
```

## Expect these to go wrong on the first run

Not pessimism — none of it has executed, and these are the specific places I would
look first:

1. **The kickstart — semantics, not syntax.** `ksvalidator` passes it, which rules
   out typos and unterminated sections and nothing else. Two defects it passed
   happily have since been fixed by reading (§ 4.10–4.11 of the inventory): the file
   had no `network` line, and set the hostname with `hostnamectl` in a dbus-less
   `%post` chroot. Both are now the single `network … --onboot=yes --hostname=…`
   line. If the VM still comes up unreachable, `--device=link` picking the wrong
   interface is the next suspect. Watch the install in
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
