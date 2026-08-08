<#
.SYNOPSIS
    Creates the external switch (if absent) and the Rocky 9 lab VM, and starts
    the unattended install.

.DESCRIPTION
    Layer 1. Everything this script does is listed in
    docs/INTEGRATION-INVENTORY.md with the reason for it.

    It refuses rather than guesses in three places, all of them cases where a
    wrong guess is expensive:

      * the physical adapter to bind the external switch to -- binding the
        wrong one drops the host's own networking for several seconds
      * an existing VM of the same name -- silently reusing one would make a
        test result depend on what a previous run left behind
      * a missing install ISO -- the VM would boot to a UEFI shell and sit
        there looking like a hung install

.NOTES
    Requires membership of Hyper-V Administrators (see integration/README.md).
    Idempotent for the switch; deliberately NOT idempotent for the VM.
#>
[CmdletBinding()]
param(
    [string] $ConfigPath = (Join-Path $PSScriptRoot 'Lab.psd1'),
    [switch] $Force
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$lab = Import-PowerShellDataFile -Path $ConfigPath

# --- preconditions --------------------------------------------------------

try {
    Get-VMHost -ErrorAction Stop | Out-Null
} catch {
    throw @"
Cannot query Hyper-V. The account is probably not in Hyper-V Administrators.

Run this once, elevated, then sign out and back in:

    Add-LocalGroupMember -Group "Hyper-V Administrators" -Member "`$env:COMPUTERNAME\`$env:USERNAME"
"@
}

$installIso = Join-Path $lab.IsoDir $lab.InstallIso
if (-not (Test-Path $installIso)) {
    throw @"
Install media not found: $installIso

Download the Rocky 9 MINIMAL ISO by hand and put it there, then set InstallIso
in Lab.psd1 to match the file name exactly. It is not downloaded automatically:
it is 2.5 GB, mirror URLs rot, and a script that silently fetches an unverified
OS image is not something this project should own.
"@
}

$ksIso = Join-Path $lab.IsoDir $lab.KickstartIso
if (-not (Test-Path $ksIso)) {
    throw "Kickstart ISO not found: $ksIso. Run .\New-KickstartIso.ps1 first."
}

foreach ($dir in @($lab.VhdDir, $lab.VmDir)) {
    if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }
}

# --- the virtual switch ---------------------------------------------------

$switch = Get-VMSwitch -Name $lab.SwitchName -ErrorAction SilentlyContinue
if ($null -eq $switch) {
    $adapterName = $lab.HostAdapterName
    if ([string]::IsNullOrWhiteSpace($adapterName)) {
        # Candidates: physically connected, not already bound to a vSwitch, and
        # not a WSL or Hyper-V virtual adapter.
        $candidates = @(
            Get-NetAdapter -Physical |
                Where-Object { $_.Status -eq 'Up' -and $_.InterfaceDescription -notmatch 'Hyper-V|WSL|Virtual' }
        )
        if ($candidates.Count -ne 1) {
            $names = ($candidates | ForEach-Object { "  $($_.Name)  [$($_.InterfaceDescription)]" }) -join "`n"
            throw @"
Cannot decide which physical adapter to bind the external switch to.
Found $($candidates.Count) candidate(s):

$names

Set HostAdapterName in Lab.psd1 to the one you want and re-run. This refuses
rather than guessing because binding the wrong adapter drops this machine's own
network connection for several seconds.
"@
        }
        $adapterName = $candidates[0].Name
    }

    Write-Host "creating external switch '$($lab.SwitchName)' on adapter '$adapterName'"
    Write-Host "NOTE: host networking will drop briefly while the switch is created."
    # AllowManagementOS so the host keeps its own connectivity through the same
    # adapter -- without it, creating the switch takes this machine off the
    # network, which is a memorable way to end a session over RDP.
    $switch = New-VMSwitch -Name $lab.SwitchName -NetAdapterName $adapterName -AllowManagementOS $true
} else {
    if ($switch.SwitchType -ne 'External') {
        throw "Switch '$($lab.SwitchName)' exists but is $($switch.SwitchType), not External. Rename or remove it."
    }
    Write-Host "reusing existing switch '$($lab.SwitchName)'"
}

