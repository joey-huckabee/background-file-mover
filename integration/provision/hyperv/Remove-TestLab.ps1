<#
.SYNOPSIS
    Removes the lab VM and its disk. Idempotent.

.DESCRIPTION
    Layer 1. Removes the VM, its VHDX and its VM directory. Does NOT remove the
    virtual switch by default: the switch is bound to a physical adapter, and
    tearing it down drops host networking for several seconds -- an expensive
    surprise for something that is meant to be routine cleanup. Pass
    -RemoveSwitch when that is genuinely what you want.

    Deleting the disk is the point. A teardown that leaves 40 GB behind on
    every run is a teardown nobody runs twice, and then the lab is full.

.NOTES
    Safe to run when nothing exists. Each step reports what it did or skipped,
    so a partial cleanup is visible rather than silent.
#>
[CmdletBinding()]
param(
    [string] $ConfigPath = (Join-Path $PSScriptRoot 'Lab.psd1'),
    [switch] $RemoveSwitch
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$lab = Import-PowerShellDataFile -Path $ConfigPath

try {
    Get-VMHost -ErrorAction Stop | Out-Null
} catch {
    throw "Cannot query Hyper-V; the account is probably not in Hyper-V Administrators. See integration/README.md."
}

$vm = Get-VM -Name $lab.VmName -ErrorAction SilentlyContinue
if ($null -ne $vm) {
    if ($vm.State -ne 'Off') {
        Write-Host "stopping '$($lab.VmName)' (forced -- this is a lab, not a service)"
        Stop-VM -VM $vm -TurnOff -Force
    }

    # Capture the disk paths BEFORE removing the VM; afterwards there is
    # nothing left to ask, and the VHDX would be orphaned on D: forever.
    $disks = @(Get-VMHardDiskDrive -VM $vm | Select-Object -ExpandProperty Path)

    Write-Host "removing VM '$($lab.VmName)'"
    Remove-VM -VM $vm -Force

    foreach ($disk in $disks) {
        if (Test-Path $disk) {
            Write-Host "removing disk $disk"
            Remove-Item -Path $disk -Force
        }
    }
} else {
    Write-Host "no VM named '$($lab.VmName)'; nothing to remove"
}

# The VM directory holds configuration XML and, on Generation 2, the UEFI NVRAM
# state. Left behind it is small but it accumulates one directory per rebuild.
$vmDir = Join-Path $lab.VmDir $lab.VmName
if (Test-Path $vmDir) {
    Write-Host "removing VM directory $vmDir"
    Remove-Item -Path $vmDir -Recurse -Force -ErrorAction SilentlyContinue
}

if ($RemoveSwitch) {
    $switch = Get-VMSwitch -Name $lab.SwitchName -ErrorAction SilentlyContinue
    if ($null -ne $switch) {
        Write-Host "removing switch '$($lab.SwitchName)' -- host networking will drop briefly"
        Remove-VMSwitch -Name $lab.SwitchName -Force
    } else {
        Write-Host "no switch named '$($lab.SwitchName)'"
    }
} else {
    Write-Host "leaving switch '$($lab.SwitchName)' in place (pass -RemoveSwitch to remove it)"
}

Write-Host "teardown complete"
