#!/bin/bash
# Development only (WSL). Run a command as the invoking user in a private mount
# namespace where the WSLg mirror of / is hidden, so the mover's mount-alias
# checks pass. Affects only this process tree; the host mount table is unchanged.
# Needs root to create the namespace:  wsl -u root -- bash scripts/dev-wsl-namespace.sh CMD...
# Set DEV_UID/DEV_GID if the target user is not 1000.
uid=${DEV_UID:-1000}; gid=${DEV_GID:-1000}
home=$(getent passwd "$uid" | cut -d: -f6)
exec unshare --mount --propagation private bash -c '
  umount -l /mnt/wslg/distro 2>/dev/null || true
  exec setpriv --reuid='"$uid"' --regid='"$gid"' --init-groups env HOME='"$home"' PATH=/usr/local/bin:/usr/bin:/bin "$@"' _ "$@"
