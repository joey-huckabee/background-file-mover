#!/bin/sh
# What can be checked about the lab WITHOUT a hypervisor, a VM, or Ansible.
#
# Shell syntax, YAML syntax and the layer-separation rule need nothing
# installed. Everything else -- ansible-lint, ksvalidator, shellcheck -- is
# reported as SKIPPED when the tool is absent rather than silently passed over,
# because a validator that quietly does nothing is the failure mode this
# project keeps finding in its own apparatus.
#
# PowerShell is validated separately, on the Windows side, by
# scripts/Test-Syntax.ps1 -- it uses the parser built into PowerShell and needs
# no modules installed.
set -eu

cd "$(dirname "$0")/.."

fails=0
report() {
    if [ "$2" -eq 0 ]; then echo "  ok    $1"; else echo "  FAIL  $1"; fails=$((fails + 1)); fi
}

echo "== integration lab validation =="

# --- POSIX shell syntax ---------------------------------------------------
echo "-- shell syntax --"
for f in $(find . -name '*.sh' | sort); do
    if sh -n "$f" 2>/tmp/shsyn.err; then
        report "$f" 0
    else
        report "$f" 1
        sed 's/^/        /' /tmp/shsyn.err
    fi
done

# --- YAML syntax ----------------------------------------------------------
echo "-- yaml syntax --"
for f in $(find . -name '*.yml' -o -name '*.yaml' | sort); do
    if python3 -c "import sys,yaml; yaml.safe_load(open(sys.argv[1]))" "$f" 2>/tmp/yamlsyn.err; then
        report "$f" 0
    else
        report "$f" 1
        sed 's/^/        /' /tmp/yamlsyn.err
    fi
done

# --- the PowerShell data file, read as text -------------------------------
# Not parsed here (that needs PowerShell) but checked for the one mistake that
# is invisible until a VM is built with the wrong disk: a path that is not on
# the data drive.
echo "-- lab configuration --"
if grep -qE "^\s*(LabRoot|IsoDir|VhdDir|VmDir|KeyDir)\s*=\s*'D:" provision/hyperv/Lab.psd1; then
    report "Lab.psd1 paths are on D:" 0
else
    report "Lab.psd1 paths are on D: (C: has no room)" 1
fi

# --- the architectural rule ----------------------------------------------
echo "-- layer separation --"
if sh scripts/assert-layer-separation.sh >/tmp/sep.out 2>&1; then
    report "layer 2 is provider-agnostic" 0
else
    report "layer 2 is provider-agnostic" 1
    sed 's/^/        /' /tmp/sep.out
fi

# --- optional tooling -----------------------------------------------------
echo "-- optional linters --"
if command -v shellcheck >/dev/null 2>&1; then
    rc=0
    for f in $(find . -name '*.sh' | sort); do
        shellcheck -s sh "$f" || rc=1
    done
    report "shellcheck" "$rc"
else
    echo "  SKIP  shellcheck (not installed -- run prereqs/install-control-node.sh)"
fi

if command -v yamllint >/dev/null 2>&1; then
    if yamllint -d relaxed configure/ >/tmp/yl.out 2>&1; then report "yamllint" 0; else
        report "yamllint" 1; sed 's/^/        /' /tmp/yl.out; fi
else
    echo "  SKIP  yamllint (not installed)"
fi

if command -v ansible-lint >/dev/null 2>&1; then
    if (cd configure && ansible-lint site.yml) >/tmp/al.out 2>&1; then report "ansible-lint" 0; else
        report "ansible-lint" 1; sed 's/^/        /' /tmp/al.out; fi
else
    echo "  SKIP  ansible-lint (not installed)"
fi

if command -v ansible-playbook >/dev/null 2>&1; then
    if (cd configure && ansible-playbook --syntax-check site.yml) >/tmp/as.out 2>&1; then
        report "ansible syntax-check" 0
    else
        report "ansible syntax-check" 1; sed 's/^/        /' /tmp/as.out
    fi
else
    echo "  SKIP  ansible-playbook --syntax-check (not installed)"
fi

if command -v ksvalidator >/dev/null 2>&1; then
    if ksvalidator provision/hyperv/kickstart/rocky9-lab.ks >/tmp/ks.out 2>&1; then
        report "ksvalidator" 0
    else
        report "ksvalidator" 1; sed 's/^/        /' /tmp/ks.out
    fi
else
    echo "  SKIP  ksvalidator (not installed) -- the kickstart is UNVALIDATED"
fi

echo ""
if [ "$fails" -ne 0 ]; then
    echo "integration validation: $fails failure(s)"
    exit 1
fi
echo "integration validation: passed (see SKIP lines for what was not checked)"
