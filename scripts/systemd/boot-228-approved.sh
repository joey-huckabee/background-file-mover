#!/bin/sh
# Requires explicit authorization for temporary Podman-VM host-cgroup access.
set -eu
mount --make-rprivate /
case ${FILE_MOVER_CGROUP_OWNER:-} in
    ''|*[!0-9a-f]*) echo 'Missing or invalid fixture owner nonce' >&2; exit 78 ;;
esac
test "${#FILE_MOVER_CGROUP_OWNER}" = 32
owned=file-mover-owned-$FILE_MOVER_CGROUP_OWNER
if grep -Eq ':[^:]*name=systemd(,|:)' /proc/self/cgroup; then
    echo 'Refusing an existing systemd v1 hierarchy' >&2
    exit 78
fi
mkdir -p /run/fm-cgroup-bootstrap
readlink /proc/self/ns/cgroup >/run/fm-outer-cgroup-namespace
mount -t cgroup -o none,name=systemd none /run/fm-cgroup-bootstrap
mkdir /run/fm-cgroup-bootstrap/$owned
printf '%s\n' "$owned" >/run/fm-owned-cgroup-name
# This shell is PID 1 in the private PID namespace; move only ourselves.
echo $$ >/run/fm-cgroup-bootstrap/$owned/cgroup.procs
printf 'FILE_MOVER_OWNED_CGROUP=%s\n' "$owned"
exec unshare --cgroup /usr/local/libexec/boot-228-inner.sh
