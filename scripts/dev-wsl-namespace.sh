#!/bin/bash
# Development only (WSL). Run a command as a non-root user in a private mount
# namespace where the WSLg mirror of / is hidden, so the mover's mount-alias
# checks pass. Affects only this process tree; the host mount table is unchanged.
# Needs root to create the namespace:  wsl -u root -- bash scripts/dev-wsl-namespace.sh CMD...
# Set DEV_UID/DEV_GID if the target user is not 1000.
uid=${DEV_UID:-1000}
gid=${DEV_GID:-1000}
if ! [[ $uid =~ ^[1-9][0-9]{0,9}$ && $gid =~ ^[1-9][0-9]{0,9}$ ]]; then
  echo "DEV_UID and DEV_GID must be numeric non-root IDs" >&2
  exit 2
fi
home=$(getent passwd "$uid" | cut -d: -f6)
if [ -z "$home" ]; then
  echo "no account for uid $uid" >&2
  exit 2
fi
# Values reach the inner shell only as quoted positional arguments, never as code.
exec unshare --mount --propagation private bash -c '
  uid=$1 gid=$2 home=$3
  shift 3
  umount -l /mnt/wslg/distro 2>/dev/null || true
  exec setpriv --reuid="$uid" --regid="$gid" --init-groups env HOME="$home" PATH=/usr/local/bin:/usr/bin:/bin "$@"' \
  _ "$uid" "$gid" "$home" "$@"
