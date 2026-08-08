<#
.SYNOPSIS
    Reports the lab VM's state and IP address, and prints the next command.

.DESCRIPTION
    Layer 1, read-only. The IP comes from the Hyper-V integration services
    rather than from a DHCP lease table, so it works without touching the
    router and without guessing at a subnet.

    The address is not written into the Ansible inventory automatically. That
    is deliberate: an inventory rewritten by a provisioning script is an
    inventory whose contents depend on which VM happened to be running, and the
    layer-2 side is supposed to work against any reachable host. Copying one
    line by hand keeps the boundary honest.

.NOTES
    Integration services report an address only once the guest has booted far
    enough to configure the interface, so "no address yet" during an install is
    expected rather than a fault.
#>
[CmdletBinding()]
param(
    [string] $ConfigPath = (Join-Path $PSScriptRoot 'Lab.psd1')
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
if ($null -eq $vm) {
    Write-Host "VM '$($lab.VmName)' does not exist. Run .\New-TestLab.ps1."
    return
}

Write-Host ("VM      : {0}" -f $vm.Name)
Write-Host ("State   : {0}" -f $vm.State)
Write-Host ("Uptime  : {0}" -f $vm.Uptime)
Write-Host ("Memory  : {0} MB" -f ($vm.MemoryAssigned / 1MB))

$addresses = @()
foreach ($nic in (Get-VMNetworkAdapter -VM $vm)) {
    foreach ($ip in $nic.IPAddresses) {
        # IPv4 only. The lab addresses hosts by v4 because that is what the
        # inventory and the service's own bind address use; listing link-local
        # v6 here would just be noise to copy past.
        if ($ip -match '^\d+\.\d+\.\d+\.\d+$' -and $ip -ne '127.0.0.1') {
            $addresses += $ip
        }
    }
}

if ($addresses.Count -eq 0) {
    Write-Host ""
    Write-Host "No IPv4 address reported yet."
    if ($vm.State -eq 'Running') {
        Write-Host "If the install is still running this is expected -- it takes 10-15 minutes."
        Write-Host "Watch it with: vmconnect.exe localhost $($lab.VmName)"
    }
    return
}

$primary = $addresses[0]
Write-Host ("Address : {0}" -f ($addresses -join ', '))
Write-Host ""
Write-Host "Next:"
Write-Host "  1. cd integration/configure && cp inventory.ini.example inventory.ini"
Write-Host "  2. put this line in it, under [lab]:"
Write-Host ""
Write-Host ("     {0} ansible_user={1} ansible_ssh_private_key_file=<path to {2}>" -f $primary, $lab.AdminUser, $lab.SshKeyName)
Write-Host ""
Write-Host "     The key is at $($lab.KeyDir)\$($lab.SshKeyName) on Windows,"
Write-Host "     which WSL2 sees as /mnt/d/filemover-lab/keys/$($lab.SshKeyName)."
Write-Host ""
Write-Host "     Copy it into WSL and chmod 600 first -- ssh refuses a key on a"
Write-Host "     DrvFs mount because the permissions always read as 0777."
Write-Host ""
Write-Host "  3. ansible-playbook -i inventory.ini site.yml"
