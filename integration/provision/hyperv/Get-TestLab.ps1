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
$method = ''

foreach ($nic in (Get-VMNetworkAdapter -VM $vm)) {
    foreach ($ip in $nic.IPAddresses) {
        # IPv4 only. The lab addresses hosts by v4 because that is what the
        # inventory and the service's own bind address use; listing link-local
        # v6 here would just be noise to copy past.
        if ($ip -match '^\d+\.\d+\.\d+\.\d+$' -and $ip -ne '127.0.0.1') {
            $addresses += $ip
            $method = 'integration services'
        }
    }
}

# --- fallback: find the guest by its MAC in the host's ARP cache -----------
#
# Integration services report an address only if the guest runs the KVP daemon,
# which comes from hyperv-daemons -- NOT part of @^minimal-environment, and the
# lab does not install it. On the first real build this branch was the whole
# story: the VM was up, networked and answering SSH for fifteen minutes while
# this script would have kept saying "no address yet, the install is probably
# still running". A status check that is confidently wrong is worse than one
# that admits it does not know.
#
# The ARP cache is authoritative in a different way: the guest is on the LAN, so
# the host learns its MAC-to-IP mapping by talking to it. The MAC is Hyper-V's
# own, which keeps this in layer 1 where it belongs.
if ($addresses.Count -eq 0 -and $vm.State -eq 'Running') {
    $mac = (Get-VMNetworkAdapter -VM $vm).MacAddress | Select-Object -First 1
    if ($mac -and $mac -ne '000000000000') {
        $dashed = $mac -replace '(..)(..)(..)(..)(..)(..)', '$1-$2-$3-$4-$5-$6'
        Write-Host ("MAC     : {0}" -f $dashed)

        $hit = Get-NetNeighbor -AddressFamily IPv4 -ErrorAction SilentlyContinue |
               Where-Object { $_.LinkLayerAddress -eq $dashed -and
                              $_.State -in @('Reachable', 'Stale', 'Delay', 'Probe', 'Permanent') }

        if ($null -eq $hit) {
            # Nothing has spoken to the guest yet, so the host has no entry.
            # Sweep the subnet the lab switch is on to provoke one. Cheap, and
            # confined to the interface the VM is actually attached to.
            $hostIf = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
                      Where-Object { $_.InterfaceAlias -like "*$($lab.SwitchName)*" } |
                      Select-Object -First 1
            if ($hostIf -and $hostIf.PrefixLength -eq 24) {
                $prefix = ($hostIf.IPAddress -replace '\.\d+$', '')
                Write-Host "no ARP entry yet; sweeping $prefix.0/24 to provoke one"
                # cmd's `start /b` rather than 254 Start-Process calls: this is
                # the form that was actually used to find the guest the first
                # time, it completes in about ten seconds, and it does not spawn
                # 254 PowerShell-tracked processes at once.
                cmd /c "for /L %i in (1,1,254) do @start /b ping -n 1 -w 200 $prefix.%i >nul" | Out-Null
                Start-Sleep -Seconds 10
                $hit = Get-NetNeighbor -AddressFamily IPv4 -ErrorAction SilentlyContinue |
                       Where-Object { $_.LinkLayerAddress -eq $dashed }
            } elseif ($hostIf) {
                Write-Host ("host is {0}/{1}; only /24 is swept automatically" -f $hostIf.IPAddress, $hostIf.PrefixLength)
            }
        }

        if ($hit) {
            $addresses += ($hit | Select-Object -ExpandProperty IPAddress -Unique)
            $method = 'ARP (integration services reported nothing)'
        }
    }
}

if ($addresses.Count -eq 0) {
    Write-Host ""
    Write-Host "No IPv4 address found, by integration services or by ARP."
    if ($vm.State -eq 'Running') {
        Write-Host "If the install is still running this is expected -- it takes 10-15 minutes."
        Write-Host "Watch it with: vmconnect.exe localhost $($lab.VmName)"
        Write-Host "If it has finished, the guest may not have got a DHCP lease."
    }
    return
}

$primary = $addresses[0]
Write-Host ("Address : {0}  (via {1})" -f ($addresses -join ', '), $method)
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
