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
    pykickstart \
    rsync \
    openssh-client

# --- collections ----------------------------------------------------------
# ansible.posix    firewalld, synchronize
# community.general timezone, make
#
# Installed per user rather than system-wide, so a later apt upgrade of the
# ansible package does not silently replace them.
echo "installing required Ansible collections"
ansible-galaxy collection install ansible.posix community.general

echo ""
echo "installed:"
for t in ansible ansible-playbook ansible-lint shellcheck yamllint ksvalidator; do
    printf '  %-18s ' "$t"
    command -v "$t" >/dev/null 2>&1 && "$t" --version 2>&1 | head -1 || echo "MISSING"
done

echo ""
echo "next: copy the lab SSH key into WSL and chmod 600 it, then fill in"
echo "      integration/configure/inventory.ini -- see inventory.ini.example."
