#!/bin/sh
set -eu
mount -t tmpfs -o mode=755 tmpfs /sys/fs/cgroup
mkdir /sys/fs/cgroup/systemd
mount -t cgroup -o none,name=systemd none /sys/fs/cgroup/systemd
umount /run/fm-cgroup-bootstrap
test "$(readlink /proc/self/ns/cgroup)" != "$(cat /run/fm-outer-cgroup-namespace)"
test ! -d /sys/fs/cgroup/systemd/"$(cat /run/fm-owned-cgroup-name)"
umask 077
readlink /proc/self/ns/cgroup >/run/fm-inner-cgroup-namespace
exec /usr/lib/systemd/systemd --system --unit=multi-user.target