# --- the VM ---------------------------------------------------------------

$existing = Get-VM -Name $lab.VmName -ErrorAction SilentlyContinue
if ($null -ne $existing) {
    if (-not $Force) {
        throw @"
VM '$($lab.VmName)' already exists.

Remove it with .\Remove-TestLab.ps1, or re-run with -Force to have this script
do that for you. It is not reused silently: a test result that depends on what
a previous run left on the disk is not a test result.
"@
    }
    Write-Host "-Force given; removing existing VM '$($lab.VmName)'"
    & (Join-Path $PSScriptRoot 'Remove-TestLab.ps1') -ConfigPath $ConfigPath
}

$vhdPath = Join-Path $lab.VhdDir ("{0}.vhdx" -f $lab.VmName)
if (Test-Path $vhdPath) {
    if (-not $Force) { throw "Disk already exists: $vhdPath. Remove it or pass -Force." }
    Remove-Item -Path $vhdPath -Force
}

Write-Host "creating VM '$($lab.VmName)' ($($lab.CpuCount) vCPU, $($lab.MemoryMB) MB, $($lab.DiskGB) GB)"

$vm = New-VM -Name $lab.VmName `
             -Generation $lab.Generation `
             -MemoryStartupBytes ($lab.MemoryMB * 1MB) `
             -NewVHDPath $vhdPath `
             -NewVHDSizeBytes ($lab.DiskGB * 1GB) `
             -SwitchName $lab.SwitchName `
             -Path $lab.VmDir

Set-VMProcessor -VM $vm -Count $lab.CpuCount

if (-not $lab.DynamicMemory) {
    # Static memory: dynamic memory makes a page-cache-sensitive I/O test depend
    # on what the host happened to be doing, and this lab exists to make results
    # reproducible.
    Set-VMMemory -VM $vm -DynamicMemoryEnabled $false
}

# Generation 2 is UEFI. Rocky 9's shim is signed by the Microsoft UEFI CA, not
# by the Microsoft Windows CA, so the default template refuses to boot it --
# which presents as an immediate "no bootable device" and looks like a broken
# ISO rather than a Secure Boot policy mismatch.
Set-VMFirmware -VM $vm -EnableSecureBoot On -SecureBootTemplate 'MicrosoftUEFICertificateAuthority'

# Two DVD drives: the install media, and the OEMDRV kickstart volume Anaconda
# auto-detects.
$installDrive = Add-VMDvdDrive -VM $vm -Path $installIso -Passthru
Add-VMDvdDrive -VM $vm -Path $ksIso | Out-Null

# Boot from the install DVD first. Without this the VM boots the empty disk.
Set-VMFirmware -VM $vm -FirstBootDevice $installDrive

# Do not restart automatically if the host reboots mid-install: a half-installed
# VM that silently reboots into a fresh install loop is hard to diagnose.
Set-VM -VM $vm -AutomaticStartAction Nothing -AutomaticStopAction ShutDown

# Checkpoints off. They are useful later for revert-between-tests, but a
# production-style checkpoint taken automatically during an install produces a
# differencing disk nobody asked for.
Set-VM -VM $vm -CheckpointType Disabled

Write-Host "starting '$($lab.VmName)'"
Start-VM -VM $vm

Write-Host ""
Write-Host "Install is running unattended and will take roughly 10-15 minutes."
Write-Host "The VM reboots and ejects the media when it finishes."
Write-Host ""
Write-Host "Watch it with:   vmconnect.exe localhost $($lab.VmName)"
Write-Host "Then run:        .\Get-TestLab.ps1"
