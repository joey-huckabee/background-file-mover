#!/bin/sh
# Enforces L2-SEC-001: filesystem operations on managed trees are
# file-descriptor relative. Path-based operations there are prohibited.
#
# The requirement's stated method is Inspection, which is the method that
# quietly stops happening -- it holds right up until someone needs one quick
# stat() somewhere else and no tool objects. The hazard is check-then-act: any
# path-based call re-resolves the whole path, so every component can be swapped
# between the check and the act. A descriptor pins the object instead.
#
# Scope is production code (src/, include/). Tests build their fixtures with
# ordinary path calls and are not operating on managed trees; scanning them
# would flag the scaffolding rather than the software.
#
# Usage:  sh scripts/assert-fd-relative.sh
set -eu

cd "$(dirname "$0")/.."

# The allowlist is explicit, short, and each entry carries its reason. Adding a
# fourth file has to be an argument someone makes, not a side effect of an
# include.
#
#   src/fsops.cpp   the layer itself. It is where the one unavoidable
#                   path-based call lives -- open_root, because a descriptor
#                   chain has to start somewhere -- and everything after it is
#                   *at-relative.
#   src/store.cpp   the SQLite state database, which is NOT a managed tree. It
#                   is the service's own file on local disk (L2-JOB-008
#                   requires it be local), not attacker-influenced, and its
#                   one stat() distinguishes first boot from a corrupt store.
#   src/config.cpp  the configuration file and the statfs check that keeps the
#                   state database off NFS. Read once at startup from an
#                   operator-supplied path, before any managed tree exists.
allowed='^src/fsops\.cpp$|^include/filemover/fsops\.hpp$|^src/store\.cpp$|^src/config\.cpp$'

# Two checks, because one of them alone is not trustworthy.
#
# The header check is the structural one and does the real work: a translation
# unit that cannot see <fcntl.h> or <dirent.h> cannot call open() or opendir()
# at all, whatever it names its own methods. This is the same shape as the
# sql-confined gate, and for the same reason -- containment is easier to
# enforce at the include than at the call site.
banned_headers='^[[:space:]]*#[[:space:]]*include[[:space:]]*<(fcntl\.h|dirent\.h|sys/stat\.h|sys/vfs\.h|utime\.h)>'

# The call check is a backstop for the qualified form the codebase uses for
# syscalls (::open, ::stat). It is deliberately narrow: an earlier version
# matched any `open(` and flagged JobStore::open -- a method declaration, not a
# syscall. A gate with false positives gets disabled, which is worse than a
# gate with a known blind spot, so this one only claims what it can prove.
banned_calls='::(open|creat|stat|lstat|rename|unlink|rmdir|mkdir|opendir|chmod|chown|lchown|symlink|readlink|access|truncate|utimes)[[:space:]]*\('

status=0
for f in $(find src include -name '*.cpp' -o -name '*.hpp' 2>/dev/null | sort); do
    if printf '%s\n' "$f" | grep -qE "$allowed"; then
        continue
    fi

    # Comments stripped: several headers explain this rule by name, and a gate
    # that punishes its own documentation is worse than no gate.
    stripped=$(sed 's://.*::' "$f")

    hits=$(printf '%s\n' "$stripped" | grep -nE "$banned_headers" || true)
    if [ -n "$hits" ]; then
        echo "assert-fd-relative: $f includes a path-based filesystem header" >&2
        echo "$hits" | sed "s|^|  $f:|" >&2
        status=1
    fi

    hits=$(printf '%s\n' "$stripped" | grep -nE "$banned_calls" || true)
    if [ -n "$hits" ]; then
        echo "assert-fd-relative: $f uses a path-based filesystem call" >&2
        echo "$hits" | sed "s|^|  $f:|" >&2
        status=1
    fi
done

if [ "$status" -ne 0 ]; then
    echo "" >&2
    echo "L2-SEC-001: use the fd-relative form via filemover/fsops.hpp --" >&2
    echo "openat, fstatat, renameat2, linkat, unlinkat, mkdirat -- against a" >&2
    echo "held DirHandle. A path-based call re-resolves every component, so" >&2
    echo "each one can be swapped between the check and the act." >&2
    exit 1
fi

echo "fd-relative OK: path-based filesystem calls appear only where allowed"
