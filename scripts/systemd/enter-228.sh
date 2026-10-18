#!/bin/sh
set -eu
test "$(stat -f -c %t /sys/fs/cgroup/systemd)" = 27e0eb
test "$(readlink /proc/1/ns/cgroup)" = "$(cat /run/fm-inner-cgroup-namespace)"
test ! -d /sys/fs/cgroup/systemd/"$(cat /run/fm-owned-cgroup-name)"
# Never enumerate/migrate unrelated VM processes: move only this fixture exec.
echo $$ >/sys/fs/cgroup/systemd/cgroup.procs
exec nsenter --target 1 --cgroup -- "$@"
