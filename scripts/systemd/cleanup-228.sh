#!/bin/sh
# Remove only empty descendants of this run's UUID-named cgroup, after teardown.
set -eu
case ${1:-} in
    ''|*[!0-9a-f]*) echo 'Invalid fixture owner nonce' >&2; exit 78 ;;
esac
test "${#1}" = 32
owned=file-mover-owned-$1
if ! grep -Eq ':[^:]*name=systemd(,|:)' /proc/self/cgroup; then
    echo 'No legacy hierarchy remains'
    exit 0
fi
mkdir /tmp/fm-owned-cleanup
mount -t cgroup -o none,name=systemd none /tmp/fm-owned-cleanup
trap 'mountpoint -q /tmp/fm-owned-cleanup && umount /tmp/fm-owned-cleanup || true' EXIT
test "$(stat -f -c %t /tmp/fm-owned-cleanup)" = 27e0eb
test "$(readlink -f /tmp/fm-owned-cleanup/$owned)" = /tmp/fm-owned-cleanup/$owned
if test ! -d /tmp/fm-owned-cleanup/$owned; then
    echo 'Owned subtree absent; refusing empty-root teardown without owned-directory evidence' >&2
    exit 78
fi
for round in $(seq 1 30); do
    if test ! -d /tmp/fm-owned-cleanup/$owned; then
        echo 'Owned empty subtree removed or absent'
        break
    fi
    # cgroupfs has no symlink directories; rmdir cannot remove a populated group.
    find /tmp/fm-owned-cleanup/$owned -depth -type d -exec rmdir '{}' \; 2>/dev/null || true
    sleep 0.2
done
if test -d /tmp/fm-owned-cleanup/$owned; then
    echo 'Owned subtree remains; no processes were signalled or moved' >&2
    exit 1
fi
# Child destruction is asynchronous. The final unmount can see dead children
# and leave an empty root alive; a later empty remount/unmount retries teardown.
# Never remove another subtree or change root process membership.
for round in $(seq 1 30); do
    test -z "$(find /tmp/fm-owned-cleanup -mindepth 1 -type d -print)"
    umount /tmp/fm-owned-cleanup
    sleep 0.2
    if ! grep -Eq ':[^:]*name=systemd(,|:)' /proc/self/cgroup; then
        echo 'Legacy hierarchy released after empty-root unmount'
        exit 0
    fi
    mount -t cgroup -o none,name=systemd none /tmp/fm-owned-cleanup
    test "$(stat -f -c %t /tmp/fm-owned-cleanup)" = 27e0eb
done
echo 'Legacy hierarchy remains after bounded empty-root teardown' >&2
exit 1
