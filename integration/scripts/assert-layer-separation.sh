#!/bin/sh
# Enforces the one architectural rule of the integration lab: layer 2 knows
# nothing about the hypervisor.
#
# integration/configure/ and integration/tests/ must target any reachable
# RHEL 9 host given an SSH address. If they learn about Hyper-V -- a VM name, a
# vhdx path, a D: drive, a PowerShell cmdlet -- then the hypervisor choice
# stops being a decision and becomes a fact, and moving to a cloud target later
# becomes a rewrite rather than a new provisioning script.
#
# That erosion happens one convenient reference at a time, which is exactly the
# kind of thing a person will not notice in review and a grep will.
#
# Usage:  sh integration/scripts/assert-layer-separation.sh
set -eu

cd "$(dirname "$0")/.."

status=0

# Terms that mean "this file knows which hypervisor it is running on".
#
# Note "Hyper-V" is matched case-insensitively but "vm" is NOT in the list:
# "VM" appears legitimately in prose ("the VM's address"), and a gate with
# false positives gets disabled -- which is worse than a gate with a known
# blind spot.
banned='Hyper-V|hyperv|\.vhdx|New-VM|Get-VM|Set-VMHost|vmconnect|[A-Za-z]:\\\\|Import-PowerShellDataFile'

# COMMENTS ARE STRIPPED FIRST. Every file under configure/ and tests/ uses '#'
# for comments, and the rule this gate enforces is worth explaining next to the
# code it governs -- site.yml says in its header that it knows nothing about
# Hyper-V, and inventory.ini.example points a human at the script that prints
# the address. Both tripped the first version of this gate.
#
# A gate that punishes its own documentation trains people to delete the
# documentation, which is a worse outcome than the blind spot. What matters is
# that no EXECUTABLE line depends on the hypervisor; a comment cannot.
for dir in configure tests; do
    [ -d "$dir" ] || continue
    for f in $(find "$dir" -type f | sort); do
        hits=$(sed 's/#.*$//' "$f" | grep -niE "$banned" || true)
        if [ -n "$hits" ]; then
            echo "assert-layer-separation: FAIL: layer 2 refers to the hypervisor" >&2
            printf '%s\n' "$hits" | sed "s|^|  $f:|" >&2
            status=1
        fi
    done
done

# The reverse is allowed and expected: layer 1 may mention Ansible, because
# handing off to it is the whole point of finishing a provision. So there is
# deliberately no check in that direction.

# The provisioning layer must still exist and be the only place these appear --
# a gate that passes because layer 1 was deleted has proved nothing.
if [ ! -f provision/hyperv/New-TestLab.ps1 ]; then
    echo "assert-layer-separation: FAIL: provision/hyperv/New-TestLab.ps1 is missing" >&2
    echo "  this gate would then be checking a separation that no longer has two sides" >&2
    status=1
fi

if [ "$status" -ne 0 ]; then
    echo "" >&2
    echo "Layer 2 (configure/, tests/) targets any RHEL 9 host over SSH." >&2
    echo "Anything hypervisor-specific belongs in provision/." >&2
    exit 1
fi

echo "layer-separation OK: configure/ and tests/ are provider-agnostic"
