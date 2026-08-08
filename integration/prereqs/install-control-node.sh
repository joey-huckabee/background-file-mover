#!/bin/sh
# Installs the Ansible control node inside WSL2. Run once.
#
# ---------------------------------------------------------------------------
# DO NOT RUN THIS BEFORE MOVING THE WSL2 DISK TO D:.
#
# Installing Ansible grows ext4.vhdx by a few hundred megabytes. On the machine
# this was written for, that file was 58.9 GB and lived on a C: drive with
# 2.8 GB free -- so the install would have taken the host disk to nearly zero,
# and a full C: breaks Windows in ways that are much more annoying than a
# missing playbook. Move it first:
#
#     wsl --shutdown
#     wsl --manage Ubuntu --move D:\WSL\Ubuntu
#
# This script checks the available space and refuses if it is tight.
# ---------------------------------------------------------------------------
#
# Ansible is installed from the distribution repository rather than pip. A pip
# install into the system interpreter is how a WSL distro ends up with two
# Ansibles and a PATH that decides between them; the apt package is older but
# it is one thing, managed by one tool.
#
# pykickstart is the one exception, and not by choice: Ubuntu does not package
# it. It is a Fedora/RHEL tool, and `apt-cache search kickstart` on 22.04 comes
# back with youtube-dl. It is installed from PyPI into ~/.local instead --
# --user, so it stays out of the system interpreter's site-packages and cannot
# be what a later apt upgrade argues with.
set -eu

echo "== file-mover integration control node =="

# --- space check ----------------------------------------------------------
avail_kb=$(df -Pk / | awk 'NR==2 {print $4}')
avail_mb=$((avail_kb / 1024))
echo "space available on / : ${avail_mb} MB"
if [ "$avail_mb" -lt 2048 ]; then
    echo "" >&2
    echo "REFUSING: less than 2 GB free inside the distro." >&2
    echo "Free some space, or move the WSL disk to a larger drive first." >&2
    exit 1
fi

# The WSL disk is sparse: it grows on the Windows host as the guest writes, and
# it does not shrink when files are deleted. Free space inside the guest is
# therefore only half the question -- the other half is the host drive, which
# this cannot see from here.
if [ -d /mnt/c ]; then
    echo ""
    echo "NOTE: if this distro's ext4.vhdx is still on C:, installing now grows"
    echo "      a file on that drive. Check free space on the Windows side"
    echo "      before continuing."
    echo ""
fi

# --- packages -------------------------------------------------------------
echo "installing ansible and lint tooling (sudo required)"
sudo apt-get update
sudo apt-get install -y --no-install-recommends \
    ansible \
    ansible-lint \
    shellcheck \
    yamllint \
    rsync \
    openssh-client \
    python3-pip

# --- pykickstart (PyPI) ---------------------------------------------------
# Provides ksvalidator, which is the only thing that checks the kickstart file
# before Anaconda does -- and Anaconda's way of reporting a syntax error is to
# stop at an interactive prompt on a VM with no console attached, which
# presents as "the install hung".
echo "installing pykickstart from PyPI (no distribution package exists)"
pip3 install --user --upgrade pykickstart

# --- collections ----------------------------------------------------------
# ansible.posix    firewalld, synchronize
# community.general timezone, make
#
# Installed per user rather than system-wide, so a later apt upgrade of the
# ansible package does not silently replace them.
echo "installing required Ansible collections"
ansible-galaxy collection install ansible.posix community.general

# --- verify ---------------------------------------------------------------
# This loop used to print MISSING and then exit 0, which made "installed
# nothing" and "installed everything" look the same from the caller's side.
# The whole point of this script is to make the validators exist, so not
# having them is a failure, and it exits accordingly.
echo ""
echo "installed:"
missing=0
for t in ansible ansible-playbook ansible-lint shellcheck yamllint ksvalidator; do
    printf '  %-18s ' "$t"
    if command -v "$t" >/dev/null 2>&1; then
        "$t" --version 2>&1 | head -1
    else
        echo "MISSING"
        missing=$((missing + 1))
    fi
done

if [ "$missing" -ne 0 ]; then
    echo "" >&2
    echo "FAILED: $missing tool(s) missing -- the control node is not usable." >&2
    if [ -x "$HOME/.local/bin/ksvalidator" ]; then
        echo "" >&2
        echo "ksvalidator is installed at ~/.local/bin but is not on PATH." >&2
        echo "Open a new shell, or: export PATH=\"\$HOME/.local/bin:\$PATH\"" >&2
    fi
    exit 1
fi

echo ""
echo "next: copy the lab SSH key into WSL and chmod 600 it, then fill in"
echo "      integration/configure/inventory.ini -- see inventory.ini.example."
